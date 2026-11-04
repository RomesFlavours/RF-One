"""Session/login and CSRF helpers for Training's Flask routes.

Session: Flask's own signed-cookie session (`flask.session`), the same
mechanism/secret key `Tips/app.py` already configures via `app.secret_key`
— reused as-is, never a second session mechanism. Only an opaque numeric
account id (never a username or password) is ever stored in it, so nothing
that reaches the browser is a credential (spec, "protezioni minime" —
"senza credenziali nel browser storage o negli URL").

CSRF: a per-session random token (`secrets.token_urlsafe`), issued once and
compared with `secrets.compare_digest` on every state-changing POST. No new
dependency (Flask-WTF is not installed anywhere in this repository) —
Werkzeug/Flask alone are already sufficient for this.
"""

from __future__ import annotations

import secrets
from functools import wraps

from flask import abort, redirect, request, session as flask_session, url_for

from db import SessionFactory
from rfone_data_store import models as m
from rfone_data_store.training import service as training_service

SESSION_ACCOUNT_KEY = "training_account_id"
SESSION_CSRF_KEY = "training_csrf_token"


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


def log_in(account_id: int) -> None:
    flask_session.clear()
    flask_session[SESSION_ACCOUNT_KEY] = account_id
    flask_session.permanent = False


def log_out() -> None:
    flask_session.clear()


def current_account_id() -> int | None:
    return flask_session.get(SESSION_ACCOUNT_KEY)


def load_current_account(db_session) -> "m.TrainingAccount | None":
    account_id = current_account_id()
    if account_id is None:
        return None
    return training_service.get_account(db_session, account_id)


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


def require_login(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_account_id() is None:
            return redirect(url_for("training.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def require_trainer(view):
    @wraps(view)
    @require_login
    def wrapped(*args, **kwargs):
        with SessionFactory() as db_session:
            account = load_current_account(db_session)
            if account is None:
                log_out()
                return redirect(url_for("training.login", next=request.path))
            if account.role != "trainer":
                abort(403)
        return view(*args, **kwargs)
    return wrapped
