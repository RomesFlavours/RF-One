"""Shared Authority service (RFONE_SHARED_IDENTITY_AUTHORITY_SIGNATURE_001).

The ONE place any Domain checks "is this Acting Identity authorized to
perform this Action, in this context" — Core Principle 21 / Architecture
doc §1: no Domain implements its own permission engine. Every Domain calls
`authorize()` below; none queries `models.AuthorityGrant` directly.

Deliberately lives at the top level of `rfone_data_store` — same placement
rationale as `acting_identity_service.py` — because this substrate must be
usable by any future Domain, not owned by whichever Domain integrates it
first. No Domain is integrated by this module (see its own module
docstring's "foundation, not integration" scope).

Scalability (task requirement — "must not become a centralized network
bottleneck"): `authorize()` performs exactly one indexed SELECT against the
same canonical database every other Domain query already uses — no remote
authorization microservice, no separate network hop. `ix_authority_grants_
lookup` (acting_identity_id, domain, action) keeps that SELECT cheap
regardless of how many Acting Identities or grants exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m

UTC = timezone.utc


class AuthorityContextError(ValueError):
    """Raised when `authorize()` (or a grant helper) is called with an
    incomplete/ambiguous context — e.g. a non-GLOBAL scope with no
    `scope_id`, or a blank domain/action. Always a caller bug (a Domain must
    always state its context explicitly — task requirement "never infer
    tenant/context from a global singleton or hard-coded current
    restaurant"), never a normal "access denied" outcome. Callers must not
    catch this to mean "not authorized" — see `AuthorizationDecision` for
    that."""


@dataclass(frozen=True)
class AuthorizationContext:
    """The explicit context `authorize()` evaluates Authority against —
    Core doc §3's Corporate/Brand/Operational Unit/Operational Area chain,
    reduced to what `models.AuthorityGrant` actually persists today (see
    that model's own docstring for why `scope_id` carries no foreign key).
    Every field must be supplied by the caller; there is no default/global
    scope a caller can silently fall back to. `module=None` means "this
    action is not scoped to a specific Module" — it does NOT mean "any
    Module" (a grant restricted to one Module never matches it)."""

    domain: str
    scope_type: str
    scope_id: int | None
    module: str | None = None


@dataclass(frozen=True)
class AuthorizationDecision:
    """The result of one `authorize()` call. `allowed=False` is a normal,
    expected outcome (an unauthorized request) — never raised as an
    exception; only a malformed CALL (see `AuthorityContextError`) is."""

    allowed: bool
    reason: str
    matched_grant_id: int | None = None


def validate_authority_context(*, domain: str, scope_type: str, scope_id: int | None) -> None:
    if not domain:
        raise AuthorityContextError("An authorization context requires a non-empty domain.")
    if scope_type not in m.AUTHORITY_SCOPE_KINDS:
        raise AuthorityContextError(
            f"Invalid scope_type {scope_type!r} — must be one of {m.AUTHORITY_SCOPE_KINDS}."
        )
    if scope_type != m.SCOPE_GLOBAL and scope_id is None:
        raise AuthorityContextError(
            f"scope_type={scope_type!r} requires an explicit scope_id — a Domain must state exactly "
            "which Corporate/Brand/Operational Unit/Operational Area it means, never leave it implicit."
        )


def authorize(
    session: Session, *, actor: m.ActingIdentity, action: str, context: AuthorizationContext,
    now: datetime | None = None,
) -> AuthorizationDecision:
    """"Is `actor` authorized to perform `action` in `context`?" — never a
    coarser question like page visibility (Architecture doc §4, §8). Backend/
    server-side only: a Domain must call this on every consequential
    request regardless of what the UI would or would not have shown.

    Matching rule — an active (`revoked_at IS NULL`) `AuthorityGrant` for
    `actor` where:
      - `domain` exactly matches `context.domain`;
      - `action` is the grant's own `'*'` wildcard or exactly matches
        `action`;
      - `module` is the grant's own `'*'` wildcard or exactly matches
        `context.module` (a grant naming a specific Module never matches a
        context with `module=None`, and vice versa);
      - AND either the grant's `scope_type` is GLOBAL, or its
        `scope_type`/`scope_id` exactly match `context`'s.

    No hierarchical scope inheritance (e.g. a Corporate-level grant does
    NOT automatically also cover one specific Operational Unit under it) —
    Corporate/Brand/Operational Unit do not exist as persisted tables yet
    (see `models.AUTHORITY_SCOPE_KINDS`), so there is nothing to walk a
    hierarchy over; a grant must name the exact scope it covers. Widening
    this to real hierarchy walking is future work for when those tables
    exist, never a silent assumption made here today.

    Returns a decision, never raises for "not authorized" — only a
    malformed call (empty domain/action, invalid scope) raises
    `AuthorityContextError`."""
    if not action:
        raise AuthorityContextError("authorize() requires a non-empty action.")
    validate_authority_context(domain=context.domain, scope_type=context.scope_type, scope_id=context.scope_id)

    if not actor.is_active:
        return AuthorizationDecision(allowed=False, reason="Acting Identity is not active.")

    now = now or datetime.now(UTC)
    candidates = session.scalars(
        select(m.AuthorityGrant).where(
            m.AuthorityGrant.acting_identity_id == actor.id,
            m.AuthorityGrant.domain == context.domain,
            m.AuthorityGrant.action.in_((action, m.AUTHORITY_WILDCARD)),
            m.AuthorityGrant.revoked_at.is_(None),
        )
    ).all()

    for grant in candidates:
        if grant.module != m.AUTHORITY_WILDCARD and grant.module != context.module:
            continue
        if grant.scope_type == m.SCOPE_GLOBAL:
            return AuthorizationDecision(allowed=True, reason="Matched a GLOBAL grant.", matched_grant_id=grant.id)
        if grant.scope_type == context.scope_type and grant.scope_id == context.scope_id:
            return AuthorizationDecision(
                allowed=True, reason="Matched a scoped grant.", matched_grant_id=grant.id,
            )

    return AuthorizationDecision(allowed=False, reason="No active grant matches this action/context.")


def grant_authority(
    session: Session, *, actor: m.ActingIdentity, domain: str, action: str,
    scope_type: str, scope_id: int | None, module: str | None = None,
    granted_by: m.ActingIdentity | None = None,
) -> m.AuthorityGrant:
    """Creates one bounded Authority grant (Core doc §4 — Delegation's own
    minimal accountability: who granted it, when). Never deletes/reuses a
    revoked grant's row; a new grant is always a new row."""
    validate_authority_context(domain=domain, scope_type=scope_type, scope_id=scope_id)
    if not action:
        raise AuthorityContextError("grant_authority() requires a non-empty action.")

    grant = m.AuthorityGrant(
        acting_identity_id=actor.id, domain=domain, module=module or m.AUTHORITY_WILDCARD, action=action,
        scope_type=scope_type, scope_id=scope_id,
        granted_by_identity_id=granted_by.id if granted_by is not None else None,
    )
    session.add(grant)
    session.flush()
    return grant


def revoke_authority(session: Session, *, grant_id: int, now: datetime | None = None) -> m.AuthorityGrant:
    """Marks a grant revoked (`revoked_at` set) — never deletes it, so a
    revoked grant remains provable as having once existed (Historical
    Integrity)."""
    grant = session.get(m.AuthorityGrant, grant_id)
    if grant is None:
        raise ValueError(f"No AuthorityGrant with id {grant_id}")
    grant.revoked_at = now or datetime.now(UTC)
    session.flush()
    return grant


def list_active_grants(session: Session, *, actor: m.ActingIdentity) -> list[m.AuthorityGrant]:
    return list(
        session.scalars(
            select(m.AuthorityGrant).where(
                m.AuthorityGrant.acting_identity_id == actor.id, m.AuthorityGrant.revoked_at.is_(None),
            )
        ).all()
    )
