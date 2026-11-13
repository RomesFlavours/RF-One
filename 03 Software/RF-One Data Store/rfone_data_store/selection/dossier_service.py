"""Operational Candidate Dossier (Task 5B; Session/ownership/Rule-Set
context added by Task 5C §27). One Application-centric, fast-to-read
aggregation of everything Selection already knows about an Application —
Primary Screening, Evidence, Trainable Gaps, Interview journey,
Decision/Outcome history, Information/Events, candidate history, Notes,
and (5C) which Selection Session it belongs to, its responsible
Selezionatore, the applicable Rule Set version, and whether it was
affected by a retroactive Rule Change.

This module is a PURE AGGREGATOR (mirrors `decision_service.py`'s own
"invents nothing new, computes no numeric score" discipline): every section
except Trainable Gap generation is read directly from an existing
authoritative service (`decision_service.get_decision_summary`,
`selection_notes_service.get_selection_notes_history`,
`application_service.list_prior_applications`, `candidate_flag_service`,
`phone_interview_service`/`in_person_interview_service`,
`ownership_service`, `rule_change_service`) — never recomputed, never
duplicated here. It never exposes `PrimaryScreeningRun.priority_index` or
any other numeric candidate score (task §23) — `decision_service.
DecisionSummary`, which this module wraps, already carries this
discipline; the Dossier template must keep it. Task 5C is not redesigned
here (task §27's own "Do NOT redesign the Dossier") — only additive
fields are appended.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from .. import models as m
from . import application_question_service as aq_svc
from . import application_service as app_svc
from . import candidate_flag_service as flag_svc
from . import communication_service as comm_svc
from . import decision_service as dec_svc
from . import in_person_interview_service as ip_svc
from . import inbound_communication_service as inbound_svc
from . import missing_evidence_service as me_svc
from . import ownership_service as own_svc
from . import phone_interview_service as pi_svc
from . import primary_screening_service as ps_svc
from . import rule_change_service as rc_svc
from . import scheduling_service as sched_svc
from . import selection_notes_service as notes_svc
from . import trainable_gap_service as tg_svc
from .core import communication_model as cm
from .core import in_person_interview_model as ipm
from .core import job_posting_model as jpm
from .core import phone_interview_model as pim
from .core import primary_screening_model as psm
from .core import stage_model as stgm


@dataclass
class InterviewJourney:
    phone_plan: m.PhoneInterviewPlan | None
    phone_incomplete_count: int
    in_person_plan: m.InPersonInterviewPlan | None
    in_person_incomplete_count: int
    consistency_items_to_verify: list[m.ConsistencyThread] = field(default_factory=list)


@dataclass
class SessionContext:
    """Task 5C §27 — the Dossier's minimal Session/ownership/Rule-Set
    addition. `None` fields throughout mean this Application does not (or
    does not yet) belong to a Selection Session — Task 5C is additive
    governance, not something every Application must have."""

    session: m.SelectionSession | None
    current_owner: m.ApplicationOwnership | None
    ownership_history_count: int
    applicable_rule_set_version: m.SelectionRuleSetVersion | None
    was_affected_by_rule_change: bool
    rule_change_impacts: list[m.SelectionRuleChangeImpact] = field(default_factory=list)


@dataclass
class CommunicationContext:
    """Task 5D §27 — the Dossier's minimal Communication/Scheduling
    addition. A pure read of the existing 5D services; nothing here is
    recomputed or duplicated."""

    latest_communication: m.CandidateCommunication | None
    communication_count: int
    pending_response: m.CandidateCommunication | None
    current_phone_appointment: m.InterviewAppointment | None
    current_in_person_appointment: m.InterviewAppointment | None
    latest_inbound: m.InboundCommunication | None
    open_alerts: list[m.InboundCommunication] = field(default_factory=list)


@dataclass
class IntakeContext:
    """Task 5E §39 — the Dossier's minimal Job-Posting-intake/Missing-
    Evidence addition. A pure read of the existing 5E services; every field
    is `None`/empty when this Application did not arrive through a tracked
    Job Posting publication (most Applications still won't)."""

    acquisition_source: m.AcquisitionSourceDefinition | None
    channel_publication: m.ChannelPublication | None
    question_answers: list[m.ApplicationQuestionAnswer] = field(default_factory=list)
    pending_questionnaire: m.MissingEvidenceQuestionnaire | None = None
    questionnaire_history: list[m.MissingEvidenceQuestionnaire] = field(default_factory=list)
    is_ready_for_phone_review: bool = False


@dataclass
class ApplicationDossier:
    application: m.Application
    decision_summary: "dec_svc.DecisionSummary"
    primary_screening_positive: list[m.PrimaryScreeningCriterionEvaluation]
    primary_screening_negative: list[m.PrimaryScreeningCriterionEvaluation]
    primary_screening_unresolved: list[m.PrimaryScreeningCriterionEvaluation]
    trainable_gaps: list[m.TrainableGap]
    non_trainable_concerns: list[dict]
    interview_journey: InterviewJourney
    prior_applications: list[m.Application]
    training_check_flags: list[m.CandidateFlag]
    notes_history: list
    session_context: SessionContext
    communication_context: CommunicationContext
    intake_context: IntakeContext


def _primary_screening_buckets(
    session: Session, run: m.PrimaryScreeningRun | None,
) -> tuple[list, list, list]:
    """Task §11 — positive/negative factors and unresolved/insufficient
    evidence, grouped by each Criterion's own restaurant-configured
    `direction` — never the numeric `priority_index` (never read here at
    all, let alone returned)."""

    if run is None:
        return [], [], []
    positive, negative, unresolved = [], [], []
    for evaluation in ps_svc.list_evaluations(session, run.id):
        if evaluation.status in (psm.INSUFFICIENT_EVIDENCE, psm.NOT_EVALUATED):
            unresolved.append(evaluation)
        elif evaluation.status == psm.EVALUATED:
            if evaluation.criterion_snapshot.direction == "NEGATIVE":
                negative.append(evaluation)
            else:
                positive.append(evaluation)
    return positive, negative, unresolved


def _training_check_flags(session: Session, application: m.Application) -> list[m.CandidateFlag]:
    """Task §17 — surfaces "TRAINING CHECK NOT PASSED" as historical
    candidate information when present (full history, not only currently-
    active flags — a past Training Check result remains relevant context
    even if the flag itself has since expired), without treating it as
    automatic disqualification (task's own "Do not automatically reject
    based on it."). Reuses the ordinary Candidate Flag mechanism — no
    bespoke flag type exists (see `industry/restaurant_templates.py`'s
    seeded "Training Check Not Passed" Outcome, which creates an ordinary
    `CandidateFlag`)."""

    flags = flag_svc.list_flags_for_person(session, application.person_id)
    return [f for f in flags if "training check" in (f.name or "").lower()]


def _session_context(session: Session, application: m.Application) -> SessionContext:
    """Task §27 — Session, role, responsible Selezionatore, applicable
    Rule Set version, and Rule-Change-impact status, all read from the
    existing 5C services rather than recomputed here."""

    if application.session_id is None:
        return SessionContext(
            session=None, current_owner=None, ownership_history_count=0,
            applicable_rule_set_version=None, was_affected_by_rule_change=False,
        )

    selection_session = session.get(m.SelectionSession, application.session_id)
    current_owner = own_svc.get_current_owner(session, application.id)
    history_count = len(own_svc.list_ownership_history(session, application.id))
    applicable_version = (
        session.get(m.SelectionRuleSetVersion, application.rule_set_version_id)
        if application.rule_set_version_id else None
    )
    impacts = rc_svc.list_impacts_for_application(session, application.id)

    return SessionContext(
        session=selection_session, current_owner=current_owner, ownership_history_count=history_count,
        applicable_rule_set_version=applicable_version, was_affected_by_rule_change=bool(impacts),
        rule_change_impacts=impacts,
    )


def _communication_context(session: Session, application: m.Application) -> CommunicationContext:
    communications = comm_svc.list_communications_for_application(session, application.id)
    inbound = inbound_svc.list_inbound_for_application(session, application.id)
    pending = next(
        (c for c in reversed(communications) if c.awaiting_response and c.response_received_at is None), None,
    )
    return CommunicationContext(
        latest_communication=communications[-1] if communications else None,
        communication_count=len(communications),
        pending_response=pending,
        current_phone_appointment=sched_svc.get_current_appointment(
            session, application.id, interview_stage=stgm.PHONE_INTERVIEW,
        ),
        current_in_person_appointment=sched_svc.get_current_appointment(
            session, application.id, interview_stage=stgm.IN_PERSON_PRACTICAL,
        ),
        latest_inbound=inbound[-1] if inbound else None,
        open_alerts=[i for i in inbound if i.alert_required and i.alert_acknowledged_at is None],
    )


def _intake_context(session: Session, application: m.Application) -> IntakeContext:
    from sqlalchemy import select
    stmt = (
        select(m.MissingEvidenceQuestionnaire)
        .where(m.MissingEvidenceQuestionnaire.application_id == application.id)
        .order_by(m.MissingEvidenceQuestionnaire.id)
    )
    history = list(session.scalars(stmt).all())
    pending = next((q for q in history if q.status == jpm.QUESTIONNAIRE_PENDING), None)
    return IntakeContext(
        acquisition_source=application.acquisition_source, channel_publication=application.channel_publication,
        question_answers=aq_svc.list_answers_for_application(session, application.id),
        pending_questionnaire=pending, questionnaire_history=history,
        is_ready_for_phone_review=me_svc.is_ready_for_phone_review(session, application.id),
    )


def get_application_dossier(session: Session, application_id: int) -> ApplicationDossier:
    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")

    # Idempotent (task §1/§8) — only creates Trainable Gaps not already
    # recorded, and only withdraws ones no longer evidenced; never
    # overwrites an existing gap's RF-One or Selezionatore level.
    tg_svc.generate_trainable_gaps_for_application(session, application_id)

    summary = dec_svc.get_decision_summary(session, application_id)

    phone_plan = pi_svc.get_plan_for_application(session, application_id)
    phone_incomplete = 0
    if phone_plan is not None:
        phone_incomplete = sum(
            1 for q in phone_plan.question_instances if q.status in pim.CARRY_FORWARD_ELIGIBLE_STATUSES
        )

    in_person_plan = ip_svc.get_plan_for_application(session, application_id)
    in_person_incomplete = 0
    if in_person_plan is not None:
        in_person_incomplete = sum(
            1 for i in in_person_plan.item_instances if i.status in ipm.INCOMPLETE_ITEM_STATUSES
        )
    consistency_items_to_verify = [
        t for t in ip_svc.list_threads_for_application(session, application_id)
        if t.comparison_status in ipm.CONSISTENCY_ITEMS_TO_VERIFY_STATUSES
    ]

    ps_positive, ps_negative, ps_unresolved = _primary_screening_buckets(session, summary.primary_screening_run)

    return ApplicationDossier(
        application=application,
        decision_summary=summary,
        primary_screening_positive=ps_positive, primary_screening_negative=ps_negative,
        primary_screening_unresolved=ps_unresolved,
        trainable_gaps=tg_svc.list_trainable_gaps_for_application(session, application_id),
        non_trainable_concerns=tg_svc.list_non_trainable_concerns_for_application(session, application_id),
        interview_journey=InterviewJourney(
            phone_plan=phone_plan, phone_incomplete_count=phone_incomplete,
            in_person_plan=in_person_plan, in_person_incomplete_count=in_person_incomplete,
            consistency_items_to_verify=consistency_items_to_verify,
        ),
        prior_applications=app_svc.list_prior_applications(session, application_id),
        training_check_flags=_training_check_flags(session, application),
        notes_history=notes_svc.get_selection_notes_history(session, application_id),
        session_context=_session_context(session, application),
        communication_context=_communication_context(session, application),
        intake_context=_intake_context(session, application),
    )
