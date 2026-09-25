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
     it does not, and no shared code can fix it. That is the AWS topology
     (`rfone-web` and `rfone-tips` are separate App Runner hostnames).

Tips does NOT validate periods (TIPS_AWS_FINALIZATION_WORKFLOW_001). The
one human finalization path is RF-One Web's `/tips/runs/<run_id>`, on the
host the person signed in to; Tips only links there (`rfone_web_link.py`).
The identity read here serves one purpose: attributing a change of the
Tips Validation Mode to the person who made it, when one is signed in.

When no identity can be resolved, every function here returns `None`.
Tips never falls back to a typed-in name and never records an invented
author.
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
