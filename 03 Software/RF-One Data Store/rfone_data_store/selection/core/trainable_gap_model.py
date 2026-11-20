"""Trainable Gap vocabulary (Task 5B; 01 Domains/Cross Domain/Selection/
TrainableGap.md). Defines the generic, restaurant-agnostic MEANING of a
Trainable Gap's 0-4 initial-level scale and eligibility rule — never a
specific candidate's actual level, which always lives in the persisted
`TrainableGap` row (`.. models`), populated via
`selection/trainable_gap_service.py`. Mirrors `core/requirement_model.py`/
`core/fit_assessment_model.py`'s role exactly: vocabulary + small pure
functions only, no persistence.

Reuses `core/fit_assessment_model.py`'s `ASSESSMENT_ORIGINS` (who/what is
responsible for the CURRENT effective level) and `core/requirement_model.py`'s
trainability vocabulary rather than redefining equivalents — the identical
pattern `core/primary_screening_model.py` already follows for origin.
"""

from __future__ import annotations

from .fit_assessment_model import (  # noqa: F401  (re-exported for callers of this module)
    ASSESSMENT_ORIGINS,
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    HUMAN_CONFIRMED,
    HUMAN_OVERRIDDEN,
    NOT_EVIDENCED,
    PARTIALLY_EVIDENCED,
    SYSTEM_GENERATED,
)
from .requirement_model import (  # noqa: F401  (re-exported)
    NOT_TRAINABLE,
    PARTIALLY_TRAINABLE,
    TRAINABILITY_UNKNOWN,
    TRAINABLE,
)

# ---------------------------------------------------------------------------
# Initial level (task §4) — the candidate's CURRENT observed level for one
# specific gap. Never a Training target (task §7/§17 — a target level is
# explicitly out of Selection's scope; this scale describes only what has
# been observed so far).
# ---------------------------------------------------------------------------

LEVEL_NO_DEMONSTRATED_CAPABILITY = 0
LEVEL_VERY_LIMITED = 1
LEVEL_PARTIAL = 2
LEVEL_SUBSTANTIAL_BUT_INCOMPLETE = 3
LEVEL_REQUIREMENT_EFFECTIVELY_SATISFIED = 4

INITIAL_LEVELS = (
    LEVEL_NO_DEMONSTRATED_CAPABILITY, LEVEL_VERY_LIMITED, LEVEL_PARTIAL,
    LEVEL_SUBSTANTIAL_BUT_INCOMPLETE, LEVEL_REQUIREMENT_EFFECTIVELY_SATISFIED,
)

LEVEL_DESCRIPTIONS = {
    LEVEL_NO_DEMONSTRATED_CAPABILITY: "No demonstrated capability",
    LEVEL_VERY_LIMITED: "Very limited",
    LEVEL_PARTIAL: "Partial",
    LEVEL_SUBSTANTIAL_BUT_INCOMPLETE: "Substantial but incomplete",
    LEVEL_REQUIREMENT_EFFECTIVELY_SATISFIED: "Requirement effectively satisfied",
}


def validate_initial_level(level: int) -> None:
    if level not in INITIAL_LEVELS:
        raise ValueError(f"Unknown Trainable Gap initial level {level!r}; expected one of {INITIAL_LEVELS}")


# ---------------------------------------------------------------------------
# Eligibility (task §1/§6) — a Trainable Gap may exist only where the
# underlying gap is ACTUALLY EVIDENCED (not merely Unknown/missing evidence
# — NOT_ASSESSED_AT_THIS_STAGE is deliberately excluded) AND the
# restaurant's own Requirement trainability says the gap is realistically
# teachable. NOT_TRAINABLE requirements are deliberately excluded here
# (task §6: "Do NOT turn NOT_TRAINABLE concerns into Trainable Gaps") — they
# remain visible separately as non-trainable concerns.
# ---------------------------------------------------------------------------

ELIGIBLE_FIT_STATUSES = (NOT_EVIDENCED, PARTIALLY_EVIDENCED)
ELIGIBLE_TRAINABILITY_LEVELS = (TRAINABLE, PARTIALLY_TRAINABLE)


def is_trainable_gap_eligible(*, effective_status: str, trainability: str) -> bool:
    return effective_status in ELIGIBLE_FIT_STATUSES and trainability in ELIGIBLE_TRAINABILITY_LEVELS


def is_non_trainable_concern(*, effective_status: str, trainability: str) -> bool:
    """The task's own contrasting example (§6): an important gap that is
    evidenced but whose Requirement trainability is NOT_TRAINABLE — shown
    separately on the Dossier, never converted into a Trainable Gap."""

    return effective_status in ELIGIBLE_FIT_STATUSES and trainability == NOT_TRAINABLE


# ---------------------------------------------------------------------------
# Status (task §3's "preserve... status") — a small, non-Training lifecycle:
# whether this Trainable Gap is still open/active evidence for the
# Selezionatore, or has been withdrawn because a later assessment refresh no
# longer evidences the gap at all. Never a Training-progress status.
# ---------------------------------------------------------------------------

ACTIVE = "ACTIVE"
WITHDRAWN = "WITHDRAWN"

TRAINABLE_GAP_STATUSES = (ACTIVE, WITHDRAWN)


def propose_initial_level(*, effective_status: str, confidence: str | None) -> int:
    """RF-One's proposed initial level from available evidence (task §4:
    "RF-One may propose the initial level from available evidence") — a
    small, honest, illustrative heuristic, not a validated measurement:
    NOT_EVIDENCED (no supporting evidence at all) always starts at the
    floor; PARTIALLY_EVIDENCED (some supporting evidence, incomplete)
    starts higher when that partial evidence is itself higher-confidence.
    A restaurant/product may refine this heuristic later without changing
    what the 0-4 scale itself means (this function, not the scale, is the
    thing that would change)."""

    if effective_status == NOT_EVIDENCED:
        return LEVEL_NO_DEMONSTRATED_CAPABILITY
    if confidence == CONFIDENCE_HIGH:
        return LEVEL_SUBSTANTIAL_BUT_INCOMPLETE
    if confidence == CONFIDENCE_MEDIUM:
        return LEVEL_PARTIAL
    return LEVEL_VERY_LIMITED
