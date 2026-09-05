"""Fit Assessment vocabulary (Task 3B; 01 Domains/Cross Domain/Selection/
CandidateEvidence.md / FitAssessment.md). Defines the generic, restaurant-
agnostic MEANING of assessment status, evidence source/classification/
relationship, and confidence — never any specific restaurant's judgment
about a specific candidate. That judgment always lives in persisted
`FitAssessment`/`RequirementAssessment`/`EvidenceItem` rows (`.. models`),
populated via `selection/fit_assessment_service.py`.

Mirrors `core/requirement_model.py`'s role exactly: vocabulary + one small
pure function (`compute_status_from_evidence`), no dataclass mirror of the
persisted shape — a Fit Assessment, like a Requirement Set, has no parser
producing it independently of persistence; it is always built directly by
the service layer, which operates on the SQLAlchemy rows themselves (the
same pattern `selection/normalization.py`'s `reprocess_candidate()` and
`selection/requirements_service.py` already use).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Assessment status (task §5) — the fundamental unit is Candidate x
# RequirementSnapshotItem; every one of these gets exactly one status.
# NOT_EVIDENCED and NOT_ASSESSED_AT_THIS_STAGE are deliberately distinct and
# must never be conflated (task's own explicit warning).
# ---------------------------------------------------------------------------

EVIDENCED = "EVIDENCED"  # Current evidence materially supports the Requirement.
PARTIALLY_EVIDENCED = "PARTIALLY_EVIDENCED"  # Relevant evidence exists but is incomplete/limited.
NOT_EVIDENCED = "NOT_EVIDENCED"  # Assessable at this stage; no adequate supporting evidence found.
CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"  # Relevant evidence materially points different directions.
NOT_ASSESSED_AT_THIS_STAGE = "NOT_ASSESSED_AT_THIS_STAGE"  # Not legitimately assessable with evidence available now.

ASSESSMENT_STATUSES = (EVIDENCED, PARTIALLY_EVIDENCED, NOT_EVIDENCED, CONFLICTING_EVIDENCE, NOT_ASSESSED_AT_THIS_STAGE)


# ---------------------------------------------------------------------------
# Evidence source type (task §7) — where one piece of evidence came from.
# Only RESUME_FACT/RESUME_DERIVED_INFORMATION are actually produced by
# Task 3B's own automatic assessment; the rest exist so later stages (never
# implemented here) have a place to plug in without a schema change.
# ---------------------------------------------------------------------------

RESUME_FACT = "RESUME_FACT"
RESUME_DERIVED_INFORMATION = "RESUME_DERIVED_INFORMATION"
PHONE_INTERVIEW_RESPONSE = "PHONE_INTERVIEW_RESPONSE"
IN_PERSON_OBSERVATION = "IN_PERSON_OBSERVATION"
PRACTICAL_ASSESSMENT_RESULT = "PRACTICAL_ASSESSMENT_RESULT"
REFERENCE_CHECK = "REFERENCE_CHECK"
HUMAN_NOTE = "HUMAN_NOTE"
OTHER_SOURCE = "OTHER"

EVIDENCE_SOURCE_TYPES = (
    RESUME_FACT, RESUME_DERIVED_INFORMATION, PHONE_INTERVIEW_RESPONSE, IN_PERSON_OBSERVATION,
    PRACTICAL_ASSESSMENT_RESULT, REFERENCE_CHECK, HUMAN_NOTE, OTHER_SOURCE,
)


# ---------------------------------------------------------------------------
# Fact vs. Derived Information vs. Inference (task §8) — never silently
# collapsed. FACT: explicitly stated in the source. DERIVED_INFORMATION: a
# deterministic calculation from facts (e.g. tenure in months, from two
# dates). INFERENCE: an interpretation — never allowed to overwrite the
# facts it was drawn from.
# ---------------------------------------------------------------------------

FACT = "FACT"
DERIVED_INFORMATION = "DERIVED_INFORMATION"
INFERENCE = "INFERENCE"

EVIDENCE_CLASSIFICATIONS = (FACT, DERIVED_INFORMATION, INFERENCE)


# ---------------------------------------------------------------------------
# Evidence relationship to the Requirement — does this item support it,
# contradict it, or is it merely contextual/neutral?
# ---------------------------------------------------------------------------

SUPPORTS = "SUPPORTS"
CONTRADICTS = "CONTRADICTS"
NEUTRAL = "NEUTRAL"

EVIDENCE_RELATIONSHIPS = (SUPPORTS, CONTRADICTS, NEUTRAL)


# ---------------------------------------------------------------------------
# Confidence (task §9) — same convention already established for date/role
# normalization (Task 2B, `parsing/flexible_dates.py`); redefined here with
# the identical string values rather than imported, since Core must not
# depend on `parsing` (dependency runs the other way).
# ---------------------------------------------------------------------------

CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"
CONFIDENCE_UNKNOWN = "UNKNOWN"

CONFIDENCE_LEVELS = (CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW, CONFIDENCE_UNKNOWN)
# Public (not a leading-underscore module detail) — `fit_assessment_service.py`
# reuses this ordering to roll several evidence items' confidence up into
# one summary value for display.
CONFIDENCE_ORDER = {CONFIDENCE_HIGH: 3, CONFIDENCE_MEDIUM: 2, CONFIDENCE_LOW: 1, CONFIDENCE_UNKNOWN: 0}


# ---------------------------------------------------------------------------
# Assessment origin (task §16) — who/what is responsible for the CURRENT
# effective status. A system-computed conclusion must never be
# indistinguishable from a human's.
# ---------------------------------------------------------------------------

SYSTEM_GENERATED = "SYSTEM_GENERATED"
HUMAN_ENTERED = "HUMAN_ENTERED"
HUMAN_CONFIRMED = "HUMAN_CONFIRMED"
HUMAN_OVERRIDDEN = "HUMAN_OVERRIDDEN"

ASSESSMENT_ORIGINS = (SYSTEM_GENERATED, HUMAN_ENTERED, HUMAN_CONFIRMED, HUMAN_OVERRIDDEN)
HUMAN_ORIGINS = (HUMAN_ENTERED, HUMAN_CONFIRMED, HUMAN_OVERRIDDEN)


def compute_status_from_evidence(evidence_items: list) -> str:
    """The one, reusable rule that turns a list of evidence items (each
    exposing `.evidence_relationship` and `.confidence` — works against
    both ORM `EvidenceItem` rows and the service layer's own evidence
    drafts) into a status. Used identically by the initial résumé-stage
    generator and by every later evidence addition/reassessment (task §19),
    so "add evidence -> recompute" is the ONLY mechanism that ever changes
    a system-computed status — never a bespoke rule per call site.

    - Both SUPPORTS and CONTRADICTS present -> CONFLICTING_EVIDENCE (task
      §14: never silently pick one side).
    - Only CONTRADICTS (no SUPPORTS) -> NOT_EVIDENCED. The five statuses
      this task defines have no "actively disproven" state; NOT_EVIDENCED
      ("adequate supporting evidence was not found") is the closest honest
      label — the contradicting evidence itself remains fully visible on
      the assessment either way.
    - Only SUPPORTS, with at least one HIGH-confidence item -> EVIDENCED.
    - Only SUPPORTS, none HIGH-confidence -> PARTIALLY_EVIDENCED.
    - No evidence at all -> NOT_EVIDENCED.

    Callers are responsible for the stage check themselves: this function
    is never called at all for a Requirement not assessable at the current
    stage (that yields NOT_ASSESSED_AT_THIS_STAGE directly, with no
    evidence gathered — task §6)."""

    supports = [e for e in evidence_items if e.evidence_relationship == SUPPORTS]
    contradicts = [e for e in evidence_items if e.evidence_relationship == CONTRADICTS]

    if supports and contradicts:
        return CONFLICTING_EVIDENCE
    if contradicts and not supports:
        return NOT_EVIDENCED
    if supports:
        if any(e.confidence == CONFIDENCE_HIGH for e in supports):
            return EVIDENCED
        return PARTIALLY_EVIDENCED
    return NOT_EVIDENCED
