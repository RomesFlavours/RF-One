"""Selection Feedback Intelligence — Pattern/Case-Memory vocabulary
(Selection Feedback Intelligence Foundation task). Mirrors every other
`core/*_model.py` module's role: vocabulary + small pure functions only, no
persistence.

THE PAST IS IMMUTABLE (task's own core principle). Nothing in this module,
or in the services built on top of it, ever overwrites a historical row —
new information is always appended and linked, never used to rewrite what
RF-One believed, predicted, or recorded at an earlier point in time.

This module is deliberately generic and reusable: it does not mention
Restaurant, FOH/BOH, or any other industry concept, the same Selection-Core
boundary `core/__init__.py` already enforces for the résumé-screening
engine. A Pattern Definition's actual vocabulary (which patterns exist,
what they mean) is restaurant/organization-authored DATA
(`models.SelectionPatternDefinition`), never hard-coded here — the same
"the SCALE is universal, the MEANING is restaurant data" split every other
Selection engine in this codebase already follows (mirrors
`core/primary_screening_model.py`, `core/outcome_model.py`).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Pattern Definition — scope hierarchy (task §3). More specific knowledge
# may coexist with broader knowledge; this task does not implement automatic
# conflict resolution between scopes beyond representing them.
# ---------------------------------------------------------------------------

SCOPE_GENERAL = "GENERAL"
SCOPE_BUSINESS_DOMAIN = "BUSINESS_DOMAIN"
SCOPE_ORGANIZATION = "ORGANIZATION"
SCOPE_ROLE_OR_JOB_FAMILY = "ROLE_OR_JOB_FAMILY"

PATTERN_SCOPES = (SCOPE_GENERAL, SCOPE_BUSINESS_DOMAIN, SCOPE_ORGANIZATION, SCOPE_ROLE_OR_JOB_FAMILY)


def validate_pattern_scope(value: str) -> None:
    if value not in PATTERN_SCOPES:
        raise ValueError(f"Unknown Pattern Definition scope {value!r}; expected one of {PATTERN_SCOPES}")


# ---------------------------------------------------------------------------
# Pattern Definition — lifecycle/status (task §3) — whether the definition
# itself is a proposal, in operative use, or retired. Deliberately SEPARATE
# from maturity (below) and from persistence type (below) — three
# independent dimensions, never collapsed into one flag.
# ---------------------------------------------------------------------------

STATUS_PROPOSED = "PROPOSED"
STATUS_ACTIVE = "ACTIVE"
STATUS_RETIRED = "RETIRED"

PATTERN_STATUSES = (STATUS_PROPOSED, STATUS_ACTIVE, STATUS_RETIRED)


def validate_pattern_status(value: str) -> None:
    if value not in PATTERN_STATUSES:
        raise ValueError(f"Unknown Pattern Definition status {value!r}; expected one of {PATTERN_STATUSES}")


# ---------------------------------------------------------------------------
# Pattern Maturity (task §4) — SEPARATE dimension from status/persistence.
# No automatic EMERGING -> ESTABLISHED promotion exists anywhere in this
# codebase; a future task may let RF-One PROPOSE the transition, but human
# governance decides it (task §4, §29 "no automatic maturity promotion").
# ---------------------------------------------------------------------------

MATURITY_EMERGING = "EMERGING"
MATURITY_ESTABLISHED = "ESTABLISHED"

PATTERN_MATURITIES = (MATURITY_EMERGING, MATURITY_ESTABLISHED)


def validate_pattern_maturity(value: str) -> None:
    if value not in PATTERN_MATURITIES:
        raise ValueError(f"Unknown Pattern maturity {value!r}; expected one of {PATTERN_MATURITIES}")


# ---------------------------------------------------------------------------
# Pattern Persistence type (task §5) — SEPARATE dimension again. STRUCTURAL
# patterns do not decay merely because time passes; CONTEXT_SENSITIVE
# patterns MAY later support contextual/time-based relevance reduction —
# no decay logic exists anywhere in this codebase yet (task §5/§29).
# ---------------------------------------------------------------------------

PERSISTENCE_STRUCTURAL = "STRUCTURAL"
PERSISTENCE_CONTEXT_SENSITIVE = "CONTEXT_SENSITIVE"

PATTERN_PERSISTENCE_TYPES = (PERSISTENCE_STRUCTURAL, PERSISTENCE_CONTEXT_SENSITIVE)


def validate_pattern_persistence_type(value: str) -> None:
    if value not in PATTERN_PERSISTENCE_TYPES:
        raise ValueError(
            f"Unknown Pattern persistence type {value!r}; expected one of {PATTERN_PERSISTENCE_TYPES}"
        )


# ---------------------------------------------------------------------------
# Pattern Signature dimension TYPES (task §6) — an open, extensible,
# NON-EXHAUSTIVE vocabulary of what a Signature's structured dimensions may
# reference. A `SelectionPatternDefinition.signature` is a JSON structure
# (see `models.py`), never constrained to only these — this tuple is seed
# vocabulary for UI/validation convenience only, mirroring exactly how
# `core/outcome_model.DRIVEN_BY_OPTIONS` and every restaurant-configurable
# "reason_choices" field elsewhere in this codebase work: the SET of
# meaningful dimensions is not RF-One's to fix permanently.
# ---------------------------------------------------------------------------

DIMENSION_EXPERIENCE_CONTEXT = "EXPERIENCE_CONTEXT"
DIMENSION_TRAJECTORY = "TRAJECTORY"
DIMENSION_DURATION = "DURATION"
DIMENSION_STABILITY = "STABILITY"
DIMENSION_RECENCY = "RECENCY"
DIMENSION_PROGRESSION = "PROGRESSION"
DIMENSION_ROLE_TRANSITIONS = "ROLE_TRANSITIONS"
DIMENSION_SKILLS = "SKILLS"
DIMENSION_TRAINING_BURDEN = "TRAINING_BURDEN"
DIMENSION_STAGE_BEHAVIOR = "STAGE_BEHAVIOR"
DIMENSION_SELECTION_EFFORT = "SELECTION_EFFORT"
DIMENSION_RULE_INTERACTION = "RULE_INTERACTION"

SUGGESTED_SIGNATURE_DIMENSIONS = (
    DIMENSION_EXPERIENCE_CONTEXT, DIMENSION_TRAJECTORY, DIMENSION_DURATION, DIMENSION_STABILITY,
    DIMENSION_RECENCY, DIMENSION_PROGRESSION, DIMENSION_ROLE_TRANSITIONS, DIMENSION_SKILLS,
    DIMENSION_TRAINING_BURDEN, DIMENSION_STAGE_BEHAVIOR, DIMENSION_SELECTION_EFFORT, DIMENSION_RULE_INTERACTION,
)


# ---------------------------------------------------------------------------
# Pattern comparison classification (task §7) — how a historical case
# classifies relative to a Pattern Definition. Deliberately NOT an
# artificial universal numeric similarity score (task's own explicit
# instruction) — an internal numeric value MAY exist for engineering
# convenience, but these natural, explainable categories are authoritative.
# ---------------------------------------------------------------------------

CONFIRMING_CASE = "CONFIRMING_CASE"
COUNTEREXAMPLE = "COUNTEREXAMPLE"
PARTIAL_MATCH = "PARTIAL_MATCH"
NOT_COMPARABLE = "NOT_COMPARABLE"

PATTERN_COMPARISON_CLASSIFICATIONS = (CONFIRMING_CASE, COUNTEREXAMPLE, PARTIAL_MATCH, NOT_COMPARABLE)


def validate_comparison_classification(value: str) -> None:
    if value not in PATTERN_COMPARISON_CLASSIFICATIONS:
        raise ValueError(
            f"Unknown Pattern comparison classification {value!r}; "
            f"expected one of {PATTERN_COMPARISON_CLASSIFICATIONS}"
        )


# ---------------------------------------------------------------------------
# Pattern Observation role (task §8) — a pattern is not forced to be always
# positive or negative; it may modify or neutralize another signal.
# ---------------------------------------------------------------------------

ROLE_POSITIVE = "POSITIVE"
ROLE_NEGATIVE = "NEGATIVE"
ROLE_MODIFIER = "MODIFIER"
ROLE_NEUTRALIZER = "NEUTRALIZER"

OBSERVATION_ROLES = (ROLE_POSITIVE, ROLE_NEGATIVE, ROLE_MODIFIER, ROLE_NEUTRALIZER)


def validate_observation_role(value: str) -> None:
    if value not in OBSERVATION_ROLES:
        raise ValueError(f"Unknown Pattern Observation role {value!r}; expected one of {OBSERVATION_ROLES}")


# Observation status — whether this Observation is still part of the LIVE
# Working Pattern Profile (task §10) or has been superseded by a later
# re-evaluation while the Stage was still open. A superseded row is never
# edited or deleted (task's core immutability principle) — a NEW row with
# ACTIVE status is created instead; see `pattern_service.supersede_observation`.
OBSERVATION_ACTIVE = "ACTIVE"
OBSERVATION_SUPERSEDED = "SUPERSEDED"

OBSERVATION_STATUSES = (OBSERVATION_ACTIVE, OBSERVATION_SUPERSEDED)

# Relevance/importance tiers (task §9's "relevance/importance representation")
# — natural/explainable, not a numeric score, mirrors Review Priority's own
# HIGH/MEDIUM/LOW-shaped tiers elsewhere in this codebase.
RELEVANCE_LOW = "LOW"
RELEVANCE_MEDIUM = "MEDIUM"
RELEVANCE_HIGH = "HIGH"

RELEVANCE_TIERS = (RELEVANCE_LOW, RELEVANCE_MEDIUM, RELEVANCE_HIGH)


# ---------------------------------------------------------------------------
# Provenance (task §8/§14/§18 "provenance" fields throughout) — reused
# everywhere a Pattern/Learning/Feedback record needs to say where it came
# from. Mirrors `core/identity_model.py`'s SYSTEM_RESOLVED/HUMAN_CONFIRMED
# and `core/fit_assessment_model.py`'s SYSTEM_GENERATED/HUMAN_* split.
# ---------------------------------------------------------------------------

PROVENANCE_SYSTEM_GENERATED = "SYSTEM_GENERATED"
PROVENANCE_HUMAN_AUTHORED = "HUMAN_AUTHORED"
PROVENANCE_HUMAN_APPROVED_AI_PROPOSAL = "HUMAN_APPROVED_AI_PROPOSAL"

PROVENANCE_VALUES = (PROVENANCE_SYSTEM_GENERATED, PROVENANCE_HUMAN_AUTHORED, PROVENANCE_HUMAN_APPROVED_AI_PROPOSAL)


def validate_provenance(value: str) -> None:
    if value not in PROVENANCE_VALUES:
        raise ValueError(f"Unknown provenance {value!r}; expected one of {PROVENANCE_VALUES}")


# ---------------------------------------------------------------------------
# Stage Delta types (task §12) — what changed between one Stage Pattern
# Snapshot and the previous one for a given Pattern Definition. Never
# derived from an opaque score — always an explicit type + explanation.
# ---------------------------------------------------------------------------

DELTA_NEW_PATTERN = "NEW_PATTERN"
DELTA_CONFIRMED = "CONFIRMED"
DELTA_STRENGTHENED = "STRENGTHENED"
DELTA_WEAKENED = "WEAKENED"
DELTA_NEUTRALIZED = "NEUTRALIZED"
DELTA_NO_LONGER_SUPPORTED = "NO_LONGER_SUPPORTED"
DELTA_IMPORTANCE_INCREASED = "IMPORTANCE_INCREASED"
DELTA_IMPORTANCE_DECREASED = "IMPORTANCE_DECREASED"

STAGE_DELTA_TYPES = (
    DELTA_NEW_PATTERN, DELTA_CONFIRMED, DELTA_STRENGTHENED, DELTA_WEAKENED, DELTA_NEUTRALIZED,
    DELTA_NO_LONGER_SUPPORTED, DELTA_IMPORTANCE_INCREASED, DELTA_IMPORTANCE_DECREASED,
)


def validate_stage_delta_type(value: str) -> None:
    if value not in STAGE_DELTA_TYPES:
        raise ValueError(f"Unknown Stage Delta type {value!r}; expected one of {STAGE_DELTA_TYPES}")


# ---------------------------------------------------------------------------
# Divergence category (task §13) — configurable/extensible; these are
# SUGGESTED seed values only, exactly like `core/outcome_model.
# DRIVEN_BY_OPTIONS` — never enforced as the only allowed values (the
# database column is a plain string, not a foreign key to a fixed table),
# so an organization can record a category this tuple doesn't anticipate
# without a schema change.
# ---------------------------------------------------------------------------

DIVERGENCE_EXPERIENCE = "EXPERIENCE"
DIVERGENCE_ATTITUDE = "ATTITUDE"
DIVERGENCE_SKILL = "SKILL"
DIVERGENCE_RELIABILITY = "RELIABILITY"
DIVERGENCE_BRAND_FIT = "BRAND_FIT"
DIVERGENCE_OTHER = "OTHER"

SUGGESTED_DIVERGENCE_CATEGORIES = (
    DIVERGENCE_EXPERIENCE, DIVERGENCE_ATTITUDE, DIVERGENCE_SKILL,
    DIVERGENCE_RELIABILITY, DIVERGENCE_BRAND_FIT, DIVERGENCE_OTHER,
)


# ---------------------------------------------------------------------------
# Learning Trace event types (task §14) — deliberately an OPEN, non-
# exhaustive vocabulary (the database column is a plain string): a new
# Learning Trace type must never require a schema/architecture change.
# These constants exist purely so callers share consistent spelling for the
# common cases the task itself names, not to gate what may be recorded.
# ---------------------------------------------------------------------------

TRACE_SELEZIONATORE_ADVANCE = "SELEZIONATORE_ADVANCE"
TRACE_HOLD = "HOLD"
TRACE_STOP = "STOP"
TRACE_HIRE = "HIRE"
TRACE_OUTCOME_APPLIED = "OUTCOME_APPLIED"
TRACE_CASE_OVERRIDE = "CASE_OVERRIDE"
TRACE_STAGE_MOVEMENT = "STAGE_MOVEMENT"
TRACE_QUEUE_MOVEMENT = "QUEUE_MOVEMENT"
TRACE_NOTE_ADDED = "NOTE_ADDED"
TRACE_DIVERGENCE = "DIVERGENCE_FROM_RECOMMENDATION"
TRACE_REPEATED_APPLICANT_SIGNAL = "REPEATED_APPLICANT_SIGNAL"
TRACE_SKILL_TEST_FINDING = "SKILL_TEST_FINDING"
TRACE_TRAINABLE_GAP = "TRAINABLE_GAP"
TRACE_TRAINING_NEED_CREATED = "TRAINING_NEED_CREATED"
TRACE_RULE_PROPOSAL_ACCEPTED = "RULE_PROPOSAL_ACCEPTED"
TRACE_RULE_PROPOSAL_MODIFIED = "RULE_PROPOSAL_MODIFIED"
TRACE_RULE_PROPOSAL_REJECTED = "RULE_PROPOSAL_REJECTED"
TRACE_RULE_REVIEW_NO_CHANGE = "RULE_REVIEW_NO_CHANGE"
TRACE_APPLICATION_REOPENED = "APPLICATION_REOPENED"
TRACE_CANDIDATE_WITHDRAWAL = "CANDIDATE_WITHDRAWAL"
TRACE_FAILED_STAGE_OR_TEST = "FAILED_STAGE_OR_TEST"
TRACE_OPERATIONAL_EFFORT = "OPERATIONAL_EFFORT"

SUGGESTED_LEARNING_TRACE_TYPES = (
    TRACE_SELEZIONATORE_ADVANCE, TRACE_HOLD, TRACE_STOP, TRACE_HIRE, TRACE_OUTCOME_APPLIED, TRACE_CASE_OVERRIDE,
    TRACE_STAGE_MOVEMENT, TRACE_QUEUE_MOVEMENT, TRACE_NOTE_ADDED, TRACE_DIVERGENCE,
    TRACE_REPEATED_APPLICANT_SIGNAL, TRACE_SKILL_TEST_FINDING, TRACE_TRAINABLE_GAP, TRACE_TRAINING_NEED_CREATED,
    TRACE_RULE_PROPOSAL_ACCEPTED, TRACE_RULE_PROPOSAL_MODIFIED, TRACE_RULE_PROPOSAL_REJECTED,
    TRACE_RULE_REVIEW_NO_CHANGE, TRACE_APPLICATION_REOPENED, TRACE_CANDIDATE_WITHDRAWAL,
    TRACE_FAILED_STAGE_OR_TEST, TRACE_OPERATIONAL_EFFORT,
)


# ---------------------------------------------------------------------------
# Learning scope (task §19) — where a piece of learning-relevant knowledge
# belongs: Business-Domain-specific technical/professional facts, or
# genuinely transversal Cross-Domain patterns. Never used to smuggle a
# protected/sensitive personal characteristic in as an operative pattern
# (task's own explicit instruction) — this module defines no such
# characteristic and none may be added without a separate, explicit
# architectural decision.
# ---------------------------------------------------------------------------

LEARNING_SCOPE_BUSINESS_DOMAIN = "BUSINESS_DOMAIN_LEARNING"
LEARNING_SCOPE_CROSS_DOMAIN = "CROSS_DOMAIN_LEARNING"

LEARNING_SCOPES = (LEARNING_SCOPE_BUSINESS_DOMAIN, LEARNING_SCOPE_CROSS_DOMAIN)


def validate_learning_scope(value: str) -> None:
    if value not in LEARNING_SCOPES:
        raise ValueError(f"Unknown learning scope {value!r}; expected one of {LEARNING_SCOPES}")


# ---------------------------------------------------------------------------
# Pattern Example type (task §20) — permanent knowledge assets attached to
# a Pattern Definition, surviving later Definition versions.
# ---------------------------------------------------------------------------

EXAMPLE_ORIGINAL = "ORIGINAL"
EXAMPLE_LATER = "LATER"
EXAMPLE_CONFIRMING = "CONFIRMING"
EXAMPLE_COUNTEREXAMPLE = "COUNTEREXAMPLE"
EXAMPLE_EXCEPTION = "EXCEPTION"

PATTERN_EXAMPLE_TYPES = (EXAMPLE_ORIGINAL, EXAMPLE_LATER, EXAMPLE_CONFIRMING, EXAMPLE_COUNTEREXAMPLE, EXAMPLE_EXCEPTION)


def validate_pattern_example_type(value: str) -> None:
    if value not in PATTERN_EXAMPLE_TYPES:
        raise ValueError(f"Unknown Pattern Example type {value!r}; expected one of {PATTERN_EXAMPLE_TYPES}")
