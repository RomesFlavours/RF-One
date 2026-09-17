"""Minimal Purchased Human Review action model ("Purchased Human Review +
Supplier Format Training UI", Task requirement 19).

**Status: TEMPORARY / NON-CANONICAL.** This module is a local, Purchased-
only stand-in, not a general-purpose authorization framework — do not
extend it to cover another Domain/module's actions, and do not treat it as
a precedent for how RF-One authorization should work generally. It exists
only until Identity & Access unfreezes (see below); "Make Effective
Purchased View canonical for all consumers" deliberately leaves it exactly
as-is.

**Why this is not the shared Authority system**: `10 System/Identity &
Access/README.md` is explicit — "Identity & Access development is
**FROZEN**... Do not continue implementation against this area until
explicitly unfrozen" — and "No Domain currently consumes this foundation
(Tips, Selection, Purchasing and other Domains are not integrated — by
design)". Wiring this feature to `rfone_data_store.authority_service.
authorize()`/`AuthorityGrant` would make Purchased the first Domain to
integrate with a foundation the Product Owner has explicitly paused; that
is a bigger decision than this task, so this module deliberately does not
do it.

Per the task's own fallback ("Se manca un action model Purchased-specifico:
implementa la minima estensione necessaria, senza creare un authority
framework parallelo"), this is the smallest usable action model for this
one feature — three roles, three actions, a plain lookup table. It is not
a reusable/general authorization framework and never claims to BE the real
Authority system; it exists to be swapped out once Identity & Access
unfreezes (see `10 System/Identity & Access/README.md` for what that
would look like).

**Enforcement, and its honest limitation**: every mutating route in
`app.py` calls `has_action()` against the role stored in Flask's signed
session cookie (`/review/login`) — never a plain request field a client
could edit directly — so the ACTION MODEL itself (view vs. correct vs.
validate) is genuinely enforced server-side (Task: "NON usare solo
'is_admin'"; "NON bypassare la service logic"). What this does NOT do is
verify who the person actually is — `/review/login` records a
self-declared name/role, not a checked credential, because no real
authentication exists anywhere in this prototype and Identity & Access
(the system that would provide one) is frozen. This is the honest, minimal
stand-in the freeze leaves available, not a defense against a malicious
actor who already has access to the UI."""

from __future__ import annotations

ROLE_VIEWER = "VIEWER"
ROLE_REVIEWER = "REVIEWER"
ROLE_VALIDATOR = "VALIDATOR"

ROLES = (ROLE_VIEWER, ROLE_REVIEWER, ROLE_VALIDATOR)

ACTION_VIEW_QUEUE = "view_review_queue"
ACTION_CORRECT = "correct_purchased_document"
ACTION_VALIDATE_FORMAT = "validate_supplier_format"

# Each role's action set is cumulative -- Task requirement 19: "Almeno
# distinguere: view review queue; edit/correct Purchased; validate
# Supplier+Format".
_ROLE_ACTIONS: dict[str, set[str]] = {
    ROLE_VIEWER: {ACTION_VIEW_QUEUE},
    ROLE_REVIEWER: {ACTION_VIEW_QUEUE, ACTION_CORRECT},
    ROLE_VALIDATOR: {ACTION_VIEW_QUEUE, ACTION_CORRECT, ACTION_VALIDATE_FORMAT},
}


def has_action(role: str | None, action: str) -> bool:
    """`False` for any unrecognized role (including `None`/not-logged-in) —
    never grants an action to an unknown actor by default."""

    return action in _ROLE_ACTIONS.get(role or "", set())
