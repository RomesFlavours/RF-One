"""Reading a résumé again with the AI, and reading scanned PDFs (SELECTION_CV_REREAD_001).

A résumé is read once, at upload (`import_pipeline.import_one_resume`): by the AI when AI résumé reading is
on and working, otherwise by the rule-based reader, which finds little in most real résumés ("name not
extracted", no experience). Uploading the same file again does not help: it is recognised as already in the
archive and the first reading is reused. So:

* `read_again` reads the SAME stored résumé text again with the AI only (never the rule-based reader), replaces
  what was read on the same Candidate row (`persistence.replace_candidate_profile`), fills the person's blank
  name/email/phone, redoes the "possible duplicate" check that the empty reading produced, and re-evaluates
  the candidate for this position. Nothing linked to the candidate is lost.
* `read_pending` does that for a position's résumés read without the AI, within a time budget per click.
* `transcribe_pdf` gives a PDF with no text inside (a scan) to the AI as page images, so it can be imported at
  all; without it such a file stops at "No extractable text".

Same permission as every other AI use on résumés: nothing is sent when AI résumé reading is off.
"""

from __future__ import annotations

import io
import re
import time

from sqlalchemy import delete, select

from rfone_data_store import models as m
from rfone_data_store.selection import application_service as app_svc
from rfone_data_store.selection import identity_service as identity_svc
from rfone_data_store.selection import persistence
from rfone_data_store.selection.core import identity_model as idm
from rfone_data_store.selection.core.parser_base import ProviderUnavailable
from rfone_data_store.selection.core.resume_source import MANUAL_PROVIDER
from rfone_data_store.selection.import_pipeline import COMPLETED, reading_status
from rfone_data_store.selection.normalization import normalize_profile
from rfone_data_store.selection.parsing import ai_client
from rfone_data_store.selection.parsing.ai_client import AIProviderUnavailable
from rfone_data_store.selection.parsing.llm_parser import LLMResumeParser
from rfone_data_store.selection import workspace_models as ps

from . import ai_adapter, position_settings

AI_READING = "REAL_AI"   # Candidate.parsing_mode of an AI reading
TIME_BUDGET_SECONDS = 60  # per click of "Read again": with one slow reading after it, still well inside the
                          # 120 s gunicorn timeout; the rest waits for the next click
PDF_PAGES = 4
PAGE_PIXELS = 1600              # longest side of a page image sent to the AI
MAX_IMAGE_BYTES = 3_500_000     # Bedrock refuses images over 3.75 MB
TRANSCRIBE_TIMEOUT_SECONDS = 25  # inside an upload request; CloudFront answers 504 after 60 s
_NOTE_PARTIAL = "Partial résumé extraction; some sections need checking."
_NOTE_WITHOUT_AI = "Read without the AI"
_NOTE_FAILED = "The AI could not read it on the last try"
_FAILED_NOTE = re.compile(re.escape(_NOTE_FAILED) + r" \([^)]*\)\.?")
_NOTE_CHECK_PERSON = ("Check the person: the AI read a different name than the person this CV is linked to "
                      "(Duplicates).")
_OLD_READING_NOTES = re.compile(re.escape(_NOTE_PARTIAL) + "|" + re.escape(_NOTE_WITHOUT_AI) + r" \([^)]*\)[^.]*\.")


def read_without_ai(candidate) -> bool:
    return candidate is not None and candidate.parsing_mode not in (AI_READING, "SP_AI")


def note_for_reading(candidate) -> str | None:
    """Why a résumé was read without the AI, for the import note (never silent)."""
    if not read_without_ai(candidate):
        return None
    reason = ("AI résumé reading is off for this position" if not ai_adapter.current_policy().cv_ai_authorized
              else "the AI was not available")
    return f"{_NOTE_WITHOUT_AI} ({reason}): the name, email or phone may be missing."


