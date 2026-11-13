"""Shared Acting Identity service (GLOBAL_INTEGRITY_FIX_002 / C-1).

The ONE place any Domain resolves "who is currently acting" and manages
`models.ActingIdentity` rows. Deliberately lives at the top level of
`rfone_data_store` — NOT inside `selection/` — because Core Principle 21
("No Domain or Module may define its own independent identity, authority or
audit mechanism") means this substrate must be usable by any future Domain,
not owned by Selection merely because Selection is its first consumer.

`get_current_acting_identity()` is the ONE pre-Authentication resolver this
fix introduces. It is explicitly, permanently temporary:

    THIS IS NOT AUTHENTICATION. It never verifies a password, a session
    token issued by a real identity provider, or any cryptographic proof of
    who is making a request. It resolves an already-existing, already-
    trusted-server-side `ActingIdentity` row from (in order) an explicitly
    requested id, a deployment-level environment variable, or a deterministic
    local default — never from an arbitrary, unauthenticated HTTP form field.
    A caller (e.g. `03 Software/Selection/app.py`) may let an operator pick
    WHICH already-existing identity is "current" for their local session
    (a developer convenience, analogous to a demo user switcher), but that
    selection is itself only ever validated against `ActingIdentity` rows
    that already exist and are active — never created from free-typed text
    at the point of use. Connecting a real Authentication provider (e.g.
    Cognito, per `03 Software/Identity Authority and Security Architecture.md`)
    means replacing the body of this ONE function with real token
    verification — no Domain route should need to change.
"""

from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m

# Deployment-level override for which ActingIdentity id is "current" when no
# per-request selection has been made (e.g. a single-operator local/staging
# deployment). Never read from request/form input.
DEV_IDENTITY_ENV_VAR = "RFONE_DEV_ACTING_IDENTITY_ID"

SYSTEM_PROVIDER = "rfone-internal"
SYSTEM_SUBJECT = "SYSTEM"
DEV_PROVIDER = "rfone-dev-local"
DEFAULT_DEV_SUBJECT = "default-operator"


def create_identity(
    session: Session, *, kind: str, display_name: str, is_active: bool = True,
    authentication_provider: str | None = None, external_subject_id: str | None = None,
) -> m.ActingIdentity:
    """Registers a new Acting Identity row. This is roster/configuration
    management (analogous to an admin creating a user record before any
    login system exists) — it is NEVER, on its own, proof that the caller
    IS that identity; only `get_current_acting_identity()`'s resolution
    order decides which identity is "current" for a request."""

    if kind not in m.ACTING_IDENTITY_KINDS:
        raise ValueError(f"Invalid ActingIdentity kind {kind!r} — must be one of {m.ACTING_IDENTITY_KINDS}.")
    if not display_name or not display_name.strip():
        raise ValueError("An Acting Identity requires a display name.")

    identity = m.ActingIdentity(
        kind=kind, display_name=display_name.strip(), is_active=is_active,
        authentication_provider=authentication_provider, external_subject_id=external_subject_id,
    )
    session.add(identity)
    session.flush()
    return identity


def get_identity(session: Session, identity_id: int) -> m.ActingIdentity | None:
    return session.get(m.ActingIdentity, identity_id)


def list_identities(
    session: Session, *, kind: str | None = None, active_only: bool = True,
) -> list[m.ActingIdentity]:
    stmt = select(m.ActingIdentity)
    if kind is not None:
        stmt = stmt.where(m.ActingIdentity.kind == kind)
    if active_only:
        stmt = stmt.where(m.ActingIdentity.is_active.is_(True))
    stmt = stmt.order_by(m.ActingIdentity.display_name)
    return list(session.scalars(stmt).all())


def deactivate_identity(session: Session, identity_id: int) -> m.ActingIdentity:
    identity = session.get(m.ActingIdentity, identity_id)
    if identity is None:
        raise ValueError(f"No ActingIdentity with id {identity_id}")
    identity.is_active = False
    session.flush()
    return identity


