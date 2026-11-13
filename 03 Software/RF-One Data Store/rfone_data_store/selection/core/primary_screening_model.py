"""Primary Screening Engine vocabulary (Task 3D). Defines the generic,
restaurant-agnostic MEANING of the fixed 0-4 level scale, Direction,
evaluation status, and evidence source — never any specific restaurant's
actual Screening Criteria, level meanings, or coefficients. Mirrors
`core/requirement_model.py`/`core/signal_model.py`'s role exactly:
vocabulary + small pure functions only, no persistence.

The level scale (0-4) is universal STRUCTURE; what each level MEANS for a
given Criterion is restaurant-authored data (`PrimaryScreeningCriterion.
level_descriptions`), never defined here (task §2's own explicit warning).

Assessment origin vocabulary is intentionally NOT redefined here — reused
directly from `core/fit_assessment_model.py`
(`SYSTEM_GENERATED`/`HUMAN_ENTERED`/`HUMAN_CONFIRMED`/`HUMAN_OVERRIDDEN`)
since it is the identical concept Task 3B/3C/4A/4B already established.
"""

from __future__ import annotations

from .fit_assessment_model import (  # noqa: F401  (re-exported)
    ASSESSMENT_ORIGINS, CONFIDENCE_LEVELS, HUMAN_CONFIRMED, HUMAN_ENTERED, HUMAN_ORIGINS, HUMAN_OVERRIDDEN,
    SYSTEM_GENERATED,
)

# ---------------------------------------------------------------------------
# Fixed level scale (task §2) — the SCALE is universal; the MEANING of each
# level for a given Criterion is always restaurant-authored data.
# ---------------------------------------------------------------------------

LEVEL_SCALE = (0, 1, 2, 3, 4)
MIN_LEVEL = 0
MAX_LEVEL = 4


def validate_level(level: int) -> None:
    if level not in LEVEL_SCALE:
        raise ValueError(f"Unknown Screening Criterion level {level!r}; expected one of {LEVEL_SCALE}")


# ---------------------------------------------------------------------------
# Direction (task §3) — coefficient magnitude stays separate from direction.
# ---------------------------------------------------------------------------

POSITIVE = "POSITIVE"
NEGATIVE = "NEGATIVE"

DIRECTIONS = (POSITIVE, NEGATIVE)


def compute_contribution(*, coefficient: float, level: int, direction: str) -> float:
    """Task §4 — `coefficient x level`, signed by `direction`. A simple,
    transparent calculation; deliberately no statistical modeling."""

    if direction not in DIRECTIONS:
        raise ValueError(f"Unknown direction {direction!r}; expected one of {DIRECTIONS}")
    validate_level(level)
    signed = coefficient * level
    return signed if direction == POSITIVE else -signed


# ---------------------------------------------------------------------------
# Evidence source (task §12) — where a Criterion Evaluation's evidence came
# from. Primary Screening happens mostly before Phone Interview, so the
# engine itself never depends on later-stage evidence to function — later
# evidence sources exist in this vocabulary only so an explicit, Selezionatore
# -chosen re-evaluation has somewhere to record them.
# ---------------------------------------------------------------------------

RESUME_FACT = "RESUME_FACT"
RESUME_DERIVED_INFORMATION = "RESUME_DERIVED_INFORMATION"
APPLICATION = "APPLICATION"
APPLICATION_HISTORY = "APPLICATION_HISTORY"
FIT_ASSESSMENT = "FIT_ASSESSMENT"
SELECTION_SIGNAL = "SELECTION_SIGNAL"
CONSISTENCY_INFORMATION = "CONSISTENCY_INFORMATION"
SELEZIONATORE_INPUT = "SELEZIONATORE_INPUT"
OTHER_EVIDENCE_SOURCE = "OTHER"

EVIDENCE_SOURCES = (
    RESUME_FACT, RESUME_DERIVED_INFORMATION, APPLICATION, APPLICATION_HISTORY, FIT_ASSESSMENT, SELECTION_SIGNAL,
    CONSISTENCY_INFORMATION, SELEZIONATORE_INPUT, OTHER_EVIDENCE_SOURCE,
)


# ---------------------------------------------------------------------------
# Evaluation status (task §14) — an unknown/uncertain Criterion must never
# silently become level 0. Only EVALUATED contributes to the Priority Index.
# ---------------------------------------------------------------------------

EVALUATED = "EVALUATED"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
NOT_APPLICABLE = "NOT_APPLICABLE"
NOT_EVALUATED = "NOT_EVALUATED"

EVALUATION_STATUSES = (EVALUATED, INSUFFICIENT_EVIDENCE, NOT_APPLICABLE, NOT_EVALUATED)
# Statuses that never contribute a level/contribution to the Priority Index
# (task §14's own "only evaluated Criteria contribute").
NON_CONTRIBUTING_STATUSES = (INSUFFICIENT_EVIDENCE, NOT_APPLICABLE, NOT_EVALUATED)


def compute_priority_index(contributions: list[float]) -> float:
    """Task §5/§9 — the sum of every EVALUATED Criterion's signed
    contribution. Cumulative by design (never "just the strongest
    Criterion"). This number is INTERNAL ONLY — never shown to the
    Selezionatore (task §5's own explicit prohibition); used only to order
    the Primary Screening Queue."""

    return sum(contributions)