def pending(session, position) -> list:
    """This position's résumés read without the AI."""
    pcs = session.scalars(select(ps.PositionCandidate).where(ps.PositionCandidate.position_id == position.id)
                          .order_by(ps.PositionCandidate.id)).all()
    todo = [pc for pc in pcs if read_without_ai(persistence.get_candidate(session, pc.candidate_id))]
    return sorted(todo, key=lambda pc: _NOTE_FAILED in (pc.import_note or ""))  # failed last time: tried last


def read_again(session, position, pc, *, actor_id, actor_name, analyze: bool = True) -> str:
    """Reads one stored résumé again with the AI and re-evaluates it (not with `analyze=False`: CV Selection SP
    keeps its own evaluation). Returns COMPLETED or PARTIAL. Raises ValueError (nothing changed) when the AI
    cannot read it now."""
    from . import engine
    position_settings.bind(position)
    if not ai_adapter.current_policy().cv_ai_authorized:
        raise ValueError("AI résumé reading is off for this position (Configuration).")
    candidate = persistence.get_candidate(session, pc.candidate_id)
    raw = session.get(m.RawResume, candidate.raw_resume_id) if candidate and candidate.raw_resume_id else None
    profile = read_profile(raw)
    status = apply_profile(session, position, pc, candidate, profile, actor_id=actor_id, actor_name=actor_name)
    if analyze and position.approved_snapshot_id:
        engine.analyze(session, position, pc, actor_id=actor_id, actor_name=actor_name)
    return status


def read_profile(raw):
    """The AI reading of one stored résumé, with no database write (it can run with no session open, as the SP
    queue does). Raises ValueError when there is nothing to read or the AI cannot read it now."""
    if raw is None or not (raw.raw_text or "").strip():
        raise ValueError("No stored résumé text to read.")
    try:
        profile = LLMResumeParser().parse(persistence.raw_resume_ref(raw))
    except ProviderUnavailable as exc:
        raise ValueError(f"The AI could not read it now: {exc}") from exc
    normalize_profile(profile)
    profile.source = raw.source_type  # as `parsing.resolve.parse_resume` does
    profile.source_provider = profile.source_provider or MANUAL_PROVIDER
    return profile


def apply_profile(session, position, pc, candidate, profile, *, actor_id, actor_name) -> str:
    """Stores a new AI reading on the same Candidate row, corrects the person's name and contacts, redoes the
    duplicate suggestions and cleans the import note. Commits. Returns COMPLETED or PARTIAL."""
    old = {"full_name": candidate.full_name, "email": candidate.email, "phone": candidate.phone}
    persistence.replace_candidate_profile(session, candidate, profile)
    # A name or contact the rule-based reader found and the AI did not is kept: the invitation email must not be
    # lost because the AI left it out. A "phone" that is really a date range is not kept.
    for field in ("full_name", "email"):
        if not getattr(candidate, field) and old[field]:
            setattr(candidate, field, old[field])
    if not candidate.phone and old["phone"] and _real_phone(old["phone"]):
        candidate.phone = old["phone"]
    _refresh_identity(session, pc, candidate, old)
    status, _ = reading_status(profile)
    note = _FAILED_NOTE.sub("", _OLD_READING_NOTES.sub("", pc.import_note or "")).strip()
    if status != COMPLETED:
        note = (note + " " + _NOTE_PARTIAL).strip()
    pc.import_note = note or None
    ps.log_event(session, position_id=position.id, position_candidate_id=pc.id, kind="CV_READ",
                 detail=f"Résumé read again with the AI: {candidate.full_name or 'name still not found'}",
                 actor_id=actor_id, actor_name=actor_name)
    session.commit()
    return status


def _real_phone(value) -> bool:
    from rfone_data_store.selection.parsing.deterministic_parser import _find_phone
    return bool(value) and _find_phone(str(value)) is not None


def mark_failed(session, pc_id: int, reason: str) -> None:
    """Remembers on the CV's import note that the AI could not read it, so the next "Read again" tries the others
    first instead of spending its time on the same CV (commits)."""
    pc = session.get(ps.PositionCandidate, pc_id)
    if pc is None:
        return
    note = _FAILED_NOTE.sub("", pc.import_note or "").strip()
    reason = reason[:120].replace("(", "[").replace(")", "]")
    pc.import_note = (note + f" {_NOTE_FAILED} ({reason}).").strip()
    session.commit()


