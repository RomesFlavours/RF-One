"""Selection Feedback Intelligence — Stage Pattern Snapshot / Delta,
Learning Trace, Selection Effort, Case Memory, Downstream Outcome Feedback
service (Selection Feedback Intelligence Foundation task).

THE PAST IS IMMUTABLE. Nothing in this module ever UPDATEs or DELETEs a
`SelectionStagePatternSnapshot`, `SelectionLearningTrace`, `SelectionEffort`,
or `SelectionCaseMemory` row after creation. Reopening an Application never
touches its prior Case Memory (task §17) — `close_case_memory()` always
INSERTs a new row and only ever flips a PRIOR Case Memory's `is_current`
flag (a state pointer, not a fact about what that row records — the same
distinction `Application.current_stage`/`CandidateFlag.is_active` already
draw elsewhere in this codebase).

Explicitly NOT implemented here (task §29): autonomous Pattern/Rule
discovery, automatic rule creation, Training/Performance integration
(`append_downstream_feedback()` is a generic, empty-of-meaning foundation
only), and no code path in this codebase calls `close_case_memory()`
automatically — it is always an explicit call, exactly like
`outcome_service.apply_outcome()`/`reopen_application()` are always
explicit Selezionatore actions, never auto-fired by another service
function (task's own "do not redesign the existing Selection workflow").
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import pattern_service
from .core import pattern_model as pm
from .core import stage_model as stgm

# Relevance ranking used only to derive an explicit, explainable Stage Delta
# direction (IMPORTANCE_INCREASED/DECREASED) — never an opaque score (task
# §12's own explicit instruction).
_RELEVANCE_RANK = {pm.RELEVANCE_LOW: 0, pm.RELEVANCE_MEDIUM: 1, pm.RELEVANCE_HIGH: 2}
_STRONG_ROLES = (pm.ROLE_POSITIVE, pm.ROLE_NEGATIVE)
_DAMPENING_ROLES = (pm.ROLE_MODIFIER, pm.ROLE_NEUTRALIZER)


# ---------------------------------------------------------------------------
# Stage Pattern Snapshot — task §11, created ONLY for Stages actually
# traversed. The CALLER decides when a Stage was traversed; this function
# never infers it, so a skipped Stage never gets an artificial snapshot
# (task §11's own explicit requirement) simply because nobody calls this
# for it.
# ---------------------------------------------------------------------------


def freeze_stage_pattern_snapshot(
    session: Session, application_id: int, stage: str, *, stage_occurrence_index: int | None = None,
    resulting_priority_interpretation: str | None = None, explanation: str | None = None,
    rf_one_judgment: str | None = None, selector_action: str | None = None,
    divergence_occurred: bool = False, divergence_category: str | None = None,
    selector_note: str | None = None, note_required_if_divergence: bool = True,
) -> m.SelectionStagePatternSnapshot:
    """Freezes the current Working Pattern Profile for one (Application,
    Stage, occurrence) into an immutable Stage Pattern Snapshot. Raises if
    `divergence_occurred` is True, a note is required, and none was
    supplied — the architecture SUPPORTS making the note mandatory on
    divergence (task §13); no sophisticated divergence DETECTOR exists —
    the caller supplies `divergence_occurred` explicitly."""

    stgm.validate_stage(stage)
    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")

    if stage_occurrence_index is None:
        existing_count = session.scalars(
            select(m.SelectionStagePatternSnapshot).where(
                m.SelectionStagePatternSnapshot.application_id == application_id,
                m.SelectionStagePatternSnapshot.stage == stage,
            )
        ).all()
        stage_occurrence_index = len(existing_count) + 1

    if divergence_occurred and note_required_if_divergence and not selector_note:
        raise ValueError(
            "A Selezionatore Note is required when recording a divergence from RF-One's judgment "
            "(freeze_stage_pattern_snapshot: divergence_occurred=True, note_required_if_divergence=True)."
        )
    if divergence_category is not None:
        # Deliberately NOT enforced against a fixed set — SUGGESTED_DIVERGENCE_CATEGORIES
        # is seed vocabulary only (task §13's own "configurable/extensible").
        pass

    observations = pattern_service.list_observations(
        session, application_id, stage=stage, stage_occurrence_index=stage_occurrence_index, active_only=True,
    )
    observation_ids = [o.id for o in observations]
    pattern_definition_versions = sorted(
        {(o.pattern_definition_id, o.pattern_definition_snapshot_id) for o in observations},
        key=lambda pair: pair[0],
    )
    pattern_definition_versions_json = [
        {
            "pattern_definition_id": pdid,
            "pattern_definition_snapshot_id": snap_id,
            "version": session.get(m.SelectionPatternDefinitionSnapshot, snap_id).version,
        }
        for pdid, snap_id in pattern_definition_versions
    ]
    evidence_references = [ref for o in observations for ref in (o.evidence_references or [])]

    previous_snapshot = session.scalars(
        select(m.SelectionStagePatternSnapshot)
        .where(m.SelectionStagePatternSnapshot.application_id == application_id)
        .order_by(m.SelectionStagePatternSnapshot.id.desc())
    ).first()

    snapshot = m.SelectionStagePatternSnapshot(
        application_id=application_id, stage=stage, stage_occurrence_index=stage_occurrence_index,
        observation_ids=observation_ids, pattern_definition_versions=pattern_definition_versions_json,
        rule_versions=[], evidence_references=evidence_references,
        resulting_priority_interpretation=resulting_priority_interpretation, explanation=explanation,
        rf_one_judgment=rf_one_judgment, selector_action=selector_action,
        divergence_occurred=divergence_occurred, divergence_category=divergence_category,
        note_required=bool(divergence_occurred and note_required_if_divergence), selector_note=selector_note,
        previous_snapshot_id=previous_snapshot.id if previous_snapshot else None,
    )
    session.add(snapshot)
    session.flush()

    _compute_stage_delta(session, snapshot, observations, previous_snapshot)

    if divergence_occurred:
        append_learning_trace(
            session, application_id=application_id, stage=stage, event_type=pm.TRACE_DIVERGENCE,
            event_data={
                "rf_one_judgment": rf_one_judgment, "selector_action": selector_action,
                "divergence_category": divergence_category, "stage_snapshot_id": snapshot.id,
            },
            source_reference={"table": "selection_stage_pattern_snapshots", "id": snapshot.id},
            explanation=selector_note,
        )

    session.flush()
    return snapshot


def _compute_stage_delta(
    session: Session, snapshot: m.SelectionStagePatternSnapshot,
    current_observations: list[m.SelectionPatternObservation],
    previous_snapshot: m.SelectionStagePatternSnapshot | None,
) -> None:
    """Derives an explicit, explainable `SelectionStagePatternDelta` row per
    Pattern Definition touched by this Snapshot or the previous one (task
    §12) — always from the named role/relevance categories, never from an
    opaque numeric score."""

    current_by_pattern = {o.pattern_definition_id: o for o in current_observations}

    previous_by_pattern: dict[int, m.SelectionPatternObservation] = {}
    if previous_snapshot is not None:
        for obs_id in previous_snapshot.observation_ids or []:
            obs = session.get(m.SelectionPatternObservation, obs_id)
            if obs is not None:
                previous_by_pattern[obs.pattern_definition_id] = obs

    all_pattern_ids = set(current_by_pattern) | set(previous_by_pattern)
    for pattern_definition_id in sorted(all_pattern_ids):
        current_obs = current_by_pattern.get(pattern_definition_id)
        previous_obs = previous_by_pattern.get(pattern_definition_id)

        if current_obs is not None and previous_obs is None:
            _add_delta(session, snapshot, pattern_definition_id, pm.DELTA_NEW_PATTERN,
                       f"First observed in this Stage (role={current_obs.role}).")
            continue
        if current_obs is None and previous_obs is not None:
            _add_delta(session, snapshot, pattern_definition_id, pm.DELTA_NO_LONGER_SUPPORTED,
                       "No longer supported by any currently-ACTIVE Observation.")
            continue
        if current_obs is None or previous_obs is None:
            continue  # unreachable, keeps type-checkers happy

        if current_obs.role in _DAMPENING_ROLES and previous_obs.role in _STRONG_ROLES:
            _add_delta(session, snapshot, pattern_definition_id, pm.DELTA_NEUTRALIZED,
                       f"Role changed from {previous_obs.role} to {current_obs.role}.")
            continue

        if current_obs.role != previous_obs.role:
            strengthened = (
                (previous_obs.role == pm.ROLE_NEGATIVE and current_obs.role == pm.ROLE_POSITIVE)
                or (previous_obs.role in _DAMPENING_ROLES and current_obs.role == pm.ROLE_POSITIVE)
            )
            delta_type = pm.DELTA_STRENGTHENED if strengthened else pm.DELTA_WEAKENED
            _add_delta(session, snapshot, pattern_definition_id, delta_type,
                       f"Role changed from {previous_obs.role} to {current_obs.role}.")
            continue

        prev_rank = _RELEVANCE_RANK.get(previous_obs.relevance, 1)
        curr_rank = _RELEVANCE_RANK.get(current_obs.relevance, 1)
        if curr_rank > prev_rank:
            _add_delta(session, snapshot, pattern_definition_id, pm.DELTA_IMPORTANCE_INCREASED,
                       f"Relevance changed from {previous_obs.relevance} to {current_obs.relevance}.")
        elif curr_rank < prev_rank:
            _add_delta(session, snapshot, pattern_definition_id, pm.DELTA_IMPORTANCE_DECREASED,
                       f"Relevance changed from {previous_obs.relevance} to {current_obs.relevance}.")
        else:
            _add_delta(session, snapshot, pattern_definition_id, pm.DELTA_CONFIRMED,
                       f"Same role ({current_obs.role}) and relevance ({current_obs.relevance}) as the "
                       "previous Stage Snapshot.")


def _add_delta(
    session: Session, snapshot: m.SelectionStagePatternSnapshot, pattern_definition_id: int,
    delta_type: str, explanation: str,
) -> m.SelectionStagePatternDelta:
    pm.validate_stage_delta_type(delta_type)
    delta = m.SelectionStagePatternDelta(
        stage_snapshot_id=snapshot.id, pattern_definition_id=pattern_definition_id,
        delta_type=delta_type, explanation=explanation,
    )
    session.add(delta)
    session.flush()
    return delta


def list_stage_pattern_snapshots(session: Session, application_id: int) -> list[m.SelectionStagePatternSnapshot]:
    stmt = (
        select(m.SelectionStagePatternSnapshot)
        .where(m.SelectionStagePatternSnapshot.application_id == application_id)
        .order_by(m.SelectionStagePatternSnapshot.id)
    )
    return list(session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Learning Trace — task §14, append-only
# ---------------------------------------------------------------------------


def append_learning_trace(
    session: Session, *, application_id: int | None = None, person_id: int | None = None,
    stage: str | None = None, event_type: str, event_data: dict | None = None,
    source_reference: dict | None = None, explanation: str | None = None,
    provenance: str = pm.PROVENANCE_SYSTEM_GENERATED,
) -> m.SelectionLearningTrace:
    """Appends one Learning Trace. There is no `update_learning_trace`/
    `delete_learning_trace` function anywhere in this codebase — Learning
    Traces are append-only by construction (task §14's own explicit
    instruction), not merely by convention."""

    pm.validate_provenance(provenance)
    trace = m.SelectionLearningTrace(
        application_id=application_id, person_id=person_id, stage=stage, event_type=event_type,
        event_data=event_data or {}, source_reference=source_reference or {}, explanation=explanation,
        provenance=provenance,
    )
    session.add(trace)
    session.flush()
    return trace


def list_learning_traces(
    session: Session, *, application_id: int | None = None, person_id: int | None = None,
) -> list[m.SelectionLearningTrace]:
    stmt = select(m.SelectionLearningTrace)
    if application_id is not None:
        stmt = stmt.where(m.SelectionLearningTrace.application_id == application_id)
    if person_id is not None:
        stmt = stmt.where(m.SelectionLearningTrace.person_id == person_id)
    stmt = stmt.order_by(m.SelectionLearningTrace.id)
    return list(session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Selection Effort — task §15
# ---------------------------------------------------------------------------


def compute_selection_effort(
    session: Session, application_id: int, *, interviewer_time_minutes: int | None = None,
    tests_administered_count: int | None = None, followups_count: int | None = None,
    preparation_notes: str | None = None, effort_elements: dict | None = None,
) -> m.SelectionEffort:
    """Derives what IS observable from Stage/Outcome/Note history; accepts
    optional manually-supplied fields for what is not directly derivable
    (interviewer time, tests administered, follow-ups, preparation notes) —
    never invented when not supplied (task's own "do not invent unavailable
    time values": all of the manually-supplied parameters default to
    `None`, not `0`)."""

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")

    transitions = session.scalars(
        select(m.ApplicationStageTransition)
        .where(m.ApplicationStageTransition.application_id == application_id)
    ).all()
    stages_seen = {t.new_stage for t in transitions} | {application.current_stage}
    stage_counts: dict[str, int] = {}
    for t in transitions:
        stage_counts[t.new_stage] = stage_counts.get(t.new_stage, 0) + 1
    repeated = sum(1 for count in stage_counts.values() if count > 1)

    notes_count = session.scalars(
        select(m.ApplicationNote).where(m.ApplicationNote.application_id == application_id)
    ).all()
    outcome_decisions = session.scalars(
        select(m.SelectionOutcomeDecision).where(m.SelectionOutcomeDecision.application_id == application_id)
    ).all()

    current_outcome_decision = outcome_decisions[-1] if outcome_decisions else None
    final_outcome_name = None
    if current_outcome_decision is not None:
        snapshot = session.get(
            m.SelectionOutcomeDefinitionSnapshot, current_outcome_decision.outcome_definition_snapshot_id
        )
        final_outcome_name = snapshot.name if snapshot is not None else None

    effort = m.SelectionEffort(
        application_id=application_id,
        stages_traversed_count=len(stages_seen),
        repeated_stages_count=repeated,
        interviewer_time_minutes=interviewer_time_minutes,
        tests_administered_count=tests_administered_count,
        followups_count=followups_count,
        preparation_notes=preparation_notes,
        interactions_count=len(transitions) + len(notes_count) + len(outcome_decisions),
        point_of_exit=application.current_stage,
        final_outcome=final_outcome_name,
        effort_elements=effort_elements or {},
    )
    session.add(effort)
    session.flush()
    return effort


# ---------------------------------------------------------------------------
# Case Memory — task §16/§17
# ---------------------------------------------------------------------------


def close_case_memory(
    session: Session, application_id: int, *, rf_one_final_judgment: str | None = None,
    selezionatore_final_decision: str | None = None, essential_facts: dict | None = None,
    selection_signals_summary: dict | None = None, materially_impactful_pattern_versions: list | None = None,
    materially_impactful_rules: list | None = None, skill_findings: dict | None = None,
    training_burden_estimate: dict | None = None, trainable_gaps: dict | None = None,
    selection_effort_kwargs: dict | None = None,
) -> m.SelectionCaseMemory:
    """Creates ONE Case Memory when an Application closes (task §16). Must
    be called explicitly — no code path in this codebase calls it
    automatically from `outcome_service.apply_outcome()` (task's own "do
    not redesign the existing Selection workflow"; wiring this in
    automatically is left to a future, separately-scoped task).

    If a PRIOR Case Memory already exists for this Application (i.e. it was
    reopened and is closing again), THE PRIOR ROW IS NEVER MODIFIED (task
    §17): this function only ever flips that prior row's `is_current` to
    False (a pointer, not a fact) and inserts a brand-new row with
    `version = previous.version + 1`, `previous_case_memory_id` linking
    back, and `reopening_event_reference` recording what happened between
    the two closures."""

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")

    current_decision = session.scalars(
        select(m.SelectionOutcomeDecision)
        .where(m.SelectionOutcomeDecision.application_id == application_id)
        .order_by(m.SelectionOutcomeDecision.id.desc())
    ).first()
    if current_decision is None:
        raise ValueError(
            f"Application {application_id} has no SelectionOutcomeDecision yet — "
            "close_case_memory() requires an Outcome to have been applied first."
        )

    previous = session.scalars(
        select(m.SelectionCaseMemory)
        .where(m.SelectionCaseMemory.application_id == application_id, m.SelectionCaseMemory.is_current.is_(True))
    ).first()

    effort = compute_selection_effort(session, application_id, **(selection_effort_kwargs or {}))

    stage_snapshots = list_stage_pattern_snapshots(session, application_id)
    final_stage_snapshot = stage_snapshots[-1] if stage_snapshots else None

    notes = session.scalars(
        select(m.ApplicationNote).where(m.ApplicationNote.application_id == application_id)
    ).all()
    traces = list_learning_traces(session, application_id=application_id)

    version = 1
    reopening_event_reference = None
    if previous is not None:
        version = previous.version + 1
        previous.is_current = False
        reopening_event_reference = {
            "previous_case_memory_id": previous.id, "previous_version": previous.version,
            "previous_closed_at": previous.closed_at.isoformat() if previous.closed_at else None,
        }
        append_learning_trace(
            session, application_id=application_id, person_id=application.person_id,
            event_type=pm.TRACE_APPLICATION_REOPENED,
            event_data={"previous_case_memory_id": previous.id, "new_version": version},
            source_reference={"table": "selection_case_memories", "id": previous.id},
        )

    case_memory = m.SelectionCaseMemory(
        application_id=application_id, person_id=application.person_id, version=version, is_current=True,
        previous_case_memory_id=previous.id if previous is not None else None,
        reopening_event_reference=reopening_event_reference,
        outcome_decision_id=current_decision.id, lifecycle_state_at_closure=application.lifecycle_state,
        essential_facts=essential_facts or {}, selection_signals_summary=selection_signals_summary or {},
        final_stage_snapshot_id=final_stage_snapshot.id if final_stage_snapshot else None,
        stage_snapshot_ids=[s.id for s in stage_snapshots],
        materially_impactful_pattern_versions=materially_impactful_pattern_versions or [],
        materially_impactful_rules=materially_impactful_rules or [],
        rf_one_final_judgment=rf_one_final_judgment, selezionatore_final_decision=selezionatore_final_decision,
        skill_findings=skill_findings, training_burden_estimate=training_burden_estimate,
        trainable_gaps=trainable_gaps, selection_effort_id=effort.id,
        notes_reference=[n.id for n in notes], learning_trace_reference=[t.id for t in traces],
        evidence_reference=[],
    )
    session.add(case_memory)
    session.flush()
    return case_memory


def get_case_memory(session: Session, case_memory_id: int) -> m.SelectionCaseMemory | None:
    return session.get(m.SelectionCaseMemory, case_memory_id)


def get_current_case_memory(session: Session, application_id: int) -> m.SelectionCaseMemory | None:
    return session.scalars(
        select(m.SelectionCaseMemory).where(
            m.SelectionCaseMemory.application_id == application_id, m.SelectionCaseMemory.is_current.is_(True)
        )
    ).first()


def list_case_memory_versions(session: Session, application_id: int) -> list[m.SelectionCaseMemory]:
    """Full, never-rewritten version history for one Application — every
    version this function returns is exactly what it was at its own
    closure time (task §17)."""

    stmt = (
        select(m.SelectionCaseMemory)
        .where(m.SelectionCaseMemory.application_id == application_id)
        .order_by(m.SelectionCaseMemory.version)
    )
    return list(session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Downstream Outcome Feedback — task §18, FOUNDATION ONLY, append-only
# ---------------------------------------------------------------------------


def append_downstream_feedback(
    session: Session, *, application_id: int, source_domain: str, feedback_type: str, observed_fact: str,
    case_memory_id: int | None = None, source_record_reference: dict | None = None,
    evidence_reference: dict | None = None, classification: str | None = None,
    provenance: str = pm.PROVENANCE_SYSTEM_GENERATED,
) -> m.SelectionDownstreamOutcomeFeedback:
    """Appends one downstream feedback record. NEVER modifies the
    referenced Case Memory or Application — this table is structurally
    separate and this function contains no code path that writes to
    `selection_case_memories` (task §18's own explicit "no retroactive
    mutation"). No Training/Performance integration exists yet — this is
    only the generic reference structure a later task would call."""

    pm.validate_provenance(provenance)
    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")

    feedback = m.SelectionDownstreamOutcomeFeedback(
        application_id=application_id, case_memory_id=case_memory_id, source_domain=source_domain,
        source_record_reference=source_record_reference or {}, feedback_type=feedback_type,
        observed_fact=observed_fact, evidence_reference=evidence_reference, classification=classification,
        provenance=provenance,
    )
    session.add(feedback)
    session.flush()
    return feedback


def list_downstream_feedback(session: Session, application_id: int) -> list[m.SelectionDownstreamOutcomeFeedback]:
    stmt = (
        select(m.SelectionDownstreamOutcomeFeedback)
        .where(m.SelectionDownstreamOutcomeFeedback.application_id == application_id)
        .order_by(m.SelectionDownstreamOutcomeFeedback.id)
    )
    return list(session.scalars(stmt).all())
