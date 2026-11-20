"""Canonical RF-One Account service — the general login identity for
RF-One's own web shell (`03 Software/RF-One Web/`), deliberately
independent of any Domain-specific account (e.g. `models.TrainingAccount`).
Lives at the top level of `rfone_data_store`, not inside any Domain
package, for the same reason `acting_identity_service.py` does (Core
Principle 21: no Domain may define its own independent identity/authority
mechanism) — RF-One Web is the general shell, not a Domain.

`RFOneAccountDomainAccess` rows only record WHETHER an account may enter a
Domain (`domain_code`, matching `RF-One Web/domain_registry.py`) and an
optional, Domain-interpreted `role_code` — this module implements no
Domain-specific authorization logic.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash

from . import models as m

VALID_STATUSES = ("ACTIVE", "INACTIVE")


class UsernameTakenError(ValueError):
    pass


class EmailTakenError(ValueError):
    pass


def normalize_email(email: str) -> str:
    """Trim + lowercase the whole address — the ONE normalization used
    everywhere an email is stored or compared (registration, verification,
    profile change, recovery lookup). Deliberately does NOT apply any
    provider-specific transformation (e.g. stripping Gmail's dots/'+'
    suffix) — task: "senza trasformazioni specifiche dei provider"."""
    return email.strip().lower()


def _validate_email_format(email: str) -> str:
    normalized = normalize_email(email)
    if not normalized or "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise ValueError("A valid email address is required.")
    return normalized


def check_email_available(session: Session, email: str, *, exclude_account_id: int | None = None) -> None:
    """Raises `EmailTakenError` if `email` (already normalized by the
    caller) belongs to another account. Public — also called from
    `03 Software/RF-One Web/app.py`'s profile email-change route to give
    an immediate error before issuing a code, ahead of the DB unique
    constraint that is the actual final authority (see
    `confirm_account_email`, which re-checks at confirmation time too)."""
    query = select(m.RFOneAccount).where(m.RFOneAccount.email == email)
    if exclude_account_id is not None:
        query = query.where(m.RFOneAccount.id != exclude_account_id)
    existing = session.scalars(query).first()
    if existing is not None:
        raise EmailTakenError("This email address is already associated with another account.")


def create_account(
    session: Session, *, username: str, display_name: str, password: str,
    status: str = "ACTIVE", is_admin: bool = False, email: str | None = None,
) -> m.RFOneAccount:
    normalized_username = username.strip().lower()
    if not normalized_username:
        raise ValueError("username is required")
    if not display_name.strip():
        raise ValueError("display_name is required")
    if not password:
        raise ValueError("password is required")
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status {status!r} — must be one of {VALID_STATUSES}")

    existing = session.scalars(
        select(m.RFOneAccount).where(m.RFOneAccount.username == normalized_username)
    ).first()
    if existing is not None:
        raise UsernameTakenError(f"Username {normalized_username!r} is already in use.")

    normalized_email = None
    if email:
        normalized_email = _validate_email_format(email)
        check_email_available(session, normalized_email)

    account = m.RFOneAccount(
        username=normalized_username, display_name=display_name.strip(),
        password_hash=generate_password_hash(password), status=status, is_admin=is_admin,
        email=normalized_email,
    )
    session.add(account)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        if normalized_email is not None:
            raise EmailTakenError("This email address is already associated with another account.") from exc
        raise UsernameTakenError(f"Username {normalized_username!r} is already in use.") from exc
    return account


def update_account(session: Session, account: m.RFOneAccount, *, display_name: str, status: str) -> None:
    if not display_name.strip():
        raise ValueError("display_name is required")
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status {status!r} — must be one of {VALID_STATUSES}")
    account.display_name = display_name.strip()
    account.status = status
    session.flush()


def set_password(session: Session, account: m.RFOneAccount, new_password: str) -> None:
    """Overwrites the password hash — the previous password is never
    recoverable. Also bumps `session_version`, the minimal server-side
    mechanism behind session revocation (task: "invalida tutte le sessioni
    RF-One precedenti"): every session cookie issued before this call
    stops matching on its very next request, for EVERY caller of this
    function — self-service password recovery, the existing admin
    reset-password route, and the Training-trainer student reset alike
    (task: "Applica la stessa revoca anche al reset amministrativo
    esistente") — with no separate mechanism needed per caller."""
    if not new_password:
        raise ValueError("password is required")
    account.password_hash = generate_password_hash(new_password)
    account.session_version += 1
    session.flush()


def request_account_email(session: Session, account: m.RFOneAccount, email: str) -> None:
    """The "no email on file yet" case only — a first email is recorded
    immediately (unverified: `email_verified_at` stays NULL) so it is
    visible right away (profile page, admin view) while confirmation is
    pending. Never used to CHANGE an already-present email — the old
    verified address must stay untouched until a new one is confirmed
    (task: "Mantieni il vecchio indirizzo verificato fino al
    completamento"); that case stages its candidate address only in the
    verification-code row itself (see `rfone_recovery_service.issue_code`'s
    `target_email`) and calls `confirm_account_email` below to apply it."""
    if account.email is not None:
        raise ValueError("Account already has an email on file — use the change flow instead.")
    normalized = _validate_email_format(email)
    check_email_available(session, normalized, exclude_account_id=account.id)
    account.email = normalized
    account.email_verified_at = None
    session.flush()


def confirm_account_email(session: Session, account: m.RFOneAccount, email: str) -> None:
    """Applies a successfully-verified email and stamps `email_verified_at`
    — called only after `rfone_recovery_service.verify_and_consume_code`
    has confirmed a matching EMAIL_VERIFICATION code for the SAME `email`.
    Covers both the first-email case (already written by
    `request_account_email`; this only stamps the verification timestamp)
    and the change case (writes the new address here, for the first time,
    exactly when the old one stops being authoritative)."""
    normalized = _validate_email_format(email)
    if account.email != normalized:
        check_email_available(session, normalized, exclude_account_id=account.id)
        account.email = normalized
    account.email_verified_at = datetime.now(timezone.utc)
    session.flush()


@dataclass(frozen=True)
class LoginResult:
    account: m.RFOneAccount | None
    error: str | None  # None on success


def verify_login(session: Session, username: str, password: str) -> LoginResult:
    """Server-side login check. Always returns a generic error for an
    unknown username or a wrong password (never reveals which); an
    otherwise-correct login against an INACTIVE account gets its own
    distinct message (task §"inactive accounts cannot log in")."""
    normalized_username = username.strip().lower()
    account = session.scalars(
        select(m.RFOneAccount).where(m.RFOneAccount.username == normalized_username)
    ).first()

    if account is None:
        return LoginResult(None, "Invalid username or password.")
    if not check_password_hash(account.password_hash, password):
        return LoginResult(None, "Invalid username or password.")
    if account.status != "ACTIVE":
        return LoginResult(None, "This account is not active.")
    return LoginResult(account, None)


def verify_password(account: m.RFOneAccount, password: str) -> bool:
    """Checks `password` against `account`'s stored hash — the same check
    `verify_login` makes, exposed standalone for a route that already has
    the account loaded and only needs to re-confirm the current password
    (e.g. before starting a profile email change)."""
    return check_password_hash(account.password_hash, password)


def get_account(session: Session, account_id: int) -> m.RFOneAccount | None:
    return session.get(m.RFOneAccount, account_id)


def get_account_by_username(session: Session, username: str) -> m.RFOneAccount | None:
    normalized_username = username.strip().lower()
    return session.scalars(
        select(m.RFOneAccount).where(m.RFOneAccount.username == normalized_username)
    ).first()


def list_accounts(session: Session) -> list[m.RFOneAccount]:
    return list(session.scalars(select(m.RFOneAccount).order_by(m.RFOneAccount.display_name)).all())


def list_domain_access_for_account(session: Session, account_id: int) -> list[m.RFOneAccountDomainAccess]:
    return list(
        session.scalars(
            select(m.RFOneAccountDomainAccess).where(m.RFOneAccountDomainAccess.account_id == account_id)
        ).all()
    )


def list_domain_item_access_for_account(session: Session, account_id: int) -> dict[str, set[str]]:
    """The items granted to `account_id`, by Domain code — meaningful only
    for a Domain whose access scope is SELECTED."""
    items: dict[str, set[str]] = {}
    for row in session.scalars(
        select(m.RFOneAccountDomainItemAccess).where(m.RFOneAccountDomainItemAccess.account_id == account_id)
    ):
        items.setdefault(row.domain_code, set()).add(row.item_code)
    return items


def set_domain_access(
    session: Session, *, account_id: int, domain_code: str, enabled: bool, role_code: str | None,
    scope: str | None = None, item_codes: Iterable[str] | None = None,
) -> m.RFOneAccountDomainAccess:
    """Creates or updates the one `RFOneAccountDomainAccess` row for
    (account_id, domain_code) — never a second row for the same pair (see
    that model's own unique constraint).

    `scope` None leaves an existing row's scope as it is (a new row gets
    ALL), so a caller that only switches a Domain on or off never narrows
    it. SELECTED requires at least one item: an access to "only these
    items" with no item would be a no-access in disguise. The item list is
    replaced as a whole when SELECTED, and cleared when the Domain is
    disabled or opened whole, so a stale selection never comes back."""
    if scope is not None and scope not in m.DOMAIN_ACCESS_SCOPES:
        raise ValueError(f"Unknown access scope {scope!r}.")
    selected_items = sorted({code.strip() for code in (item_codes or ()) if code and code.strip()})
    if enabled and scope == m.DOMAIN_ACCESS_SCOPE_SELECTED and not selected_items:
        raise ValueError(f"{domain_code}: choose at least one item, or give no access / access to the whole Domain.")

    existing = session.scalars(
        select(m.RFOneAccountDomainAccess).where(
            m.RFOneAccountDomainAccess.account_id == account_id,
            m.RFOneAccountDomainAccess.domain_code == domain_code,
        )
    ).first()
    if existing is None:
        existing = m.RFOneAccountDomainAccess(
            account_id=account_id, domain_code=domain_code, enabled=enabled, role_code=role_code,
            scope=scope or m.DOMAIN_ACCESS_SCOPE_ALL,
        )
        session.add(existing)
    else:
        existing.enabled = enabled
        existing.role_code = role_code
        if scope is not None:
            existing.scope = scope

    if scope is not None or not enabled:
        session.execute(
            delete(m.RFOneAccountDomainItemAccess).where(
                m.RFOneAccountDomainItemAccess.account_id == account_id,
                m.RFOneAccountDomainItemAccess.domain_code == domain_code,
            )
        )
        if enabled and scope == m.DOMAIN_ACCESS_SCOPE_SELECTED:
            session.add_all(
                m.RFOneAccountDomainItemAccess(account_id=account_id, domain_code=domain_code, item_code=code)
                for code in selected_items
            )
    session.flush()
    return existing
