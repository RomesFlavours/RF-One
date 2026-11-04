"""Candidate Fit Assessment — service layer (Task 3B). Runtime orchestration
combining Selection Core's Fit Assessment vocabulary
(`core/fit_assessment_model.py`), the immutable Requirement snapshot
mechanism (`requirements_service.py`, Task 3A-FIX), a candidate's
`CandidateCVProfile` (`persistence.py`, Task 2A/2B), and the résumé-stage
evidence matcher (`resume_evidence_matcher.py`) — the same role
`import_pipeline.py`/`normalization.py`/`requirements_service.py` already
play elsewhere in Selection. Flask routes should call into this module
rather than touching `.. models` directly.

Fundamental boundary (task §1): a Requirement is what the restaurant wants
(`requirements_service.py`'s job); a Fit Assessment is how AVAILABLE
EVIDENCE relates to that Requirement (this module's job). Nothing here ever
decides whether a candidate should be hired, produces a score, or ranks
candidates — it only ever organizes evidence per Requirement.

Snapshot binding (task §2): every Fit Assessment is created against an
immutable `RequirementSetSnapshot`, never against live `Requirement` rows.
`create_fit_assessment()` (from a live Requirement Set) is a thin wrapper
around `requirements_service.create_requirement_set_snapshot()` — reusing
that existing, idempotent-per-version mechanism rather than building a
parallel one.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from .. import models as m
from . import persistence, requirements_service as req_svc, resume_evidence_matcher
from .core import fit_assessment_model as fam

RESUME_STAGE = "RESUME"


def _validate_status(value: str) -> None:
    if value not in fam.ASSESSMENT_STATUSES:
        raise ValueError(f"Unknown assessment status {value!r}; expected one of {fam.ASSESSMENT_STATUSES}")


def _validate_source_type(value: str) -> None:
    if value not in fam.EVIDENCE_SOURCE_TYPES:
        raise ValueError(f"Unknown evidence source type {value!r}; expected one of {fam.EVIDENCE_SOURCE_TYPES}")


def _validate_classification(value: str) -> None:
    if value not in fam.EVIDENCE_CLASSIFICATIONS:
        raise ValueError(f"Unknown evidence classification {value!r}; expected one of {fam.EVIDENCE_CLASSIFICATIONS}")


def _validate_evidence_relationship(value: str) -> None:
    if value not in fam.EVIDENCE_RELATIONSHIPS:
        raise ValueError(f"Unknown evidence relationship {value!r}; expected one of {fam.EVIDENCE_RELATIONSHIPS}")


def _validate_confidence(value: str) -> None:
    if value not in fam.CONFIDENCE_LEVELS:
        raise ValueError(f"Unknown confidence {value!r}; expected one of {fam.CONFIDENCE_LEVELS}")


# ---------------------------------------------------------------------------
# Creation (task §2/§22)
# ---------------------------------------------------------------------------

def create_fit_assessment_from_snapshot(
    session: Session, *, candidate_id: int, snapshot_id: int, stage: str = RESUME_STAGE,
) -> m.FitAssessment:
    """Creates a Fit Assessment directly against an already-known immutable
    snapshot — the primitive every other creation path funnels through.
    Every ACTIVE (`was_active=True`) item in the snapshot gets exactly one
    `RequirementAssessment` row, initialized `NOT_ASSESSED_AT_THIS_STAGE`
    (never guessed before any evidence-gathering has actually run)."""

    candidate = session.get(m.Candidate, candidate_id)
    if candidate is None:
        raise ValueError(f"No Candidate with id {candidate_id}")
    snapshot = req_svc.get_snapshot(session, snapshot_id)
    if snapshot is None:
        raise ValueError(f"No RequirementSetSnapshot with id {snapshot_id}")

    fit_assessment = m.FitAssessment(
        candidate_id=candidate_id, requirement_set_snapshot_id=snapshot.id,
        requirement_set_id=snapshot.requirement_set_id, current_stage=stage,
    )
    session.add(fit_assessment)
    session.flush()

    for item in sorted(snapshot.items, key=lambda i: i.display_order):
        if not item.was_active:
            continue
        session.add(
            m.RequirementAssessment(
                fit_assessment_id=fit_assessment.id, requirement_snapshot_item_id=item.id, stage=stage,
                system_status=fam.NOT_ASSESSED_AT_THIS_STAGE, effective_status=fam.NOT_ASSESSED_AT_THIS_STAGE,
                origin=fam.SYSTEM_GENERATED, display_order=item.display_order,
            )
        )
    session.flush()

    if stage == RESUME_STAGE:
        generate_resume_stage_assessment(session, fit_assessment.id)
    return fit_assessment


def create_fit_assessment(
    session: Session, *, candidate_id: int, requirement_set_id: int, stage: str = RESUME_STAGE,
) -> m.FitAssessment:
    """Creates a Fit Assessment from a LIVE Requirement Set — captures (or
    reuses, per `requirements_service`'s own idempotent-per-version
    behavior) an immutable snapshot of its CURRENT version first, then
    assesses against that snapshot exactly like
    `create_fit_assessment_from_snapshot`. Assessing the same candidate
    against a newer live version later always produces a NEW Fit
    Assessment bound to a NEW snapshot — this function never repoints an
    existing one (task §21)."""

    snapshot = req_svc.create_requirement_set_snapshot(session, requirement_set_id)
    return create_fit_assessment_from_snapshot(
        session, candidate_id=candidate_id, snapshot_id=snapshot.id, stage=stage,
    )


# ---------------------------------------------------------------------------
# Résumé-stage assessment (task §10) — also the refresh entry point (§21):
# calling this again re-runs the SAME conservative matcher against the SAME
# snapshot, replacing only system-generated evidence.
# ---------------------------------------------------------------------------

def generate_resume_stage_assessment(session: Session, fit_assessment_id: int) -> m.FitAssessment:
    """(Re)generates RESUME-stage evidence for every RequirementAssessment
    in this Fit Assessment whose snapshotted item permits RESUME. Safe to
    call more than once (task §21's "refresh"): existing system-generated
    evidence is replaced with a fresh pass over the SAME
    `RequirementSetSnapshot` (never a newer one); any human-added evidence
    (`is_system_generated=False`) is left completely untouched, and once a
    `RequirementAssessment.origin` is any HUMAN_* value, `effective_status`
    is no longer auto-updated by this function — only `system_status` is,
    so the human's recorded conclusion is never silently overwritten."""

    fit_assessment = session.get(m.FitAssessment, fit_assessment_id)
    if fit_assessment is None:
        raise ValueError(f"No FitAssessment with id {fit_assessment_id}")

    candidate = session.get(m.Candidate, fit_assessment.candidate_id)
    profile = persistence.to_profile(candidate)

    for requirement_assessment in fit_assessment.requirement_assessments:
        item = requirement_assessment.requirement_snapshot_item

        if RESUME_STAGE not in (item.assessment_stages or []):
            # Stage not permitted at all — no evidence gathering attempted
            # (task §6). Never overwrite a human-touched conclusion just
            # because résumé assessment does not apply to this Requirement.
            if requirement_assessment.origin == fam.SYSTEM_GENERATED:
                requirement_assessment.system_status = fam.NOT_ASSESSED_AT_THIS_STAGE
                requirement_assessment.effective_status = fam.NOT_ASSESSED_AT_THIS_STAGE
            continue

        for evidence in list(requirement_assessment.evidence_items):
            if evidence.is_system_generated:
                session.delete(evidence)
        session.flush()

        for draft in resume_evidence_matcher.generate_resume_evidence(item, profile):
            session.add(
                m.EvidenceItem(
                    requirement_assessment_id=requirement_assessment.id, source_type=draft.source_type,
                    source_stage=RESUME_STAGE, source_reference=draft.source_reference,
                    evidence_text=draft.evidence_text, evidence_classification=draft.evidence_classification,
                    evidence_relationship=draft.evidence_relationship, confidence=draft.confidence,
                    explanation=draft.explanation, is_system_generated=draft.is_system_generated,
                )
            )
        session.flush()
        # `evidence_items` was already loaded above (for the deletion loop);
        # new rows were added by setting the FK column directly, which does
        # NOT update an already-loaded relationship collection in memory.
        # Expire it so the next access below reloads fresh from the DB —
        # without this, the new evidence would be silently invisible to
        # `compute_status_from_evidence`.
        session.expire(requirement_assessment, ["evidence_items"])

        new_system_status = fam.compute_status_from_evidence(list(requirement_assessment.evidence_items))
        requirement_assessment.system_status = new_system_status
        if requirement_assessment.origin == fam.SYSTEM_GENERATED:
            requirement_assessment.effective_status = new_system_status
        requirement_assessment.stage = RESUME_STAGE
        requirement_assessment.confidence = _dominant_confidence(requirement_assessment.evidence_items)

    fit_assessment.current_stage = RESUME_STAGE
    session.flush()
    return fit_assessment


def _dominant_confidence(evidence_items: list) -> str | None:
    """A simple, honest summary confidence for the RequirementAssessment
    row itself — the highest confidence among SUPPORTS/CONTRADICTS
    evidence, or None if there is no evidence at all. Individual evidence
    items keep their own confidence regardless; this is only a convenience
    rollup for display."""

    relevant = [e for e in evidence_items if e.evidence_relationship in (fam.SUPPORTS, fam.CONTRADICTS)]
    if not relevant:
        return None
    return max((e.confidence for e in relevant), key=lambda c: fam.CONFIDENCE_ORDER.get(c, 0))


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def get_fit_assessment(session: Session, fit_assessment_id: int) -> m.FitAssessment | None:
    return session.get(m.FitAssessment, fit_assessment_id)


def list_fit_assessments_for_candidate(session: Session, candidate_id: int) -> list[m.FitAssessment]:
    from sqlalchemy import select
    stmt = (
        select(m.FitAssessment)
        .where(m.FitAssessment.candidate_id == candidate_id)
        .order_by(m.FitAssessment.created_at.desc())
    )
    return list(session.scalars(stmt).all())


def list_requirement_assessments(session: Session, fit_assessment_id: int) -> list[m.RequirementAssessment]:
    fit_assessment = session.get(m.FitAssessment, fit_assessment_id)
    if fit_assessment is None:
        return []
    return list(fit_assessment.requirement_assessments)


def get_summary(session: Session, fit_assessment_id: int) -> dict:
    """Task §15's own acceptable summary shape — counts per status, total,
    and nothing else. Never a score, percentage, or aggregate."""

    fit_assessment = session.get(m.FitAssessment, fit_assessment_id)
    if fit_assessment is None:
        raise ValueError(f"No FitAssessment with id {fit_assessment_id}")

    counts = {status: 0 for status in fam.ASSESSMENT_STATUSES}
    for ra in fit_assessment.requirement_assessments:
        counts[ra.effective_status] = counts.get(ra.effective_status, 0) + 1
    return {"total": len(fit_assessment.requirement_assessments), "counts": counts}


# ---------------------------------------------------------------------------
# Evidence / notes / human review (task §14/§16/§17/§18)
# ---------------------------------------------------------------------------

def add_evidence(
    session: Session, requirement_assessment_id: int, *, source_type: str, evidence_classification: str,
    evidence_relationship: str, confidence: str = fam.CONFIDENCE_UNKNOWN, evidence_text: str | None = None,
    source_stage: str | None = None, source_reference: str | None = None, explanation: str | None = None,
    is_system_generated: bool = False,
) -> m.EvidenceItem:
    """Appends one evidence item — never overwrites or removes existing
    evidence (task §14/§19), so this is the ONLY way a
    `RequirementAssessment`'s status changes going forward. Recomputes
    `system_status` from ALL evidence (old + new); `effective_status` is
    only auto-updated when `origin` is still `SYSTEM_GENERATED` — a
    human-touched assessment (`HUMAN_ENTERED`/`HUMAN_CONFIRMED`/
    `HUMAN_OVERRIDDEN`) keeps its recorded `effective_status` even as new
    evidence arrives, until a human explicitly re-confirms or re-overrides
    it."""

    _validate_source_type(source_type)
    _validate_classification(evidence_classification)
    _validate_evidence_relationship(evidence_relationship)
    _validate_confidence(confidence)

    requirement_assessment = session.get(m.RequirementAssessment, requirement_assessment_id)
    if requirement_assessment is None:
        raise ValueError(f"No RequirementAssessment with id {requirement_assessment_id}")

    evidence = m.EvidenceItem(
        requirement_assessment_id=requirement_assessment.id, source_type=source_type, source_stage=source_stage,
        source_reference=source_reference, evidence_text=evidence_text,
        evidence_classification=evidence_classification, evidence_relationship=evidence_relationship,
        confidence=confidence, explanation=explanation, is_system_generated=is_system_generated,
    )
    session.add(evidence)
    session.flush()
    # See the matching comment in `generate_resume_stage_assessment`: a new
    # row added via its FK column does not update an already-loaded
    # `evidence_items` collection, so force a fresh reload before recomputing.
    session.expire(requirement_assessment, ["evidence_items"])

    new_system_status = fam.compute_status_from_evidence(list(requirement_assessment.evidence_items))
    requirement_assessment.system_status = new_system_status
    if requirement_assessment.origin == fam.SYSTEM_GENERATED:
        requirement_assessment.effective_status = new_system_status
    if source_stage:
        requirement_assessment.stage = source_stage
    requirement_assessment.confidence = _dominant_confidence(requirement_assessment.evidence_items)
    session.flush()
    return evidence


def add_note(
    session: Session, *, fit_assessment_id: int | None = None, requirement_assessment_id: int | None = None,
    note_text: str,
) -> None:
    """Sets a plain human note — on the Fit Assessment, a Requirement
    Assessment, or both. NEVER creates evidence and NEVER changes any
    status (task §18) — a note is purely for the human evaluator's own
    reference."""

    if fit_assessment_id is not None:
        fit_assessment = session.get(m.FitAssessment, fit_assessment_id)
        if fit_assessment is None:
            raise ValueError(f"No FitAssessment with id {fit_assessment_id}")
        fit_assessment.notes = note_text
    if requirement_assessment_id is not None:
        requirement_assessment = session.get(m.RequirementAssessment, requirement_assessment_id)
        if requirement_assessment is None:
            raise ValueError(f"No RequirementAssessment with id {requirement_assessment_id}")
        requirement_assessment.notes = note_text
    session.flush()


def human_confirm(session: Session, requirement_assessment_id: int, *, note: str | None = None) -> m.RequirementAssessment:
    """A human reviewed the current (system or already-human) status and
    agrees with it — `effective_status` is left exactly as it is;
    `origin` becomes `HUMAN_CONFIRMED` so a later refresh no longer
    auto-updates `effective_status` (task §16/§17)."""

    requirement_assessment = session.get(m.RequirementAssessment, requirement_assessment_id)
    if requirement_assessment is None:
        raise ValueError(f"No RequirementAssessment with id {requirement_assessment_id}")
    requirement_assessment.origin = fam.HUMAN_CONFIRMED
    if note:
        requirement_assessment.notes = note
    session.flush()
    return requirement_assessment


def human_override(
    session: Session, requirement_assessment_id: int, *, new_status: str, reason: str | None = None,
) -> m.RequirementAssessment:
    """A human sets a different effective status than the system computed.
    `system_status` is preserved exactly as the system last computed it —
    never deleted or replaced — only `effective_status` changes, alongside
    `origin`, `override_reason` and `overridden_at` (task §17)."""

    _validate_status(new_status)
    requirement_assessment = session.get(m.RequirementAssessment, requirement_assessment_id)
    if requirement_assessment is None:
        raise ValueError(f"No RequirementAssessment with id {requirement_assessment_id}")

    requirement_assessment.effective_status = new_status
    requirement_assessment.origin = fam.HUMAN_OVERRIDDEN
    requirement_assessment.override_reason = reason
    # Naive by convention, matching every other Selection datetime
    # (`core/experience_analysis.py`'s own module note: SQLite round-trips
    # DateTime columns as naive regardless of `timezone=True`).
    requirement_assessment.overridden_at = datetime.utcnow()
    session.flush()
    return requirement_assessment
