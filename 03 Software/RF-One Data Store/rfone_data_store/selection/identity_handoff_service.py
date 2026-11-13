"""Candidate identity verified on the careers page hosted on Aruba
(SELECTION_ARUBA_IDENTITY_001).

The careers page on Aruba (`03 Software/Selection/aruba-careers/`) asks for
first name, last name and email, emails a 5-digit code and checks it. Once
the code is confirmed it issues ONE signed token and posts it — in the body
of an HTTPS form, never in a URL — to Selection. This module is the
Selection side: it accepts the token only when

- its HMAC-SHA256 signature matches the secret shared with Aruba
  (`RFONE_SELECTION_IDENTITY_HANDOFF_SECRET`, from AWS Secrets Manager; it is
  never in the code);
- it is addressed to Selection (`aud`), comes from the careers page (`iss`)
  and is still valid (at most `MAX_LIFETIME`, a minute of clock skew);
- it names an open position (`pos`, the position's public token);
- it was never used before (its `jti` is recorded in
  `selection_candidate_identity_handoffs`, unique).

It then returns the candidate identity for the verified email: the existing
one when the email already applied (so a returning candidate resumes the
same application, never a duplicate), otherwise a new identity with no
password. Nothing here sends email; neither the token nor the email is
logged.

Token format, shared with `aruba-careers/upload/private/lib.php`:

    RF1.<base64url(JSON claims)>.<base64url(HMAC-SHA256(secret, "RF1." + claims part))>
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from rfone_data_store.selection import candidate_identity_service as identity
from rfone_data_store.selection import workspace_models as ws

TOKEN_PREFIX = "RF1"
ISSUER = "rfone-careers-aruba"
AUDIENCE = "rfone-selection"
AUTH_METHOD = "email-code"
MAX_LIFETIME = timedelta(minutes=10)
CLOCK_SKEW = timedelta(seconds=60)
MIN_SECRET_LENGTH = 32
MAX_TOKEN_LENGTH = 4096
MAX_NAME_LENGTH = 120

_TOKEN_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_POSITION_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class HandoffRefused(ValueError):
    """The token cannot be accepted. The message is safe to show to the candidate."""


class HandoffNotConfigured(HandoffRefused):
    pass


@dataclass(frozen=True)
class VerifiedIdentity:
    account: ws.CandidateAccount
    position: ws.Position


def _b64decode(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def sign(claims: dict, secret: str) -> str:
    """Builds a token exactly as the careers page does (used by the tests
    and by the local stand-in of the careers page)."""
    body = _b64encode(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    signed = f"{TOKEN_PREFIX}.{body}"
    signature = hmac.new(secret.encode("utf-8"), signed.encode("ascii"), hashlib.sha256).digest()
    return f"{signed}.{_b64encode(signature)}"


def read_claims(token: str, secret: str | None, *, now: datetime | None = None) -> dict:
    """Checks signature, issuer, audience and validity window; returns the claims."""
    if not secret or len(secret) < MIN_SECRET_LENGTH:
        raise HandoffNotConfigured("Email verification is not available right now. Please try again later.")
    expired = HandoffRefused("This verification has expired or was already used. Please verify your email again.")
    token = (token or "").strip()
    parts = token.split(".")
    if len(token) > MAX_TOKEN_LENGTH or len(parts) != 3 or parts[0] != TOKEN_PREFIX:
        raise expired
    expected = hmac.new(secret.encode("utf-8"), f"{parts[0]}.{parts[1]}".encode("ascii"), hashlib.sha256).digest()
    try:
        signature = _b64decode(parts[2])
        claims = json.loads(_b64decode(parts[1]).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise expired from None
    if not hmac.compare_digest(signature, expected) or not isinstance(claims, dict):
        raise expired
    if claims.get("v") != 1 or claims.get("iss") != ISSUER or claims.get("aud") != AUDIENCE \
            or claims.get("amr") != AUTH_METHOD:
        raise expired
    now_ts = (now or datetime.now(UTC)).timestamp()
    iat, exp = claims.get("iat"), claims.get("exp")
    if not isinstance(iat, int) or not isinstance(exp, int):
        raise expired
    if iat > now_ts + CLOCK_SKEW.total_seconds() or exp <= now_ts or exp - iat > MAX_LIFETIME.total_seconds():
        raise expired
    if not isinstance(claims.get("jti"), str) or not _TOKEN_ID_RE.match(claims["jti"]):
        raise expired
    if not isinstance(claims.get("pos"), str) or not _POSITION_RE.match(claims["pos"]):
        raise expired
    for key in ("fn", "ln", "em"):
        if not isinstance(claims.get(key), str):
            raise expired
    return claims


def _clean_name(value: str) -> str:
    return " ".join(value.split())[:MAX_NAME_LENGTH]


def accept(session: Session, *, token: str, secret: str | None, request_ip: str | None = None,
           now: datetime | None = None) -> VerifiedIdentity:
    """Accepts the token once and returns the verified identity and its
    position. Raises `HandoffRefused`. Commits nothing: the caller commits on
    success (and rolls back on a refusal)."""
    claims = read_claims(token, secret, now=now)
    first, last = _clean_name(claims["fn"]), _clean_name(claims["ln"])
    email = identity.normalize_email(claims["em"])
    if not first or not last or len(email) > 320 or not _EMAIL_RE.match(email):
        raise HandoffRefused("Your details could not be read. Please verify your email again.")
    position = session.scalars(select(ws.Position).where(ws.Position.public_token == claims["pos"])).first()
    if position is None:
        raise HandoffRefused("This position does not exist or is no longer available.")
    if position.status != ws.OPEN:
        raise HandoffRefused("This position is not accepting applications at the moment.")
    if session.scalars(select(ws.CandidateIdentityHandoff.id).where(
            ws.CandidateIdentityHandoff.token_id == claims["jti"])).first() is not None:
        raise HandoffRefused("This verification has expired or was already used. Please verify your email again.")

    moment = ws.utcnow() if now is None else now.astimezone(UTC).replace(tzinfo=None)
    account = identity.get_account_by_email(session, email)
    if account is None:
        account = ws.CandidateAccount(email=email, password_hash=None, status=ws.CANDIDATE_PENDING,
                                      full_name=f"{first} {last}"[:255])
        session.add(account)
    # Whoever proves the email now owns the identity: the latest names are the candidate's own.
    account.first_name, account.last_name, account.full_name = first, last, f"{first} {last}"[:255]
    account.email_verified_at = account.email_verified_at or moment
    account.status, account.last_login_at, account.updated_at = ws.CANDIDATE_ACTIVE, moment, moment
    account.failed_login_count, account.locked_until = 0, None
    session.flush()
    session.add(ws.CandidateIdentityHandoff(
        token_id=claims["jti"], position_id=position.id, candidate_account_id=account.id,
        issued_at=datetime.fromtimestamp(claims["iat"], UTC).replace(tzinfo=None),
        expires_at=datetime.fromtimestamp(claims["exp"], UTC).replace(tzinfo=None),
        used_at=moment, request_ip=(request_ip or "")[:64] or None))
    try:
        session.flush()
    except IntegrityError:
        # The same token arrived twice at the same moment: only the first one counts.
        raise HandoffRefused("This verification has expired or was already used. "
                             "Please verify your email again.") from None
    return VerifiedIdentity(account=account, position=position)
