"""Selection Outcome vocabulary (Task 5A). Defines the generic, universal
STRUCTURE of a restaurant-configurable Selection Outcome — the Application
lifecycle effect it applies, the future-contact policy it implies, and the
Candidate Flag scope/operational-effect vocabulary a Flag it creates may
use. Never any specific restaurant's actual Outcome names, meanings, or
reason lists — those are restaurant-authored data
(`models.SelectionOutcomeDefinition`), exactly like every other
`core/*_model.py` module's boundary (mirrors `core/primary_screening_model.
py`'s "the SCALE is universal, the MEANING is restaurant data" split).

No Outcome is technically irreversible (task §7) — this module defines no
"terminal"/"final" state; CLOSED is a lifecycle effect an Outcome may
apply, not a system-enforced dead end. Reopening is always a deliberate,
always-available Selezionatore action (`outcome_service.reopen_application`).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Application lifecycle effect (task §6) — what an Outcome does to the
# Application's operational availability. Restaurant-configured per Outcome
# Definition, never hard-coded per Outcome name.
# ---------------------------------------------------------------------------

ACTIVE = "ACTIVE"
SUSPENDED = "SUSPENDED"
CLOSED = "CLOSED"

LIFECYCLE_STATES = (ACTIVE, SUSPENDED, CLOSED)
DEFAULT_LIFECYCLE_STATE = ACTIVE


def validate_lifecycle_state(value: str) -> None:
    if value not in LIFECYCLE_STATES:
        raise ValueError(f"Unknown Application lifecycle state {value!r}; expected one of {LIFECYCLE_STATES}")


# ---------------------------------------------------------------------------
# Future-contact policy (task §5) — a single tri-state axis covering both
# "is future contact allowed" and "should it be discouraged/blocked."
# ---------------------------------------------------------------------------

CONTACT_ALLOWED = "ALLOWED"
CONTACT_DISCOURAGED = "DISCOURAGED"
CONTACT_BLOCKED = "BLOCKED"

FUTURE_CONTACT_POLICIES = (CONTACT_ALLOWED, CONTACT_DISCOURAGED, CONTACT_BLOCKED)
DEFAULT_FUTURE_CONTACT_POLICY = CONTACT_ALLOWED


# ---------------------------------------------------------------------------
# Candidate Flag scope (task §17) — kept as plain fields rather than a
# separate scoping table, per the task's own "avoid unnecessary complexity"
# instruction.
# ---------------------------------------------------------------------------

FLAG_INFORMATIONAL = "INFORMATIONAL"
FLAG_ROLE_SPECIFIC = "ROLE_SPECIFIC"
FLAG_LOCATION_SPECIFIC = "LOCATION_SPECIFIC"
FLAG_TEMPORARY = "TEMPORARY"
FLAG_GLOBAL_WITHIN_RESTAURANT = "GLOBAL_WITHIN_RESTAURANT"

FLAG_SCOPES = (
    FLAG_INFORMATIONAL, FLAG_ROLE_SPECIFIC, FLAG_LOCATION_SPECIFIC, FLAG_TEMPORARY, FLAG_GLOBAL_WITHIN_RESTAURANT,
)
DEFAULT_FLAG_SCOPE = FLAG_INFORMATIONAL


# ---------------------------------------------------------------------------
# Candidate Flag operational effect (task §18) — never an automatic
# permanent rejection; the strongest configurable effect only requires
# Selezionatore attention.
# ---------------------------------------------------------------------------

FLAG_INFORMATION_ONLY = "INFORMATION_ONLY"
FLAG_WARNING = "WARNING"
FLAG_OPERATIONAL_ACTION = "OPERATIONAL_ACTION"

FLAG_OPERATIONAL_EFFECTS = (FLAG_INFORMATION_ONLY, FLAG_WARNING, FLAG_OPERATIONAL_ACTION)
DEFAULT_FLAG_OPERATIONAL_EFFECT = FLAG_INFORMATION_ONLY


def validate_flag_scope(value: str) -> None:
    if value not in FLAG_SCOPES:
        raise ValueError(f"Unknown Candidate Flag scope {value!r}; expected one of {FLAG_SCOPES}")


def validate_flag_operational_effect(value: str) -> None:
    if value not in FLAG_OPERATIONAL_EFFECTS:
        raise ValueError(f"Unknown Candidate Flag operational effect {value!r}; expected one of {FLAG_OPERATIONAL_EFFECTS}")


# ---------------------------------------------------------------------------
# "Driven by" (task 5A-ALIGN §14 — "whether it is candidate-driven or
# restaurant-driven where relevant"). Purely descriptive/UI-dropdown-
# convenience, like `SelectionOutcomeDefinition.authority_label` — neither
# is enforced by any RBAC/workflow-gating mechanism, since none exists in
# Selection (same honest-placeholder rationale as `performed_by`
# throughout this codebase).
# ---------------------------------------------------------------------------

DRIVEN_BY_RESTAURANT = "RESTAURANT"
DRIVEN_BY_CANDIDATE = "CANDIDATE"
DRIVEN_BY_EITHER = "EITHER"

DRIVEN_BY_OPTIONS = (DRIVEN_BY_RESTAURANT, DRIVEN_BY_CANDIDATE, DRIVEN_BY_EITHER)
