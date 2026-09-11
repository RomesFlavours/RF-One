"""RF-One Account email verification and password recovery — ONE shared
mechanism at the `RFOneAccount` level, reusable by every Domain that logs
in through RF-One Web (task: "un'unica funzione a livello RFOneAccount,
riutilizzabile da tutti i Domain che usano il login RF-One" — never a
per-Domain recovery, e.g. never a separate one for Training).

A "code" here is always a random 6-digit string, valid 10 minutes, capped
at 5 verify attempts, scoped to exactly one `purpose`
(`EMAIL_VERIFICATION` or `PASSWORD_RESET` — see
`models.RFOneAccountVerificationCode`) and to exactly one target email —
never valid for the other purpose, and never re-targetable to a different
address after being issued.

The plaintext code is generated here, returned once to the caller (who is
responsible for emailing it — see `03 Software/RF-One Web/app.py`), and
NEVER persisted, logged, or returned again: only `_hash_code`'s HMAC
digest is stored. The HMAC key is derived from the server's own
`RFONE_FLASK_SECRET_KEY` (never itself stored in the database) rather than
a bare hash of the code, specifically because a 6-digit code is too small
a space (1,000,000 possibilities) to survive an offline brute force
against a leaked database alone — task: "una rappresentazione protetta con
chiave server, adatta anche a codici con poche combinazioni."
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models as m

CODE_LENGTH = 6
CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS_PER_CODE = 5
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_SENDS_PER_ACCOUNT_PER_HOUR = 5
# No number is given in the task for the per-IP cap ("ulteriore limite per
# IP") beyond "further" than the per-account one — set generously above the
# per-account cap so it only ever engages a single IP hammering MANY
# accounts (the scenario a per-account limit alone cannot catch), never a
# legitimate user on a normal connection.
MAX_SENDS_PER_IP_PER_HOUR = 20
RATE_WINDOW = timedelta(hours=1)

PURPOSE_EMAIL_VERIFICATION = "EMAIL_VERIFICATION"
PURPOSE_PASSWORD_RESET = "PASSWORD_RESET"
VALID_PURPOSES = (PURPOSE_EMAIL_VERIFICATION, PURPOSE_PASSWORD_RESET)

_HMAC_KEY_LABEL = b"rfone-account-verification-code-v1"
_DIGITS = "0123456789"


def _as_aware_utc(value: datetime) -> datetime:
    """SQLite (local/test) does not actually preserve tzinfo through a
    `DateTime(timezone=True)` column the way PostgreSQL (RDS) does — a
    value read back from SQLite comes back naive. Every Python-level
    comparison against `datetime.now(timezone.utc)` in this module goes
    through this first, so the two dialects behave identically instead of
    the naive/aware comparison raising `TypeError` only under SQLite."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _hmac_key(flask_secret_key: str) -> bytes:
    return hmac.new(flask_secret_key.encode("utf-8"), _HMAC_KEY_LABEL, hashlib.sha256).digest()


def _hash_code(code: str, flask_secret_key: str) -> str:
    key = _hmac_key(flask_secret_key)
    return hmac.new(key, code.encode("utf-8"), hashlib.sha256).hexdigest()


def generate_numeric_code() -> str:
    return "".join(secrets.choice(_DIGITS) for _ in range(CODE_LENGTH))


class RateLimitedError(Exception):
    """A resend was refused by the 60s cooldown or an hourly cap. Callers
    in the web layer must still show the SAME generic response as any
    other ineligible case (task: "non rivelare esistenza, stato o email
    dell'account attraverso messaggi diversi") — this is never surfaced to
    the end user as a distinct message."""


def _recent_send_count(session: Session, *, account_id: int | None, request_ip: str | None, purpose: str | None, since: datetime) -> int:
    query = select(func.count()).select_from(m.RFOneAccountVerificationCode).where(
        m.RFOneAccountVerificationCode.created_at >= since,
    )
    if account_id is not None:
        query = query.where(m.RFOneAccountVerificationCode.account_id == account_id)
    if purpose is not None:
        query = query.where(m.RFOneAccountVerificationCode.purpose == purpose)
    if request_ip is not None:
        query = query.where(m.RFOneAccountVerificationCode.request_ip == request_ip)
    return session.scalar(query) or 0


def issue_code(
    session: Session, *, account: m.RFOneAccount, purpose: str, target_email: str,
    flask_secret_key: str, request_ip: str | None,
) -> str:
    """Creates a new code row for (account, purpose), first invalidating
    any still-active code for that SAME pair (task: "il reinvio invalida
    il codice precedente"). Raises `RateLimitedError` — without creating
    or sending anything — if the 60s cooldown since the last code, the
    5-per-hour per-account cap, or the per-IP cap are not satisfied; this
    also bounds how many attempts a resend loop could ever accumulate
    (task: "non deve consentire di aggirare i limiti dei tentativi").
    Returns the plaintext code; the caller must send it and never persist
    or log it."""
    if purpose not in VALID_PURPOSES:
        raise ValueError(f"Invalid purpose {purpose!r} — must be one of {VALID_PURPOSES}")

    now = datetime.now(timezone.utc)

    active = session.scalars(
        select(m.RFOneAccountVerificationCode).where(
            m.RFOneAccountVerificationCode.account_id == account.id,
            m.RFOneAccountVerificationCode.purpose == purpose,
            m.RFOneAccountVerificationCode.consumed_at.is_(None),
            m.RFOneAccountVerificationCode.invalidated_at.is_(None),
        ).order_by(m.RFOneAccountVerificationCode.created_at.desc(), m.RFOneAccountVerificationCode.id.desc())
    ).first()

    if active is not None and _as_aware_utc(active.created_at) > now - RESEND_COOLDOWN:
        raise RateLimitedError("Please wait before requesting another code.")

    since = now - RATE_WINDOW
    if _recent_send_count(session, account_id=account.id, request_ip=None, purpose=purpose, since=since) >= MAX_SENDS_PER_ACCOUNT_PER_HOUR:
        raise RateLimitedError("Too many codes requested for this account in the last hour.")
    if request_ip and _recent_send_count(session, account_id=None, request_ip=request_ip, purpose=None, since=since) >= MAX_SENDS_PER_IP_PER_HOUR:
        raise RateLimitedError("Too many codes requested from this network in the last hour.")

    if active is not None:
        active.invalidated_at = now

    code = generate_numeric_code()
    row = m.RFOneAccountVerificationCode(
        account_id=account.id, purpose=purpose, target_email=target_email,
        code_hmac=_hash_code(code, flask_secret_key), request_ip=request_ip,
        expires_at=now + CODE_TTL,
    )
    session.add(row)
    session.flush()
    return code


