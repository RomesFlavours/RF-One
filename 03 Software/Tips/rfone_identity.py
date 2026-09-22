"""Who is logged into RF-One, as seen from the Tips app.

TIPS_FINALIZED_PERIOD_CALCULATION_AND_REPORT_001 §15: the person who
validates a calculated Tips period "deve essere identificata tramite il
sistema di accesso già esistente in RF-One", and explicitly NOT through a
second login system, a separate Tips access, a manually entered name or an
anonymous validator.

This file is the whole integration, and it is deliberately the smallest one
that satisfies that: Tips reads the SAME Flask signed-cookie session
RF-One Web issues, and resolves it through the SAME shared lookup
(`rfone_data_store.rfone_web_session`) that RF-One Web's own `auth.py` now
delegates to. Tips has no login page, no account table, no password
handling and no session of its own, and it never creates or modifies an
account — it only reads the identity that already exists. Logging in stays
entirely RF-One Web's job.

WHAT THIS REQUIRES OPERATIONALLY, stated plainly because it is a deployment
fact and not something code can arrange:

  1. Both apps must run with the SAME `RFONE_FLASK_SECRET_KEY`. Without it
     Tips cannot verify a cookie RF-One Web signed, and every request looks
     anonymous. Tips already reads that exact variable for its own
     `secret_key`, so this is configuration, not code.
  2. Both apps must be reachable on the SAME hostname, because a browser
     sends a cookie by host and ignores the port. Locally (both on
     `localhost`) that already holds. Served from two different hostnames
     it does not, and no shared code can fix it — that is a deployment
     decision (one host with two paths, or a single shell), and it is
     reported as such rather than worked around here with a token in a URL
     or a duplicated login.

When no identity can be resolved, every function here returns `None` and
the caller REFUSES the action. Tips never falls back to a typed-in name and
never records an unidentified validator: an unsigned approval on a payroll
figure is worse than a blocked one, because it looks signed.
"""

from __future__ import annotations

from flask import session as flask_session

from rfone_data_store import models as m
from rfone_data_store import rfone_web_session as shared_session


def current_account_id() -> int | None:
    """The account id in the shared RF-One session cookie, if any."""
    return flask_session.get(shared_session.SESSION_ACCOUNT_KEY)


def current_account(db_session) -> "m.RFOneAccount | None":
    """The RF-One account this request is authenticated as, or `None`.

    `None` covers every failure mode identically — no cookie, a cookie this
    app cannot verify, a deleted account, or a session revoked by a
    password change — because the caller's response to all of them is the
    same: refuse, and say why."""
    return shared_session.account_for_session(
        db_session,
        account_id=current_account_id(),
        session_version=flask_session.get(shared_session.SESSION_VERSION_KEY),
    )


def display_name(account: "m.RFOneAccount | None") -> str:
    return shared_session.account_display_name(account)


# The one message the UI shows when an action needs an identified person and
# there is none. It names the cause and the fix rather than saying "denied".
NOT_IDENTIFIED_MESSAGE = (
    "This action records WHO performed it, so it needs an identified RF-One user. "
    "No RF-One login session was found for this request. Sign in to RF-One Web and "
    "return here; if you are already signed in there, the two apps are not sharing "
    "the RF-One session (same RFONE_FLASK_SECRET_KEY, same hostname) and that has to "
    "be fixed in the deployment — Tips will not record an unidentified approval."
)
