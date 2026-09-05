"""Selection Session Rule Set — service layer (Task 5C §11-§15/§23-§24).
Builds and confirms the versioned configuration envelope a Session/role
operates under. Never duplicates Requirement/Primary Screening/Signal/
Outcome/Interview-question DATA — it references existing immutable
snapshots (captured fresh at build time via `requirements_service`/
`primary_screening_service`, the same mechanisms Task 3A-FIX/3D already
established) or, where no snapshot mechanism exists yet, the live
configuration row ids directly (see `models.SelectionRuleSetVersion`'s own
docstring for exactly which fields are which).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from . import requirements_service as req_svc
from . import primary_screening_service as ps_svc
from . import session_service as sess_svc
from .core import session_model as sesm


def _next_version_number(session: Session, session_id: int) -> int:
    current_max = session.scalar(
        select(func.max(m.SelectionRuleSetVersion.version)).where(
            m.SelectionRuleSetVersion.session_id == session_id
        )
    )
    return (current_max or 0) + 1


def build_rule_set_version(
    session: Session, session_id: int, *, requirement_set_id: int | None = None,
    primary_screening_criterion_ids: list[int] | None = None, signal_definition_ids: list[int] | None = None,
    review_priority_policy_id: int | None = None, outcome_definition_ids: list[int] | None = None,
    phone_interview_question_definition_ids: list[int] | None = None,
    in_person_interview_section_definition_ids: list[int] | None = None, change_summary: str | None = None,
    created_by: str | None = None, created_from_version_id: int | None = None,
) -> m.SelectionRuleSetVersion:
    """Creates ONE new, immutable Rule Set version (task §12) and makes it
    the Session's current version. `requirement_set_id` is captured as a
    fresh `RequirementSetSnapshot` (via `requirements_service`'s own
    idempotent-per-version mechanism) and each
    `primary_screening_criterion_ids` entry as a fresh
    `PrimaryScreeningCriterionSnapshot` — both AT THE MOMENT this version
    is built, so the envelope can never silently drift if the live
    Requirement Set/Criteria are edited afterward."""

    selection_session = session.get(m.SelectionSession, session_id)
    if selection_session is None:
        raise ValueError(f"No SelectionSession with id {session_id}")

    requirement_set_snapshot_id = None
    if requirement_set_id is not None:
        snapshot = req_svc.create_requirement_set_snapshot(session, requirement_set_id)
        requirement_set_snapshot_id = snapshot.id

    criterion_snapshot_ids = []
    for criterion_id in (primary_screening_criterion_ids or []):
        snapshot = ps_svc.get_or_create_criterion_snapshot(session, criterion_id)
        criterion_snapshot_ids.append(snapshot.id)

    version = m.SelectionRuleSetVersion(
        session_id=session_id, version=_next_version_number(session, session_id),
        requirement_set_id=requirement_set_id, requirement_set_snapshot_id=requirement_set_snapshot_id,
        primary_screening_criterion_snapshot_ids=criterion_snapshot_ids,
        signal_definition_ids=list(signal_definition_ids or []),
        review_priority_policy_id=review_priority_policy_id,
        outcome_definition_ids=list(outcome_definition_ids or []),
        phone_interview_question_definition_ids=list(phone_interview_question_definition_ids or []),
        in_person_interview_section_definition_ids=list(in_person_interview_section_definition_ids or []),
        change_summary=change_summary, created_by=created_by, created_from_version_id=created_from_version_id,
    )
    session.add(version)
    session.flush()

    selection_session.current_rule_set_version_id = version.id
    session.flush()
    return version


def create_initial_version(
    session: Session, session_id: int, *, seed_from_version_id: int | None = None, created_by: str | None = None,
) -> m.SelectionRuleSetVersion:
    """Task §23 — version 1 of a Session's Rule Set. When
    `seed_from_version_id` is given (an explicit choice, or
    `session_service.create_session`'s own auto-detected latest prior
    Session for the same restaurant/role), the COMPLETE current
    configuration is carried forward — re-resolved back to live
    Requirement Set / Criterion ids and re-snapshotted fresh, never a
    stale copy of the old snapshot rows themselves. Absent a seed, this is
    an empty envelope the Selezionatore populates during Rule Review
    before confirming."""

    seed = session.get(m.SelectionRuleSetVersion, seed_from_version_id) if seed_from_version_id else None
    if seed is None:
        return build_rule_set_version(session, session_id, created_by=created_by)

    criterion_ids = []
    for snapshot_id in seed.primary_screening_criterion_snapshot_ids:
        snapshot = session.get(m.PrimaryScreeningCriterionSnapshot, snapshot_id)
        if snapshot is not None:
            criterion_ids.append(snapshot.criterion_id)

    return build_rule_set_version(
        session, session_id, requirement_set_id=seed.requirement_set_id,
        primary_screening_criterion_ids=criterion_ids, signal_definition_ids=list(seed.signal_definition_ids),
        review_priority_policy_id=seed.review_priority_policy_id,
        outcome_definition_ids=list(seed.outcome_definition_ids),
        phone_interview_question_definition_ids=list(seed.phone_interview_question_definition_ids),
        in_person_interview_section_definition_ids=list(seed.in_person_interview_section_definition_ids),
        change_summary="Carried forward from a prior Session's complete Rule Set.",
        created_by=created_by, created_from_version_id=seed_from_version_id,
    )


def get_version(session: Session, version_id: int) -> m.SelectionRuleSetVersion | None:
    return session.get(m.SelectionRuleSetVersion, version_id)


def list_versions_for_session(session: Session, session_id: int) -> list[m.SelectionRuleSetVersion]:
    stmt = (
        select(m.SelectionRuleSetVersion)
        .where(m.SelectionRuleSetVersion.session_id == session_id)
        .order_by(m.SelectionRuleSetVersion.version)
    )
    return list(session.scalars(stmt).all())


def confirm_rule_set_version(
    session: Session, session_id: int, *, confirmed_by: str, note: str | None = None, version_id: int | None = None,
) -> m.SelectionRuleSetVersion:
    """Task §13/§15 — explicit, mandatory confirmation of the Session's
    CURRENT Rule Set version. Never personal to a Selezionatore (task §14):
    one confirmation applies to the whole Session. Activates the Session as
    a side effect (task §13's own SESSION CREATED -> RULES REVIEW ->
    EXPLICIT CONFIRMATION -> ACTIVE flow) — mirrors
    `outcome_service.apply_outcome` setting `lifecycle_state` as a
    documented side effect of its own governed action."""

    if not confirmed_by or not confirmed_by.strip():
        raise ValueError("Confirming a Rule Set requires identifying who confirmed it.")

    selection_session = session.get(m.SelectionSession, session_id)
    if selection_session is None:
        raise ValueError(f"No SelectionSession with id {session_id}")

    target_version_id = version_id or selection_session.current_rule_set_version_id
    if target_version_id is None:
        raise ValueError("This Session has no Rule Set version to confirm yet.")
    version = session.get(m.SelectionRuleSetVersion, target_version_id)
    if version is None:
        raise ValueError(f"No SelectionRuleSetVersion with id {target_version_id}")
    if target_version_id != selection_session.current_rule_set_version_id:
        raise ValueError("Only the Session's CURRENT Rule Set version may be confirmed.")
    if version.confirmed_at is not None:
        raise ValueError(
            f"Rule Set version {version.version} was already confirmed by {version.confirmed_by} on "
            f"{version.confirmed_at}. Propose a Rule Change to create a new version if something must change."
        )

    version.confirmed_by = confirmed_by
    version.confirmed_at = datetime.utcnow()
    version.confirmation_note = note
    selection_session.status = sesm.ACTIVE
    session.flush()

    sess_svc.add_session_note(
        session, session_id,
        f"Rule Set version {version.version} confirmed by {confirmed_by}." + (f" {note}" if note else ""),
        context_type=sess_svc.NOTE_CONTEXT_RULE_SET_CONFIRMATION, context_id=version.id,
    )
    return version


def get_rule_set_summary(session: Session, version_id: int) -> dict:
    """Task §29 — everything a Rule Review screen needs in one coherent
    place: Requirements, Screening Criteria (coefficients/directions/level
    definitions/Hard Disqualifiers), Signals, and the other referenced
    configuration — resolved from the version's stored references, never
    recomputed or duplicated."""

    version = session.get(m.SelectionRuleSetVersion, version_id)
    if version is None:
        raise ValueError(f"No SelectionRuleSetVersion with id {version_id}")

    requirement_items = []
    if version.requirement_set_snapshot_id is not None:
        snapshot = session.get(m.RequirementSetSnapshot, version.requirement_set_snapshot_id)
        if snapshot is not None:
            requirement_items = sorted(snapshot.items, key=lambda i: i.display_order)

    criteria = [
        session.get(m.PrimaryScreeningCriterionSnapshot, sid)
        for sid in version.primary_screening_criterion_snapshot_ids
    ]
    criteria = [c for c in criteria if c is not None]

    signals = [session.get(m.SignalDefinition, sid) for sid in version.signal_definition_ids]
    signals = [s for s in signals if s is not None]

    outcomes = [session.get(m.SelectionOutcomeDefinition, oid) for oid in version.outcome_definition_ids]
    outcomes = [o for o in outcomes if o is not None]

    phone_questions = [
        session.get(m.PhoneInterviewQuestionDefinition, qid)
        for qid in version.phone_interview_question_definition_ids
    ]
    phone_questions = [q for q in phone_questions if q is not None]

    in_person_sections = [
        session.get(m.InPersonInterviewSectionDefinition, sid)
        for sid in version.in_person_interview_section_definition_ids
    ]
    in_person_sections = [s for s in in_person_sections if s is not None]

    return {
        "version": version,
        "requirement_set": session.get(m.RequirementSet, version.requirement_set_id) if version.requirement_set_id else None,
        "requirement_items": requirement_items,
        "criteria": criteria,
        "signals": signals,
        "review_priority_policy": session.get(m.ReviewPriorityPolicy, version.review_priority_policy_id) if version.review_priority_policy_id else None,
        "outcomes": outcomes,
        "phone_questions": phone_questions,
        "in_person_sections": in_person_sections,
    }
