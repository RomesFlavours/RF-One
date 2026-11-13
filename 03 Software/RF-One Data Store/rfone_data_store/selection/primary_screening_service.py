"""Primary Screening Engine — service layer (Task 3D). Runtime
orchestration combining Selection Core's Primary Screening vocabulary
(`core/primary_screening_model.py`) with restaurant-configured Screening
Criteria and existing Selection Signal evidence. Flask routes should call
into this module rather than touching `.. models` directly.

Fundamental boundaries this module enforces:

- RF-One never decides which Criteria matter, what a level 0-4 means, or
  how important a Criterion is — every one of those is restaurant-
  authored data (task §1/§10). This module only executes the restaurant's
  own configuration.
- The internal `priority_index` this module computes is NEVER returned by
  any function meant for direct Selezionatore display without going
  through `list_normal_pool`/`list_hard_disqualifier_pool`'s own ordering
  — no route/template should ever render the raw number (task §5/§17).
- A Hard Disqualifier is a categorical gate, never mathematically
  cancellable by positive contributions (task §9) — pool membership is
  decided by `PrimaryScreeningRun.has_active_hard_disqualifier` alone,
  never by comparing the Priority Index against a threshold.
- An unresolved/uncertain Criterion Evaluation is never silently coerced
  to level 0 (task §14) — only `EVALUATED` evaluations contribute to the
  Priority Index.
- A screening run stays permanently tied to the exact Criterion
  configuration snapshot used (task §16) — editing a live Criterion
  later never rewrites a historical run's meaning.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from . import application_service as app_svc
from . import primary_screening_ai_evaluator as ai_eval
from . import signal_service as sig_svc
from .core import primary_screening_model as psm
from .core import signal_model as sm

_LEVEL_KEYS = {"0", "1", "2", "3", "4"}

# Task 3D-FIX §16 — context tags for `ApplicationNote.context_type`, used
# by `add_run_note`/`add_evaluation_note` below (reusing, not duplicating,
# the Task 3C-FIX notes mechanism).
NOTE_CONTEXT_RUN = "PRIMARY_SCREENING_RUN"
NOTE_CONTEXT_EVALUATION = "PRIMARY_SCREENING_CRITERION_EVALUATION"


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_direction(value: str) -> None:
    if value not in psm.DIRECTIONS:
        raise ValueError(f"Unknown direction {value!r}; expected one of {psm.DIRECTIONS}")


def _validate_evidence_sources(values: list[str]) -> None:
    unknown = [v for v in values if v not in psm.EVIDENCE_SOURCES]
    if unknown:
        raise ValueError(f"Unknown evidence source(s) {unknown!r}; expected one of {psm.EVIDENCE_SOURCES}")


def _validate_level_descriptions(value: dict) -> None:
    unknown = [k for k in value if k not in _LEVEL_KEYS]
    if unknown:
        raise ValueError(f"level_descriptions keys must be one of {sorted(_LEVEL_KEYS)}; got {unknown!r}")


def _validate_hard_disqualifier_trigger(is_hard_disqualifier: bool, trigger_level: int | None) -> None:
    if is_hard_disqualifier and trigger_level is not None:
        psm.validate_level(trigger_level)


# ---------------------------------------------------------------------------
# Primary Screening Criterion (task §1/§25) — restaurant-configurable.
# ---------------------------------------------------------------------------

def create_criterion(
    session: Session, *, restaurant_id: int | None, name: str, coefficient: float = 1.0,
    direction: str = psm.POSITIVE, description: str | None = None, category: str | None = None,
    target_role: str | None = None, location_label: str | None = None, is_hard_disqualifier: bool = False,
    hard_disqualifier_trigger_level: int | None = None, level_descriptions: dict | None = None,
    evidence_sources_allowed: list[str] | None = None, evaluation_guidance: str | None = None,
    evidence_positive: str | None = None, evidence_contrary: str | None = None,
    evidence_insufficient: str | None = None, auto_evaluation_signal_definition_id: int | None = None,
    auto_evaluation_level_map: dict | None = None, display_order: int | None = None,
    required_for_phone_review: bool = False, missing_evidence_question_text: str | None = None,
    missing_evidence_answer_level_map: dict | None = None,
) -> m.PrimaryScreeningCriterion:
    _validate_direction(direction)
    level_descriptions = dict(level_descriptions or {})
    _validate_level_descriptions(level_descriptions)
    evidence_sources_allowed = list(evidence_sources_allowed or [])
    _validate_evidence_sources(evidence_sources_allowed)
    _validate_hard_disqualifier_trigger(is_hard_disqualifier, hard_disqualifier_trigger_level)

    if display_order is None:
        display_order = session.scalar(
            select(func.count()).select_from(m.PrimaryScreeningCriterion)
            .where(m.PrimaryScreeningCriterion.restaurant_id == restaurant_id)
        )

    criterion = m.PrimaryScreeningCriterion(
        restaurant_id=restaurant_id, name=name, description=description, category=category,
        target_role=target_role, location_label=location_label, coefficient=coefficient, direction=direction,
        is_hard_disqualifier=is_hard_disqualifier, hard_disqualifier_trigger_level=hard_disqualifier_trigger_level,
        level_descriptions=level_descriptions, evidence_sources_allowed=evidence_sources_allowed,
        evaluation_guidance=evaluation_guidance, evidence_positive=evidence_positive,
        evidence_contrary=evidence_contrary, evidence_insufficient=evidence_insufficient,
        auto_evaluation_signal_definition_id=auto_evaluation_signal_definition_id,
        auto_evaluation_level_map=dict(auto_evaluation_level_map or {}), display_order=display_order,
        required_for_phone_review=required_for_phone_review,
        missing_evidence_question_text=missing_evidence_question_text,
        missing_evidence_answer_level_map=dict(missing_evidence_answer_level_map or {}),
    )
    session.add(criterion)
    session.flush()
    return criterion


def list_criteria(
    session: Session, *, restaurant_id: int | None = None, target_role: str | None = None, active_only: bool = True,
) -> list[m.PrimaryScreeningCriterion]:
    stmt = select(m.PrimaryScreeningCriterion).order_by(m.PrimaryScreeningCriterion.display_order)
    if restaurant_id is not None:
        stmt = stmt.where(m.PrimaryScreeningCriterion.restaurant_id == restaurant_id)
    if target_role is not None:
        stmt = stmt.where(m.PrimaryScreeningCriterion.target_role == target_role)
    if active_only:
        stmt = stmt.where(m.PrimaryScreeningCriterion.is_active.is_(True))
    return list(session.scalars(stmt).all())


def get_criterion(session: Session, criterion_id: int) -> m.PrimaryScreeningCriterion | None:
    return session.get(m.PrimaryScreeningCriterion, criterion_id)


def update_criterion(session: Session, criterion_id: int, **fields) -> m.PrimaryScreeningCriterion:
    criterion = session.get(m.PrimaryScreeningCriterion, criterion_id)
    if criterion is None:
        raise ValueError(f"No PrimaryScreeningCriterion with id {criterion_id}")

    allowed = {
        "name", "description", "category", "target_role", "location_label", "coefficient", "direction",
        "is_hard_disqualifier", "hard_disqualifier_trigger_level", "level_descriptions", "evidence_sources_allowed",
        "evaluation_guidance", "evidence_positive", "evidence_contrary", "evidence_insufficient",
        "auto_evaluation_signal_definition_id", "auto_evaluation_level_map", "display_order", "is_active",
        "required_for_phone_review", "missing_evidence_question_text", "missing_evidence_answer_level_map",
    }
    for key in fields:
        if key not in allowed:
            raise ValueError(f"Cannot set {key!r} on a PrimaryScreeningCriterion through update_criterion")
    if "direction" in fields:
        _validate_direction(fields["direction"])
    if "level_descriptions" in fields:
        fields["level_descriptions"] = dict(fields["level_descriptions"])
        _validate_level_descriptions(fields["level_descriptions"])
    if "evidence_sources_allowed" in fields:
        fields["evidence_sources_allowed"] = list(fields["evidence_sources_allowed"])
        _validate_evidence_sources(fields["evidence_sources_allowed"])
    if "auto_evaluation_level_map" in fields:
        fields["auto_evaluation_level_map"] = dict(fields["auto_evaluation_level_map"])
    is_hard = fields.get("is_hard_disqualifier", criterion.is_hard_disqualifier)
    trigger = fields.get("hard_disqualifier_trigger_level", criterion.hard_disqualifier_trigger_level)
    _validate_hard_disqualifier_trigger(is_hard, trigger)

    for key, value in fields.items():
        setattr(criterion, key, value)
    if fields:
        criterion.version += 1
    session.flush()
    return criterion


def deactivate_criterion(session: Session, criterion_id: int) -> m.PrimaryScreeningCriterion:
    return update_criterion(session, criterion_id, is_active=False)


def reactivate_criterion(session: Session, criterion_id: int) -> m.PrimaryScreeningCriterion:
    return update_criterion(session, criterion_id, is_active=True)


# ---------------------------------------------------------------------------
# Immutable snapshots (task §16) — mirrors
# `requirements_service.create_requirement_set_snapshot()`'s idempotent-
# per-version behavior, at single-Criterion granularity.
# ---------------------------------------------------------------------------

def get_or_create_criterion_snapshot(session: Session, criterion_id: int) -> m.PrimaryScreeningCriterionSnapshot:
    criterion = session.get(m.PrimaryScreeningCriterion, criterion_id)
    if criterion is None:
        raise ValueError(f"No PrimaryScreeningCriterion with id {criterion_id}")

    existing = session.scalars(
        select(m.PrimaryScreeningCriterionSnapshot).where(
            m.PrimaryScreeningCriterionSnapshot.criterion_id == criterion_id,
            m.PrimaryScreeningCriterionSnapshot.version == criterion.version,
        )
    ).first()
    if existing is not None:
        return existing

    snapshot = m.PrimaryScreeningCriterionSnapshot(
        criterion_id=criterion.id, version=criterion.version, restaurant_id=criterion.restaurant_id,
        name=criterion.name, description=criterion.description, category=criterion.category,
        target_role=criterion.target_role, location_label=criterion.location_label,
        coefficient=criterion.coefficient, direction=criterion.direction,
        is_hard_disqualifier=criterion.is_hard_disqualifier,
        hard_disqualifier_trigger_level=criterion.hard_disqualifier_trigger_level,
        level_descriptions=dict(criterion.level_descriptions or {}),
        evidence_sources_allowed=list(criterion.evidence_sources_allowed or []),
        evaluation_guidance=criterion.evaluation_guidance, evidence_positive=criterion.evidence_positive,
        evidence_contrary=criterion.evidence_contrary, evidence_insufficient=criterion.evidence_insufficient,
        auto_evaluation_signal_definition_id=criterion.auto_evaluation_signal_definition_id,
        auto_evaluation_level_map=dict(criterion.auto_evaluation_level_map or {}), was_active=criterion.is_active,
        required_for_phone_review=criterion.required_for_phone_review,
        missing_evidence_question_text=criterion.missing_evidence_question_text,
        missing_evidence_answer_level_map=dict(criterion.missing_evidence_answer_level_map or {}),
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def get_snapshot(session: Session, snapshot_id: int) -> m.PrimaryScreeningCriterionSnapshot | None:
    return session.get(m.PrimaryScreeningCriterionSnapshot, snapshot_id)


# ---------------------------------------------------------------------------
# Primary Screening Run (task §17) — multiple runs may exist per
# Application over time; each stays tied to its own exact snapshot set.
# ---------------------------------------------------------------------------

def get_run(session: Session, run_id: int) -> m.PrimaryScreeningRun | None:
    return session.get(m.PrimaryScreeningRun, run_id)


def get_latest_run_for_application(session: Session, application_id: int) -> m.PrimaryScreeningRun | None:
    stmt = (
        select(m.PrimaryScreeningRun)
        .where(m.PrimaryScreeningRun.application_id == application_id)
        .order_by(m.PrimaryScreeningRun.id.desc())
    )
    return session.scalars(stmt).first()


def list_runs_for_application(session: Session, application_id: int) -> list[m.PrimaryScreeningRun]:
    stmt = (
        select(m.PrimaryScreeningRun)
        .where(m.PrimaryScreeningRun.application_id == application_id)
        .order_by(m.PrimaryScreeningRun.id.desc())
    )
    return list(session.scalars(stmt).all())


def list_evaluations(session: Session, run_id: int) -> list[m.PrimaryScreeningCriterionEvaluation]:
    stmt = (
        select(m.PrimaryScreeningCriterionEvaluation)
        .where(m.PrimaryScreeningCriterionEvaluation.run_id == run_id)
        .order_by(m.PrimaryScreeningCriterionEvaluation.id)
    )
    return list(session.scalars(stmt).all())


def _auto_evaluate_from_signal(
    session: Session, application: m.Application, evaluation: m.PrimaryScreeningCriterionEvaluation,
    snapshot: m.PrimaryScreeningCriterionSnapshot,
) -> None:
    """Task §12/§18 — an OPTIONAL, fully restaurant-configured deterministic
    shortcut: if this Criterion's snapshot declares a linked Signal
    Definition and a restaurant-authored status->level map, read the
    Application's own Signal Observation and look the level up in that
    map. Never invents a level RF-One itself decided was correct — the
    mapping is entirely the restaurant's own data."""

    if not snapshot.auto_evaluation_signal_definition_id:
        return

    observation = sig_svc.get_or_create_observation(session, application.id, snapshot.auto_evaluation_signal_definition_id)
    level = snapshot.auto_evaluation_level_map.get(observation.status)
    if level is not None:
        psm.validate_level(level)
        evaluation.system_level = level
        evaluation.effective_level = level
        evaluation.status = psm.EVALUATED
        evaluation.origin = psm.SYSTEM_GENERATED
        evaluation.evidence_source = psm.SELECTION_SIGNAL
        evaluation.confidence = observation.confidence
        evaluation.explanation = (
            f"Auto-evaluated from Signal '{observation.signal_definition.name}' (status {observation.status}), "
            "per this restaurant's own configured mapping."
        )
    elif observation.status != sm.NOT_ASSESSED:
        evaluation.status = psm.INSUFFICIENT_EVIDENCE
        evaluation.evidence_source = psm.SELECTION_SIGNAL
        evaluation.explanation = (
            f"Signal '{observation.signal_definition.name}' status ({observation.status}) has no configured "
            "level mapping for this Criterion."
        )
    session.flush()


