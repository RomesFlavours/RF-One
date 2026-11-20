"""Selection Decision Summary (Task 5A §23/§24) — the consolidated,
CURRENT-STATE view of an Application, usable at any moment; never a
mandatory "final phase." Aggregates data already computed by existing
Selection services (Fit Assessment, Primary Screening, Signals, Candidate
Flags, Stage/Outcome history) — invents nothing new, computes no numeric
score, and never states or implies a hiring recommendation (task §24/§25:
"Do not say 'RF-One recommends hiring.'").
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from .. import models as m
from . import application_service as app_svc
from . import candidate_flag_service as flag_svc
from . import fit_assessment_service as fa_svc
from . import outcome_service as outcome_svc
from . import primary_screening_service as ps_svc
from . import queue_service as queue_svc
from . import signal_service as sig_svc
from . import stage_service as stage_svc
from .core import fit_assessment_model as fam
from .core import requirement_model as rm
from .core import signal_model as sm


@dataclass
class DecisionSummary:
    application: m.Application
    current_stage: str
    lifecycle_state: str
    current_outcome_decision: m.SelectionOutcomeDecision | None
    outcome_history: list[m.SelectionOutcomeDecision]
    stage_history: list[m.ApplicationStageTransition]
    current_queue: m.SelectionQueue | None
    queue_history: list[m.ApplicationQueueMovement]
    primary_screening_run: m.PrimaryScreeningRun | None
    active_hard_disqualifiers: list[m.PrimaryScreeningCriterionEvaluation]
    strongest_evidence: list[dict] = field(default_factory=list)
    weaker_evidence: list[dict] = field(default_factory=list)
    conflicting_evidence: list[dict] = field(default_factory=list)
    unresolved_evidence: list[dict] = field(default_factory=list)
    trainable_gaps: list[dict] = field(default_factory=list)
    important_signals: list[m.SignalObservation] = field(default_factory=list)
    active_flags: list[m.CandidateFlag] = field(default_factory=list)
    reminders: list[m.SelectionReminder] = field(default_factory=list)


def _requirement_assessment_breakdown(session: Session, candidate_id: int) -> tuple[list, list, list, list, list]:
    """Splits the most recent Fit Assessment's Requirement Assessments into
    strongest / weaker / conflicting / unresolved / trainable-gap buckets —
    facts only, no scoring."""

    fit_assessments = fa_svc.list_fit_assessments_for_candidate(session, candidate_id)
    if not fit_assessments:
        return [], [], [], [], []

    strongest, weaker, conflicting, unresolved, trainable_gaps = [], [], [], [], []
    for ra in fa_svc.list_requirement_assessments(session, fit_assessments[0].id):
        item = ra.requirement_snapshot_item
        row = {
            "name": item.name, "criticality": item.criticality, "status": ra.effective_status,
            "rationale": ra.notes, "evidence_count": len(ra.evidence_items),
        }
        if ra.effective_status == fam.EVIDENCED:
            strongest.append(row)
        elif ra.effective_status == fam.PARTIALLY_EVIDENCED:
            weaker.append(row)
        elif ra.effective_status == fam.CONFLICTING_EVIDENCE:
            conflicting.append(row)
        elif ra.effective_status in (fam.NOT_EVIDENCED, fam.NOT_ASSESSED_AT_THIS_STAGE):
            unresolved.append(row)

        if ra.effective_status in (fam.PARTIALLY_EVIDENCED, fam.NOT_EVIDENCED) and item.trainability in (
            rm.TRAINABLE, rm.PARTIALLY_TRAINABLE,
        ):
            trainable_gaps.append({"name": item.name, "trainability": item.trainability, "status": ra.effective_status})

    return strongest, weaker, conflicting, unresolved, trainable_gaps


def get_decision_summary(session: Session, application_id: int) -> DecisionSummary:
    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")

    run = ps_svc.get_latest_run_for_application(session, application_id)
    active_hard_disqualifiers = []
    if run is not None:
        active_hard_disqualifiers = [
            e for e in ps_svc.list_evaluations(session, run.id)
            if e.is_active_hard_disqualifier and not e.hard_disqualifier_overridden
        ]

    strongest, weaker, conflicting, unresolved, trainable_gaps = _requirement_assessment_breakdown(
        session, application.candidate_id,
    )

    important_signals = [
        o for o in sig_svc.list_observations(session, application_id) if o.status in (sm.DETECTED, sm.POSSIBLE, sm.CONFLICTING)
    ]

    return DecisionSummary(
        application=application, current_stage=application.current_stage,
        lifecycle_state=application.lifecycle_state,
        current_outcome_decision=outcome_svc.get_current_outcome_decision(session, application_id),
        outcome_history=outcome_svc.list_outcome_history(session, application_id),
        stage_history=stage_svc.list_stage_history(session, application_id),
        current_queue=queue_svc.get_current_queue(session, application_id),
        queue_history=queue_svc.list_queue_history(session, application_id),
        primary_screening_run=run, active_hard_disqualifiers=active_hard_disqualifiers,
        strongest_evidence=strongest, weaker_evidence=weaker, conflicting_evidence=conflicting,
        unresolved_evidence=unresolved, trainable_gaps=trainable_gaps, important_signals=important_signals,
        active_flags=flag_svc.list_active_flags_for_application(session, application_id),
        reminders=outcome_svc.list_reminders_for_application(session, application_id, unresolved_only=True),
    )


def generate_current_summary_text(session: Session, application_id: int) -> str:
    """Task §24 — a concise, discursive, evidence-based summary supporting
    HIRE without requiring a separate prose justification. Never a
    recommendation (task §24/§25's own explicit prohibition) — states what
    the evidence shows, never what RF-One thinks should happen."""

    summary = get_decision_summary(session, application_id)
    sentences: list[str] = []

    if summary.strongest_evidence:
        names = ", ".join(r["name"] for r in summary.strongest_evidence[:4])
        sentences.append(f"Strongest evidence: {names}.")
    if summary.weaker_evidence:
        names = ", ".join(r["name"] for r in summary.weaker_evidence[:4])
        sentences.append(f"Weaker/partial evidence: {names}.")
    if summary.conflicting_evidence:
        names = ", ".join(r["name"] for r in summary.conflicting_evidence[:4])
        sentences.append(f"Conflicting evidence on: {names}.")
    if summary.unresolved_evidence:
        names = ", ".join(r["name"] for r in summary.unresolved_evidence[:4])
        sentences.append(f"Not yet evidenced/unresolved: {names}.")
    if summary.trainable_gaps:
        names = ", ".join(f"{g['name']} ({g['trainability'].lower()})" for g in summary.trainable_gaps[:4])
        sentences.append(f"Gaps that appear trainable: {names}.")
    if summary.important_signals:
        names = ", ".join(o.signal_definition.name for o in summary.important_signals[:4])
        sentences.append(f"Notable Selection Signals: {names}.")
    if summary.active_hard_disqualifiers:
        names = ", ".join(e.criterion_snapshot.name for e in summary.active_hard_disqualifiers)
        sentences.append(f"Active, un-overridden Hard Disqualifier(s): {names}.")
    if summary.active_flags:
        names = ", ".join(f.name for f in summary.active_flags)
        sentences.append(f"Active Candidate Flag(s) on record for this person: {names}.")
    if not sentences:
        sentences.append("No Selection evidence has been recorded for this Application yet.")

    return " ".join(sentences)
