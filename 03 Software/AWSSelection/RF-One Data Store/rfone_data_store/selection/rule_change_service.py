"""Selection Session Rule Change — service layer (Task 5C §16-§21). A
legitimate way for Selection rules to evolve DURING an ACTIVE Session,
without ever silently rewriting prior results or prior human decisions.

Every Rule Change creates exactly one new `SelectionRuleSetVersion` (via
`rule_set_service.build_rule_set_version`) and one `SelectionRuleChange`
event row recording why and under what scope. For `ENTIRE_SESSION` scope,
already-processed Applications are identified and, where a safe
deterministic component exists, refreshed — never silently decided for.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import fit_assessment_service as fa_svc
from . import rule_set_service as rs_svc
from .core import rule_set_model as rsm


def propose_rule_change(
    session: Session, session_id: int, *, rules_changed_summary: str, reason: str, scope: str,
    acting_identity_id: int | None = None, performed_by: str | None = None, requirement_set_id: int | None = None,
    primary_screening_criterion_ids: list[int] | None = None, signal_definition_ids: list[int] | None = None,
    review_priority_policy_id: int | None = None, outcome_definition_ids: list[int] | None = None,
    phone_interview_question_definition_ids: list[int] | None = None,
    in_person_interview_section_definition_ids: list[int] | None = None,
) -> m.SelectionRuleChange:
    """Task §16/§17 — a Rule Change is only legitimate during an ACTIVE
    Session, always carries a reason (task §21/checks U), and always
    carries an explicit scope (task §17/§20 — never silently chosen).
    Fields not passed default to CARRYING FORWARD the previous version's
    own references unchanged — a Rule Change normally touches one or two
    things, not the whole envelope; pass an explicit (possibly empty) value
    only for what actually changed.

    GLOBAL_INTEGRITY_FIX_002 / C-1/I-4: `acting_identity_id`, when given, is
    the authoritative actor reference — `performed_by` is then DERIVED from
    it (a caller-supplied `performed_by` is ignored in that case) and any
    restaurant-configured governance requirement for proposing a Rule
    Change is enforced. `performed_by` alone (no identity) remains accepted
    as plain descriptive text for callers that have no Acting Identity to
    resolve (e.g. a system-triggered or historical-equivalent call) — Rule
    Change proposals are gated by the Session being ACTIVE, not by a
    per-actor ownership check, so this is not the load-bearing C-1 path
    `ownership_service`/`rule_set_service` are."""

    if not rules_changed_summary or not rules_changed_summary.strip():
        raise ValueError("A Rule Change requires a summary of what rule(s) changed.")
    if not reason or not reason.strip():
        raise ValueError("A Rule Change requires a reason.")
    rsm.validate_rule_change_scope(scope)

    identity = None
    if acting_identity_id is not None:
        identity = session.get(m.ActingIdentity, acting_identity_id)
        if identity is None or not identity.is_active:
            raise ValueError("Proposing a Rule Change requires a valid, active Acting Identity.")
        performed_by = identity.display_name

    selection_session = session.get(m.SelectionSession, session_id)
    if selection_session is None:
        raise ValueError(f"No SelectionSession with id {session_id}")
    if selection_session.status != "ACTIVE":
        raise ValueError("A Rule Change can only be proposed for an ACTIVE Session.")

    if identity is not None:
        from . import authority_service as auth_svc

        auth_svc.check_authority_for_action(
            session, restaurant_id=selection_session.restaurant_id, action_type=auth_svc.ACTION_PROPOSE_RULE_CHANGE,
            identity_id=identity.id, session_id=session_id,
        )

    previous_version_id = selection_session.current_rule_set_version_id
    previous_version = session.get(m.SelectionRuleSetVersion, previous_version_id) if previous_version_id else None

    def _carry(value, fallback):
        return value if value is not None else fallback

    if primary_screening_criterion_ids is None and previous_version is not None:
        criterion_ids = []
        for snapshot_id in previous_version.primary_screening_criterion_snapshot_ids:
            snapshot = session.get(m.PrimaryScreeningCriterionSnapshot, snapshot_id)
            if snapshot is not None:
                criterion_ids.append(snapshot.criterion_id)
    else:
        criterion_ids = primary_screening_criterion_ids or []

    new_version = rs_svc.build_rule_set_version(
        session, session_id,
        requirement_set_id=_carry(requirement_set_id, previous_version.requirement_set_id if previous_version else None),
        primary_screening_criterion_ids=criterion_ids,
        signal_definition_ids=_carry(signal_definition_ids, list(previous_version.signal_definition_ids) if previous_version else []),
        review_priority_policy_id=_carry(review_priority_policy_id, previous_version.review_priority_policy_id if previous_version else None),
        outcome_definition_ids=_carry(outcome_definition_ids, list(previous_version.outcome_definition_ids) if previous_version else []),
        phone_interview_question_definition_ids=_carry(
            phone_interview_question_definition_ids,
            list(previous_version.phone_interview_question_definition_ids) if previous_version else [],
        ),
        in_person_interview_section_definition_ids=_carry(
            in_person_interview_section_definition_ids,
            list(previous_version.in_person_interview_section_definition_ids) if previous_version else [],
        ),
        change_summary=rules_changed_summary, created_by=performed_by, created_from_version_id=previous_version_id,
    )

    rule_change = m.SelectionRuleChange(
        session_id=session_id, previous_version_id=previous_version_id, new_version_id=new_version.id,
        rules_changed_summary=rules_changed_summary, reason=reason, scope=scope, performed_by=performed_by,
        performed_by_identity_id=identity.id if identity is not None else None,
    )
    session.add(rule_change)
    session.flush()

    if scope == rsm.ENTIRE_SESSION:
        _create_impacts_and_recalculate(session, rule_change, new_version)

    from . import session_service as sess_svc
    sess_svc.add_session_note(
        session, session_id,
        f"Rule Change ({scope}): {rules_changed_summary} — {reason}",
        context_type=sess_svc.NOTE_CONTEXT_RULE_CHANGE, context_id=rule_change.id,
    )

    session.flush()
    return rule_change


def _create_impacts_and_recalculate(
    session: Session, rule_change: m.SelectionRuleChange, new_version: m.SelectionRuleSetVersion,
) -> None:
    """Task §19/§20/§21 — every Application already linked to this Session
    under an OLDER Rule Set version is identified as impacted. Where a
    safe, deterministic component exists (an already-generated résumé-
    stage Fit Assessment — `fit_assessment_service.
    generate_resume_stage_assessment` is idempotent and, by its own
    existing design, NEVER overwrites a human-touched `effective_status`),
    it is refreshed. Nothing here ever sets an Outcome, Stage, or
    Trainable Gap level — `review_status` always starts NEEDS_REVIEW so a
    human decides what (if anything) the impact means."""

    stmt = select(m.Application).where(
        m.Application.session_id == rule_change.session_id,
        m.Application.rule_set_version_id.is_not(None),
        m.Application.rule_set_version_id != new_version.id,
    )
    impacted_applications = list(session.scalars(stmt).all())

    for application in impacted_applications:
        impact = m.SelectionRuleChangeImpact(
            rule_change_id=rule_change.id, application_id=application.id,
            recalculation_status=rsm.RECALC_PENDING, review_status=rsm.REVIEW_NEEDS_REVIEW,
        )
        session.add(impact)
        session.flush()

        fit_assessments = fa_svc.list_fit_assessments_for_candidate(session, application.candidate_id)
        if not fit_assessments:
            impact.recalculation_status = rsm.RECALC_NOT_APPLICABLE
            impact.notes = "No Fit Assessment exists yet for this Application — nothing to recalculate."
            session.flush()
            continue
        try:
            fa_svc.generate_resume_stage_assessment(session, fit_assessments[0].id)
            impact.recalculation_status = rsm.RECALC_RECALCULATED
            impact.recalculated_at = datetime.utcnow()
            impact.notes = (
                "Résumé-stage evidence refreshed against the new Rule Set version. Any human-confirmed/"
                "overridden assessment was left untouched. Selezionatore review still required."
            )
        except Exception as exc:  # pragma: no cover - defensive; never silently swallowed
            impact.recalculation_status = rsm.RECALC_FAILED
            impact.notes = f"Automatic recalculation failed: {exc}"
        session.flush()


def list_rule_changes_for_session(session: Session, session_id: int) -> list[m.SelectionRuleChange]:
    stmt = (
        select(m.SelectionRuleChange)
        .where(m.SelectionRuleChange.session_id == session_id)
        .order_by(m.SelectionRuleChange.id)
    )
    return list(session.scalars(stmt).all())


def list_impacts_for_rule_change(session: Session, rule_change_id: int) -> list[m.SelectionRuleChangeImpact]:
    stmt = (
        select(m.SelectionRuleChangeImpact)
        .where(m.SelectionRuleChangeImpact.rule_change_id == rule_change_id)
        .order_by(m.SelectionRuleChangeImpact.id)
    )
    return list(session.scalars(stmt).all())


def list_impacts_needing_review_for_session(session: Session, session_id: int) -> list[m.SelectionRuleChangeImpact]:
    stmt = (
        select(m.SelectionRuleChangeImpact)
        .join(m.SelectionRuleChange, m.SelectionRuleChangeImpact.rule_change_id == m.SelectionRuleChange.id)
        .where(
            m.SelectionRuleChange.session_id == session_id,
            m.SelectionRuleChangeImpact.review_status == rsm.REVIEW_NEEDS_REVIEW,
        )
        .order_by(m.SelectionRuleChangeImpact.id)
    )
    return list(session.scalars(stmt).all())


def list_impacts_for_application(session: Session, application_id: int) -> list[m.SelectionRuleChangeImpact]:
    stmt = (
        select(m.SelectionRuleChangeImpact)
        .where(m.SelectionRuleChangeImpact.application_id == application_id)
        .order_by(m.SelectionRuleChangeImpact.id)
    )
    return list(session.scalars(stmt).all())


def mark_impact_reviewed(
    session: Session, impact_id: int, *, note: str | None = None,
) -> m.SelectionRuleChangeImpact:
    """Task §20 — the ONLY way an impacted Application's `review_status`
    ever advances: an explicit Selezionatore action. Never automatic."""

    impact = session.get(m.SelectionRuleChangeImpact, impact_id)
    if impact is None:
        raise ValueError(f"No SelectionRuleChangeImpact with id {impact_id}")
    impact.review_status = rsm.REVIEW_REVIEWED
    if note:
        impact.notes = f"{impact.notes or ''}\nReview note: {note}".strip()
    session.flush()
    return impact
