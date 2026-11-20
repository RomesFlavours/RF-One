"""Selection Authority — consolidated checking convention
(GLOBAL_INTEGRITY_FIX_002 / I-4).

Before this fix, "who is allowed to do this consequential thing" was
answered four different, mutually-inconsistent ways inside Selection
(Global Integrity Review 001 §8/I-4): `ownership_service` compared
authority-order via a private helper; `rule_change_service` required only a
free-text reason with no actor-authorization check; `rule_set_service`
required only a non-empty free-text `confirmed_by`; and `governance_service.
get_governance_requirement_for_action` was fully configured but had zero
callers anywhere. This module is the ONE reconciled convention every
Selection service now goes through — it does not invent a new authority
model; it consolidates and wires the two that already existed
(`SelectionAuthorityLevel`'s per-Session ordering, and
`SelectionGovernanceRequirement`'s per-restaurant-configured action gate).

Two independent, composable questions:

1. `get_authority_order_for_identity_in_session()` / `is_strictly_superior()`
   — the Session-scoped ordering `ownership_service` already used, now keyed
   by `ActingIdentity` id (never a display name) via
   `session_service.get_assignment_for_identity`.
2. `check_authority_for_action()` — the restaurant-level, OPT-IN governance
   gate (`SelectionGovernanceRequirement`). No configured requirement for an
   `action_type` means the action is permitted — governance is something a
   restaurant configures, never an invented default block (mirrors
   `governance_service`'s own pre-existing "an unconfigured action type is
   never blocked" documented behavior).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .. import models as m
from . import governance_service as gov_svc
from . import session_service as sess_svc

# Governed action-type identifiers (task §13/§14) — restaurant-configurable
# via `SelectionGovernanceRequirement.action_type`; absent configuration for
# any of these is a valid, unblocked state, never an invented requirement.
ACTION_TAKE_IN_CHARGE = "SELECTION_OWNERSHIP_TAKE_IN_CHARGE"
ACTION_REASSIGN_OWNERSHIP = "SELECTION_OWNERSHIP_REASSIGN"
ACTION_CONFIRM_RULE_SET = "SELECTION_RULE_SET_CONFIRM"
ACTION_PROPOSE_RULE_CHANGE = "SELECTION_RULE_CHANGE_PROPOSE"


def get_authority_order_for_identity_in_session(
    session: Session, session_id: int, identity_id: int | None,
) -> int | None:
    """The ONE place Selection resolves an Acting Identity's configured
    authority order within a Session (1 = lowest). `None` means "no
    configured level" — undefined dependency, per `SelectionAuthorityLevel`'s
    own docstring, means peers, never an invented rank."""

    assignment = sess_svc.get_assignment_for_identity(session, session_id, identity_id)
    if assignment is None or assignment.authority_level_id is None:
        return None
    level = gov_svc.get_authority_level(session, assignment.authority_level_id)
    return level.level_order if level is not None else None


def is_strictly_superior(
    session: Session, session_id: int, requester_identity_id: int | None, other_identity_id: int | None,
) -> bool:
    """True only when `requester_identity_id` has a STRICTLY higher
    configured authority order than `other_identity_id` within this
    Session. Two identities with no configured level (or with the
    requester's level not strictly above the other's) are peers — a peer is
    never "strictly superior" (mirrors the pre-existing `ownership_service.
    can_reassign` peer rule, now identity-keyed)."""

    requester_order = get_authority_order_for_identity_in_session(session, session_id, requester_identity_id)
    other_order = get_authority_order_for_identity_in_session(session, session_id, other_identity_id)
    if requester_order is None or other_order is None:
        return False
    return requester_order > other_order


def check_authority_for_action(
    session: Session, *, restaurant_id: int | None, action_type: str, identity_id: int | None,
    session_id: int | None = None,
) -> None:
    """The ONE choke point that wires `governance_service.
    get_governance_requirement_for_action` (Global Integrity Review I-4 —
    "configured but unused") into an actual enforcement path. Raises
    `ValueError` only when a restaurant HAS configured a governance
    requirement for `action_type` AND the Acting Identity does not meet it
    within the given Session; a restaurant that has configured nothing for
    this `action_type` is never blocked (governance is opt-in, never an
    invented default gate — same principle `governance_service` itself
    already documented)."""

    requirement = gov_svc.get_governance_requirement_for_action(
        session, restaurant_id=restaurant_id, action_type=action_type,
    )
    if requirement is None or requirement.required_authority_level_id is None:
        return

    required_level = gov_svc.get_authority_level(session, requirement.required_authority_level_id)
    if required_level is None:
        return

    order = None
    if session_id is not None:
        order = get_authority_order_for_identity_in_session(session, session_id, identity_id)

    if order is None or order < required_level.level_order:
        raise ValueError(
            f"This action requires configured authority level '{required_level.label or required_level.level_key}' "
            "or higher, which this Acting Identity does not hold in this Session."
        )
