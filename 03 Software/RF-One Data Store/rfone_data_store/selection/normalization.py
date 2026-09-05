"""Date + role normalization (Task 2B). Runtime orchestration — combines
Selection Core's date parsing (`parsing/flexible_dates.py`) with the
Restaurant Industry Extension's role catalog (`industry/restaurant.py`) and
applies both uniformly to a `CandidateCVProfile`, exactly like
`analysis.py` already does for the read-time Derived layer. This is the
single place both `ResumeParser` implementations converge before
persistence (task's own pipeline: "structured parsing → DATE + ROLE
NORMALIZATION → persisted candidate profile").

Every normalized field is ALWAYS re-derived from its one raw source
(`start_date_text`/`end_date_text` for dates, `original_job_title` for
roles) — never from another already-normalized field — which is what makes
`normalize_profile()`/`reprocess_candidate()` idempotent by construction:
running either twice on unchanged raw input reproduces the same output,
never drifts.

This module never invents a value: a record with no raw date text captured
is left with its date fields exactly as they were (never guessed into
existence); a title with no catalog match is left with `normalized_title`/
`role_family`/`seniority_level` all None rather than an invented
classification.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from . import persistence
from .core.profile import CandidateCVProfile, EducationRecord, WorkHistoryRecord
from .industry import restaurant as restaurant_industry
from .parsing import flexible_dates


def _normalize_dates(record: WorkHistoryRecord | EducationRecord) -> None:
    """Mutates `record`'s date fields in place, but ONLY when raw text was
    actually captured — a record with neither `start_date_text` nor
    `end_date_text` (a pre-Task-2B legacy row, or a record whose dates
    simply were not found) is left completely untouched, never
    destructively overwritten with a guess (task §"DATA MIGRATION": "do not
    destructively overwrite original dates or titles")."""

    if not (record.start_date_text or record.end_date_text):
        return

    result = flexible_dates.normalize_date_pair(record.start_date_text, record.end_date_text)
    record.start_date = result.normalized_start
    record.end_date = result.normalized_end
    record.start_date_precision = result.start_precision
    record.end_date_precision = result.end_precision
    record.date_normalization_confidence = result.confidence
    if isinstance(record, WorkHistoryRecord):
        record.is_current = result.is_current


def _normalize_role(record: WorkHistoryRecord) -> None:
    """Mutates `record`'s role fields in place, from `original_job_title`
    only. A title matching zero catalog roles (ambiguous/company-specific —
    task §"CONFIDENCE AND CONSERVATIVE NORMALIZATION") leaves every Task 2B
    role field None; `normalized_role` (Task 2A's single catalog-code field,
    still read by the existing analysis engine) is likewise left as it was
    rather than fabricated."""

    if not record.original_job_title:
        return

    segments = restaurant_industry.split_multi_role_title(record.original_job_title)
    codes: list[str] = []
    for segment in segments:
        code = restaurant_industry.normalize_title(segment)
        if code and code not in codes:
            codes.append(code)

    if not codes:
        return

    record.normalized_role = codes[0]
    display_names = [restaurant_industry.display_name_for(c, record.original_job_title) for c in codes]
    record.normalized_title = " / ".join(dict.fromkeys(n for n in display_names if n))
    families = [restaurant_industry.role_family(c) for c in codes]
    record.role_family = " / ".join(dict.fromkeys(f for f in families if f)) or None
    record.multi_role = len(codes) > 1
    record.seniority_level = restaurant_industry.seniority_level_from_title(record.original_job_title)
    record.title_normalization_confidence = "MEDIUM" if record.multi_role else "HIGH"


def normalize_profile(profile: CandidateCVProfile) -> CandidateCVProfile:
    """Normalizes every work-history and education record on `profile` in
    place and returns it (task's integration point, called from
    `parsing/resolve.py` right after parsing, before persistence)."""

    for record in profile.work_history:
        _normalize_dates(record)
        _normalize_role(record)
    for record in profile.education:
        _normalize_dates(record)
    return profile


def reprocess_candidate(session: Session, candidate_id: int) -> bool:
    """Re-runs date + role normalization for one already-persisted
    candidate, using only its already-stored raw values — never re-uploads
    or re-parses the source résumé (task §"REPROCESSING EXISTING
    CANDIDATES"). Returns False if the candidate does not exist, True
    otherwise (including when the candidate had nothing normalizable, which
    is not an error).

    A legacy candidate imported before Task 2B has no `start_date_text`/
    `end_date_text` — `_normalize_dates` leaves its dates exactly as Task 2A
    left them in that case, so reprocessing it only ever adds role
    normalization, never touches or blanks its existing dates."""

    candidate = persistence.get_candidate(session, candidate_id)
    if candidate is None:
        return False

    for row in candidate.work_history:
        record = WorkHistoryRecord(
            original_job_title=row.original_job_title, normalized_role=row.normalized_role,
            start_date=row.start_date, end_date=row.end_date, is_current=row.is_current,
            start_date_text=row.start_date_text, end_date_text=row.end_date_text,
        )
        _normalize_dates(record)
        _normalize_role(record)
        row.start_date, row.end_date, row.is_current = record.start_date, record.end_date, record.is_current
        row.start_date_precision, row.end_date_precision = record.start_date_precision, record.end_date_precision
        row.date_normalization_confidence = record.date_normalization_confidence
        row.normalized_role = record.normalized_role
        row.normalized_title, row.role_family = record.normalized_title, record.role_family
        row.seniority_level, row.multi_role = record.seniority_level, record.multi_role
        row.title_normalization_confidence = record.title_normalization_confidence

    for row in candidate.education:
        record = EducationRecord(
            start_date=row.start_date, end_date=row.end_date,
            start_date_text=row.start_date_text, end_date_text=row.end_date_text,
        )
        _normalize_dates(record)
        row.start_date, row.end_date = record.start_date, record.end_date
        row.start_date_precision, row.end_date_precision = record.start_date_precision, record.end_date_precision
        row.date_normalization_confidence = record.date_normalization_confidence

    session.commit()
    return True