def read_pending(session, position, *, actor_id, actor_name, analyze: bool = True) -> dict:
    """Reads again this position's résumés read without the AI, until the time budget is used up. One CV failing,
    for any reason, never stops the others."""
    started, result = time.monotonic(), {"read": 0, "partial": 0, "failed": [], "left": 0}
    todo = pending(session, position)
    for i, pc in enumerate(todo):
        if time.monotonic() - started > TIME_BUDGET_SECONDS:
            result["left"] = len(todo) - i
            break
        pc_id = pc.id
        try:
            status = read_again(session, position, pc, actor_id=actor_id, actor_name=actor_name, analyze=analyze)
            result["read" if status == COMPLETED else "partial"] += 1
        except Exception as exc:
            session.rollback()
            reason = str(exc) if isinstance(exc, ValueError) else f"unexpected error ({exc.__class__.__name__})"
            result["failed"].append(reason)
            if "off for this position" in reason:
                result["left"] = len(todo) - i - 1
                break
            try:
                mark_failed(session, pc_id, reason)
            except Exception:
                session.rollback()
    return result


def _refresh_identity(session, pc, candidate, old: dict | None = None) -> None:
    """The first reading (rule-based) often gave the person no name, a wrong name ("RESUME") or a date range as a
    phone, and "possible duplicate" suggestions were computed from that. Here a person's field is filled when it
    is blank or still holds exactly what the first reading of this CV put there; anything else (typed or confirmed
    by someone, or from another CV of the same person) is never overwritten. An email or phone another person
    already has is not copied: it becomes a suggestion to confirm. Persons are never merged or split here; when
    this CV is linked to a person with other applications and the AI reads a different name, the import note
    asks a person to check."""
    old = old or {}
    application = app_svc.get_application(session, pc.application_id)
    person = session.get(m.CandidatePerson, application.person_id) if application else None
    if person is None:
        return
    shared = len(app_svc.list_applications_for_person(session, person.id)) > 1

    def replaceable(current, first_reading) -> bool:
        return not current or (not shared and first_reading is not None and current == first_reading)

    if candidate.full_name and replaceable(person.full_name, old.get("full_name")):
        person.full_name, person.normalized_name = candidate.full_name, idm.normalize_name(candidate.full_name)
    elif shared and candidate.full_name and person.normalized_name != idm.normalize_name(candidate.full_name):
        if _NOTE_CHECK_PERSON not in (pc.import_note or ""):
            pc.import_note = ((pc.import_note or "") + f" {_NOTE_CHECK_PERSON}").strip()
    suggestions = []
    email = idm.normalize_email(candidate.email) if candidate.email else None
    old_email = idm.normalize_email(old["email"]) if old.get("email") else None
    if email and email != person.primary_email and replaceable(person.primary_email, old_email):
        other, confidence, basis = identity_svc._find_by_contact(
            session, restaurant_id=person.restaurant_id, normalized_email=email, normalized_phone=None)
        if other is not None and other.id != person.id:
            suggestions.append((other, confidence, basis))
        else:
            person.primary_email = email
    phone = idm.normalize_phone(candidate.phone) if candidate.phone else None
    if phone and phone != person.primary_phone_normalized and (
            replaceable(person.primary_phone, old.get("phone")) or not _real_phone(person.primary_phone)):
        other, confidence, basis = identity_svc._find_by_contact(
            session, restaurant_id=person.restaurant_id, normalized_email=None, normalized_phone=phone)
        if other is not None and other.id != person.id:
            suggestions.append((other, confidence, basis))
        else:
            person.primary_phone, person.primary_phone_normalized = candidate.phone, phone
    if shared:
        return  # the person's other applications keep their suggestions; nothing is recomputed from this CV alone
    session.execute(delete(m.PersonMatchCandidate).where(
        m.PersonMatchCandidate.application_id == application.id, m.PersonMatchCandidate.status == idm.PENDING))
    session.flush()
    created = identity_svc.create_pending_suggestions_for_application(session, application_id=application.id,
                                                                      new_person=person)
    already = {s.suggested_person_id for s in created}
    for other, confidence, basis in suggestions:
        if other.id not in already:
            already.add(other.id)
            session.add(m.PersonMatchCandidate(application_id=application.id, source_person_id=person.id,
                                               suggested_person_id=other.id, confidence=confidence,
                                               match_basis=basis))
    session.flush()