def _auto_evaluate_generic(
    session: Session, application: m.Application, evaluation: m.PrimaryScreeningCriterionEvaluation,
    snapshot: m.PrimaryScreeningCriterionSnapshot, *, generate_json_fn: Callable | None,
) -> None:
    """Task 3D-FIX §2/§6/§9 — the generic, AI-assisted fallback, used ONLY
    when the deterministic Signal-based shortcut above did not already
    reach EVALUATED (task's own preferred order: deterministic mapping
    first, generic evaluator second, otherwise leave explicitly
    unresolved). Interprets this Criterion's OWN snapshot (level meanings,
    guidance, allowed evidence sources) against a structured evidence
    package — never criterion-specific logic.

    Never fabricates a level: any failure (`AIEvaluationUnavailable` — no
    provider configured, a request failure, or malformed AI output) simply
    leaves the evaluation exactly as the deterministic step already left
    it, recording the failure reason only when nothing more informative
    was already set (task §8's "one failed Criterion must not crash the
    entire batch" — this function never raises)."""

    try:
        result = ai_eval.evaluate_criterion_with_ai(
            session, application, snapshot, generate_json_fn=generate_json_fn,
        )
    except ai_eval.AIEvaluationUnavailable as exc:
        if evaluation.status == psm.NOT_EVALUATED:
            evaluation.explanation = f"Automatic evaluation not available: {exc}"
            session.flush()
        return

    evaluation.status = result.status
    evaluation.system_level = result.level
    evaluation.effective_level = result.level
    evaluation.origin = psm.SYSTEM_GENERATED
    evaluation.confidence = result.confidence
    evaluation.explanation = result.explanation
    evaluation.evidence_items = [
        {
            "source_type": e.source_type, "source_reference": e.source_reference,
            "evidence_text": e.evidence_text, "interpretation": e.interpretation,
        }
        for e in result.evidence
    ]
    if result.evidence:
        evaluation.evidence_source = result.evidence[0].source_type
        evaluation.evidence_text = "; ".join(e.evidence_text for e in result.evidence)
    session.flush()


