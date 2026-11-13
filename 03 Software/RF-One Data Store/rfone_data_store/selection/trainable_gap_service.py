"""Trainable Gap — service layer (Task 5B). Runtime orchestration between
Selection Core's Trainable Gap vocabulary (`core/trainable_gap_model.py`)
and the persisted `TrainableGap` rows (`.. models`). Flask routes should
call into this module rather than touching `.. models` directly (same
"routes are thin" discipline every other Selection service follows — see
`fit_assessment_service.py`, `primary_screening_service.py`).

Fundamental boundary (TrainableGap.md): a Trainable Gap is a candidate gap
that is ALREADY EVIDENCED (NOT_EVIDENCED/PARTIALLY_EVIDENCED on a
`RequirementAssessment`) against a Requirement the restaurant considers
TRAINABLE/PARTIALLY_TRAINABLE — never a Training target, never a hiring
decision, never something that automatically changes Stage/Outcome. This
module never creates, and must never be extended to create, a Training
Plan, Training Check, or Autonomy Level (task's explicit "do not implement
Training Domain").
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import application_service as app_svc
from . import fit_assessment_service as fa_svc
from .core import fit_assessment_model as fam
from .core import trainable_gap_model as tgm

NOTE_CONTEXT_TRAINABLE_GAP = "TRAINABLE_GAP"


# ---------------------------------------------------------------------------
# Generation (task §1/§4/§8) — identifies eligible gaps from an existing
# Fit Assessment's RequirementAssessments and proposes an RF-One initial
# level for each. Safe to call more than once: never creates a duplicate
# row for a RequirementAssessment that already has one, and never modifies
# `rf_one_initial_level`/`selezionatore_initial_level` on an existing row.
# ---------------------------------------------------------------------------

def generate_trainable_gaps_for_fit_assessment(session: Session, fit_assessment_id: int) -> list[m.TrainableGap]:
    fit_assessment = session.get(m.FitAssessment, fit_assessment_id)
    if fit_assessment is None:
        raise ValueError(f"No FitAssessment with id {fit_assessment_id}")

    application = session.scalars(
        select(m.Application).where(m.Application.candidate_id == fit_assessment.candidate_id)
    ).first()

    created: list[m.TrainableGap] = []
    if application is not None:
        for ra in fa_svc.list_requirement_assessments(session, fit_assessment_id):
            item = ra.requirement_snapshot_item
            if not tgm.is_trainable_gap_eligible(effective_status=ra.effective_status, trainability=item.trainability):
                continue
            existing = session.scalars(
                select(m.TrainableGap).where(m.TrainableGap.requirement_assessment_id == ra.id)
            ).first()
            if existing is not None:
                continue

            rf_one_level = tgm.propose_initial_level(effective_status=ra.effective_status, confidence=ra.confidence)
            gap = m.TrainableGap(
                application_id=application.id, candidate_id=fit_assessment.candidate_id,
                fit_assessment_id=fit_assessment_id, requirement_assessment_id=ra.id,
                missing_capability=item.name, trainability=item.trainability, source_fit_status=ra.effective_status,
                importance=item.criticality, rf_one_initial_level=rf_one_level,
                effective_initial_level=rf_one_level, confidence=ra.confidence, origin=fam.SYSTEM_GENERATED,
                status=tgm.ACTIVE,
            )
            session.add(gap)
            created.append(gap)

    # Task §8/§3 (status) — withdraw any previously ACTIVE gap whose
    # RequirementAssessment is no longer evidenced as a gap at all (e.g. new
    # evidence moved it to EVIDENCED). Never touches `rf_one_initial_level`/
    # `selezionatore_initial_level`/`effective_initial_level` — only the
    # lifecycle `status` flag, so a Selezionatore's own prior judgment on
    # this gap is preserved in history even after it closes.
    still_active = session.scalars(
        select(m.TrainableGap).where(
            m.TrainableGap.fit_assessment_id == fit_assessment_id, m.TrainableGap.status == tgm.ACTIVE,
        )
    ).all()
    for gap in still_active:
        ra = gap.requirement_assessment
        if ra.effective_status not in tgm.ELIGIBLE_FIT_STATUSES:
            gap.status = tgm.WITHDRAWN

    session.flush()
    return created


def generate_trainable_gaps_for_application(session: Session, application_id: int) -> list[m.TrainableGap]:
    """Convenience wrapper (task §8's "structurally available... by
    Application") — generates against the Application's most recent Fit
    Assessment. A no-op (returns an empty list) when no Fit Assessment
    exists yet."""

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")
    fit_assessments = fa_svc.list_fit_assessments_for_candidate(session, application.candidate_id)
    if not fit_assessments:
        return []
    return generate_trainable_gaps_for_fit_assessment(session, fit_assessments[0].id)


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def get_trainable_gap(session: Session, gap_id: int) -> m.TrainableGap | None:
    return session.get(m.TrainableGap, gap_id)


def list_trainable_gaps_for_application(
    session: Session, application_id: int, *, active_only: bool = True,
) -> list[m.TrainableGap]:
    stmt = select(m.TrainableGap).where(m.TrainableGap.application_id == application_id)
    if active_only:
        stmt = stmt.where(m.TrainableGap.status == tgm.ACTIVE)
    stmt = stmt.order_by(m.TrainableGap.id)
    return list(session.scalars(stmt).all())


def list_non_trainable_concerns_for_application(session: Session, application_id: int) -> list[dict]:
    """Task §6/§13 — important gaps whose Requirement trainability is
    NOT_TRAINABLE, shown separately from Trainable Gaps (never persisted as
    a `TrainableGap` row — the same "derived, on-the-fly" treatment
    `decision_service.py` already gives Trainable Gaps themselves before
    this task, kept here for the deliberately-excluded NOT_TRAINABLE case,
    which must never become a persisted Trainable Gap)."""

    application = session.get(m.Application, application_id)
    if application is None:
        return []
    fit_assessments = fa_svc.list_fit_assessments_for_candidate(session, application.candidate_id)
    if not fit_assessments:
        return []

    concerns = []
    for ra in fa_svc.list_requirement_assessments(session, fit_assessments[0].id):
        item = ra.requirement_snapshot_item
        if tgm.is_non_trainable_concern(effective_status=ra.effective_status, trainability=item.trainability):
            concerns.append({
                "requirement_name": item.name, "criticality": item.criticality,
                "status": ra.effective_status, "notes": ra.notes, "requirement_assessment_id": ra.id,
            })
    return concerns


# ---------------------------------------------------------------------------
# Selezionatore review (task §5) — the one write path for a human's own
# initial-level judgment. Mirrors `primary_screening_service.
# override_hard_disqualifier`'s mandatory-reason enforcement (strict
# ValueError on a blank reason) combined with `outcome_service.
# apply_outcome`'s change-detection semantics (a reason is required only
# when the value actually differs from what is already recorded).
# ---------------------------------------------------------------------------

def set_selezionatore_level(
    session: Session, gap_id: int, *, level: int, reason: str | None = None, performed_by: str | None = None,
) -> m.TrainableGap:
    """Records the Selezionatore's own initial-level judgment. `rf_one_
    initial_level` is NEVER modified here — only read for comparison. When
    `level` equals RF-One's proposed level, this is treated as agreement
    (task §5): no duplicate manual value is stored
    (`selezionatore_initial_level` stays `None`), `origin` becomes
    HUMAN_CONFIRMED, and no reason is required — any prior override is
    cleared since the Selezionatore is no longer diverging from RF-One.
    When `level` differs, a non-empty `reason` is mandatory;
    `selezionatore_initial_level`, `origin=HUMAN_OVERRIDDEN`,
    `override_reason` and `overridden_at` are then set, and
    `effective_initial_level` becomes the Selezionatore's level (task §5:
    "The effective level becomes the Selezionatore level")."""

    tgm.validate_initial_level(level)
    gap = session.get(m.TrainableGap, gap_id)
    if gap is None:
        raise ValueError(f"No TrainableGap with id {gap_id}")

    if level == gap.rf_one_initial_level:
        gap.selezionatore_initial_level = None
        gap.effective_initial_level = gap.rf_one_initial_level
        gap.origin = fam.HUMAN_CONFIRMED
        gap.override_reason = None
        gap.overridden_at = None
        gap.overridden_by = performed_by
    else:
        if not reason or not reason.strip():
            raise ValueError(
                "A reason is mandatory when the Selezionatore's initial level differs from RF-One's proposed level."
            )
        gap.selezionatore_initial_level = level
        gap.effective_initial_level = level
        gap.origin = fam.HUMAN_OVERRIDDEN
        gap.override_reason = reason
        gap.overridden_at = datetime.utcnow()
        gap.overridden_by = performed_by

    session.flush()
    return gap


def add_note(session: Session, gap_id: int, note_text: str) -> m.ApplicationNote:
    """Appends a note through the unified Application Notes mechanism
    (task §22 — "Do not create one new notes table per section"), tagged so
    `selection_notes_service.get_selection_notes_history` can attribute it
    back to this specific Trainable Gap."""

    gap = session.get(m.TrainableGap, gap_id)
    if gap is None:
        raise ValueError(f"No TrainableGap with id {gap_id}")
    return app_svc.add_note(
        session, gap.application_id, note_text, context_type=NOTE_CONTEXT_TRAINABLE_GAP, context_id=gap.id,
    )