# ---------------------------------------------------------------------------
# Scanned PDFs
# ---------------------------------------------------------------------------

_TRANSCRIBE_PROMPT = ("These are the pages of one job applicant's résumé. Copy all of its text exactly, top to "
                      "bottom, as plain text. Keep the line breaks. Do not summarize, correct or add anything.")


def transcribe_pdf(path: str, *, sp: bool = False) -> str:
    """The text of a PDF with no text inside, read by the AI from its first pages as images.
    Raises AIProviderUnavailable when AI résumé reading is off or the AI cannot be reached."""
    if not ai_adapter.current_policy().cv_ai_authorized:
        raise AIProviderUnavailable("AI résumé processing is not authorized.")
    import pdfplumber
    images = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages[:PDF_PAGES]:
            images.append(_page_image(page))
    if not images:
        raise AIProviderUnavailable("The PDF has no pages.")
    try:
        if sp:
            from .sp import provider
            text = provider.transcribe(images, _TRANSCRIBE_PROMPT)
        else:
            text = _transcribe_transport(images)
    except AIProviderUnavailable as exc:
        ai_adapter._record("scanned résumé reading", False, str(exc))
        raise
    ai_adapter._record("scanned résumé reading", True, "ok")
    return text


def _page_image(page) -> bytes:
    """One page as a JPEG of at most PAGE_PIXELS on its longest side and under Bedrock's image limit. A phone photo
    saved as PDF has a page the size of the photo, and anyone applying can upload a PDF with a huge page: rendered
    at a fixed resolution, that ran to gigapixels (memory) and to images Bedrock refuses."""
    longest = max(float(page.width or 0), float(page.height or 0), 1.0)
    resolution = min(130.0, PAGE_PIXELS * 72 / longest)
    image = page.to_image(resolution=resolution).original.convert("RGB")
    for quality in (80, 65, 50):
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=quality)
        if buffer.tell() <= MAX_IMAGE_BYTES:
            return buffer.getvalue()
    raise AIProviderUnavailable("A page of the scan is too large to read.")


def _transcribe_transport(images: list[bytes]) -> str:
    """AWS Bedrock Converse with image blocks (the configured model, as `ai_client` uses). Seam for tests."""
    if ai_client._active_provider() != ai_client.PROVIDER_BEDROCK:
        raise AIProviderUnavailable("Scanned résumés are read only through AWS Bedrock.")
    model_id = ai_client._read_env_or_dotenv("RFONE_BEDROCK_MODEL_ID")
    if not model_id:
        raise AIProviderUnavailable("No RFONE_BEDROCK_MODEL_ID configured.")
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
        from botocore.config import Config
        # Runs inside an upload request: one attempt, bounded, never boto3's 60 s x 5 retries.
        client = boto3.client("bedrock-runtime", region_name=ai_client._read_env_or_dotenv("AWS_REGION"),
                              config=Config(connect_timeout=10, read_timeout=TRANSCRIBE_TIMEOUT_SECONDS,
                                            retries={"max_attempts": 1, "mode": "standard"}))
        response = client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"image": {"format": "jpeg", "source": {"bytes": b}}} for b in images]
                       + [{"text": _TRANSCRIBE_PROMPT}]}],
            inferenceConfig={"maxTokens": ai_client.MAX_OUTPUT_TOKENS, "temperature": 0})
    except ImportError as exc:
        raise AIProviderUnavailable("The 'boto3' package is not installed.") from exc
    except (BotoCoreError, ClientError) as exc:
        raise AIProviderUnavailable(f"AWS Bedrock call failed: {exc}") from exc
    return "".join(b.get("text", "") for b in response["output"]["message"]["content"]).strip()
