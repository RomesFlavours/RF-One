"""Phone Interview vocabulary (Task 4A; 01 Domains/Cross Domain/Selection Phone
Interview framework). Defines the generic, restaurant-agnostic MEANING of
Question Source, Question Importance, Gate Evaluation, Question Instance
status, and Phone Interview Plan status — never any specific restaurant's
actual Core Questions or interview philosophy. Mirrors
`core/requirement_model.py`/`core/signal_model.py`'s role exactly:
vocabulary + small pure functions only, no persistence.

Two structurally separate question sources feed one `PhoneInterviewPlan`
(`selection/phone_interview_service.py`): CORE (restaurant-configured,
`PhoneInterviewQuestionDefinition`) and DYNAMIC (candidate-specific,
generated from existing Fit Assessment/Signal evidence). Neither ever
produces a score — Question Importance orders presentation only, it never
determines outcome (task §4)."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Question source (task §2/§9) — where one Question Instance came from.
# ---------------------------------------------------------------------------

CORE = "CORE"
DYNAMIC = "DYNAMIC"
COURTESY = "COURTESY"
FOLLOW_UP = "FOLLOW_UP"

QUESTION_SOURCE_TYPES = (CORE, DYNAMIC, COURTESY, FOLLOW_UP)


# ---------------------------------------------------------------------------
# Question importance (task §4) — operational ordering only, deliberately
# NOT a candidate score. Do not let this determine candidate outcome.
# ---------------------------------------------------------------------------

CRITICAL = "CRITICAL"
HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"

IMPORTANCE_LEVELS = (CRITICAL, HIGH, MEDIUM, LOW)
IMPORTANCE_ORDER = {CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3}


# ---------------------------------------------------------------------------
# Gate Evaluation (task §6) — a Sine Qua Non Question's own outcome, kept
# separate from the raw answer text. A FAILED gate never automatically
# rejects the Application (task §7) — it only makes the Escape Route
# available to the Selezionatore, who remains the decision authority.
# ---------------------------------------------------------------------------

PASSED = "PASSED"
FAILED = "FAILED"
UNCLEAR = "UNCLEAR"
NOT_ASKED_GATE = "NOT_ASKED"

GATE_EVALUATIONS = (PASSED, FAILED, UNCLEAR, NOT_ASKED_GATE)


# ---------------------------------------------------------------------------
# Question Instance status (task §9/§16) — NOT_ASKED/PARTIALLY_ANSWERED/
# UNRESOLVED are the three statuses eligible for automatic carry-forward to
# a future In-Person Interview (never silently dropped).
# ---------------------------------------------------------------------------

NOT_ASKED = "NOT_ASKED"
ASKED = "ASKED"
ANSWERED = "ANSWERED"
PARTIALLY_ANSWERED = "PARTIALLY_ANSWERED"
UNRESOLVED = "UNRESOLVED"
SKIPPED = "SKIPPED"
CARRIED_FORWARD = "CARRIED_FORWARD"

QUESTION_INSTANCE_STATUSES = (
    NOT_ASKED, ASKED, ANSWERED, PARTIALLY_ANSWERED, UNRESOLVED, SKIPPED, CARRIED_FORWARD,
)

# Statuses eligible for automatic carry-forward (task §16) when the Phone
# Interview closes — never CARRIED_FORWARD itself (already there) and never
# ANSWERED/SKIPPED (resolved, or deliberately not pursued).
CARRY_FORWARD_ELIGIBLE_STATUSES = (NOT_ASKED, PARTIALLY_ANSWERED, UNRESOLVED)


# ---------------------------------------------------------------------------
# Phone Interview Plan status (task §21) — the INTERVIEW PROCESS status,
# deliberately separate from `Application.workflow_status` (never confused
# with it — see `selection/phone_interview_service.py`).
# ---------------------------------------------------------------------------

NOT_STARTED = "NOT_STARTED"
IN_PROGRESS = "IN_PROGRESS"
ESCAPE_ROUTE = "ESCAPE_ROUTE"
COMPLETED = "COMPLETED"
STOPPED_EARLY = "STOPPED_EARLY"

PLAN_STATUSES = (NOT_STARTED, IN_PROGRESS, ESCAPE_ROUTE, COMPLETED, STOPPED_EARLY)
# A plan whose interview has meaningfully started (task §23) — once here,
# already-asked Question Instances are never silently reordered or deleted.
PLAN_STARTED_STATUSES = (IN_PROGRESS, ESCAPE_ROUTE, COMPLETED, STOPPED_EARLY)


def question_sort_key(*, is_sine_qua_non: bool, importance: str, display_order: int) -> tuple:
    """The presentation-order key (task §8): GATE QUESTIONS -> CRITICAL ->
    HIGH -> MEDIUM -> LOW, Dynamic Questions interleaved by their own
    importance, `display_order` (insertion order) breaking ties within the
    same bucket. Never a numeric rank shown to anyone — used only to `sort()`
    a Python list for display."""

    gate_bucket = 0 if is_sine_qua_non else 1
    importance_bucket = IMPORTANCE_ORDER.get(importance, len(IMPORTANCE_ORDER))
    return (gate_bucket, importance_bucket, display_order)
