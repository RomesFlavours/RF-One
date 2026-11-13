"""External candidate identity for Selection's public application pages
(SELECTION_AI_INTEGRATION_001 §4, SELECTION_CANDIDATE_SMS_001).

A candidate registers with full name, email, password and — for the text
message option — a US mobile number, chooses how to receive a 6-digit code
(email or text message) and confirms it; only an identity with at least one
verified channel may apply. A registered candidate signs in again with email
and password, never a second registration. ONE identity whatever the
channel; it is separate from `rfone_accounts` and grants no access to any
internal RF-One function.

The code mechanism mirrors `rfone_recovery_service` (RF-One's own account
email verification): random 6-digit code, only an HMAC keyed by the server
secret is stored, 10-minute validity, 5 attempts, a new code invalidates the
previous one, 60-second cooldown and hourly caps per identity, per
destination (so several registrations cannot flood one inbox or phone) and
per network. The plaintext code and the password are never stored or logged.

Delivering the code is the caller's job (the web layer owns the email and
text-message configuration); this module never sends anything.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash

from rfone_data_store.selection import workspace_models as ws

CODE_LENGTH = 6
CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS_PER_CODE = 5
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_CODES_PER_ACCOUNT_PER_HOUR = 5
MAX_CODES_PER_TARGET_PER_HOUR = 5
MAX_CODES_PER_IP_PER_HOUR = 20
RATE_WINDOW = timedelta(hours=1)
MIN_PASSWORD_LENGTH = 10
MAX_FAILED_LOGINS = 5
LOGIN_LOCK = timedelta(minutes=15)
CHANNELS = (ws.CHANNEL_EMAIL, ws.CHANNEL_SMS)

_HMAC_KEY_LABEL = b"rfone-selection-candidate-email-code-v1"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class CandidateIdentityError(ValueError):
    """A refusal whose message is safe to show to the candidate as is."""


class AlreadyRegistered(CandidateIdentityError):
    pass


class RateLimited(CandidateIdentityError):
    pass


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def normalize_us_phone(phone: str | None) -> str | None:
    """A US number as E.164 (+1 and 10 digits), or None when left empty.
    Raises `CandidateIdentityError` when it is not a valid US number."""
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return None
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] in "01" or digits[3] in "01":
        raise CandidateIdentityError("Please enter a valid US mobile number, for example (407) 555-0123.")
    return "+1" + digits


def masked_phone(phone: str) -> str:
    return f"(***) ***-{phone[-4:]}"


def _hash_code(code: str, secret_key: str) -> str:
    key = hmac.new(secret_key.encode("utf-8"), _HMAC_KEY_LABEL, hashlib.sha256).digest()
    return hmac.new(key, code.encode("utf-8"), hashlib.sha256).hexdigest()


def get_account(session: Session, account_id: int | None) -> ws.CandidateAccount | None:
    return session.get(ws.CandidateAccount, account_id) if account_id else None


def get_account_by_email(session: Session, email: str) -> ws.CandidateAccount | None:
    return session.scalars(select(ws.CandidateAccount).where(
        ws.CandidateAccount.email == normalize_email(email))).first()


def is_verified(account: ws.CandidateAccount | None) -> bool:
    return (account is not None and account.status == ws.CANDIDATE_ACTIVE
            and (account.email_verified_at is not None or account.phone_verified_at is not None))


def _active_code(session: Session, account_id: int) -> ws.CandidateEmailCode | None:
    return session.scalars(select(ws.CandidateEmailCode).where(
        ws.CandidateEmailCode.candidate_account_id == account_id,
        ws.CandidateEmailCode.consumed_at.is_(None),
        ws.CandidateEmailCode.invalidated_at.is_(None),
    ).order_by(ws.CandidateEmailCode.id.desc())).first()


def _validate_registration(full_name: str, email: str, password: str) -> None:
    if not full_name.strip():
        raise CandidateIdentityError("Please enter your full name.")
    if not _EMAIL_RE.match(email):
        raise CandidateIdentityError("Please enter a valid email address.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise CandidateIdentityError(f"Your password must be at least {MIN_PASSWORD_LENGTH} characters long.")


def start_registration(session: Session, *, full_name: str, email: str, password: str, secret_key: str,
                       request_ip: str | None, channel: str = ws.CHANNEL_EMAIL,
                       phone: str | None = None) -> tuple[ws.CandidateAccount, str, str]:
    """Creates (or, while still unverified, updates) the candidate identity
    and issues a new code for `channel`. Returns the account, the plaintext
    code (which the caller must deliver and never store) and the target it
    must go to (email address or E.164 number). Commits nothing."""
    email = normalize_email(email)
    _validate_registration(full_name, email, password)
    if channel not in CHANNELS:
        raise CandidateIdentityError("Please choose how to receive your code.")
    phone = normalize_us_phone(phone)
    if channel == ws.CHANNEL_SMS and phone is None:
        raise CandidateIdentityError("Please enter your mobile number to receive the code by text message.")
    account = get_account_by_email(session, email)
    if is_verified(account):
        raise AlreadyRegistered("This email is already registered. Please sign in with your password.")
    now = ws.utcnow()
    if account is None:
        account = ws.CandidateAccount(email=email, full_name=full_name.strip()[:255], phone=phone,
                                      password_hash=generate_password_hash(password), status=ws.CANDIDATE_PENDING)
        session.add(account)
        session.flush()
    else:
        # Never verified: the identity has no owner yet, so the newest registration attempt defines it.
        account.full_name = full_name.strip()[:255]
        account.password_hash = generate_password_hash(password)
        account.phone = phone
        account.updated_at = now
    target = phone if channel == ws.CHANNEL_SMS else email
    return account, issue_code(session, account=account, secret_key=secret_key, request_ip=request_ip,
                               channel=channel, target=target), target


def issue_code(session: Session, *, account: ws.CandidateAccount, secret_key: str, request_ip: str | None,
               channel: str = ws.CHANNEL_EMAIL, target: str | None = None) -> str:
    now = ws.utcnow()
    target = target or account.email
    active = _active_code(session, account.id)
    if active is not None and active.created_at > now - RESEND_COOLDOWN:
        wait = int((active.created_at + RESEND_COOLDOWN - now).total_seconds()) + 1
        raise RateLimited(f"A code was just sent. Please wait {wait} seconds before asking for a new one.")
    since = now - RATE_WINDOW

    def sent(*conditions) -> int:
        return session.scalar(select(func.count()).select_from(ws.CandidateEmailCode).where(
            ws.CandidateEmailCode.created_at >= since, *conditions)) or 0

    if sent(ws.CandidateEmailCode.candidate_account_id == account.id) >= MAX_CODES_PER_ACCOUNT_PER_HOUR:
        raise RateLimited("Too many codes were requested for this account. Please try again in an hour.")
    if sent(ws.CandidateEmailCode.target == target) >= MAX_CODES_PER_TARGET_PER_HOUR:
        raise RateLimited("Too many codes were sent to this address or number. Please try again in an hour.")
    if request_ip and sent(ws.CandidateEmailCode.request_ip == request_ip) >= MAX_CODES_PER_IP_PER_HOUR:
        raise RateLimited("Too many codes were requested from this network. Please try again later.")
    if active is not None:
        active.invalidated_at = now
    code = "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))
    session.add(ws.CandidateEmailCode(candidate_account_id=account.id, code_hmac=_hash_code(code, secret_key),
                                      channel=channel, target=target, request_ip=request_ip,
                                      expires_at=now + CODE_TTL))
    session.flush()
    return code


def withdraw_code(session: Session, account: ws.CandidateAccount) -> None:
    """The code could not be delivered, or the candidate cancelled: it can
    no longer be used, and the cooldown does not block a new request."""
    active = _active_code(session, account.id)
    if active is not None:
        active.invalidated_at = ws.utcnow()
        session.flush()


def confirm_registration(session: Session, *, email: str, code: str, secret_key: str) -> ws.CandidateAccount:
    """Verifies the code and activates the identity, marking verified the
    channel the code was sent through. Raises `CandidateIdentityError` with
    a clear message on a wrong, expired or exhausted code. Commits nothing;
    the caller commits in every case so a failed attempt is counted."""
    account = get_account_by_email(session, email)
    if account is None:
        raise CandidateIdentityError("Please request a verification code first.")
    if is_verified(account):
        raise AlreadyRegistered("This account is already verified. Please sign in with your password.")
    row = session.scalars(select(ws.CandidateEmailCode).where(
        ws.CandidateEmailCode.candidate_account_id == account.id,
        ws.CandidateEmailCode.consumed_at.is_(None),
        ws.CandidateEmailCode.invalidated_at.is_(None),
    ).order_by(ws.CandidateEmailCode.id.desc()).with_for_update()).first()
    now = ws.utcnow()
    if row is None:
        raise CandidateIdentityError("This code is no longer valid. Please ask for a new code.")
    if row.expires_at <= now:
        row.invalidated_at = now
        session.flush()
        raise CandidateIdentityError("This code has expired. Please ask for a new code.")
    if not hmac.compare_digest(_hash_code((code or "").strip(), secret_key), row.code_hmac):
        row.attempts_used += 1
        left = MAX_ATTEMPTS_PER_CODE - row.attempts_used
        if left <= 0:
            row.invalidated_at = now
            session.flush()
            raise CandidateIdentityError("Too many wrong attempts. Please ask for a new code.")
        session.flush()
        raise CandidateIdentityError(f"The code is not correct. {left} attempt{'s' if left != 1 else ''} left.")
    row.consumed_at = now
    if row.channel == ws.CHANNEL_SMS:
        account.phone_verified_at = now
    else:
        account.email_verified_at = now
    account.status, account.updated_at, account.last_login_at = ws.CANDIDATE_ACTIVE, now, now
    session.flush()
    return account


def authenticate(session: Session, *, email: str, password: str) -> ws.CandidateAccount:
    """Email + password sign-in of a verified candidate. Raises
    `CandidateIdentityError`; locks the identity for 15 minutes after 5
    wrong passwords. Commits nothing; the caller commits in every case."""
    account = get_account_by_email(session, email)
    now = ws.utcnow()
    generic = "Email or password is not correct."
    if account is None or not account.password_hash:  # email-only identity (careers page on Aruba): no password
        raise CandidateIdentityError(generic)
    if account.locked_until and account.locked_until > now:
        raise CandidateIdentityError("Too many wrong attempts. Please try again in 15 minutes.")
    if not check_password_hash(account.password_hash, password or ""):
        account.failed_login_count += 1
        if account.failed_login_count >= MAX_FAILED_LOGINS:
            account.failed_login_count, account.locked_until = 0, now + LOGIN_LOCK
        session.flush()
        raise CandidateIdentityError(generic)
    if not is_verified(account):
        raise CandidateIdentityError("Your account is not verified yet. Please create your account again to "
                                     "receive a new code.")
    account.failed_login_count, account.locked_until, account.last_login_at = 0, None, now
    session.flush()
    return account
