"""Central authorization of financial actions taken by a signed-in person
(CLOVER_MULTISITE_001, Product Owner 2026-11-21).

The ONE check every Domain that moves or approves money calls before acting
for a person — Tips today (Approve & Pay, retry of a failed payment);
Compensation and the other financial Domains reuse it with their own
`domain_code`/`action`, never a copy. It composes the existing shared parts,
it adds no new permission engine:

1. **Who acts** is the authenticated RF-One account, never a person chosen on
   a page. `acting_identity_for_account` binds each account to exactly one
   `ActingIdentity` (provider `rfone-account`, subject = account id), through
   the same idempotent get-or-create primitive the system identity uses.
   Payment authorities are granted to that identity, so a payment is always
   approved and recorded as the person who is signed in.
2. **Where** — the account must be allowed the restaurant in that Domain
   (`site_selection.account_restaurant_ids`, the central per-company/per-site
   rule) and the restaurant must be operational (an inactive site never pays).
3. **What** — the identity must hold the specific payment authority
   (`authority_service.authorize`, scope RESTAURANT or GLOBAL) for the action.

All three are required (Product Owner rule 4: restaurant access AND a specific
payment authorization). The decision is evaluated server-side on every
request; a page may show it, never replace it.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import acting_identity_service
from . import models as m
from . import site_selection
from .authority_service import AuthorizationContext, authorize, grant_authority, list_active_grants, revoke_authority

ACCOUNT_IDENTITY_PROVIDER = "rfone-account"


@dataclass(frozen=True)
class PaymentPermission:
    """One grantable financial authority, as offered on the account's Access
    page. Adding a Domain's financial action = one more entry here."""
    domain_code: str
    action: str
    label: str


TIPS_APPROVE_AND_PAY = PaymentPermission("TIPS", "APPROVE_AND_PAY", "Tips — Approve & Pay and retry of failed payments")
PAYMENT_PERMISSIONS: tuple[PaymentPermission, ...] = (TIPS_APPROVE_AND_PAY,)


class FinancialAuthorizationError(PermissionError):
    """The signed-in person may not take this financial action. Nothing has
    been changed and no payment provider has been called."""


@dataclass(frozen=True)
class FinancialDecision:
    allowed: bool
    reason: str
    acting_identity: "m.ActingIdentity | None" = None


def _active_account(account) -> bool:
    return account is not None and account.status == "ACTIVE"


def acting_identity_for_account(session: Session, account: "m.RFOneAccount") -> "m.ActingIdentity":
    """The one Acting Identity of a signed-in RF-One account (created on first
    use, then always the same row)."""
    if not _active_account(account):
        raise FinancialAuthorizationError("Sign in with an active RF-One account.")
    identity = acting_identity_service.get_or_create_identity_for_verified_subject(
        session, provider=ACCOUNT_IDENTITY_PROVIDER, subject=str(account.id),
        display_name=(account.display_name or "").strip() or account.username,
    )
    return identity


def existing_identity_for_account(session: Session, account) -> "m.ActingIdentity | None":
    """The account's Acting Identity if it was already created (read-only)."""
    if account is None:
        return None
    return session.scalars(select(m.ActingIdentity).where(
        m.ActingIdentity.authentication_provider == ACCOUNT_IDENTITY_PROVIDER,
        m.ActingIdentity.external_subject_id == str(account.id))).first()


def decide(
    session: Session, *, account, permission: PaymentPermission, restaurant_id: int | None,
) -> FinancialDecision:
    """Whether `account` may take `permission` for `restaurant_id` now."""
    if not _active_account(account):
        return FinancialDecision(False, "Sign in with an active RF-One account.")
    if restaurant_id is None or not site_selection.account_may_use_restaurant(
            session, account, permission.domain_code, restaurant_id):
        return FinancialDecision(False, "Your account has no access to this restaurant in this area.")
    if not site_selection.restaurant_is_operational(session, restaurant_id):
        return FinancialDecision(False, "This restaurant is not active yet: no payment is made for it.")
    # Read-only: an authority is always granted to an existing account identity
    # (`set_restaurant_grants` creates it), so no identity means no authority.
    identity = existing_identity_for_account(session, account)
    if identity is None:
        return FinancialDecision(False, "Your account has no payment authorization for this restaurant.")
    decision = authorize(
        session, actor=identity, action=permission.action,
        context=AuthorizationContext(domain=permission.domain_code, scope_type=m.SCOPE_RESTAURANT,
                                     scope_id=restaurant_id),
    )
    if not decision.allowed:
        return FinancialDecision(False, "Your account has no payment authorization for this restaurant.", identity)
    return FinancialDecision(True, decision.reason, identity)


def require(
    session: Session, *, account, permission: PaymentPermission, restaurant_id: int | None,
) -> "m.ActingIdentity":
    """`decide`, raising `FinancialAuthorizationError` when refused; returns
    the account's own Acting Identity to record as the actor."""
    decision = decide(session, account=account, permission=permission, restaurant_id=restaurant_id)
    if not decision.allowed:
        raise FinancialAuthorizationError(decision.reason)
    return decision.acting_identity


# --- Granting (administration, Access page) ---------------------------------

def granted_restaurant_ids(session: Session, account, permission: PaymentPermission) -> set[int | None]:
    """Restaurants for which the account's identity holds `permission`
    (None in the set = a GLOBAL grant)."""
    identity = existing_identity_for_account(session, account)
    if identity is None:
        return set()
    result: set[int | None] = set()
    for grant in list_active_grants(session, actor=identity):
        if grant.domain != permission.domain_code or grant.action not in (permission.action, m.AUTHORITY_WILDCARD):
            continue
        if grant.scope_type == m.SCOPE_GLOBAL:
            result.add(None)
        elif grant.scope_type == m.SCOPE_RESTAURANT:
            result.add(grant.scope_id)
    return result


def set_restaurant_grants(
    session: Session, *, account, permission: PaymentPermission, restaurant_ids, granted_by_account=None,
) -> None:
    """Makes the account's RESTAURANT-scoped grants of `permission` exactly
    `restaurant_ids`: new ones are granted (who granted it is recorded), removed
    ones are revoked (kept as history, never deleted). GLOBAL grants are left
    untouched — they are not managed from this page."""
    identity = acting_identity_for_account(session, account)
    granter = acting_identity_for_account(session, granted_by_account) if _active_account(granted_by_account) else None
    wanted = {int(r) for r in restaurant_ids}
    current = {
        grant.scope_id: grant for grant in list_active_grants(session, actor=identity)
        if grant.domain == permission.domain_code and grant.action == permission.action
        and grant.scope_type == m.SCOPE_RESTAURANT
    }
    for restaurant_id, grant in current.items():
        if restaurant_id not in wanted:
            revoke_authority(session, grant_id=grant.id)
    for restaurant_id in wanted - set(current):
        if session.get(m.Restaurant, restaurant_id) is None:
            raise ValueError(f"Unknown restaurant #{restaurant_id}.")
        grant_authority(session, actor=identity, domain=permission.domain_code, action=permission.action,
                        scope_type=m.SCOPE_RESTAURANT, scope_id=restaurant_id, granted_by=granter)
    session.flush()