def _get_or_create_by_subject(
    session: Session, *, kind: str, provider: str, subject: str, display_name: str,
) -> m.ActingIdentity:
    """The idempotent bootstrap primitive both `get_or_create_system_
    identity` and `get_or_create_default_dev_identity` use — matches on the
    (provider, subject) pair the migration's own SYSTEM bootstrap uses, so
    calling this at runtime is always safe even if a migration already
    created the row (get, not duplicate-create)."""

    existing = session.scalars(
        select(m.ActingIdentity).where(
            m.ActingIdentity.authentication_provider == provider,
            m.ActingIdentity.external_subject_id == subject,
        )
    ).first()
    if existing is not None:
        return existing

    identity = m.ActingIdentity(
        kind=kind, display_name=display_name, is_active=True,
        authentication_provider=provider, external_subject_id=subject,
    )
    session.add(identity)
    session.flush()
    return identity


def get_or_create_system_identity(session: Session) -> m.ActingIdentity:
    """The ONE stable SYSTEM Acting Identity for automated/system-originated
    actions (task §6) — never a bare string literal ("SYSTEM", "RF-ONE",
    etc.) written as an actor. Deterministic and idempotent: the same
    (provider, subject) pair the migration's own bootstrap uses, so this
    never creates a second SYSTEM row."""

    return _get_or_create_by_subject(
        session, kind=m.SYSTEM, provider=SYSTEM_PROVIDER, subject=SYSTEM_SUBJECT, display_name="RF-One System",
    )


COGNITO_PROVIDER = "cognito"


def get_or_create_identity_for_verified_subject(
    session: Session, *, provider: str, subject: str, display_name: str, kind: str = m.HUMAN_USER,
) -> m.ActingIdentity:
    """The authentication-boundary hook: called ONLY after a token/subject
    has already been cryptographically verified elsewhere (e.g.
    `technical.cognito_jwt.verify_cognito_jwt()`), never with an
    unverified, client-asserted subject. Just-in-time-provisions the
    `ActingIdentity` row for that (provider, subject) pair on first sight,
    idempotently — a returning subject always resolves to the SAME row
    (its permanent RF-One identifier), never a duplicate.

    This is a thin public wrapper over the same `_get_or_create_by_subject`
    primitive `get_or_create_system_identity`/`get_or_create_default_dev_
    identity` already use — one bootstrap mechanism, not a second one added
    for Cognito specifically. Adding this function does NOT change
    `get_current_acting_identity()`'s own resolution order above — no
    Domain is switched over to it by this change (foundation only)."""

    return _get_or_create_by_subject(
        session, kind=kind, provider=provider, subject=subject, display_name=display_name,
    )


def get_or_create_default_dev_identity(session: Session) -> m.ActingIdentity:
    """The pre-Authentication fallback `HUMAN_USER` identity used when
    nothing more specific has been resolved (task §5) — a single,
    deterministic local-development stand-in, never fabricated per request."""

    return _get_or_create_by_subject(
        session, kind=m.HUMAN_USER, provider=DEV_PROVIDER, subject=DEFAULT_DEV_SUBJECT,
        display_name="Local Operator (pre-Authentication)",
    )


def get_current_acting_identity(
    session: Session, *, requested_identity_id: int | None = None,
) -> m.ActingIdentity:
    """Resolves the current Acting Identity from a trusted server-side
    mechanism (task §5) — NEVER from an arbitrary client-supplied form
    field carrying a name. Resolution order:

    1. `requested_identity_id` — an id already selected through a prior
       trusted server-side action (e.g. a Flask session cookie set only by
       `/identity/switch` after validating the id against an existing,
       active `ActingIdentity` row — see `Selection/app.py`). This is NOT
       the request trusting a name; it is the request trusting an id that
       was already validated to exist and be active.
    2. `RFONE_DEV_ACTING_IDENTITY_ID` — a deployment-level environment
       variable, for a single-operator deployment that wants one fixed
       identity without per-request selection.
    3. The deterministic default pre-Authentication identity (bootstrapped
       idempotently) — never a fabricated per-request identity.

    This function, and only this function, is what a future real
    Authentication provider replaces (see module docstring)."""

    if requested_identity_id is not None:
        identity = session.get(m.ActingIdentity, requested_identity_id)
        if identity is not None and identity.is_active:
            return identity

    env_value = os.environ.get(DEV_IDENTITY_ENV_VAR)
    if env_value:
        try:
            env_identity_id = int(env_value)
        except ValueError:
            env_identity_id = None
        if env_identity_id is not None:
            identity = session.get(m.ActingIdentity, env_identity_id)
            if identity is not None and identity.is_active:
                return identity

    return get_or_create_default_dev_identity(session)