def create_screening_run(
    session: Session, application_id: int, *, ai_generate_json_fn: Callable | None = None,
) -> m.PrimaryScreeningRun:
    """Task §17 — always creates a NEW run (never idempotent-return, unlike
    the 1:1 Phone/In-Person Plans) so historical screening results are
    never silently overwritten; the Primary Screening Queue simply reads
    the most recent one per Application. Snapshots every active,
    role-matching Criterion for this restaurant at its CURRENT version,
    creates one Criterion Evaluation per snapshot (starting NOT_EVALUATED
    — task §14's own "never silently invent a level"), then applies the
    restaurant's own optional Signal-based auto-evaluation where
    configured, falling back to the generic AI-assisted evaluator (Task
    3D-FIX) for whatever the deterministic step leaves unresolved. This IS
    the explicit re-evaluation action (task 3D-FIX §13): calling this again
    for an Application already screened creates a fresh run against the
    CURRENT live Criterion configuration without touching any prior run.

    `ai_generate_json_fn` is an optional test/DI seam threaded down to
    `primary_screening_ai_evaluator.evaluate_criterion_with_ai` — production
    callers never need to pass it (the real provider is used by default)."""

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")

    run = m.PrimaryScreeningRun(application_id=application.id, restaurant_id=application.restaurant_id)
    session.add(run)
    session.flush()

    criteria = [
        c for c in list_criteria(session, restaurant_id=application.restaurant_id, active_only=True)
        if c.target_role is None or c.target_role == application.target_role
    ]
    for criterion in criteria:
        snapshot = get_or_create_criterion_snapshot(session, criterion.id)
        evaluation = m.PrimaryScreeningCriterionEvaluation(
            run_id=run.id, criterion_snapshot_id=snapshot.id, status=psm.NOT_EVALUATED,
        )
        session.add(evaluation)
        session.flush()
        _auto_evaluate_from_signal(session, application, evaluation, snapshot)
        if evaluation.status != psm.EVALUATED:
            _auto_evaluate_generic(session, application, evaluation, snapshot, generate_json_fn=ai_generate_json_fn)

    _recompute_run(session, run)
    return run


