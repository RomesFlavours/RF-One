"""In-Person Interview + Practical Assessment + Consistency Engine
vocabulary (Task 4B). Defines the generic, restaurant-agnostic MEANING of
Interview Section kind, Assessment Item type/status, and Consistency
Thread/Statement status — never any specific restaurant's actual interview
structure or judgment. Mirrors `core/phone_interview_model.py`'s role
exactly: vocabulary + small pure functions only, no persistence.

Importance vocabulary is intentionally NOT redefined here — reused directly
from `core/phone_interview_model.py` (`IMPORTANCE_LEVELS`/`IMPORTANCE_ORDER`)
since it is the identical CRITICAL/HIGH/MEDIUM/LOW concept, ordering
presentation only, never a score (same rule Task 4A already established).
"""

from __future__ import annotations

from .phone_interview_model import IMPORTANCE_LEVELS, IMPORTANCE_ORDER  # noqa: F401  (re-exported)

# ---------------------------------------------------------------------------
# Interview Section "kind" (task §2) — a small, recognized vocabulary used
# ONLY to hang the two behaviorally special sections off of (automatic
# Phone carry-forward population, and the Final Observation phase's "never
# automatically evidence" rule). Restaurants are free to create a Section
# with any name and ANY kind (including OTHER) — RF-One never hard-codes
# one universal interview sequence (task's own instruction); Rome's
# Flavours' 7-section structure is one example of configured DATA, not
# universal logic.
# ---------------------------------------------------------------------------

CARRY_FORWARD = "CARRY_FORWARD"
WELCOME_OBSERVATION = "WELCOME_OBSERVATION"
WORK_PERSONALITY = "WORK_PERSONALITY"
HOSPITALITY_MOTIVATION = "HOSPITALITY_MOTIVATION"
PRACTICAL_TECHNICAL = "PRACTICAL_TECHNICAL"
COMMITMENT = "COMMITMENT"
FINAL_OBSERVATION = "FINAL_OBSERVATION"
OTHER_SECTION_KIND = "OTHER"

SECTION_KINDS = (
    CARRY_FORWARD, WELCOME_OBSERVATION, WORK_PERSONALITY, HOSPITALITY_MOTIVATION, PRACTICAL_TECHNICAL,
    COMMITMENT, FINAL_OBSERVATION, OTHER_SECTION_KIND,
)


# ---------------------------------------------------------------------------
# Assessment Item type (task §3).
# ---------------------------------------------------------------------------

QUESTION = "QUESTION"
OBSERVATION = "OBSERVATION"
PRACTICAL_TEST = "PRACTICAL_TEST"
ROLE_PLAY = "ROLE_PLAY"
CONSISTENCY_CHECK = "CONSISTENCY_CHECK"
CARRY_FORWARD_ITEM = "CARRY_FORWARD"
COURTESY = "COURTESY"

ASSESSMENT_ITEM_TYPES = (
    QUESTION, OBSERVATION, PRACTICAL_TEST, ROLE_PLAY, CONSISTENCY_CHECK, CARRY_FORWARD_ITEM, COURTESY,
)


# ---------------------------------------------------------------------------
# Assessment Item completion status (task §19) — NOT_DONE/PARTIAL/UNRESOLVED
# are the task's own explicit "uncompleted important items remain ..."
# vocabulary; DONE/SKIPPED fill the same structural role
# ANSWERED/SKIPPED play for the Phone Interview Question Instance.
# ---------------------------------------------------------------------------

NOT_DONE = "NOT_DONE"
DONE = "DONE"
PARTIAL = "PARTIAL"
UNRESOLVED = "UNRESOLVED"
SKIPPED = "SKIPPED"

ASSESSMENT_ITEM_STATUSES = (NOT_DONE, DONE, PARTIAL, UNRESOLVED, SKIPPED)
# Statuses under which an item is still "incomplete/open" (task §19/§10) —
# visible before any future Final Selection Decision, never silently
# dropped. Task 4B does not carry these any further (no next stage exists
# yet) — this is only used for the "unresolved/incomplete" UI listing.
INCOMPLETE_ITEM_STATUSES = (NOT_DONE, PARTIAL, UNRESOLVED)


# ---------------------------------------------------------------------------
# In-Person Interview Plan status (task §21) — the interview PROCESS
# status, deliberately separate from `Application.workflow_status` (same
# separation Task 4A's Phone Interview Plan already established). No
# Escape Route concept here — Task 4B does not ask for one.
# ---------------------------------------------------------------------------

