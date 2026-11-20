"""Selection Session Rule Set / Rule Change vocabulary (Task 5C). Defines
the generic MEANING of a Rule Change's scope and of an impacted
Application's recalculation/review status — never a specific Session's
actual rule content, which always lives in the persisted
`SelectionRuleSetVersion`/`SelectionRuleChange`/`SelectionRuleChangeImpact`
rows (`.. models`), populated via `selection/rule_set_service.py` and
`selection/rule_change_service.py`.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Rule Change scope (task §17) — must always be chosen explicitly; never
# silently defaulted (task's own "Do not silently choose the scope").
# ---------------------------------------------------------------------------

SUBSEQUENT_ONLY = "SUBSEQUENT_ONLY"
ENTIRE_SESSION = "ENTIRE_SESSION"

RULE_CHANGE_SCOPES = (SUBSEQUENT_ONLY, ENTIRE_SESSION)


def validate_rule_change_scope(scope: str) -> None:
    if scope not in RULE_CHANGE_SCOPES:
        raise ValueError(f"Unknown Rule Change scope {scope!r}; expected one of {RULE_CHANGE_SCOPES}")


# ---------------------------------------------------------------------------
# Impact recalculation status (task §19/§21) — an ENTIRE_SESSION Rule
# Change may safely re-run a deterministic component for an already-
# processed Application; this tracks whether that happened, never whether
# a human has reviewed the result (see REVIEW_STATUSES below).
# ---------------------------------------------------------------------------

RECALC_NOT_APPLICABLE = "NOT_APPLICABLE"
RECALC_PENDING = "PENDING"
RECALC_RECALCULATED = "RECALCULATED"
RECALC_FAILED = "RECALCULATION_FAILED"

RECALCULATION_STATUSES = (RECALC_NOT_APPLICABLE, RECALC_PENDING, RECALC_RECALCULATED, RECALC_FAILED)


# ---------------------------------------------------------------------------
# Impact review status (task §20) — a retroactive Rule Change must never
# silently decide anything; every impacted Application starts
# NEEDS_REVIEW and only an explicit Selezionatore action ever advances it.
# ---------------------------------------------------------------------------

REVIEW_NOT_REQUIRED = "NOT_REQUIRED"
REVIEW_NEEDS_REVIEW = "NEEDS_REVIEW"
REVIEW_REVIEWED = "REVIEWED"

REVIEW_STATUSES = (REVIEW_NOT_REQUIRED, REVIEW_NEEDS_REVIEW, REVIEW_REVIEWED)