def _generate_explanation(
    evaluations: list[m.PrimaryScreeningCriterionEvaluation],
    active_hard_disqualifiers: list[tuple[m.PrimaryScreeningCriterionSnapshot, m.PrimaryScreeningCriterionEvaluation]],
) -> str:
    """Task §18 — a concise, conversational, evidence-based explanation.
    Never shows the mathematical calculation or any numeric index/score."""

    if active_hard_disqualifiers:
        parts = []
        for snapshot, evaluation in active_hard_disqualifiers:
            level_desc = (snapshot.level_descriptions or {}).get(str(evaluation.effective_level))
            parts.append(
                f"Hard Disqualifier detected: {snapshot.name}" + (f" — {level_desc}." if level_desc else ".")
            )
        return " ".join(parts)

    contributions = [
        (evaluation.criterion_snapshot.name, evaluation.contribution)
        for evaluation in evaluations if evaluation.status == psm.EVALUATED
    ]
    positives = sorted((t for t in contributions if t[1] > 0), key=lambda t: t[1], reverse=True)[:2]
    negatives = sorted((t for t in contributions if t[1] < 0), key=lambda t: t[1])[:2]
    uncertain = [
        evaluation.criterion_snapshot.name for evaluation in evaluations
        if evaluation.status == psm.INSUFFICIENT_EVIDENCE
    ][:3]

    sentences = []
    if positives:
        names = " and ".join(name for name, _ in positives)
        verb = "is the main positive factor" if len(positives) == 1 else "are the main positive factors"
        sentences.append(f"{names} {verb}.")
    if negatives:
        names = " and ".join(name for name, _ in negatives)
        verb = "reduces" if len(negatives) == 1 else "reduce"
        sentences.append(f"{names} {verb} current priority.")
    if not positives and not negatives:
        sentences.append("No Screening Criteria have been evaluated with a clear positive or negative effect yet.")
    if uncertain:
        sentences.append(f"Insufficient evidence so far for: {', '.join(uncertain)}.")
    return " ".join(sentences)


