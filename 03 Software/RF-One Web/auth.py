"""Session/login and CSRF helpers for RF-One Web's routes.

Session: Flask's own signed-cookie session (`flask.session`), keyed off
`app.secret_key` (`RFONE_FLASK_SECRET_KEY`). Only an opaque numeric account
id (plus the session-version check below) is ever stored in it — never a
username or password — so nothing that reaches the browser is a
credential.

Session revocation: the cookie itself is stateless and cannot be reached
once issued, so remote revocation (task: "invalida tutte le sessioni
RF-One precedenti" after a password reset) works by comparing the
`session_version` the cookie was ISSUED with (`log_in`, below) against the
account's CURRENT `session_version` (bumped by
`rfone_account_service.set_password` on every password change) — a stale
cookie stops matching on its very next request and is treated as logged
out (`load_current_account`). This is the "minimo meccanismo necessario"
the task asked for: no server-side session store, just one integer
compared per request.

CSRF: a per-session random token (`secrets.token_urlsafe`), issued once and
compared with `secrets.compare_digest` on every state-changing POST. Same
mechanism `Training/auth.py` already uses — no new dependency.
"""

from __future__ import annotations

import secrets
from functools import wraps

from flask import abort, redirect, request, session as flask_session, url_for

from db import SessionFactory
from rfone_data_store import models as m
from rfone_data_store import rfone_web_session as shared_session

# TIPS_FINALIZED_PERIOD_CALCULATION_AND_REPORT_001 §15 — these two keys and
# the account+revocation lookup below now live in
# `rfone_data_store/rfone_web_session.py`, so a second RF-One app (Tips)
# honours THIS session rather than growing a login of its own. Imported
# rather than re-declared: two copies of a session key drift, and the day
# they drift everyone is silently logged out of one app only.
SESSION_ACCOUNT_KEY = shared_session.SESSION_ACCOUNT_KEY
SESSION_VERSION_KEY = shared_session.SESSION_VERSION_KEY
SESSION_CSRF_KEY = "rfone_csrf_token"
# Deliberately a DIFFERENT key from SESSION_ACCOUNT_KEY: holding the
# in-progress forgot-password username here (rather than reusing the real
# login key) means an anonymous visitor mid-recovery is never mistaken for
# a logged-in account by `current_account_id()`/`load_current_account()`.
SESSION_FORGOT_PASSWORD_USERNAME_KEY = "rfone_forgot_password_username"


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------


def get_csrf_token() -> str:
    token = flask_session.get(SESSION_CSRF_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        flask_session[SESSION_CSRF_KEY] = token
    return token


def csrf_valid() -> bool:
    expected = flask_session.get(SESSION_CSRF_KEY)
    submitted = request.form.get("csrf_token", "")
    return bool(expected) and bool(submitted) and secrets.compare_digest(expected, submitted)


def require_csrf() -> None:
    """Call at the top of every POST handler. Aborts with 400 on mismatch —
    never silently ignored."""
    if not csrf_valid():
        abort(400, description="Invalid or missing CSRF token.")


# ---------------------------------------------------------------------------
# Login session
# ---------------------------------------------------------------------------


def log_in(account_id: int, session_version: int) -> None:
    flask_session.clear()
    flask_session[SESSION_ACCOUNT_KEY] = account_id
    flask_session[SESSION_VERSION_KEY] = session_version
    flask_session.permanent = False


def log_out() -> None:
    flask_session.clear()


def current_account_id() -> int | None:
    return flask_session.get(SESSION_ACCOUNT_KEY)


def load_current_account(db_session) -> "m.RFOneAccount | None":
    """Returns the account for the current session — or `None` if there is
    no session, the account no longer exists, OR the session's own
    `session_version` no longer matches the account's current one (i.e. a
    password change has revoked this session; see module docstring). Every
    call site (this app's own `require_login`/`require_admin` below, and
    `training_integration.py`'s SSO gate/trainer check, which both call
    this same function) gets the revocation check for free — there is
    exactly one place this comparison is made — `rfone_web_session.
    account_for_session`, which Tips calls too (§15)."""
    return shared_session.account_for_session(
        db_session,
        account_id=current_account_id(),
        session_version=flask_session.get(SESSION_VERSION_KEY),
    )


# ---------------------------------------------------------------------------
# Forgot-password step 1 -> step 2 handoff — carries only a username (never
# a code, never an account id) across the two requests, in the session
# rather than the URL/a hidden form field, so it never appears in a log
# line or browser history. Deliberately a "peek", not a "pop": both GET and
# POST on step 2 need to read it, and it is cleared explicitly only once
# the flow actually concludes (`clear_pending_password_reset_username`).
# ---------------------------------------------------------------------------


def set_pending_password_reset_username(username: str) -> None:
    flask_session[SESSION_FORGOT_PASSWORD_USERNAME_KEY] = username


def get_pending_password_reset_username() -> str | None:
    return flask_session.get(SESSION_FORGOT_PASSWORD_USERNAME_KEY)


def clear_pending_password_reset_username() -> None:
    flask_session.pop(SESSION_FORGOT_PASSWORD_USERNAME_KEY, None)


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


def require_login(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_account_id() is None:
            return redirect(url_for("login", next=request.path))
        with SessionFactory() as db_session:
            if load_current_account(db_session) is None:
                log_out()
                return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def require_admin(view):
    @wraps(view)
    @require_login
    def wrapped(*args, **kwargs):
        with SessionFactory() as db_session:
            account = load_current_account(db_session)
            if account is None:
                log_out()
                return redirect(url_for("login", next=request.path))
            if not account.is_admin:
                abort(403)
        return view(*args, **kwargs)
    return wrapped
