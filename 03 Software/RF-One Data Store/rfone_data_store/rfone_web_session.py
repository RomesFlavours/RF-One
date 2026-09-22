"""The ONE definition of "who is logged into RF-One" for a signed-cookie
session — shared by every RF-One app that runs on the RF-One login.

TIPS_FINALIZED_PERIOD_CALCULATION_AND_REPORT_001 §15 asked for the person
who validates a Tips period to be identified through "il sistema di accesso
già esistente in RF-One", explicitly forbidding a second login, a separate
Tips access, a manually typed name and an anonymous validator. That
existing system is RF-One Web's `auth.py`: Flask's own signed-cookie
session, carrying nothing but an account id and the session version it was
issued with, plus one integer comparison per request for remote revocation.

This module holds the parts of that mechanism that are NOT web-framework
code — the two session keys and the account+revocation lookup — so a second
app can honour exactly the same session without copying the logic or
inventing its own. `RF-One Web/auth.py` and `Tips/rfone_identity.py` both
delegate here, which is what makes it one system rather than two that
happen to agree today.

Deliberately free of any Flask import: this package is the data store, and
the session OBJECT stays the caller's business. A caller reads the two keys
out of whatever session mapping it has and passes the values in.

THE SHARED CONTRACT, in full:

  * the same signed-cookie secret (`RFONE_FLASK_SECRET_KEY`) in every app,
    so a cookie issued by one verifies in the other;
  * the two session keys below, spelled identically;
  * the same `rfone_accounts` table.

Two apps served from the same host share the cookie automatically (cookies
ignore the port). Two apps on DIFFERENT hostnames do not, and no amount of
shared code changes that — see `Tips/rfone_identity.py` for what that means
operationally.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from . import models as m
from . import rfone_account_service as account_service

# The exact keys RF-One Web's `auth.log_in` writes. Changing either value
# logs every existing session out of every app at once, which is why they
# live here and not in two places.
SESSION_ACCOUNT_KEY = "rfone_account_id"
SESSION_VERSION_KEY = "rfone_session_version"


def account_for_session(
    db_session: Session, *, account_id: int | None, session_version: int | None,
) -> "m.RFOneAccount | None":
    """The `RFOneAccount` this session identifies, or `None`.

    `None` for every failure mode without distinguishing between them,
    because a caller must treat them identically: no session, an account
    that no longer exists, and a session whose `session_version` no longer
    matches the account's current one (i.e. the password changed and this
    cookie is revoked — `rfone_account_service.set_password` bumps it).

    This is the one place that comparison is made, so every app gets
    revocation for free rather than remembering to implement it."""
    if account_id is None:
        return None
    account = account_service.get_account(db_session, account_id)
    if account is None:
        return None
    if session_version != account.session_version:
        return None
    return account


def account_display_name(account: "m.RFOneAccount | None") -> str:
    """How an identified person is named in a report or an audit line.

    Returns the account's own `display_name`, falling back to its
    `username` — never an email address (which is a recovery channel, not
    an identity to publish on a payroll report) and never a fabricated
    placeholder. An absent account is stated as such rather than rendered
    as a blank or a dash that could read as "nobody needed to sign"."""
    if account is None:
        return "not identified"
    return (account.display_name or "").strip() or account.username