def _recompute_run(session: Session, run: m.PrimaryScreeningRun) -> m.PrimaryScreeningRun:
    """The ONE place `contribution`/`is_active_hard_disqualifier`/
    `priority_index`/`has_active_hard_disqualifier`/`explanation` are
    (re)computed — called after every evaluation change so the Run always
    reflects its evaluations' current EFFECTIVE state."""

    evaluations = list_evaluations(session, run.id)
    active_hard_disqualifiers: list[tuple] = []

    for evaluation in evaluations:
        snapshot = evaluation.criterion_snapshot
        if evaluation.status == psm.EVALUATED and evaluation.effective_level is not None:
            evaluation.contribution = psm.compute_contribution(
                coefficient=snapshot.coefficient, level=evaluation.effective_level, direction=snapshot.direction,
            )
        else:
            evaluation.contribution = 0.0

        is_hard = (
            snapshot.is_hard_disqualifier and snapshot.hard_disqualifier_trigger_level is not None
            and evaluation.status == psm.EVALUATED and evaluation.effective_level is not None
            and evaluation.effective_level >= snapshot.hard_disqualifier_trigger_level
        )
        evaluation.is_active_hard_disqualifier = is_hard
        if is_hard and not evaluation.hard_disqualifier_overridden:
            active_hard_disqualifiers.append((snapshot, evaluation))

    run.priority_index = psm.compute_priority_index(
        [e.contribution for e in evaluations if e.status == psm.EVALUATED]
    )
    run.has_active_hard_disqualifier = bool(active_hard_disqualifiers)
    run.explanation = _generate_explanation(evaluations, active_hard_disqualifiers)
    session.flush()
    return run


# ---------------------------------------------------------------------------
# Criterion Evaluation actions (task §13/§15) — the Selezionatore's own
# input; nothing here fires on its own beyond the optional auto-evaluation
# already applied at run creation.
# ---------------------------------------------------------------------------

