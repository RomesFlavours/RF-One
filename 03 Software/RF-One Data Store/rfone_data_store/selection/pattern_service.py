"""Selection Feedback Intelligence — Pattern Definition / Signature /
Example / Observation / Working Profile / Case Comparison service
(Selection Feedback Intelligence Foundation task).

THE PAST IS IMMUTABLE. `get_or_create_pattern_definition_snapshot()`
mirrors `outcome_service.get_or_create_outcome_definition_snapshot()`'s
exact idempotent-per-version discipline: editing a live Pattern Definition
bumps its `version` and never touches a prior Snapshot, so every
Observation/Comparison pinned to an earlier Snapshot keeps meaning exactly
what it meant when it was recorded.

Explicitly NOT implemented here (task §29 — out of scope for this
foundation task): autonomous Pattern discovery, automatic EMERGING ->
ESTABLISHED promotion, automatic conflict resolution between overlapping
scopes, a similarity-search engine, or an AI Signature-proposal workflow.
`update_pattern_definition()` never promotes maturity on its own; nothing
in this module ever changes `maturity`/`status` except an explicit caller-
supplied value.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .core import pattern_model as pm


# ---------------------------------------------------------------------------
# Pattern Definition (live, versioned) — task §3
# ---------------------------------------------------------------------------


def create_pattern_definition(
    session: Session, *, restaurant_id: int | None, name: str, description: str | None = None,
    scope: str = pm.SCOPE_GENERAL, applicability_context: str | None = None,
    status: str = pm.STATUS_PROPOSED, maturity: str = pm.MATURITY_EMERGING,
    persistence_type: str = pm.PERSISTENCE_STRUCTURAL, signature: dict | None = None,
    creation_provenance: str = pm.PROVENANCE_HUMAN_AUTHORED, created_by: str | None = None,
    required_authority_level_id: int | None = None,
) -> m.SelectionPatternDefinition:
    pm.validate_pattern_scope(scope)
    pm.validate_pattern_status(status)
    pm.validate_pattern_maturity(maturity)
    pm.validate_pattern_persistence_type(persistence_type)
    pm.validate_provenance(creation_provenance)

    definition = m.SelectionPatternDefinition(
        restaurant_id=restaurant_id, name=name, description=description, scope=scope,
        applicability_context=applicability_context, status=status, maturity=maturity,
        persistence_type=persistence_type, signature=signature or {}, creation_provenance=creation_provenance,
        created_by=created_by, required_authority_level_id=required_authority_level_id,
    )
    session.add(definition)
    session.flush()
    get_or_create_pattern_definition_snapshot(session, definition.id)
    return definition


def get_pattern_definition(session: Session, definition_id: int) -> m.SelectionPatternDefinition | None:
    return session.get(m.SelectionPatternDefinition, definition_id)


def list_pattern_definitions(
    session: Session, *, restaurant_id: int | None = None, scope: str | None = None,
    is_active: bool | None = None,
) -> list[m.SelectionPatternDefinition]:
    stmt = select(m.SelectionPatternDefinition)
    if restaurant_id is not None:
        stmt = stmt.where(m.SelectionPatternDefinition.restaurant_id == restaurant_id)
    if scope is not None:
        stmt = stmt.where(m.SelectionPatternDefinition.scope == scope)
    if is_active is not None:
        stmt = stmt.where(m.SelectionPatternDefinition.is_active == is_active)
    stmt = stmt.order_by(m.SelectionPatternDefinition.id)
    return list(session.scalars(stmt).all())


def update_pattern_definition(session: Session, definition_id: int, **fields) -> m.SelectionPatternDefinition:
    """Edits the LIVE Pattern Definition and bumps `version` — never
    touches any existing Snapshot (task's core immutability principle).
    The caller must explicitly pass `maturity`/`status` to change them;
    this function never promotes either on its own (task §4's "no
    automatic promotion")."""

    definition = session.get(m.SelectionPatternDefinition, definition_id)
    if definition is None:
        raise ValueError(f"No SelectionPatternDefinition with id {definition_id}")

    for key in ("scope", "status", "maturity", "persistence_type"):
        if key in fields and fields[key] is not None:
            {
                "scope": pm.validate_pattern_scope, "status": pm.validate_pattern_status,
                "maturity": pm.validate_pattern_maturity, "persistence_type": pm.validate_pattern_persistence_type,
            }[key](fields[key])

    allowed = {
        "name", "description", "scope", "applicability_context", "status", "maturity", "persistence_type",
        "signature", "required_authority_level_id",
    }
    changed = False
    for key, value in fields.items():
        if key not in allowed:
            raise ValueError(f"Cannot update SelectionPatternDefinition.{key} via update_pattern_definition")
        if getattr(definition, key) != value:
            setattr(definition, key, value)
            changed = True

    if changed:
        definition.version += 1
    session.flush()
    get_or_create_pattern_definition_snapshot(session, definition.id)
    return definition


def deactivate_pattern_definition(session: Session, definition_id: int) -> m.SelectionPatternDefinition:
    definition = session.get(m.SelectionPatternDefinition, definition_id)
    if definition is None:
        raise ValueError(f"No SelectionPatternDefinition with id {definition_id}")
    definition.is_active = False
    session.flush()
    return definition


# ---------------------------------------------------------------------------
# Pattern Definition Snapshot — immutable per version (mirrors
# outcome_service.get_or_create_outcome_definition_snapshot exactly)
# ---------------------------------------------------------------------------


def get_or_create_pattern_definition_snapshot(
    session: Session, definition_id: int,
) -> m.SelectionPatternDefinitionSnapshot:
    definition = session.get(m.SelectionPatternDefinition, definition_id)
    if definition is None:
        raise ValueError(f"No SelectionPatternDefinition with id {definition_id}")

    existing = session.scalars(
        select(m.SelectionPatternDefinitionSnapshot).where(
            m.SelectionPatternDefinitionSnapshot.definition_id == definition_id,
            m.SelectionPatternDefinitionSnapshot.version == definition.version,
        )
    ).first()
    if existing is not None:
        return existing

    snapshot = m.SelectionPatternDefinitionSnapshot(
        definition_id=definition.id, version=definition.version, restaurant_id=definition.restaurant_id,
        name=definition.name, description=definition.description, scope=definition.scope,
        applicability_context=definition.applicability_context, status=definition.status,
        maturity=definition.maturity, persistence_type=definition.persistence_type,
        signature=dict(definition.signature or {}), creation_provenance=definition.creation_provenance,
        was_active=definition.is_active,
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def get_snapshot(session: Session, snapshot_id: int) -> m.SelectionPatternDefinitionSnapshot | None:
    return session.get(m.SelectionPatternDefinitionSnapshot, snapshot_id)


# ---------------------------------------------------------------------------
# Pattern Example — permanent knowledge asset (task §20), append-only
# ---------------------------------------------------------------------------


def add_pattern_example(
    session: Session, pattern_definition_id: int, *, example_type: str = pm.EXAMPLE_ORIGINAL,
    case_reference: dict | None = None, description: str | None = None, reason: str | None = None,
    provenance: str = pm.PROVENANCE_HUMAN_AUTHORED,
) -> m.SelectionPatternExample:
    pm.validate_pattern_example_type(example_type)
    pm.validate_provenance(provenance)
    definition = session.get(m.SelectionPatternDefinition, pattern_definition_id)
    if definition is None:
        raise ValueError(f"No SelectionPatternDefinition with id {pattern_definition_id}")

    example = m.SelectionPatternExample(
        pattern_definition_id=pattern_definition_id, definition_version_at_capture=definition.version,
        example_type=example_type, case_reference=case_reference or {}, description=description,
        reason=reason, provenance=provenance,
    )
    session.add(example)
    session.flush()
    return example


def list_pattern_examples(session: Session, pattern_definition_id: int) -> list[m.SelectionPatternExample]:
    stmt = (
        select(m.SelectionPatternExample)
        .where(m.SelectionPatternExample.pattern_definition_id == pattern_definition_id)
        .order_by(m.SelectionPatternExample.id)
    )
    return list(session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Pattern Case Comparison — task §7/§24, append-only
# ---------------------------------------------------------------------------


def record_case_comparison(
    session: Session, *, pattern_definition_id: int, application_id: int, classification: str,
    dimensions_compared: list | None = None, supporting_evidence_references: list | None = None,
    explanation: str | None = None, internal_numeric_value: float | None = None,
    provenance: str = pm.PROVENANCE_SYSTEM_GENERATED,
) -> m.SelectionPatternCaseComparison:
    pm.validate_comparison_classification(classification)
    pm.validate_provenance(provenance)
    snapshot = get_or_create_pattern_definition_snapshot(session, pattern_definition_id)

    comparison = m.SelectionPatternCaseComparison(
        pattern_definition_id=pattern_definition_id, pattern_definition_snapshot_id=snapshot.id,
        application_id=application_id, classification=classification,
        dimensions_compared=dimensions_compared or [], supporting_evidence_references=supporting_evidence_references or [],
        explanation=explanation, internal_numeric_value=internal_numeric_value, provenance=provenance,
    )
    session.add(comparison)
    session.flush()
    return comparison


def list_case_comparisons_for_pattern(
    session: Session, pattern_definition_id: int,
) -> list[m.SelectionPatternCaseComparison]:
    stmt = (
        select(m.SelectionPatternCaseComparison)
        .where(m.SelectionPatternCaseComparison.pattern_definition_id == pattern_definition_id)
        .order_by(m.SelectionPatternCaseComparison.id)
    )
    return list(session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Pattern Observation — task §8, append-only per fact; "supersede" only
# ever changes the OLD row's STATUS pointer (observation_status/
# superseded_by_id), never its recorded facts (role/relevance/explanation/
# evidence) — the same "state pointer vs. permanent fact" distinction
# `CandidateFlag.is_active` and `Application.current_stage` already draw
# elsewhere in this codebase.
# ---------------------------------------------------------------------------


def record_observation(
    session: Session, *, pattern_definition_id: int, application_id: int, person_id: int | None,
    stage: str, stage_occurrence_index: int = 1, role: str, relevance: str = pm.RELEVANCE_MEDIUM,
    explanation: str | None = None, evidence_references: list | None = None, rule_references: list | None = None,
    provenance: str = pm.PROVENANCE_SYSTEM_GENERATED,
) -> m.SelectionPatternObservation:
    pm.validate_observation_role(role)
    pm.validate_provenance(provenance)
    snapshot = get_or_create_pattern_definition_snapshot(session, pattern_definition_id)

    observation = m.SelectionPatternObservation(
        pattern_definition_id=pattern_definition_id, pattern_definition_snapshot_id=snapshot.id,
        application_id=application_id, person_id=person_id, stage=stage,
        stage_occurrence_index=stage_occurrence_index, observation_status=pm.OBSERVATION_ACTIVE,
        role=role, relevance=relevance, explanation=explanation,
        evidence_references=evidence_references or [], rule_references=rule_references or [],
        provenance=provenance,
    )
    session.add(observation)
    session.flush()
    return observation


def supersede_observation(
    session: Session, observation_id: int, **new_fields,
) -> m.SelectionPatternObservation:
    """Marks the OLD Observation `SUPERSEDED` (never edits its role/
    relevance/explanation/evidence — those remain exactly what was
    recorded) and inserts a brand-new `ACTIVE` Observation carrying
    `new_fields` (role/relevance/explanation/evidence_references/
    rule_references), defaulting anything not overridden to the old row's
    own value. Used while a Stage is still open, when new evidence changes
    RF-One's current read of a pattern (task §10's "may be recalculated or
    updated while the Stage remains open")."""

    old = session.get(m.SelectionPatternObservation, observation_id)
    if old is None:
        raise ValueError(f"No SelectionPatternObservation with id {observation_id}")

    new = record_observation(
        session,
        pattern_definition_id=old.pattern_definition_id, application_id=old.application_id,
        person_id=old.person_id, stage=old.stage, stage_occurrence_index=old.stage_occurrence_index,
        role=new_fields.get("role", old.role), relevance=new_fields.get("relevance", old.relevance),
        explanation=new_fields.get("explanation", old.explanation),
        evidence_references=new_fields.get("evidence_references", list(old.evidence_references or [])),
        rule_references=new_fields.get("rule_references", list(old.rule_references or [])),
        provenance=new_fields.get("provenance", old.provenance),
    )
    old.observation_status = pm.OBSERVATION_SUPERSEDED
    old.superseded_by_id = new.id
    session.flush()
    return new


def list_observations(
    session: Session, application_id: int, *, stage: str | None = None,
    stage_occurrence_index: int | None = None, active_only: bool = True,
) -> list[m.SelectionPatternObservation]:
    stmt = select(m.SelectionPatternObservation).where(
        m.SelectionPatternObservation.application_id == application_id
    )
    if stage is not None:
        stmt = stmt.where(m.SelectionPatternObservation.stage == stage)
    if stage_occurrence_index is not None:
        stmt = stmt.where(m.SelectionPatternObservation.stage_occurrence_index == stage_occurrence_index)
    if active_only:
        stmt = stmt.where(m.SelectionPatternObservation.observation_status == pm.OBSERVATION_ACTIVE)
    stmt = stmt.order_by(m.SelectionPatternObservation.id)
    return list(session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Working Pattern Profile — task §9/§10. Computed on read, never itself a
# persisted, separately-mutable row — RF-One's "current understanding" is
# always exactly the set of currently-ACTIVE Observations, so there is
# never a second copy that could drift out of sync with them.
# ---------------------------------------------------------------------------


def compute_working_pattern_profile(
    session: Session, application_id: int, *, stage: str | None = None,
) -> dict:
    """Returns a plain dict (not persisted) — task §9/§10's "dynamic while
    a Stage is open... may be recalculated." `stage=None` returns every
    currently-ACTIVE Observation across all Stages seen so far; passing a
    Stage narrows to that Stage only (the shape a Stage-close freeze
    uses)."""

    observations = list_observations(session, application_id, stage=stage, active_only=True)
    positive = [o for o in observations if o.role == pm.ROLE_POSITIVE]
    negative = [o for o in observations if o.role == pm.ROLE_NEGATIVE]
    modifiers = [o for o in observations if o.role in (pm.ROLE_MODIFIER, pm.ROLE_NEUTRALIZER)]

    return {
        "application_id": application_id,
        "stage": stage,
        "observations": observations,
        "positive_patterns": positive,
        "negative_patterns": negative,
        "modifiers": modifiers,
        "is_historical_truth": False,  # task §10 — never confuse this with a frozen Stage snapshot
    }
