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
TIME_BUDGET_SECONDS = 80  # per click of "Read again": stays inside a web request; the rest waits for the next click
PDF_PAGES = 4
_NOTE_PARTIAL = "Partial résumé extraction; some sections need checking."
_NOTE_WITHOUT_AI = "Read without the AI"
_OLD_READING_NOTES = re.compile(re.escape(_NOTE_PARTIAL) + "|" + re.escape(_NOTE_WITHOUT_AI) + r" \([^)]*\)[^.]*\.")


def read_without_ai(candidate) -> bool:
    return candidate is not None and candidate.parsing_mode != AI_READING


def note_for_reading(candidate) -> str | None:
    """Why a résumé was read without the AI, for the import note (never silent)."""
    if not read_without_ai(candidate):
        return None
    reason = ("AI résumé reading is off for this position" if not ai_adapter.current_policy().cv_ai_authorized
              else "the AI was not available")
    return f"{_NOTE_WITHOUT_AI} ({reason}): use “Read again with the AI”."


def pending(session, position) -> list:
    """This position's résumés read without the AI."""
    pcs = session.scalars(select(ps.PositionCandidate).where(ps.PositionCandidate.position_id == position.id)
                          .order_by(ps.PositionCandidate.id)).all()
    return [pc for pc in pcs if read_without_ai(persistence.get_candidate(session, pc.candidate_id))]


def read_again(session, position, pc, *, actor_id, actor_name) -> str:
    """Reads one stored résumé again with the AI and re-evaluates it. Returns COMPLETED or PARTIAL.
    Raises ValueError (nothing changed) when the AI cannot read it now."""
    from . import engine
    position_settings.bind(position)
    if not ai_adapter.current_policy().cv_ai_authorized:
        raise ValueError("AI résumé reading is off for this position (Configuration).")
    candidate = persistence.get_candidate(session, pc.candidate_id)
    raw = session.get(m.RawResume, candidate.raw_resume_id) if candidate and candidate.raw_resume_id else None
    if raw is None or not (raw.raw_text or "").strip():
        raise ValueError("No stored résumé text to read.")
    try:
        profile = LLMResumeParser().parse(persistence.raw_resume_ref(raw))
    except ProviderUnavailable as exc:
        raise ValueError(f"The AI could not read it now: {exc}") from exc
    normalize_profile(profile)
    profile.source = raw.source_type  # as `parsing.resolve.parse_resume` does
    profile.source_provider = profile.source_provider or MANUAL_PROVIDER

    persistence.replace_candidate_profile(session, candidate, profile)
    _refresh_identity(session, pc, candidate)
    status, _ = reading_status(profile)
    note = _OLD_READING_NOTES.sub("", pc.import_note or "").strip()
    if status != COMPLETED:
        note = (note + " " + _NOTE_PARTIAL).strip()
    pc.import_note = note or None
    ps.log_event(session, position_id=position.id, position_candidate_id=pc.id, kind="CV_READ",
                 detail=f"Résumé read again with the AI: {candidate.full_name or 'name still not found'}",
                 actor_id=actor_id, actor_name=actor_name)
    session.commit()
    if position.approved_snapshot_id:
        engine.analyze(session, position, pc, actor_id=actor_id, actor_name=actor_name)
    return status


def read_pending(session, position, *, actor_id, actor_name) -> dict:
    """Reads again this position's résumés read without the AI, until the time budget is used up."""
    started, result = time.monotonic(), {"read": 0, "partial": 0, "failed": [], "left": 0}
    todo = pending(session, position)
    for i, pc in enumerate(todo):
        if time.monotonic() - started > TIME_BUDGET_SECONDS:
            result["left"] = len(todo) - i
            break
        try:
            status = read_again(session, position, pc, actor_id=actor_id, actor_name=actor_name)
            result["read" if status == COMPLETED else "partial"] += 1
        except ValueError as exc:
            session.rollback()
            result["failed"].append(str(exc))
            if "off for this position" in str(exc):
                result["left"] = len(todo) - i - 1
                break
    return result


def _refresh_identity(session, pc, candidate) -> None:
    """The empty first reading created a person with no name or contacts, and "possible duplicate" suggestions
    were computed from that. Fill only blank fields (the same rule as `identity_service.resolve_or_create_person`)
    and compute the suggestions again from the real name. Confirmed or rejected suggestions are kept; persons are
    never merged here: a real duplicate shows up as a suggestion for a person to confirm."""
    application = app_svc.get_application(session, pc.application_id)
    person = session.get(m.CandidatePerson, application.person_id) if application else None
    if person is None:
        return
    if not person.full_name and candidate.full_name:
        person.full_name, person.normalized_name = candidate.full_name, idm.normalize_name(candidate.full_name)
    if not person.primary_email and candidate.email:
        person.primary_email = idm.normalize_email(candidate.email)
    if not person.primary_phone and candidate.phone:
        person.primary_phone, person.primary_phone_normalized = candidate.phone, idm.normalize_phone(candidate.phone)
    session.execute(delete(m.PersonMatchCandidate).where(
        m.PersonMatchCandidate.application_id == application.id, m.PersonMatchCandidate.status == idm.PENDING))
    if len(app_svc.list_applications_for_person(session, person.id)) == 1:
        identity_svc.create_pending_suggestions_for_application(session, application_id=application.id,
                                                                new_person=person)


# ---------------------------------------------------------------------------
# Scanned PDFs
# ---------------------------------------------------------------------------

_TRANSCRIBE_PROMPT = ("These are the pages of one job applicant's résumé. Copy all of its text exactly, top to "
                      "bottom, as plain text. Keep the line breaks. Do not summarize, correct or add anything.")


def transcribe_pdf(path: str) -> str:
    """The text of a PDF with no text inside, read by the AI from its first pages as images.
    Raises AIProviderUnavailable when AI résumé reading is off or the AI cannot be reached."""
    if not ai_adapter.current_policy().cv_ai_authorized:
        raise AIProviderUnavailable("AI résumé processing is not authorized.")
    import pdfplumber
    images = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages[:PDF_PAGES]:
            buffer = io.BytesIO()
            page.to_image(resolution=130).original.convert("RGB").save(buffer, "PNG")
            images.append(buffer.getvalue())
    if not images:
        raise AIProviderUnavailable("The PDF has no pages.")
    try:
        text = _transcribe_transport(images)
    except AIProviderUnavailable as exc:
        ai_adapter._record("scanned résumé reading", False, str(exc))
        raise
    ai_adapter._record("scanned résumé reading", True, "ok")
    return text


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
        client = boto3.client("bedrock-runtime", region_name=ai_client._read_env_or_dotenv("AWS_REGION"))
        response = client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"image": {"format": "png", "source": {"bytes": b}}} for b in images]
                       + [{"text": _TRANSCRIBE_PROMPT}]}],
            inferenceConfig={"maxTokens": 4096, "temperature": 0})
    except ImportError as exc:
        raise AIProviderUnavailable("The 'boto3' package is not installed.") from exc
    except (BotoCoreError, ClientError) as exc:
        raise AIProviderUnavailable(f"AWS Bedrock call failed: {exc}") from exc
    return "".join(b.get("text", "") for b in response["output"]["message"]["content"]).strip()