NOT_STARTED = "NOT_STARTED"
IN_PROGRESS = "IN_PROGRESS"
COMPLETED = "COMPLETED"
STOPPED_EARLY = "STOPPED_EARLY"

PLAN_STATUSES = (NOT_STARTED, IN_PROGRESS, COMPLETED, STOPPED_EARLY)


# ---------------------------------------------------------------------------
# Consistency source stage (task §8) — WHERE a compared statement/evidence
# item came from. Deliberately its own small vocabulary rather than reusing
# `core/fit_assessment_model.EVIDENCE_SOURCE_TYPES` — a Consistency
# Statement is a comparison INPUT (may come from a prior Application, which
# is not an evidence source type at all), not itself Fit Assessment/Signal
# evidence.
# ---------------------------------------------------------------------------

CV_APPLICATION = "CV_APPLICATION"
PRIOR_APPLICATION = "PRIOR_APPLICATION"
PHONE_INTERVIEW = "PHONE_INTERVIEW"
IN_PERSON_INTERVIEW = "IN_PERSON_INTERVIEW"
PRACTICAL_ASSESSMENT = "PRACTICAL_ASSESSMENT"
SELEZIONATORE_ENTERED = "SELEZIONATORE_ENTERED"

CONSISTENCY_SOURCE_STAGES = (
    CV_APPLICATION, PRIOR_APPLICATION, PHONE_INTERVIEW, IN_PERSON_INTERVIEW, PRACTICAL_ASSESSMENT,
    SELEZIONATORE_ENTERED,
)


# ---------------------------------------------------------------------------
# Consistency comparison status (task §11) — a contradiction is EVIDENCE,
# never automatic proof of dishonesty (task §12: never "liar"/"dishonest"/
# "deceptive"/"manipulative" anywhere in this vocabulary or the generated
# explanation text). NEW_INFORMATION is an addition beyond the task's
# minimum five, needed for task §14's own distinction ("a change is NOT
# automatically negative... distinguish NEW INFORMATION from MATERIAL
# CONTRADICTION") — the task explicitly asks for "at minimum" the other
# five, leaving room for exactly this.
# ---------------------------------------------------------------------------

CONSISTENT = "CONSISTENT"
MINOR_VARIATION = "MINOR_VARIATION"
MATERIAL_INCONSISTENCY = "MATERIAL_INCONSISTENCY"
CONSISTENCY_UNRESOLVED = "UNRESOLVED"
EXPLAINED_DIFFERENCE = "EXPLAINED_DIFFERENCE"
NEW_INFORMATION = "NEW_INFORMATION"

CONSISTENCY_STATUSES = (
    CONSISTENT, MINOR_VARIATION, MATERIAL_INCONSISTENCY, CONSISTENCY_UNRESOLVED, EXPLAINED_DIFFERENCE,
    NEW_INFORMATION,
)

# Statuses worth surfacing as "Consistency Items to Verify" (task §13) —
# the most important still-open discrepancies, never the full thread list.
CONSISTENCY_ITEMS_TO_VERIFY_STATUSES = (MATERIAL_INCONSISTENCY, CONSISTENCY_UNRESOLVED)


# ---------------------------------------------------------------------------
# Starter consistency topics (task §9) — a practical, non-exhaustive
# starter set offered as UI convenience (same role
# `core/requirement_model.STARTER_CATEGORIES` plays), never enforced as the
# only allowed topics and never implying every topic must be compared for
# every Application (task's own instruction).
# ---------------------------------------------------------------------------

STARTER_CONSISTENCY_TOPICS = (
    "Employment dates", "Job titles", "Responsibilities", "Reason for leaving", "Current employment status",
    "Availability", "Schedule commitments", "Training availability", "Management relationships",
    "Teamwork descriptions", "Professional goals", "Motivation for applying", "Income expectations",
    "Technical experience", "Certifications", "Claimed skills", "Prior Application statements",
)


def item_sort_key(*, section_display_order: int, importance: str, item_display_order: int) -> tuple:
    """The presentation-order key (task §19): the restaurant's own
    configured Section order first (never overridden by RF-One), then
    importance within a section (CRITICAL -> HIGH -> MEDIUM -> LOW), then
    insertion order as the final tie-break. A Carry-Forward section
    configured early (task §4: "carry-forward items should appear early")
    is simply one more restaurant-configured section position — never a
    numeric rank shown to anyone, used only to `sort()` a Python list."""

    importance_bucket = IMPORTANCE_ORDER.get(importance, len(IMPORTANCE_ORDER))
    return (section_display_order, importance_bucket, item_display_order)
