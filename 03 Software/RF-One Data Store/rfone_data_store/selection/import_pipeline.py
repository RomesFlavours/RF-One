"""Batch résumé import orchestration (TASK_SELECTION_002; PARTIAL status and
the no-extractable-text short-circuit added by Task 2A §1/§8). Turns one
already-acquired résumé (file saved to disk, text already extracted by the
caller) into a persisted `CandidateCVProfile`, with duplicate detection and
per-file failure isolation ("a failure on one resume must not prevent the
remaining resumes from being processed" — task §2).

Kept here, in `rfone_data_store/selection/`, rather than in
`03 Software/Selection/app.py`, so it is exercised by tests without a
running Flask app, and so a future ResumeSource (e.g. an API feed instead of
local upload) can reuse this same per-item orchestration unchanged — the web
app's job stays limited to routing/HTTP/file I/O (its own module docstring).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from . import persistence
from .core.profile import CandidateCVProfile
from .core.resume_source import RawResumeRef
from .parsing.resolve import parse_resume

COMPLETED = "COMPLETED"
PARTIAL = "PARTIAL"
FAILED = "FAILED"
DUPLICATE = "DUPLICATE"


@dataclass
class ImportResult:
    """One file's outcome — always one of COMPLETED / PARTIAL / FAILED /
    DUPLICATE, never a raised exception, so a caller looping over many files
    gets per-file isolation for free without its own try/except per
    iteration."""

    status: str
    original_filename: str | None
    candidate_id: int | None = None
    full_name: str | None = None
    parsing_mode: str | None = None
    error: str | None = None
    duplicate_of_candidate_id: int | None = None
    duplicate_of_raw_resume_id: int | None = None


def _has_minimal_signal(profile: CandidateCVProfile) -> bool:
    """True when the parser found at least something to show a human
    evaluator — task §1: distinguish a genuinely usable import from one that
    merely stored raw text with nothing structured recognized in it
    (PARTIAL, not COMPLETED, and never silently indistinguishable from a
    well-parsed résumé)."""

    return bool(
        profile.full_name or profile.email or profile.phone
        or profile.work_history or profile.education
    )


def import_one_resume(
    session: Session, *, restaurant_id: int | None, source_type: str,
    original_filename: str | None, storage_path: str | None, raw_text: str | None,
    content_hash: str | None,
) -> ImportResult:
    """Processes exactly one résumé end to end: no-extractable-text check,
    duplicate check, persist RawResume, parse (real AI, falling back to
    real rule-based extraction — see `parsing/resolve.py`), persist
    CandidateCVProfile. Commits on success; rolls back and returns a FAILED
    result on any error, never raising."""

    try:
        if not raw_text or not raw_text.strip():
            return ImportResult(
                status=FAILED, original_filename=original_filename,
                error="No extractable text found in this résumé (e.g. a scanned/image-only PDF, "
                "a corrupt file, or an empty file).",
            )

        if content_hash:
            existing_raw = persistence.find_raw_resume_by_hash(
                session, restaurant_id=restaurant_id, content_hash=content_hash,
            )
            if existing_raw is not None:
                existing_candidate = persistence.find_candidate_by_raw_resume_id(session, existing_raw.id)
                return ImportResult(
                    status=DUPLICATE, original_filename=original_filename,
                    candidate_id=existing_candidate.id if existing_candidate else None,
                    full_name=existing_candidate.full_name if existing_candidate else None,
                    duplicate_of_candidate_id=existing_candidate.id if existing_candidate else None,
                    duplicate_of_raw_resume_id=existing_raw.id,
                )

        raw_resume = persistence.save_raw_resume(
            session, restaurant_id=restaurant_id, source_type=source_type,
            original_filename=original_filename, storage_path=storage_path,
            raw_text=raw_text, content_hash=content_hash,
        )
        profile = parse_resume(
            RawResumeRef(source_type=source_type, raw_text=raw_text, original_filename=original_filename)
        )
        candidate = persistence.save_candidate_profile(
            session, profile, restaurant_id=restaurant_id, raw_resume_id=raw_resume.id,
        )
        session.commit()
        status = COMPLETED if _has_minimal_signal(profile) else PARTIAL
        return ImportResult(
            status=status, original_filename=original_filename,
            candidate_id=candidate.id, full_name=candidate.full_name,
            parsing_mode=candidate.parsing_mode,
            error=None if status == COMPLETED else
            "Résumé text was extracted and saved, but no name, contact details, work history or "
            "education could be confidently identified — review the raw text manually.",
        )
    except Exception as exc:
        # Never log/propagate the résumé's own text (task §12 — no raw
        # personal information in server logs); the exception's type name is
        # enough to diagnose without risking that.
        session.rollback()
        return ImportResult(
            status=FAILED, original_filename=original_filename,
            error=f"Could not process this résumé ({type(exc).__name__}).",
        )