def human_enter_evaluation(
    session: Session, evaluation_id: int, *, level: int, confidence: str | None = None,
    evidence_source: str | None = None, evidence_text: str | None = None, explanation: str | None = None,
) -> m.PrimaryScreeningCriterionEvaluation:
    """A Selezionatore directly enters a level where none was auto-
    evaluated (task §15's HUMAN_ENTERED)."""

    psm.validate_level(level)
    evaluation = session.get(m.PrimaryScreeningCriterionEvaluation, evaluation_id)
    if evaluation is None:
        raise ValueError(f"No PrimaryScreeningCriterionEvaluation with id {evaluation_id}")
    if evidence_source is not None and evidence_source not in psm.EVIDENCE_SOURCES:
        raise ValueError(f"Unknown evidence source {evidence_source!r}; expected one of {psm.EVIDENCE_SOURCES}")

    evaluation.effective_level = level
    evaluation.status = psm.EVALUATED
    evaluation.origin = psm.HUMAN_ENTERED
    if confidence:
        evaluation.confidence = confidence
    if evidence_source:
        evaluation.evidence_source = evidence_source
    if evidence_text is not None:
        evaluation.evidence_text = evidence_text
    if explanation is not None:
        evaluation.explanation = explanation
    session.flush()

    run = session.get(m.PrimaryScreeningRun, evaluation.run_id)
    _recompute_run(session, run)
    return evaluation


def human_confirm_evaluation(session: Session, evaluation_id: int, *, note: str | None = None) -> m.PrimaryScreeningCriterionEvaluation:
    """The Selezionatore reviewed the current (system or human) level and
    agrees with it — `effective_level` is left exactly as it is; `origin`
    becomes HUMAN_CONFIRMED (task §15)."""

    evaluation = session.get(m.PrimaryScreeningCriterionEvaluation, evaluation_id)
    if evaluation is None:
        raise ValueError(f"No PrimaryScreeningCriterionEvaluation with id {evaluation_id}")
    evaluation.origin = psm.HUMAN_CONFIRMED
    if evaluation.effective_level is not None:
        evaluation.status = psm.EVALUATED
    if note:
        evaluation.explanation = note
    session.flush()

    run = session.get(m.PrimaryScreeningRun, evaluation.run_id)
    _recompute_run(session, run)
    return evaluation


def human_override_evaluation(
    session: Session, evaluation_id: int, *, level: int, reason: str | None = None,
) -> m.PrimaryScreeningCriterionEvaluation:
    """A human sets a different effective level than the system computed.
    `system_level` is preserved exactly as it was — never deleted or
    replaced (task §15)."""

    psm.validate_level(level)
    evaluation = session.get(m.PrimaryScreeningCriterionEvaluation, evaluation_id)
    if evaluation is None:
        raise ValueError(f"No PrimaryScreeningCriterionEvaluation with id {evaluation_id}")

    evaluation.effective_level = level
    evaluation.status = psm.EVALUATED
    evaluation.origin = psm.HUMAN_OVERRIDDEN
    evaluation.override_reason = reason
    evaluation.overridden_at = datetime.utcnow()
    session.flush()

    run = session.get(m.PrimaryScreeningRun, evaluation.run_id)
    _recompute_run(session, run)
    return evaluation


def mark_not_applicable(session: Session, evaluation_id: int, *, note: str | None = None) -> m.PrimaryScreeningCriterionEvaluation:
    evaluation = session.get(m.PrimaryScreeningCriterionEvaluation, evaluation_id)
    if evaluation is None:
        raise ValueError(f"No PrimaryScreeningCriterionEvaluation with id {evaluation_id}")
    evaluation.status = psm.NOT_APPLICABLE
    evaluation.effective_level = None
    if note:
        evaluation.explanation = note
    session.flush()

    run = session.get(m.PrimaryScreeningRun, evaluation.run_id)
    _recompute_run(session, run)
    return evaluation


def get_evaluation_for_criterion(
    session: Session, run_id: int, criterion_id: int,
) -> m.PrimaryScreeningCriterionEvaluation | None:
    """Task 5E — the one lookup Application-Question/Missing-Evidence
    answer processing needs: which Evaluation, in a given Run, corresponds
    to a given LIVE Criterion (joined through its pinned snapshot)."""

    stmt = (
        select(m.PrimaryScreeningCriterionEvaluation)
        .join(
            m.PrimaryScreeningCriterionSnapshot,
            m.PrimaryScreeningCriterionEvaluation.criterion_snapshot_id == m.PrimaryScreeningCriterionSnapshot.id,
        )
        .where(
            m.PrimaryScreeningCriterionEvaluation.run_id == run_id,
            m.PrimaryScreeningCriterionSnapshot.criterion_id == criterion_id,
        )
    )
    return session.scalars(stmt).first()


