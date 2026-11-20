"""Selection Signal + Review Priority vocabulary (Task 3C; RF-One Selection
3C Concept Note — Selection Signals + Review Priority). Defines the
generic, restaurant-agnostic MEANING of Signal Family, Signal Observation
status, Review Priority category, and the priority-contribution tier a
restaurant's own policy assigns to a Signal — never any specific
restaurant's actual Signal Definitions or judgment. Mirrors
`core/requirement_model.py`'s role exactly: vocabulary + one small pure
function, no dataclass mirror of the persisted shape (a Signal Observation,
like a Requirement Assessment, is always built directly by the service
layer against SQLAlchemy rows).

Confidence and evidence classification/relationship/source-type vocabulary
is intentionally NOT redefined here — Signal evidence reuses
`core/fit_assessment_model.py`'s constants directly (concept note itself:
Signals "must remain explainable and traceable to evidence," the exact
same requirement Task 3B's evidence model already satisfies).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Signal families (concept note §3). "PERSONAL" motivation here means
# job-related motivation the candidate explicitly expressed — never
# demographic or protected personal characteristics (concept note's own
# clarification).
# ---------------------------------------------------------------------------

FIT_EXPERIENCE = "FIT_EXPERIENCE"
READINESS_RECENCY = "READINESS_RECENCY"
MOTIVATION_PERSONAL = "MOTIVATION_PERSONAL"
MOTIVATION_PROFESSIONAL = "MOTIVATION_PROFESSIONAL"

SIGNAL_FAMILIES = (FIT_EXPERIENCE, READINESS_RECENCY, MOTIVATION_PERSONAL, MOTIVATION_PROFESSIONAL)


# ---------------------------------------------------------------------------
# Signal Observation status (concept note §6). DETECTED/NOT_DETECTED are
# the two most common concrete states; CONFLICTING mirrors Task 3B's
# CONFLICTING_EVIDENCE for the same reason (multiple evidence items point
# different directions — never silently pick one); NOT_ASSESSED is the
# Signal-framework equivalent of Task 3B's NOT_ASSESSED_AT_THIS_STAGE (not
# legitimately assessable with evidence available now — never guessed).
# ---------------------------------------------------------------------------

DETECTED = "DETECTED"
POSSIBLE = "POSSIBLE"
CONFLICTING = "CONFLICTING"
NOT_DETECTED = "NOT_DETECTED"
NOT_ASSESSED = "NOT_ASSESSED"

SIGNAL_STATUSES = (DETECTED, POSSIBLE, CONFLICTING, NOT_DETECTED, NOT_ASSESSED)


# ---------------------------------------------------------------------------
# Review Priority (concept note §7) — a category, never a score/rank.
# ---------------------------------------------------------------------------

HIGH_PRIORITY = "HIGH_PRIORITY"
INTERESTING = "INTERESTING"
STANDARD = "STANDARD"
LOW_PRIORITY = "LOW_PRIORITY"

REVIEW_PRIORITY_CATEGORIES = (HIGH_PRIORITY, INTERESTING, STANDARD, LOW_PRIORITY)


# ---------------------------------------------------------------------------
# Priority contribution tier (concept note §9: "Signal detection must
# remain separate from how much that Signal affects Review Priority" —
# EVIDENCE -> SIGNAL -> RESTAURANT REVIEW PRIORITY POLICY -> REVIEW
# PRIORITY). A restaurant's `ReviewPriorityPolicyRule` assigns one of these
# QUALITATIVE tiers to one (SignalDefinition, observed status) pair —
# deliberately not a number (§9: "Do not encode an inherent universal
# numeric value into a Signal"). `compute_review_priority()` below combines
# tiers into a category using only counts, never a weighted sum exposed
# anywhere.
# ---------------------------------------------------------------------------

STRONGLY_INCREASE = "STRONGLY_INCREASE"
INCREASE = "INCREASE"
NEUTRAL_CONTRIBUTION = "NEUTRAL"
DECREASE = "DECREASE"
STRONGLY_DECREASE = "STRONGLY_DECREASE"

PRIORITY_CONTRIBUTIONS = (STRONGLY_INCREASE, INCREASE, NEUTRAL_CONTRIBUTION, DECREASE, STRONGLY_DECREASE)


# ---------------------------------------------------------------------------
# Application outcomes (concept note §11) — a historical record field only.
# Task 3C does not implement any learning/correlation logic from these; the
# vocabulary exists so that capability has somewhere to write to later.
# ---------------------------------------------------------------------------

APPLICATION_OUTCOMES = (
    "REVIEWED", "ADVANCED", "HELD", "STOPPED", "INTERVIEWED", "HIRED",
    "TRAINING_STARTED", "TRAINING_COMPLETED", "CANDIDATE_WITHDREW",
    "WITHDREW_DURING_TRAINING", "LEFT_AFTER_SHORT_PERIOD", "RETAINED",
)


def compute_signal_status_from_evidence(evidence_items: list) -> str:
    """The Signal-framework counterpart of
    `core.fit_assessment_model.compute_status_from_evidence()` — same rule,
    mapped onto this module's own status vocabulary instead:

    - both SUPPORTS and CONTRADICTS present -> CONFLICTING (never silently
      pick a side, concept note §8).
    - only CONTRADICTS -> NOT_DETECTED.
    - SUPPORTS with a HIGH-confidence item -> DETECTED.
    - SUPPORTS only at lower confidence -> POSSIBLE.
    - nothing -> NOT_DETECTED.

    NOT_ASSESSED is never produced here — callers (the detection engine,
    `signal_service.py`) set it directly whenever a Signal is not
    legitimately assessable yet, with zero evidence gathered, exactly like
    Task 3B's NOT_ASSESSED_AT_THIS_STAGE."""

    from . import fit_assessment_model as fam

    supports = [e for e in evidence_items if e.evidence_relationship == fam.SUPPORTS]
    contradicts = [e for e in evidence_items if e.evidence_relationship == fam.CONTRADICTS]

    if supports and contradicts:
        return CONFLICTING
    if contradicts and not supports:
        return NOT_DETECTED
    if supports:
        if any(e.confidence == fam.CONFIDENCE_HIGH for e in supports):
            return DETECTED
        return POSSIBLE
    return NOT_DETECTED