def get_pending_code(session: Session, account_id: int, purpose: str) -> "m.RFOneAccountVerificationCode | None":
    """The current still-usable code for (account, purpose), if any — used
    to show "a code was sent to X, awaiting confirmation" state (e.g. on
    the profile page) without exposing the code itself."""
    now = datetime.now(timezone.utc)
    return session.scalars(
        select(m.RFOneAccountVerificationCode).where(
            m.RFOneAccountVerificationCode.account_id == account_id,
            m.RFOneAccountVerificationCode.purpose == purpose,
            m.RFOneAccountVerificationCode.consumed_at.is_(None),
            m.RFOneAccountVerificationCode.invalidated_at.is_(None),
            m.RFOneAccountVerificationCode.expires_at > now,
        ).order_by(m.RFOneAccountVerificationCode.created_at.desc(), m.RFOneAccountVerificationCode.id.desc())
    ).first()


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    code_row: "m.RFOneAccountVerificationCode | None"


def verify_and_consume_code(
    session: Session, *, account_id: int, purpose: str, submitted_code: str, flask_secret_key: str,
) -> VerifyResult:
    """Locks the account's current code row for `purpose`
    (`with_for_update()`) for the rest of the caller's transaction, so two
    concurrent submissions of the same code can never both succeed — the
    second blocks on the row lock until the first commits, then observes
    the row already consumed or attempts-exhausted (task: "il consumo deve
    essere atomico"). A purpose mismatch is structurally impossible to
    exploit here: the query itself is filtered on `purpose`, so a
    PASSWORD_RESET code is never even considered for an EMAIL_VERIFICATION
    call and vice versa. On a wrong code, increments `attempts_used` and,
    at `MAX_ATTEMPTS_PER_CODE`, invalidates the code outright. Callers
    MUST commit (or otherwise release the transaction) promptly either
    way, since the row lock is held until then."""
    now = datetime.now(timezone.utc)

    # Filtered to the still-active row (never consumed/invalidated), not
    # just "most recent by created_at": the invariant `issue_code`
    # maintains (at most one active row per account+purpose at a time)
    # means this is the ONLY row that can legitimately match a submission,
    # and unlike relying on ORDER BY alone it stays correct even when two
    # rows tie on `created_at` — SQLite's CURRENT_TIMESTAMP is only
    # second-resolution, so two codes issued less than a second apart
    # (e.g. a fast resend in a test, or in practice) would otherwise sort
    # unpredictably and could resolve to an already-consumed/invalidated
    # sibling instead of the real active code.
    row = session.scalars(
        select(m.RFOneAccountVerificationCode).where(
            m.RFOneAccountVerificationCode.account_id == account_id,
            m.RFOneAccountVerificationCode.purpose == purpose,
            m.RFOneAccountVerificationCode.consumed_at.is_(None),
            m.RFOneAccountVerificationCode.invalidated_at.is_(None),
        ).order_by(
            m.RFOneAccountVerificationCode.created_at.desc(), m.RFOneAccountVerificationCode.id.desc(),
        ).with_for_update()
    ).first()

    if row is None or row.consumed_at is not None or row.invalidated_at is not None:
        return VerifyResult(False, None)
    if _as_aware_utc(row.expires_at) <= now:
        row.invalidated_at = now
        session.flush()
        return VerifyResult(False, None)
    if row.attempts_used >= MAX_ATTEMPTS_PER_CODE:
        row.invalidated_at = now
        session.flush()
        return VerifyResult(False, None)

    expected = _hash_code((submitted_code or "").strip(), flask_secret_key)
    if not hmac.compare_digest(expected, row.code_hmac):
        row.attempts_used += 1
        if row.attempts_used >= MAX_ATTEMPTS_PER_CODE:
            row.invalidated_at = now
        session.flush()
        return VerifyResult(False, None)

    row.consumed_at = now
    session.flush()
    return VerifyResult(True, row)


def invalidate_pending_codes(session: Session, account_id: int, *, exclude_id: int | None = None) -> None:
    """Invalidates every still-active code for this account, across BOTH
    purposes — called after a successful self-service password reset
    (task: "invalida il codice e le altre richieste di recupero pendenti
    dell'account") and after a successful email change (task: "invalida le
    richieste pendenti legate al precedente indirizzo quando la modifica
    riesce")."""
    now = datetime.now(timezone.utc)
    rows = session.scalars(
        select(m.RFOneAccountVerificationCode).where(
            m.RFOneAccountVerificationCode.account_id == account_id,
            m.RFOneAccountVerificationCode.consumed_at.is_(None),
            m.RFOneAccountVerificationCode.invalidated_at.is_(None),
        )
    ).all()
    for row in rows:
        if exclude_id is not None and row.id == exclude_id:
            continue
        row.invalidated_at = now
    session.flush()