def apply_self_reported_evidence(
    session: Session, evaluation_id: int, *, evidence_text: str, level: int | None = None,
    evidence_source: str = psm.APPLICATION,
) -> m.PrimaryScreeningCriterionEvaluation:
    """Task 5E §18/§27 — records a candidate's OWN self-reported answer
    (an Application Question or Missing-Evidence Questionnaire answer) as
    evidence. Mirrors `_auto_evaluate_from_signal`'s exact discipline: a
    `level` is set ONLY when the restaurant's own configured answer-mapping
    resolved one (never fabricated here); when no level is given, the raw
    answer is still preserved as `evidence_text` so a human (or a later
    evaluation pass) can use it, without silently inventing certainty
    (task §19 — "missing evidence must never become negative evidence").
    Never overwrites a HUMAN_* origin evaluation (task §27's own "do not
    overwrite previous evidence") — a Selezionatore's own decision always
    takes precedence over a candidate's self-report."""

    evaluation = session.get(m.PrimaryScreeningCriterionEvaluation, evaluation_id)
    if evaluation is None:
        raise ValueError(f"No PrimaryScreeningCriterionEvaluation with id {evaluation_id}")
    if evaluation.origin in (psm.HUMAN_ENTERED, psm.HUMAN_CONFIRMED, psm.HUMAN_OVERRIDDEN):
        return evaluation

    evaluation.evidence_text = (
        f"{evaluation.evidence_text}\n{evidence_text}" if evaluation.evidence_text else evidence_text
    )
    evaluation.evidence_source = evidence_source
    evaluation.evidence_items = list(evaluation.evidence_items or []) + [{
        "source_type": evidence_source, "source_reference": "candidate self-report",
        "evidence_text": evidence_text, "interpretation": None,
    }]

    if level is not None:
        psm.validate_level(level)
        evaluation.system_level = level
        evaluation.effective_level = level
        evaluation.status = psm.EVALUATED
        evaluation.origin = psm.SYSTEM_GENERATED
    elif evaluation.status == psm.NOT_EVALUATED:
        # Task §20 — genuinely new information was recorded, but not
        # resolvable to a level deterministically; explicit
        # INSUFFICIENT_EVIDENCE is the honest state, never a silent level 0.
        evaluation.status = psm.INSUFFICIENT_EVIDENCE

    session.flush()
    run = session.get(m.PrimaryScreeningRun, evaluation.run_id)
    _recompute_run(session, run)
    return evaluation


def mark_insufficient_evidence(session: Session, evaluation_id: int, *, note: str | None = None) -> m.PrimaryScreeningCriterionEvaluation:
    evaluation = session.get(m.PrimaryScreeningCriterionEvaluation, evaluation_id)
    if evaluation is None:
        raise ValueError(f"No PrimaryScreeningCriterionEvaluation with id {evaluation_id}")
    evaluation.status = psm.INSUFFICIENT_EVIDENCE
    evaluation.effective_level = None
    if note:
        evaluation.explanation = note
    session.flush()

    run = session.get(m.PrimaryScreeningRun, evaluation.run_id)
    _recompute_run(session, run)
    return evaluation


def override_hard_disqualifier(session: Session, evaluation_id: int, *, reason: str) -> m.PrimaryScreeningCriterionEvaluation:
    """Task §8 — a mandatory free-text reason is required; the system-
    detected Hard Disqualifier, its Criterion, level, and evidence all
    remain visible afterward (task's own "do not erase historical
    evidence") — only `hard_disqualifier_overridden` and the override
    metadata are set. `_recompute_run` then excludes this evaluation from
    `Run.has_active_hard_disqualifier`, which is what actually returns the
    Application to the normal pool / normal Selection flow (task §23)."""

    if not reason or not reason.strip():
        raise ValueError("A reason is mandatory to override a Hard Disqualifier.")
    evaluation = session.get(m.PrimaryScreeningCriterionEvaluation, evaluation_id)
    if evaluation is None:
        raise ValueError(f"No PrimaryScreeningCriterionEvaluation with id {evaluation_id}")
    if not evaluation.is_active_hard_disqualifier:
        raise ValueError("This Criterion Evaluation is not an active Hard Disqualifier.")

    evaluation.hard_disqualifier_overridden = True
    evaluation.hard_disqualifier_override_reason = reason
    evaluation.hard_disqualifier_overridden_at = datetime.utcnow()
    session.flush()

    run = session.get(m.PrimaryScreeningRun, evaluation.run_id)
    _recompute_run(session, run)
    return evaluation


# ---------------------------------------------------------------------------
# Primary Screening Queue (task §19/§20/§21/§22) — internal ordering only;
# the Priority Index number itself is never returned for direct display.
# ---------------------------------------------------------------------------

