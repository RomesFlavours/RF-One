"""Selection Signal + Review Priority — service layer (Task 3C). Mirrors
`requirements_service.py` (Signal Definitions ~ Requirements) and
`fit_assessment_service.py` (Signal Observations ~ Requirement Assessments)
exactly, reusing `core/signal_model.py`'s vocabulary and
`core/fit_assessment_model.py`'s evidence vocabulary rather than inventing
either again. Flask routes should call into this module rather than
touching `.. models` directly.

Fundamental boundary (concept note §2/§9): a Signal Definition is WHAT to
look for; a Signal Observation is what the AVAILABLE EVIDENCE currently
says about it for one Application; a Review Priority Policy decides HOW
MUCH a detected Signal matters. Nothing here ever ranks candidates,
produces a hiring decision, or discards an Application — Review Priority is
always one of four categories with explicit reasons, never a score.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import application_service as app_svc
from . import fit_assessment_service as fa_svc
from . import persistence
from .core import fit_assessment_model as fam, requirement_model as rm, signal_model as sm
from .industry import restaurant as restaurant_industry
from .signal_detector import DetectionContext, generate_signal_evidence

RESUME_STAGE = "RESUME"


def _validate_family(value: str) -> None:
    if value not in sm.SIGNAL_FAMILIES:
        raise ValueError(f"Unknown signal family {value!r}; expected one of {sm.SIGNAL_FAMILIES}")


def _validate_signal_status(value: str) -> None:
    if value not in sm.SIGNAL_STATUSES:
        raise ValueError(f"Unknown signal status {value!r}; expected one of {sm.SIGNAL_STATUSES}")


def _validate_stages(values: list[str]) -> None:
    unknown = [v for v in values if v not in rm.ASSESSMENT_STAGES]
    if unknown:
        raise ValueError(f"Unknown assessment stage(s) {unknown!r}; expected one of {rm.ASSESSMENT_STAGES}")


def _validate_evidence_sources(values: list[str]) -> None:
    unknown = [v for v in values if v not in fam.EVIDENCE_SOURCE_TYPES]
    if unknown:
        raise ValueError(f"Unknown evidence source(s) {unknown!r}; expected one of {fam.EVIDENCE_SOURCE_TYPES}")


def _validate_contribution(value: str) -> None:
    if value not in sm.PRIORITY_CONTRIBUTIONS:
        raise ValueError(f"Unknown priority contribution {value!r}; expected one of {sm.PRIORITY_CONTRIBUTIONS}")


# ---------------------------------------------------------------------------
# Signal Definitions (concept note §5) — restaurant-configurable.
# ---------------------------------------------------------------------------

def create_signal_definition(
    session: Session, *, restaurant_id: int | None, name: str, signal_family: str,
    description: str | None = None, signal_subtype: str | None = None,
    assessment_stages: list[str] | None = None, evidence_sources_allowed: list[str] | None = None,
    detection_guidance: str | None = None, evidence_positive: str | None = None,
    evidence_contrary: str | None = None, evidence_insufficient: str | None = None,
) -> m.SignalDefinition:
    _validate_family(signal_family)
    assessment_stages = list(assessment_stages or [])
    evidence_sources_allowed = list(evidence_sources_allowed or [])
    _validate_stages(assessment_stages)
    _validate_evidence_sources(evidence_sources_allowed)

    definition = m.SignalDefinition(
        restaurant_id=restaurant_id, name=name, description=description, signal_family=signal_family,
        signal_subtype=signal_subtype, assessment_stages=assessment_stages,
        evidence_sources_allowed=evidence_sources_allowed, detection_guidance=detection_guidance,
        evidence_positive=evidence_positive, evidence_contrary=evidence_contrary,
        evidence_insufficient=evidence_insufficient,
    )
    session.add(definition)
    session.flush()
    return definition


def list_signal_definitions(
    session: Session, *, restaurant_id: int | None = None, signal_family: str | None = None,
    active_only: bool = True,
) -> list[m.SignalDefinition]:
    stmt = select(m.SignalDefinition).order_by(m.SignalDefinition.signal_family, m.SignalDefinition.name)
    if restaurant_id is not None:
        stmt = stmt.where(m.SignalDefinition.restaurant_id == restaurant_id)
    if signal_family is not None:
        stmt = stmt.where(m.SignalDefinition.signal_family == signal_family)
    if active_only:
        stmt = stmt.where(m.SignalDefinition.is_active.is_(True))
    return list(session.scalars(stmt).all())


def get_signal_definition(session: Session, signal_definition_id: int) -> m.SignalDefinition | None:
    return session.get(m.SignalDefinition, signal_definition_id)


def update_signal_definition(session: Session, signal_definition_id: int, **fields) -> m.SignalDefinition:
    definition = session.get(m.SignalDefinition, signal_definition_id)
    if definition is None:
        raise ValueError(f"No SignalDefinition with id {signal_definition_id}")

    allowed = {
        "name", "description", "signal_family", "signal_subtype", "assessment_stages",
        "evidence_sources_allowed", "detection_guidance", "evidence_positive", "evidence_contrary",
        "evidence_insufficient", "is_active",
    }
    for key in fields:
        if key not in allowed:
            raise ValueError(f"Cannot set {key!r} on a SignalDefinition through update_signal_definition")
    if "signal_family" in fields:
        _validate_family(fields["signal_family"])
    if "assessment_stages" in fields:
        _validate_stages(fields["assessment_stages"])
        fields["assessment_stages"] = list(fields["assessment_stages"])
    if "evidence_sources_allowed" in fields:
        _validate_evidence_sources(fields["evidence_sources_allowed"])
        fields["evidence_sources_allowed"] = list(fields["evidence_sources_allowed"])

    for key, value in fields.items():
        setattr(definition, key, value)
    if fields:
        definition.version += 1
    session.flush()
    return definition


def deactivate_signal_definition(session: Session, signal_definition_id: int) -> m.SignalDefinition:
    return update_signal_definition(session, signal_definition_id, is_active=False)


def reactivate_signal_definition(session: Session, signal_definition_id: int) -> m.SignalDefinition:
    return update_signal_definition(session, signal_definition_id, is_active=True)


# ---------------------------------------------------------------------------
# Signal Observations (concept note §6) — the Application x SignalDefinition
# unit. Exactly one row per pair; evidence enriches the SAME row.
# ---------------------------------------------------------------------------

def get_or_create_observation(session: Session, application_id: int, signal_definition_id: int) -> m.SignalObservation:
    stmt = select(m.SignalObservation).where(
        m.SignalObservation.application_id == application_id,
        m.SignalObservation.signal_definition_id == signal_definition_id,
    )
    existing = session.scalars(stmt).first()
    if existing is not None:
        return existing

    observation = m.SignalObservation(
        application_id=application_id, signal_definition_id=signal_definition_id,
        status=sm.NOT_ASSESSED, origin=fam.SYSTEM_GENERATED,
    )
    session.add(observation)
    session.flush()
    return observation


def list_observations(session: Session, application_id: int) -> list[m.SignalObservation]:
    stmt = (
        select(m.SignalObservation)
        .where(m.SignalObservation.application_id == application_id)
        .order_by(m.SignalObservation.id)
    )
    return list(session.scalars(stmt).all())


def mark_not_assessed(session: Session, observation_id: int) -> m.SignalObservation:
    """No evidence gathered — the Signal is not legitimately assessable
    with what's currently available (concept note's own NOT_ASSESSED
    status). Never overwrites a human-touched observation."""

    observation = session.get(m.SignalObservation, observation_id)
    if observation is None:
        raise ValueError(f"No SignalObservation with id {observation_id}")
    if observation.origin == fam.SYSTEM_GENERATED:
        observation.status = sm.NOT_ASSESSED
        observation.confidence = None
        observation.rationale = None
    session.flush()
    return observation


def add_evidence(
    session: Session, signal_observation_id: int, *, source_type: str, evidence_classification: str,
    evidence_relationship: str, confidence: str = fam.CONFIDENCE_UNKNOWN, evidence_text: str | None = None,
    source_stage: str | None = None, source_reference: str | None = None, explanation: str | None = None,
    is_system_generated: bool = False, rationale: str | None = None, detected_pattern: str | None = None,
) -> m.SignalEvidenceItem:
    """Appends one evidence item — never overwrites or removes existing
    evidence, mirroring `fit_assessment_service.add_evidence()` exactly,
    including the origin-lock rule: a human-touched observation's `status`
    is never silently changed by this function, only its evidence list
    grows."""

    if source_type not in fam.EVIDENCE_SOURCE_TYPES:
        raise ValueError(f"Unknown evidence source type {source_type!r}")
    if evidence_classification not in fam.EVIDENCE_CLASSIFICATIONS:
        raise ValueError(f"Unknown evidence classification {evidence_classification!r}")
    if evidence_relationship not in fam.EVIDENCE_RELATIONSHIPS:
        raise ValueError(f"Unknown evidence relationship {evidence_relationship!r}")
    if confidence not in fam.CONFIDENCE_LEVELS:
        raise ValueError(f"Unknown confidence {confidence!r}")

    observation = session.get(m.SignalObservation, signal_observation_id)
    if observation is None:
        raise ValueError(f"No SignalObservation with id {signal_observation_id}")

    evidence = m.SignalEvidenceItem(
        signal_observation_id=observation.id, source_type=source_type, source_stage=source_stage,
        source_reference=source_reference, evidence_text=evidence_text,
        evidence_classification=evidence_classification, evidence_relationship=evidence_relationship,
        confidence=confidence, explanation=explanation, is_system_generated=is_system_generated,
    )
    session.add(evidence)
    session.flush()
    # See `fit_assessment_service.py`'s matching comment: a row added via
    # its FK column does not update an already-loaded relationship
    # collection, so force a fresh reload before recomputing.
    session.expire(observation, ["evidence_items"])

    new_status = sm.compute_signal_status_from_evidence(list(observation.evidence_items))
    if observation.origin == fam.SYSTEM_GENERATED:
        observation.status = new_status
    if rationale:
        observation.rationale = rationale
    if detected_pattern:
        observation.detected_pattern = detected_pattern
    if observation.evidence_items:
        observation.confidence = max(
            (e.confidence for e in observation.evidence_items if e.evidence_relationship in (fam.SUPPORTS, fam.CONTRADICTS)),
            key=lambda c: fam.CONFIDENCE_ORDER.get(c, 0), default=None,
        )
    session.flush()
    return evidence


def human_confirm(session: Session, observation_id: int, *, note: str | None = None) -> m.SignalObservation:
    observation = session.get(m.SignalObservation, observation_id)
    if observation is None:
        raise ValueError(f"No SignalObservation with id {observation_id}")
    observation.origin = fam.HUMAN_CONFIRMED
    if note:
        observation.rationale = note
    session.flush()
    return observation


def human_override(
    session: Session, observation_id: int, *, new_status: str, reason: str | None = None,
) -> m.SignalObservation:
    _validate_signal_status(new_status)
    observation = session.get(m.SignalObservation, observation_id)
    if observation is None:
        raise ValueError(f"No SignalObservation with id {observation_id}")
    observation.status = new_status
    observation.origin = fam.HUMAN_OVERRIDDEN
    observation.override_reason = reason
    observation.overridden_at = datetime.utcnow()
    session.flush()
    return observation


# ---------------------------------------------------------------------------
# Review Priority Policy (concept note §9) — separate from Signal
# detection: decides how much a detected Signal matters, restaurant by
# restaurant.
# ---------------------------------------------------------------------------

def create_policy(session: Session, *, restaurant_id: int | None, name: str) -> m.ReviewPriorityPolicy:
    policy = m.ReviewPriorityPolicy(restaurant_id=restaurant_id, name=name)
    session.add(policy)
    session.flush()
    return policy


def list_policies(session: Session, *, restaurant_id: int | None = None) -> list[m.ReviewPriorityPolicy]:
    stmt = select(m.ReviewPriorityPolicy).order_by(m.ReviewPriorityPolicy.name)
    if restaurant_id is not None:
        stmt = stmt.where(m.ReviewPriorityPolicy.restaurant_id == restaurant_id)
    return list(session.scalars(stmt).all())


def get_policy(session: Session, policy_id: int) -> m.ReviewPriorityPolicy | None:
    return session.get(m.ReviewPriorityPolicy, policy_id)


def update_policy(session: Session, policy_id: int, *, name: str | None = None) -> m.ReviewPriorityPolicy:
    policy = session.get(m.ReviewPriorityPolicy, policy_id)
    if policy is None:
        raise ValueError(f"No ReviewPriorityPolicy with id {policy_id}")
    if name:
        policy.name = name
    session.flush()
    return policy


def deactivate_policy(session: Session, policy_id: int) -> m.ReviewPriorityPolicy:
    return update_policy_active(session, policy_id, is_active=False)


def reactivate_policy(session: Session, policy_id: int) -> m.ReviewPriorityPolicy:
    return update_policy_active(session, policy_id, is_active=True)


def update_policy_active(session: Session, policy_id: int, *, is_active: bool) -> m.ReviewPriorityPolicy:
    policy = session.get(m.ReviewPriorityPolicy, policy_id)
    if policy is None:
        raise ValueError(f"No ReviewPriorityPolicy with id {policy_id}")
    policy.is_active = is_active
    session.flush()
    return policy


def add_policy_rule(
    session: Session, policy_id: int, *, signal_definition_id: int, observed_status: str, contribution: str,
) -> m.ReviewPriorityPolicyRule:
    _validate_signal_status(observed_status)
    _validate_contribution(contribution)
    rule = m.ReviewPriorityPolicyRule(
        policy_id=policy_id, signal_definition_id=signal_definition_id, observed_status=observed_status,
        contribution=contribution,
    )
    session.add(rule)
    session.flush()
    return rule


def update_policy_rule(session: Session, rule_id: int, *, contribution: str) -> m.ReviewPriorityPolicyRule:
    """Edits how much an EXISTING (Signal Definition, observed status) pair
    contributes — never the pair itself (a policy cannot contradict itself
    for the same Signal/status, per the unique constraint backing this
    table; changing the pair means adding a new rule instead)."""

    _validate_contribution(contribution)
    rule = session.get(m.ReviewPriorityPolicyRule, rule_id)
    if rule is None:
        raise ValueError(f"No ReviewPriorityPolicyRule with id {rule_id}")
    rule.contribution = contribution
    session.flush()
    return rule


def deactivate_policy_rule(session: Session, rule_id: int) -> m.ReviewPriorityPolicyRule:
    rule = session.get(m.ReviewPriorityPolicyRule, rule_id)
    if rule is None:
        raise ValueError(f"No ReviewPriorityPolicyRule with id {rule_id}")
    rule.is_active = False
    session.flush()
    return rule


def reactivate_policy_rule(session: Session, rule_id: int) -> m.ReviewPriorityPolicyRule:
    rule = session.get(m.ReviewPriorityPolicyRule, rule_id)
    if rule is None:
        raise ValueError(f"No ReviewPriorityPolicyRule with id {rule_id}")
    rule.is_active = True
    session.flush()
    return rule


def remove_policy_rule(session: Session, rule_id: int) -> None:
    """A hard delete (task §4: "add/edit/remove/deactivate policy rules" —
    remove is distinct from deactivate). Removing a rule never touches the
    SignalDefinition it referenced or any already-recorded Signal
    Observation — only how much that (definition, status) pair contributes
    to a FUTURE Review Priority computation."""

    rule = session.get(m.ReviewPriorityPolicyRule, rule_id)
    if rule is not None:
        session.delete(rule)
        session.flush()


def get_active_policy(session: Session, restaurant_id: int | None) -> m.ReviewPriorityPolicy | None:
    stmt = (
        select(m.ReviewPriorityPolicy)
        .where(m.ReviewPriorityPolicy.restaurant_id == restaurant_id, m.ReviewPriorityPolicy.is_active.is_(True))
        .order_by(m.ReviewPriorityPolicy.updated_at.desc())
    )
    return session.scalars(stmt).first()


def compute_and_apply_review_priority(session: Session, application_id: int) -> m.Application:
    """Reads every current Signal Observation for this Application, maps
    each DETECTED/POSSIBLE one through the restaurant's active Review
    Priority Policy (if any) into a qualitative contribution, and computes
    the resulting category via `core.signal_model.compute_review_priority()`
    (concept note's own pipeline: EVIDENCE -> SIGNAL -> RESTAURANT REVIEW
    PRIORITY POLICY -> REVIEW PRIORITY). With no active policy, or no
    Signal contributing either way, the result is STANDARD — never a
    default judgment invented on the restaurant's behalf.

    Always sets `review_priority_system`; only updates
    `review_priority_effective` when `review_priority_origin` is still
    SYSTEM_GENERATED — a Selezionatore override is never silently
    recalculated away (same rule as `RequirementAssessment`/
    `SignalObservation` effective-status handling)."""

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")

    policy = get_active_policy(session, application.restaurant_id)
    contributions: list[tuple[str, str]] = []
    if policy is not None:
        rules_by_key = {
            (r.signal_definition_id, r.observed_status): r.contribution for r in policy.rules if r.is_active
        }
        for observation in list_observations(session, application_id):
            key = (observation.signal_definition_id, observation.status)
            contribution = rules_by_key.get(key)
            if contribution and contribution != sm.NEUTRAL_CONTRIBUTION:
                reason = (
                    f"{observation.signal_definition.name} ({observation.status})"
                    + (f" — {observation.rationale}" if observation.rationale else "")
                )
                contributions.append((contribution, reason))

    category, reasons = sm.compute_review_priority(contributions)
    application.review_priority_system = category
    application.review_priority_reasons = reasons
    if application.review_priority_origin == fam.SYSTEM_GENERATED:
        application.review_priority_effective = category
    session.flush()
    return application


def human_confirm_priority(session: Session, application_id: int, *, note: str | None = None) -> m.Application:
    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")
    application.review_priority_origin = fam.HUMAN_CONFIRMED
    if note:
        application.notes = note
    session.flush()
    return application


def human_override_priority(
    session: Session, application_id: int, *, new_priority: str, reason: str | None = None,
) -> m.Application:
    if new_priority not in sm.REVIEW_PRIORITY_CATEGORIES:
        raise ValueError(f"Unknown Review Priority {new_priority!r}; expected one of {sm.REVIEW_PRIORITY_CATEGORIES}")
    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")
    application.review_priority_effective = new_priority
    application.review_priority_origin = fam.HUMAN_OVERRIDDEN
    application.review_priority_override_reason = reason
    application.review_priority_overridden_at = datetime.utcnow()
    session.flush()
    return application


# ---------------------------------------------------------------------------
# Résumé-stage Signal generation (also the refresh entry point) — builds
# the `DetectionContext` from real, already-persisted evidence (this
# Application's CandidateCVProfile, its person's PRIOR Applications, and an
# existing Fit Assessment's summary where one exists) and runs every active
# Signal Definition's detector against it.
# ---------------------------------------------------------------------------

def _build_detection_context(session: Session, application: m.Application) -> DetectionContext:
    profile = persistence.to_profile(application.candidate)

    target_role_family = restaurant_industry.role_family(application.target_role)
    target_normalized_role = application.target_role

    prior_pairs = []
    for prior in app_svc.list_prior_applications(session, application.id):
        prior_pairs.append((prior.target_role, persistence.to_profile(prior.candidate)))

    fit_assessments = fa_svc.list_fit_assessments_for_candidate(session, application.candidate_id)
    fit_summary = fa_svc.get_summary(session, fit_assessments[0].id) if fit_assessments else None

    restaurant = session.get(m.Restaurant, application.restaurant_id) if application.restaurant_id else None

    return DetectionContext(
        profile=profile, target_role_family=target_role_family, target_normalized_role=target_normalized_role,
        prior_target_roles_and_profiles=prior_pairs, fit_assessment_summary=fit_summary,
        restaurant_name=restaurant.name if restaurant else None,
    )


def generate_resume_stage_signals(session: Session, application_id: int) -> m.Application:
    """(Re)generates RESUME-stage Signal Observations for every active
    Signal Definition available to this Application's restaurant. Safe to
    call more than once (refresh): existing system-generated evidence per
    observation is replaced with a fresh pass; human-touched observations
    (`origin` any HUMAN_* value) keep their recorded `status` — only new
    evidence may be appended to them by `add_evidence()` directly, never a
    silent overwrite here. Always finishes by recomputing Review Priority
    (`compute_and_apply_review_priority`)."""

    application = session.get(m.Application, application_id)
    if application is None:
        raise ValueError(f"No Application with id {application_id}")

    context = _build_detection_context(session, application)
    definitions = list_signal_definitions(session, restaurant_id=application.restaurant_id, active_only=True)

    for definition in definitions:
        observation = get_or_create_observation(session, application.id, definition.id)

        if RESUME_STAGE not in (definition.assessment_stages or []):
            mark_not_assessed(session, observation.id)
            continue

        for evidence in list(observation.evidence_items):
            if evidence.is_system_generated:
                session.delete(evidence)
        session.flush()
        session.expire(observation, ["evidence_items"])

        drafts = generate_signal_evidence(definition, context)
        if not drafts:
            if observation.origin == fam.SYSTEM_GENERATED:
                observation.status = sm.NOT_DETECTED
            session.flush()
            continue

        for draft in drafts:
            add_evidence(
                session, observation.id, source_type=draft.source_type,
                evidence_classification=draft.evidence_classification,
                evidence_relationship=draft.evidence_relationship, confidence=draft.confidence,
                evidence_text=draft.evidence_text, source_stage=RESUME_STAGE,
                source_reference=draft.source_reference, explanation=draft.explanation,
                is_system_generated=draft.is_system_generated, detected_pattern=draft.detected_pattern,
            )

    compute_and_apply_review_priority(session, application.id)
    session.flush()
    return application
