"""Selection Audit / Explainability service (Task 5F Part B). A PURE,
READ-ONLY aggregator — reconstructs "why did RF-One and the Selezionatore
treat this Application this way," across its full HISTORY, not merely its
current state. Every field is read directly from an already-existing,
unmodified authoritative service (mirrors `dossier_service.py`'s own
"invents nothing new" discipline, applied here across the Application's
entire lifetime rather than just its present Dossier view) — this module
computes nothing new and never writes anything.

The internal Primary Screening Priority Index is reconstructed here
explicitly (task §14) — this is the ONE place in Selection that is allowed
to surface it, because this is an explicit Audit/Explainability context for
authorized review, never the ordinary Selezionatore operational UI (which
must keep hiding it, unchanged).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from .. import models as m
from . import application_question_service as aq_svc
from . import application_service as app_svc
from . import candidate_flag_service as flag_svc
from . import communication_service as comm_svc
from . import compliance_service as compliance_svc
from . import decision_service as dec_svc
from . import in_person_interview_service as ip_svc
from . import inbound_communication_service as inbound_svc
from . import missing_evidence_service as me_svc
from . import outcome_service as outcome_svc
from . import ownership_service as own_svc
from . import phone_interview_service as pi_svc
from . import primary_screening_service as ps_svc
from . import queue_service as queue_svc
from . import rule_change_service as rc_svc
from . import rule_set_service as rs_svc
from . import scheduling_service as sched_svc
from . import selection_notes_service as notes_svc
from . import stage_service as stage_svc
from . import trainable_gap_service as tg_svc
from .core import compliance_model as cpm
from .core import stage_model as stgm

AUDIT_DISCLAIMER = (
    "This Audit reconstructs the historical record exactly as it happened — it does not re-evaluate the "
    "candidate or apply today's configuration to a past moment. " + cpm.DISCLAIMER
)


@dataclass
class ScreeningEvaluationRow:
    """Task §14 — one row of the internal Priority Index reconstruction:
    Criterion, its CONFIGURED coefficient/direction (from the exact
    snapshot pinned at the time), the candidate's evaluation level, the
    resulting signed contribution, and the evidence behind it. Never shown
    outside this Audit context."""

    criterion_name: str
    rule_version: int
    coefficient: float
    direction: str
    status: str
    effective_level: int | None
    contribution: float
    evidence_source: str | None
    evidence_items: list
    confidence: str | None
    origin: str
    is_active_hard_disqualifier: bool
    hard_disqualifier_overridden: bool
    hard_disqualifier_override_reason: str | None


@dataclass
class ScreeningRunAudit:
    run: m.PrimaryScreeningRun
    resulting_priority_index: float
    has_active_hard_disqualifier: bool
    rows: list[ScreeningEvaluationRow]


@dataclass
class RuleChangeAuditEntry:
    rule_change: m.SelectionRuleChange
    impact_on_this_application: m.SelectionRuleChangeImpact | None


@dataclass
class CriterionComplianceContext:
    criterion_name: str
    review: m.ComplianceReview
    warnings: list[m.ComplianceWarning]
    latest_disposition: m.ComplianceDisposition | None


@dataclass
class TimelineEntry:
    at: datetime | None
    kind: str
    description: str


@dataclass
class AuditReport:
    disclaimer: str
    application: m.Application
    person: m.CandidatePerson
    # A. Application Context
    selection_session: m.SelectionSession | None
    current_owner: m.ApplicationOwnership | None
    # B. Acquisition
    acquisition_source: m.AcquisitionSourceDefinition | None
    channel_publication: m.ChannelPublication | None
    # C. Applicable Rules
    rule_set_version: m.SelectionRuleSetVersion | None
    rule_set_summary: dict | None
    # D/E. Primary Screening + internal Priority Index + Evidence
    screening_runs: list[ScreeningRunAudit]
    application_answers: list[m.ApplicationQuestionAnswer]
    missing_evidence_questionnaires: list[m.MissingEvidenceQuestionnaire]
    decision_summary: "dec_svc.DecisionSummary"
    # F. Interviews / Practical
    phone_plan: m.PhoneInterviewPlan | None
    in_person_plan: m.InPersonInterviewPlan | None
    # G. Consistency
    consistency_threads: list[m.ConsistencyThread]
    # H. Trainable Gaps
    trainable_gaps: list[m.TrainableGap]
    non_trainable_concerns: list[dict]
    # I. Decisions / Outcomes
    outcome_history: list[m.SelectionOutcomeDecision]
    stage_history: list[m.ApplicationStageTransition]
    queue_history: list[m.ApplicationQueueMovement]
    # J. Events / Communication (kept explicitly distinct — task §18)
    information_events: list
    outbound_communications: list[m.CandidateCommunication]
    inbound_communications: list[m.InboundCommunication]
    scheduling_history: list[m.InterviewAppointment]
    # K. Rule / Ownership changes
    ownership_history: list[m.ApplicationOwnership]
    rule_changes: list[RuleChangeAuditEntry]
    # L. Compliance context
    compliance_context: list[CriterionComplianceContext]
    # Repeated-applicant / candidate history
    prior_applications: list[m.Application]
    change_summary: object
    training_check_flags: list[m.CandidateFlag]
    candidate_flags: list[m.CandidateFlag]
    # M. Notes (reused, not duplicated)
    notes_history: list
    # N. Timeline
    timeline: list[TimelineEntry] = field(default_factory=list)


def _screening_run_audit(session: Session, run: m.PrimaryScreeningRun) -> ScreeningRunAudit:
    rows = []
    for evaluation in ps_svc.list_evaluations(session, run.id):
        snapshot = evaluation.criterion_snapshot
        rows.append(ScreeningEvaluationRow(
            criterion_name=snapshot.name, rule_version=snapshot.version, coefficient=snapshot.coefficient,
            direction=snapshot.direction, status=evaluation.status, effective_level=evaluation.effective_level,
            contribution=evaluation.contribution, evidence_source=evaluation.evidence_source,
            evidence_items=evaluation.evidence_items, confidence=evaluation.confidence, origin=evaluation.origin,
            is_active_hard_disqualifier=evaluation.is_active_hard_disqualifier,
            hard_disqualifier_overridden=evaluation.hard_disqualifier_overridden,
            hard_disqualifier_override_reason=evaluation.hard_disqualifier_override_reason,
        ))
    return ScreeningRunAudit(
        run=run, resulting_priority_index=run.priority_index, has_active_hard_disqualifier=run.has_active_hard_disqualifier,
        rows=rows,
    )


def _compliance_context(session: Session, screening_runs: list[ScreeningRunAudit]) -> list[CriterionComplianceContext]:
    """Task §13's "Compliance warnings affecting applicable rules" — for
    every Criterion actually used in any of this Application's Primary
    Screening Runs, surface its latest Compliance Review (if any exists and
    carries warnings). Criterion identity is re-derived through the Run's
    own pinned snapshot, never through the (unstable) display name alone."""

    contexts: list[CriterionComplianceContext] = []
    for run_audit in screening_runs:
        for evaluation in ps_svc.list_evaluations(session, run_audit.run.id):
            criterion_id = evaluation.criterion_snapshot.criterion_id
            review = compliance_svc.get_latest_review(session, cpm.PRIMARY_SCREENING_CRITERION, criterion_id)
            if review is None or not review.warnings:
                continue
            if any(c.review.id == review.id for c in contexts):
                continue
            dispositions = compliance_svc.list_dispositions(session, review.id)
            contexts.append(CriterionComplianceContext(
                criterion_name=evaluation.criterion_snapshot.name, review=review, warnings=list(review.warnings),
                latest_disposition=dispositions[-1] if dispositions else None,
            ))
    return contexts


def _build_timeline(report: AuditReport) -> list[TimelineEntry]:
    entries: list[TimelineEntry] = []
    entries.append(TimelineEntry(report.application.applied_at, "APPLICATION", "Application submitted."))
    for t in report.stage_history:
        entries.append(TimelineEntry(t.created_at, "STAGE", f"Stage -> {t.new_stage}" + (f" (by {t.performed_by})" if t.performed_by else "")))
    for d in report.outcome_history:
        label = "Reopen" if d.is_reopen_event else "Outcome"
        entries.append(TimelineEntry(d.created_at, "OUTCOME", f"{label}: {d.outcome_definition_snapshot.name}" + (f" — {d.reason}" if d.reason else "")))
    for q in report.queue_history:
        entries.append(TimelineEntry(q.created_at, "QUEUE", f"Queue -> {q.new_queue.name if q.new_queue else '(none)'} ({q.source})"))
    for c in report.outbound_communications:
        entries.append(TimelineEntry(c.created_at, "COMMUNICATION_OUT", f"Sent: {c.trigger_event}" + (" [reminder]" if c.is_reminder else "")))
    for i in report.inbound_communications:
        entries.append(TimelineEntry(i.received_at, "COMMUNICATION_IN", f"Received ({i.channel}): classified {i.classification_effective}"))
    for a in report.scheduling_history:
        entries.append(TimelineEntry(a.candidate_selected_at, "APPOINTMENT", f"{a.interview_stage} appointment {a.status} for {a.slot_start_at}"))
    for o in report.ownership_history:
        entries.append(TimelineEntry(o.started_at, "OWNERSHIP", f"Owner -> {o.owner_name}" + (f" ({o.reason})" if o.reason else "")))
    for entry in report.information_events:
        entries.append(TimelineEntry(entry.created_at, "EVENT", entry.note_text))
    for questionnaire in report.missing_evidence_questionnaires:
        entries.append(TimelineEntry(questionnaire.created_at, "MISSING_EVIDENCE", f"Questionnaire {questionnaire.status}"))
        if questionnaire.completed_at:
            entries.append(TimelineEntry(questionnaire.completed_at, "MISSING_EVIDENCE", "Questionnaire answered."))
    entries.sort(key=lambda e: e.at or datetime.min)
    return entries


def build_audit(session: Session, application_id: int) -> AuditReport:
    application = app_svc.get_application(session, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")

    # Idempotent, matches Dossier's own discipline — never overwrites a
    # Selezionatore-set gap level.
    tg_svc.generate_trainable_gaps_for_application(session, application_id)

    selection_session = session.get(m.SelectionSession, application.session_id) if application.session_id else None
    current_owner = own_svc.get_current_owner(session, application_id) if application.session_id else None
    rule_set_version = (
        session.get(m.SelectionRuleSetVersion, application.rule_set_version_id)
        if application.rule_set_version_id else None
    )
    rule_set_summary = rs_svc.get_rule_set_summary(session, rule_set_version.id) if rule_set_version else None

    screening_runs = [_screening_run_audit(session, r) for r in ps_svc.list_runs_for_application(session, application_id)]

    rule_changes = []
    if selection_session is not None:
        impacts = {i.rule_change_id: i for i in rc_svc.list_impacts_for_application(session, application_id)}
        for change in rc_svc.list_rule_changes_for_session(session, selection_session.id):
            rule_changes.append(RuleChangeAuditEntry(rule_change=change, impact_on_this_application=impacts.get(change.id)))

    notes_history = notes_svc.get_selection_notes_history(session, application_id)
    information_events = [n for n in app_svc.list_notes(session, application_id) if n.context_type == "INFORMATION_EVENT"]

    report = AuditReport(
        disclaimer=AUDIT_DISCLAIMER, application=application, person=application.person,
        selection_session=selection_session, current_owner=current_owner,
        acquisition_source=application.acquisition_source, channel_publication=application.channel_publication,
        rule_set_version=rule_set_version, rule_set_summary=rule_set_summary,
        screening_runs=screening_runs, application_answers=aq_svc.list_answers_for_application(session, application_id),
        missing_evidence_questionnaires=me_svc.list_questionnaires_for_application(session, application_id),
        decision_summary=dec_svc.get_decision_summary(session, application_id),
        phone_plan=pi_svc.get_plan_for_application(session, application_id),
        in_person_plan=ip_svc.get_plan_for_application(session, application_id),
        consistency_threads=ip_svc.list_threads_for_application(session, application_id),
        trainable_gaps=tg_svc.list_trainable_gaps_for_application(session, application_id),
        non_trainable_concerns=tg_svc.list_non_trainable_concerns_for_application(session, application_id),
        outcome_history=outcome_svc.list_outcome_history(session, application_id),
        stage_history=stage_svc.list_stage_history(session, application_id),
        queue_history=queue_svc.list_queue_history(session, application_id),
        information_events=information_events,
        outbound_communications=comm_svc.list_communications_for_application(session, application_id),
        inbound_communications=inbound_svc.list_inbound_for_application(session, application_id),
        scheduling_history=sched_svc.list_appointment_history(session, application_id),
        ownership_history=own_svc.list_ownership_history(session, application_id) if application.session_id else [],
        rule_changes=rule_changes,
        compliance_context=[],
        prior_applications=app_svc.list_prior_applications(session, application_id),
        change_summary=app_svc.get_application_change_summary(session, application_id),
        training_check_flags=[f for f in flag_svc.list_flags_for_person(session, application.person_id) if "training check" in (f.name or "").lower()],
        candidate_flags=flag_svc.list_flags_for_person(session, application.person_id),
        notes_history=notes_history,
    )
    report.compliance_context = _compliance_context(session, screening_runs)
    report.timeline = _build_timeline(report)
    return report


def to_json_dict(report: AuditReport) -> dict:
    """Task §21 — a structured export. Deliberately simple/flat (never a
    PDF-rendering effort — task's own "do NOT spend significant scope on
    PDF generation")."""

    def _dt(value):
        return value.isoformat() if isinstance(value, datetime) else None

    return {
        "disclaimer": report.disclaimer,
        "application_id": report.application.id,
        "person_id": report.person.id,
        "person_name": report.person.full_name,
        "session_id": report.selection_session.id if report.selection_session else None,
        "role": report.application.target_role,
        "acquisition_source": report.acquisition_source.name if report.acquisition_source else None,
        "channel_publication_id": report.channel_publication.id if report.channel_publication else None,
        "rule_set_version": report.rule_set_version.version if report.rule_set_version else None,
        "screening_runs": [
            {
                "run_id": ra.run.id, "priority_index": ra.resulting_priority_index,
                "has_active_hard_disqualifier": ra.has_active_hard_disqualifier,
                "evaluations": [
                    {
                        "criterion": row.criterion_name, "rule_version": row.rule_version,
                        "coefficient": row.coefficient, "direction": row.direction, "status": row.status,
                        "effective_level": row.effective_level, "contribution": row.contribution,
                        "evidence_source": row.evidence_source, "confidence": row.confidence, "origin": row.origin,
                        "is_active_hard_disqualifier": row.is_active_hard_disqualifier,
                    }
                    for row in ra.rows
                ],
            }
            for ra in report.screening_runs
        ],
        "outcome_history": [
            {"at": _dt(d.created_at), "outcome": d.outcome_definition_snapshot.name, "reason": d.reason, "is_reopen_event": d.is_reopen_event, "performed_by": d.performed_by}
            for d in report.outcome_history
        ],
        "stage_history": [
            {"at": _dt(t.created_at), "stage": t.new_stage, "performed_by": t.performed_by} for t in report.stage_history
        ],
        "prior_application_count": len(report.prior_applications),
        "compliance_context": [
            {"criterion": c.criterion_name, "warnings": [{"category": w.category, "severity": w.severity, "explanation": w.explanation} for w in c.warnings]}
            for c in report.compliance_context
        ],
        "timeline": [{"at": _dt(t.at), "kind": t.kind, "description": t.description} for t in report.timeline],
    }