def _latest_runs_by_application(session: Session, restaurant_id: int | None) -> dict[int, m.PrimaryScreeningRun]:
    stmt = select(m.PrimaryScreeningRun).order_by(m.PrimaryScreeningRun.application_id, m.PrimaryScreeningRun.id.desc())
    if restaurant_id is not None:
        stmt = stmt.where(m.PrimaryScreeningRun.restaurant_id == restaurant_id)
    latest: dict[int, m.PrimaryScreeningRun] = {}
    for run in session.scalars(stmt).all():
        if run.application_id not in latest:
            latest[run.application_id] = run
    return latest


def list_normal_pool(session: Session, restaurant_id: int | None, *, limit: int | None = None) -> list[m.PrimaryScreeningRun]:
    """Task §19/§21 — the NORMAL POOL, ordered by the internal Priority
    Index descending. `limit` is a pure display convenience (e.g. "first
    20") — it never changes any underlying decision (task §21's own
    instruction)."""

    latest = _latest_runs_by_application(session, restaurant_id)
    normal = sorted(
        (run for run in latest.values() if not run.has_active_hard_disqualifier),
        key=lambda run: run.priority_index, reverse=True,
    )
    return normal[:limit] if limit is not None else normal


def list_hard_disqualifier_pool(session: Session, restaurant_id: int | None) -> list[m.PrimaryScreeningRun]:
    """Task §20 — the separate, clearly visible Hard Disqualifier pool.
    Applications here are never deleted and remain fully searchable."""

    latest = _latest_runs_by_application(session, restaurant_id)
    return sorted(
        (run for run in latest.values() if run.has_active_hard_disqualifier),
        key=lambda run: run.priority_index, reverse=True,
    )


def run_screening_for_unscreened_applications(
    session: Session, restaurant_id: int | None, *, ai_generate_json_fn: Callable | None = None,
) -> list[m.PrimaryScreeningRun]:
    """A practical bulk convenience for the task's own "200 Applications"
    use case (task §12: "Processing 200 Applications must not require the
    Selezionatore to manually open each one first.") — screens every
    Application in this restaurant that does not yet have a Primary
    Screening Run, evaluating every applicable Criterion for each one
    (deterministic Signal mapping first, the generic AI-assisted evaluator
    second — see `create_screening_run`). Never re-screens (and so never
    silently changes) an Application that already has one; use
    `create_screening_run` directly for an explicit, Selezionatore-chosen
    re-evaluation (task §12/3D-FIX §13). One Application's failure never
    stops the batch: `create_screening_run` itself never raises for an
    unresolved/failed Criterion, only for a genuinely missing Application."""

    applications = app_svc.list_applications(session, restaurant_id=restaurant_id)
    created = []
    for application in applications:
        if get_latest_run_for_application(session, application.id) is None:
            created.append(create_screening_run(session, application.id, ai_generate_json_fn=ai_generate_json_fn))
    return created


# ---------------------------------------------------------------------------
# Selezionatore notes (Task 3D-FIX §16) — reuses `application_service`'s
# `ApplicationNote` mechanism (Task 3C-FIX) with a context tag, rather than
# inventing a parallel notes system for Primary Screening.
# ---------------------------------------------------------------------------

def add_run_note(session: Session, run_id: int, note_text: str) -> m.ApplicationNote:
    run = session.get(m.PrimaryScreeningRun, run_id)
    if run is None:
        raise ValueError(f"No PrimaryScreeningRun with id {run_id}")
    return app_svc.add_note(session, run.application_id, note_text, context_type=NOTE_CONTEXT_RUN, context_id=run.id)


def list_run_notes(session: Session, run_id: int) -> list[m.ApplicationNote]:
    run = session.get(m.PrimaryScreeningRun, run_id)
    if run is None:
        return []
    return app_svc.list_notes(session, run.application_id, context_type=NOTE_CONTEXT_RUN, context_id=run.id)


def add_evaluation_note(session: Session, evaluation_id: int, note_text: str) -> m.ApplicationNote:
    evaluation = session.get(m.PrimaryScreeningCriterionEvaluation, evaluation_id)
    if evaluation is None:
        raise ValueError(f"No PrimaryScreeningCriterionEvaluation with id {evaluation_id}")
    run = session.get(m.PrimaryScreeningRun, evaluation.run_id)
    return app_svc.add_note(
        session, run.application_id, note_text, context_type=NOTE_CONTEXT_EVALUATION, context_id=evaluation.id,
    )


def list_evaluation_notes(session: Session, evaluation_id: int) -> list[m.ApplicationNote]:
    evaluation = session.get(m.PrimaryScreeningCriterionEvaluation, evaluation_id)
    if evaluation is None:
        return []
    run = session.get(m.PrimaryScreeningRun, evaluation.run_id)
    return app_svc.list_notes(
        session, run.application_id, context_type=NOTE_CONTEXT_EVALUATION, context_id=evaluation.id,
    )