def compute_review_priority(contributions: list[tuple[str, str]]) -> tuple[str, list[str]]:
    """Turns a list of `(priority_contribution_tier, reason_text)` pairs —
    one per DETECTED/POSSIBLE Signal Observation whose restaurant policy
    assigns a contribution — into one of the four Review Priority
    categories, plus the reasons that produced it (concept note §7: "The
    system must always provide the reasons supporting the priority.").

    Rule-based and deliberately simple — only COUNTS of qualitative tiers
    are used internally, never a weighted sum exposed anywhere:

    - a STRONGLY_INCREASE present, no DECREASE-side contribution -> HIGH_PRIORITY
    - 2+ INCREASE (no STRONGLY_INCREASE), no DECREASE-side -> HIGH_PRIORITY
    - exactly one INCREASE alone, no DECREASE-side -> INTERESTING (positive,
      but not yet a clear-cut case)
    - the mirror image on the DECREASE side -> LOW_PRIORITY / INTERESTING
    - INCREASE-side and DECREASE-side contributions both present -> INTERESTING
      (concept note §7/§8's own example: signals pointing different
      directions must coexist and remain explainable, never silently
      resolved to one side)
    - nothing contributing either way -> STANDARD
    """

    up_strong = [reason for tier, reason in contributions if tier == STRONGLY_INCREASE]
    up = [reason for tier, reason in contributions if tier == INCREASE]
    down = [reason for tier, reason in contributions if tier == DECREASE]
    down_strong = [reason for tier, reason in contributions if tier == STRONGLY_DECREASE]

    has_up, has_down = bool(up_strong or up), bool(down_strong or down)

    if has_up and has_down:
        return INTERESTING, up_strong + up + down + down_strong
    if has_up:
        if up_strong or len(up) >= 2:
            return HIGH_PRIORITY, up_strong + up
        return INTERESTING, up
    if has_down:
        if down_strong or len(down) >= 2:
            return LOW_PRIORITY, down_strong + down
        return INTERESTING, down
    return STANDARD, []
