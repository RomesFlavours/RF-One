"""RF-One Web — the general RF-One entry point (V1: accounts + Domain
access shell).

This is the common front door RF-One is intended to grow into: a login,
one Home page listing the Domains an account may enter, and an Admin area
for managing accounts and their Domain access. It does NOT own or replace
any existing Domain application (`Tips/app.py`, `Training/`) — moving
their actual routes/authentication in here is an explicit, separate future
task (see the task's own §15).

Follows the same small-local-Flask-app convention `Tips/app.py`/
`Selection/app.py`/`Training`'s own files already establish: server-
rendered Jinja2 templates, no JS framework/build step, one shared
operational database via `get_database_url()`.

Architectural rule (learned from the Training deployment crash-loop
incident): importing this module must never run Alembic or write to the
database. `db.py` only builds an engine/session factory; migrations and
account bootstrap (`create_admin.py`) are explicit, operator-invoked steps,
never repeated per Gunicorn worker.
"""

from __future__ import annotations

import os
import sys
from functools import wraps

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from flask import Flask, abort, flash, redirect, render_template, request, send_from_directory, url_for  # noqa: E402

import auth  # noqa: E402
from auth import (  # noqa: E402
    current_account_id, get_csrf_token, load_current_account, log_in, log_out,
    require_admin, require_csrf, require_login,
)
from db import SessionFactory  # noqa: E402
from domain_registry import DOMAINS  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import legal_entity_service  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store import rfone_recovery_service as recovery_service  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402
from rfone_data_store.technical import ses_email  # noqa: E402
from compensation_routes import register_compensation_routes  # noqa: E402
from organizational_responsibility_routes import register_organizational_responsibility_routes  # noqa: E402
from bank_routes import register_bank_routes  # noqa: E402
from tips_validation_routes import register_tips_validation_routes  # noqa: E402
import training_integration  # noqa: E402

app = Flask(__name__)

# The persistent Flask secret, from Secrets Manager in production
# (RFONE_FLASK_SECRET_KEY) — never generated randomly here, unlike Tips's
# own (pre-existing, unrelated) `os.urandom(24)` fallback: a general-shell
# session cookie signed with a secret that changes on every restart would
# silently log every operator out on each deploy. Local tests set
# RFONE_WEB_TEST_SECRET_KEY explicitly instead of the real production var.
_TEST_SECRET_ENV_VAR = "RFONE_WEB_TEST_SECRET_KEY"
_secret_key = os.environ.get("RFONE_FLASK_SECRET_KEY") or os.environ.get(_TEST_SECRET_ENV_VAR)
if not _secret_key:
    raise RuntimeError(
        "RFONE_FLASK_SECRET_KEY is not set. RF-One Web never generates a random "
        f"secret automatically. For local development/tests, set {_TEST_SECRET_ENV_VAR} "
        "explicitly instead."
    )
app.secret_key = _secret_key

# HTTPS-only cookies: App Runner terminates TLS at the edge, so the app
# itself is always reached over HTTPS in any real deployment — the session
# cookie must never be sent over a plain-HTTP fallback. Never disabled by
# an environment flag: there is no supported production configuration
# where this app is served over HTTP.
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)


@app.context_processor
def inject_csrf():
    return {"csrf_token": get_csrf_token}


# ---------------------------------------------------------------------------
# Email verification / password recovery — shared helpers for every route
# below that issues a code (account creation, profile email add/change,
# forgot-password). One sender address for the whole application
# (RFONE_EMAIL_FROM_ADDRESS) — never a caller-chosen or recipient-derived
# address (see `ses_email.py`'s own docstring for why).
# ---------------------------------------------------------------------------

EMAIL_FROM_ADDRESS = os.environ.get("RFONE_EMAIL_FROM_ADDRESS", "")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

_VERIFICATION_EMAIL_SUBJECT = "Your RF-One verification code"
_VERIFICATION_EMAIL_BODY = (
    "Your RF-One verification code is: {code}\n\n"
    "This code expires in 10 minutes. If you did not request this, you can ignore this email."
)
_PASSWORD_RESET_EMAIL_SUBJECT = "Your RF-One password reset code"
_PASSWORD_RESET_EMAIL_BODY = (
    "Your RF-One password reset code is: {code}\n\n"
    "This code expires in 10 minutes. If you did not request a password reset, you can ignore this "
    "email — your password has not been changed."
)
_PASSWORD_CHANGED_EMAIL_SUBJECT = "Your RF-One password was changed"
_PASSWORD_CHANGED_EMAIL_BODY = (
    "This is a confirmation that the password for your RF-One account (username: {username}) was just "
    "changed. If you did not make this change, contact an RF-One administrator immediately."
)


def _client_ip() -> str | None:
    """App Runner terminates TLS at the edge and proxies to the container;
    the first `X-Forwarded-For` entry is the real client. Used only as a
    soft rate-limit signal (`recovery_service`'s per-IP cap) — never for
    any access-control decision."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr


def _issue_and_send_code(db, *, account: "m.RFOneAccount", purpose: str, target_email: str, subject: str, body_template: str) -> None:
    """Issues a code (committing it immediately, on its own, before any
    email-sending attempt) and emails it. Raises
    `recovery_service.RateLimitedError` if refused by the cooldown/hourly
    caps — callers decide for themselves whether that must stay invisible
    (forgot-password: task requires the SAME generic response regardless)
    or may be shown directly (the authenticated profile "resend" action).
    A subsequent SES failure is swallowed here: the code was already
    issued and is still usable (e.g. via a resend) even if this particular
    send attempt failed — callers must never show `EmailSendError`'s own
    text to the end user."""
    code = recovery_service.issue_code(
        db, account=account, purpose=purpose, target_email=target_email,
        flask_secret_key=app.secret_key, request_ip=_client_ip(),
    )
    db.commit()
    try:
        ses_email.send_email(
            to_address=target_email, from_address=EMAIL_FROM_ADDRESS, region_name=AWS_REGION,
            subject=subject, text_body=body_template.format(code=code),
        )
    except ses_email.EmailSendError:
        pass


# ---------------------------------------------------------------------------
# Shared RF-One branding — same "sibling module, served via
# send_from_directory" pattern Tips's own `shared_brand_logo` route already
# uses. Never copied into this app's own `static/`.
# ---------------------------------------------------------------------------

_SHARED_UI_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "Shared UI"))
_SHARED_BRAND_LOGOS_DIR = os.path.join(_SHARED_UI_DIR, "brand", "logos")


def _brand_logo_filename() -> str | None:
    if not os.path.isdir(_SHARED_BRAND_LOGOS_DIR):
        return None
    for name in sorted(os.listdir(_SHARED_BRAND_LOGOS_DIR)):
        if name == ".gitkeep":
            continue
        if os.path.isfile(os.path.join(_SHARED_BRAND_LOGOS_DIR, name)):
            return name
    return None


@app.route("/shared-brand/logos/<path:filename>")
def shared_brand_logo(filename: str):
    return send_from_directory(_SHARED_BRAND_LOGOS_DIR, filename)


@app.context_processor
def inject_brand_logo():
    return {"brand_logo_filename": _brand_logo_filename()}


# ---------------------------------------------------------------------------
# Training integration — mounts Training's EXISTING, unmodified blueprint
# (single-login: see `training_integration.py`'s own module docstring for
# how requests are silently authorized against the current RF-One session,
# so Training's own login form is never shown for an RF-One-integrated
# account) and the same unauthenticated dish-guide route Tips already
# exposes, kept working here for consistency within this application too.
# ---------------------------------------------------------------------------

_training_bp = training_integration.install_training_blueprint()
app.register_blueprint(_training_bp)


@app.before_request
def _training_sso_gate():
    return training_integration.enforce_training_sso(auth, SessionFactory)


_TRAINING_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "Training"))


@app.route("/training/menu")
def training_menu():
    return send_from_directory(_TRAINING_DIR, "RF-One-Training.html")


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_account_id() is not None:
        return redirect(url_for("home"))

    if request.method == "POST":
        require_csrf()
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        with SessionFactory() as db:
            result = account_service.verify_login(db, username, password)
        if result.account is None:
            flash(result.error or "Invalid username or password.", "error")
            return render_template("login.html"), 401
        log_in(result.account.id, result.account.session_version)
        return redirect(url_for("home"))

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@require_login
def logout():
    require_csrf()
    log_out()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------


@app.route("/", strict_slashes=False)
@require_login
def home():
    with SessionFactory() as db:
        account = load_current_account(db)
        if account is None:
            log_out()
            return redirect(url_for("login"))

        access_rows = account_service.list_domain_access_for_account(db, account.id)
        enabled_codes = {row.domain_code for row in access_rows if row.enabled}
        domains_view = [d for d in DOMAINS if d.code in enabled_codes]

        return render_template(
            "home.html", account=account, domains_view=domains_view,
            tips_validation_available="TIPS" in enabled_codes,
        )


def require_domain_access(domain_code: str):
    """Decorator factory: the SAME server-side check Home already uses to
    decide which Domain cards to show (`RFOneAccountDomainAccess`,
    enabled=True) — reused here, not a new authorization mechanism, to gate
    the actual destination route too. An account must be ACTIVE and hold an
    ENABLED access row for `domain_code`; anything else gets a 403 (never a
    redirect that would confirm the route exists to an unauthorized caller,
    matching `require_admin`'s own convention). This is what makes the
    Home filtering meaningful — a Domain link is never itself the access
    control (task: "Il collegamento nella Home filtrato per Domain non
    protegge da solo la destinazione")."""
    def decorator(view):
        @wraps(view)
        @require_login
        def wrapped(*args, **kwargs):
            with SessionFactory() as db:
                account = load_current_account(db)
                if account is None:
                    log_out()
                    return redirect(url_for("login", next=request.path))
                # The one Domain rule, shared with Tips (`rfone_web_session`).
                if not shared_session.account_may_enter_domain(db, account, domain_code):
                    abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


# ---------------------------------------------------------------------------
# Selection — still a provisional "Work in progress" page (task: publish
# only what's actually ready; Selection's real app is not routed here
# unless/until it has its own usable server-side auth — see the
# domain_registry.py comment on SELECTION for the current decision).
# ---------------------------------------------------------------------------


@app.route("/selection")
@require_domain_access("SELECTION")
def selection_work_in_progress():
    return render_template("work_in_progress.html", title="Selection")


# ---------------------------------------------------------------------------
# Compensation — V1 operational application (manual Payroll Handoff).
# Replaces the former "Work in progress" page. Every route is defined in
# `compensation_routes.py` and gated the same way as every other
# destination here: `require_domain_access("COMPENSATION")`.
# ---------------------------------------------------------------------------

register_compensation_routes(
    app, require_domain_access=require_domain_access, SessionFactory=SessionFactory,
    load_current_account=load_current_account, require_csrf=require_csrf,
)

# ---------------------------------------------------------------------------
# Admin — Organizational Responsibility + Attention Management (TASK_
# ATTENTION_ORG_RUNTIME §12). ADMIN / CONFIGURATION / TEST HARNESS only —
# never the eventual end-user Attention Inbox (task explicitly forbids
# building that here; see `organizational_responsibility_routes.py`'s own
# module docstring for the full boundary statement).
# ---------------------------------------------------------------------------

register_organizational_responsibility_routes(
    app, require_admin=require_admin, SessionFactory=SessionFactory, require_csrf=require_csrf,
)


# ---------------------------------------------------------------------------
# Bank Reconciliation — Canonical Financial Model Convergence (Phases 1-6B,
# FINANCIAL_MODEL_CONVERGENCE_001). Manual CSV import (Chase, First
# Citizens) and PayPal acquisition, normalized into the canonical
# PaymentInstrument/FinancialTransaction ledger; the Bank Recognition
# Expert System, Kermali Monthly Accountant Export, and automatic
# cross-ledger internal-transfer matching (Phase 6B). Gated the same way
# as every other destination here: `require_domain_access("BANK")`.
# ---------------------------------------------------------------------------

register_bank_routes(
    app, require_domain_access=require_domain_access, SessionFactory=SessionFactory,
    load_current_account=load_current_account, require_csrf=require_csrf,
)


# ---------------------------------------------------------------------------
# Tips — period validation only (TIPS_AWS_FINALIZATION_WORKFLOW_001). The
# human step that turns a CALCULATED Tips period FINAL needs the RF-One
# login, which only reaches this host; everything else in Tips stays in the
# Tips app. Gated by `require_domain_access("TIPS")` + CSRF — see
# `tips_validation_routes.py`'s own module docstring.
# ---------------------------------------------------------------------------

register_tips_validation_routes(
    app, require_domain_access=require_domain_access, SessionFactory=SessionFactory,
    load_current_account=load_current_account, require_csrf=require_csrf,
)


# ---------------------------------------------------------------------------
# Admin — accounts
# ---------------------------------------------------------------------------


@app.route("/admin/accounts")
@require_admin
def admin_accounts():
    with SessionFactory() as db:
        accounts = account_service.list_accounts(db)
        return render_template("admin_accounts.html", accounts=accounts)


@app.route("/admin/accounts/new", methods=["GET", "POST"])
@require_admin
def admin_account_new():
    if request.method == "POST":
        require_csrf()
        username = request.form.get("username", "").strip()
        display_name = request.form.get("display_name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")
        status = "ACTIVE" if request.form.get("status") == "ACTIVE" else "INACTIVE"

        if password != password_confirm:
            flash("Passwords did not match.", "error")
            return render_template("admin_account_form.html", mode="create", account=None), 400
        if not email:
            flash("Email is required for a new account.", "error")
            return render_template("admin_account_form.html", mode="create", account=None), 400

        with SessionFactory() as db:
            try:
                account = account_service.create_account(
                    db, username=username, display_name=display_name, password=password, status=status,
                    email=email,
                )
                db.commit()
            except (account_service.UsernameTakenError, account_service.EmailTakenError, ValueError) as exc:
                db.rollback()
                flash(str(exc), "error")
                return render_template("admin_account_form.html", mode="create", account=None), 400

            try:
                _issue_and_send_code(
                    db, account=account, purpose=recovery_service.PURPOSE_EMAIL_VERIFICATION,
                    target_email=account.email, subject=_VERIFICATION_EMAIL_SUBJECT,
                    body_template=_VERIFICATION_EMAIL_BODY,
                )
            except recovery_service.RateLimitedError:
                pass  # cannot happen for a brand-new account's first code; defensive only

        flash(f"Account {display_name!r} created. A verification code has been emailed to {email}.", "info")
        return redirect(url_for("admin_accounts"))

    return render_template("admin_account_form.html", mode="create", account=None)


@app.route("/admin/accounts/<int:account_id>/edit", methods=["GET", "POST"])
@require_admin
def admin_account_edit(account_id: int):
    with SessionFactory() as db:
        account = account_service.get_account(db, account_id)
        if account is None:
            abort(404)

        if request.method == "POST":
            require_csrf()
            display_name = request.form.get("display_name", "").strip()
            status = "ACTIVE" if request.form.get("status") == "ACTIVE" else "INACTIVE"
            try:
                account_service.update_account(db, account, display_name=display_name, status=status)
                db.commit()
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
                return render_template("admin_account_form.html", mode="edit", account=account), 400

            flash("Account updated.", "info")
            return redirect(url_for("admin_accounts"))

        return render_template("admin_account_form.html", mode="edit", account=account)


@app.route("/admin/accounts/<int:account_id>/reset-password", methods=["POST"])
@require_admin
def admin_account_reset_password(account_id: int):
    require_csrf()
    password = request.form.get("password", "")
    password_confirm = request.form.get("password_confirm", "")

    with SessionFactory() as db:
        account = account_service.get_account(db, account_id)
        if account is None:
            abort(404)

        if password != password_confirm:
            flash("Passwords did not match.", "error")
        else:
            try:
                account_service.set_password(db, account, password)
                db.commit()
                flash("Password updated.", "info")
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")

    return redirect(url_for("admin_account_edit", account_id=account_id))


@app.route("/admin/accounts/<int:account_id>/access", methods=["GET", "POST"])
@require_admin
def admin_account_access(account_id: int):
    with SessionFactory() as db:
        account = account_service.get_account(db, account_id)
        if account is None:
            abort(404)

        if request.method == "POST":
            require_csrf()
            for domain in DOMAINS:
                enabled = request.form.get(f"enabled_{domain.code}") == "on"
                role_code = request.form.get(f"role_{domain.code}", "").strip() or None
                account_service.set_domain_access(
                    db, account_id=account.id, domain_code=domain.code, enabled=enabled, role_code=role_code,
                )
                if domain.code == "TRAINING":
                    # Explicit, authorized sync point (task: "assegnano o
                    # modificano il ruolo TRAINING di un account già
                    # collegato") — same transaction as the access change
                    # itself, committed together below.
                    training_integration.sync_training_role_if_linked(db, account.id, role_code)
            db.commit()
            flash("Domain access updated.", "info")
            return redirect(url_for("admin_accounts"))

        access_by_code = {row.domain_code: row for row in account_service.list_domain_access_for_account(db, account.id)}
        domains_view = [{"domain": d, "access": access_by_code.get(d.code)} for d in DOMAINS]
        return render_template("admin_account_access.html", account=account, domains_view=domains_view)


# ---------------------------------------------------------------------------
# Admin — Legal Entities (standalone, separate from Compensation — task:
# "La gestione Legal Entity resta separata da Compensation e richiamabile
# in futuro dalle impostazioni del dominio"). Compensation only ever reads
# these rows (`legal_entity_service.list_legal_entities`/`get_legal_entity`
# — see `compensation_routes.py`); this is the one place they are created
# or edited.
# ---------------------------------------------------------------------------


@app.route("/admin/legal-entities")
@require_admin
def admin_legal_entities():
    with SessionFactory() as db:
        entities = legal_entity_service.list_legal_entities(db)
        return render_template("admin_legal_entities.html", entities=entities)


@app.route("/admin/legal-entities/new", methods=["GET", "POST"])
@require_admin
def admin_legal_entity_new():
    if request.method == "POST":
        require_csrf()
        legal_name = request.form.get("legal_name", "").strip()
        status = request.form.get("status") or "ACTIVE"

        with SessionFactory() as db:
            try:
                legal_entity_service.create_legal_entity(db, legal_name=legal_name, status=status)
                db.commit()
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
                return render_template("admin_legal_entity_form.html", mode="create", entity=None), 400

        flash(f"Legal Entity {legal_name!r} created.", "info")
        return redirect(url_for("admin_legal_entities"))

    return render_template("admin_legal_entity_form.html", mode="create", entity=None)


@app.route("/admin/legal-entities/<int:entity_id>/edit", methods=["GET", "POST"])
@require_admin
def admin_legal_entity_edit(entity_id: int):
    with SessionFactory() as db:
        entity = legal_entity_service.get_legal_entity(db, entity_id)
        if entity is None:
            abort(404)

        if request.method == "POST":
            require_csrf()
            legal_name = request.form.get("legal_name", "").strip()
            status = request.form.get("status") or "ACTIVE"
            try:
                legal_entity_service.update_legal_entity(db, entity, legal_name=legal_name, status=status)
                db.commit()
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")
                return render_template("admin_legal_entity_form.html", mode="edit", entity=entity), 400

            flash("Legal Entity updated.", "info")
            return redirect(url_for("admin_legal_entities"))

        return render_template("admin_legal_entity_form.html", mode="edit", entity=entity)


# ---------------------------------------------------------------------------
# Admin — linking an RF-One account to a Training identity
# ---------------------------------------------------------------------------


@app.route("/admin/accounts/<int:account_id>/training-link", methods=["GET", "POST"])
@require_admin
def admin_account_training_link(account_id: int):
    with SessionFactory() as db:
        account = account_service.get_account(db, account_id)
        if account is None:
            abort(404)
        existing_link = training_integration.get_link_for_rfone_account(db, account_id)

        if request.method == "POST":
            require_csrf()
            action = request.form.get("action")
            try:
                if action == "link_existing":
                    training_account_id = request.form.get("training_account_id", type=int)
                    if not training_account_id:
                        raise ValueError("Select a Training identity to link.")
                    training_integration.link_existing_training_account(
                        db, rfone_account_id=account_id, training_account_id=training_account_id,
                    )
                elif action == "create_new":
                    role_code = request.form.get("role_code", "")
                    training_integration.create_and_link_training_identity(
                        db, rfone_account_id=account_id, role_code=role_code,
                    )
                else:
                    raise ValueError("Unknown action.")
                db.commit()
            except (ValueError, training_integration.AlreadyLinkedError) as exc:
                db.rollback()
                flash(str(exc), "error")
                return redirect(url_for("admin_account_training_link", account_id=account_id))

            flash("Training identity linked.", "info")
            return redirect(url_for("admin_accounts"))

        unlinked_accounts = training_integration.list_unlinked_training_accounts(db) if existing_link is None else []
        linked_training_account = (
            db.get(m.TrainingAccount, existing_link.training_account_id) if existing_link is not None else None
        )
        return render_template(
            "admin_account_training_link.html", account=account, existing_link=existing_link,
            linked_training_account=linked_training_account, unlinked_accounts=unlinked_accounts,
        )


# ---------------------------------------------------------------------------
# Trainer-facing — creating a brand-new student directly usable with the
# RF-One login (task §4). Independent of RF-One admin status: gated on
# "currently has the Training trainer role", never on `is_admin`.
# ---------------------------------------------------------------------------


@app.route("/training-trainer/students/new", methods=["GET", "POST"])
@training_integration.require_training_trainer(auth, SessionFactory)
def training_trainer_new_student():
    if request.method == "POST":
        require_csrf()
        username = request.form.get("username", "").strip()
        display_name = request.form.get("display_name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")

        if password != password_confirm:
            flash("Passwords did not match.", "error")
            return render_template("training_trainer_new_student.html"), 400
        if not email:
            flash("Email is required for a new student.", "error")
            return render_template("training_trainer_new_student.html"), 400

        with SessionFactory() as db:
            try:
                rfone_account, _training_account = training_integration.create_student_via_rf_one(
                    db, username=username, display_name=display_name, password=password, email=email,
                )
                db.commit()
            except (training_integration.StudentCreationError, account_service.EmailTakenError, ValueError) as exc:
                db.rollback()
                flash(str(exc), "error")
                return render_template("training_trainer_new_student.html"), 400

            try:
                _issue_and_send_code(
                    db, account=rfone_account, purpose=recovery_service.PURPOSE_EMAIL_VERIFICATION,
                    target_email=rfone_account.email, subject=_VERIFICATION_EMAIL_SUBJECT,
                    body_template=_VERIFICATION_EMAIL_BODY,
                )
            except recovery_service.RateLimitedError:
                pass  # cannot happen for a brand-new account's first code; defensive only

        flash(f"Student {display_name!r} created — they can now log in to RF-One directly.", "info")
        return redirect(url_for("home"))

    return render_template("training_trainer_new_student.html")


@app.route("/training-trainer/students")
@training_integration.require_training_trainer(auth, SessionFactory)
def training_trainer_students():
    with SessionFactory() as db:
        students = training_integration.list_training_students(db)
        return render_template("training_trainer_students.html", students=students)


@app.route("/training-trainer/students/<int:account_id>/reset-password", methods=["POST"])
@training_integration.require_training_trainer(auth, SessionFactory)
def training_trainer_reset_student_password(account_id: int):
    require_csrf()
    password = request.form.get("password", "")
    password_confirm = request.form.get("password_confirm", "")

    with SessionFactory() as db:
        student = account_service.get_account(db, account_id)
        if student is None or not training_integration.is_pure_training_student(db, student):
            abort(404)
        if password != password_confirm:
            flash("Passwords did not match.", "error")
        else:
            try:
                account_service.set_password(db, student, password)
                db.commit()
                flash("Student password updated.", "info")
            except ValueError as exc:
                db.rollback()
                flash(str(exc), "error")

    return redirect(url_for("training_trainer_students"))


# ---------------------------------------------------------------------------
# Profile — email on file, verification, and change (task §1). The ONE
# general mechanism every RF-One-login Domain shares; never a per-Domain
# profile/recovery. Login itself is never gated on email/verification
# status (task: "mantieni funzionante il login attuale") — only the
# self-service recovery flow below is.
# ---------------------------------------------------------------------------


@app.route("/profile")
@require_login
def profile():
    with SessionFactory() as db:
        account = load_current_account(db)
        if account is None:
            log_out()
            return redirect(url_for("login"))
        pending = recovery_service.get_pending_code(db, account.id, recovery_service.PURPOSE_EMAIL_VERIFICATION)
        return render_template(
            "profile.html", account=account,
            pending_email=pending.target_email if pending is not None else None,
        )


@app.route("/profile/email", methods=["POST"])
@require_login
def profile_email():
    require_csrf()
    current_password = request.form.get("current_password", "")
    new_email_raw = request.form.get("email", "")

    with SessionFactory() as db:
        account = load_current_account(db)
        if account is None:
            log_out()
            return redirect(url_for("login"))

        if not account_service.verify_password(account, current_password):
            flash("Current password is incorrect.", "error")
            return redirect(url_for("profile"))

        try:
            new_email = account_service.normalize_email(new_email_raw)
            if not new_email or "@" not in new_email:
                raise ValueError("A valid email address is required.")
            if account.email == new_email:
                raise ValueError("This is already your current email.")
            account_service.check_email_available(db, new_email, exclude_account_id=account.id)
        except (ValueError, account_service.EmailTakenError) as exc:
            flash(str(exc), "error")
            return redirect(url_for("profile"))

        # Case A (no email on file yet): record it now, unverified, so the
        # profile shows "on file, pending confirmation" immediately. Case B
        # (changing an existing, verified email): deliberately do NOT touch
        # `account.email` here — it stays the old, verified address until
        # the code below is confirmed (task: "Mantieni il vecchio indirizzo
        # verificato fino al completamento"); the new address lives only in
        # the code row's `target_email` until then.
        if account.email is None:
            account_service.request_account_email(db, account, new_email)
            db.commit()

        try:
            _issue_and_send_code(
                db, account=account, purpose=recovery_service.PURPOSE_EMAIL_VERIFICATION,
                target_email=new_email, subject=_VERIFICATION_EMAIL_SUBJECT,
                body_template=_VERIFICATION_EMAIL_BODY,
            )
        except recovery_service.RateLimitedError:
            flash("Please wait a minute before requesting another code.", "error")
            return redirect(url_for("profile"))

    flash(f"A verification code has been sent to {new_email}.", "info")
    return redirect(url_for("profile"))


@app.route("/profile/email/resend", methods=["POST"])
@require_login
def profile_email_resend():
    require_csrf()
    with SessionFactory() as db:
        account = load_current_account(db)
        if account is None:
            log_out()
            return redirect(url_for("login"))

        pending = recovery_service.get_pending_code(db, account.id, recovery_service.PURPOSE_EMAIL_VERIFICATION)
        if pending is None:
            flash("There is no pending email verification to resend.", "error")
            return redirect(url_for("profile"))

        try:
            _issue_and_send_code(
                db, account=account, purpose=recovery_service.PURPOSE_EMAIL_VERIFICATION,
                target_email=pending.target_email, subject=_VERIFICATION_EMAIL_SUBJECT,
                body_template=_VERIFICATION_EMAIL_BODY,
            )
        except recovery_service.RateLimitedError:
            flash("Please wait a minute before requesting another code.", "error")
            return redirect(url_for("profile"))

    flash("A new verification code has been sent.", "info")
    return redirect(url_for("profile"))


@app.route("/profile/email/verify", methods=["POST"])
@require_login
def profile_email_verify():
    require_csrf()
    submitted_code = request.form.get("code", "")

    with SessionFactory() as db:
        account = load_current_account(db)
        if account is None:
            log_out()
            return redirect(url_for("login"))

        pending = recovery_service.get_pending_code(db, account.id, recovery_service.PURPOSE_EMAIL_VERIFICATION)
        if pending is None:
            flash("There is no pending verification code — request a new one.", "error")
            return redirect(url_for("profile"))
        target_email = pending.target_email

        result = recovery_service.verify_and_consume_code(
            db, account_id=account.id, purpose=recovery_service.PURPOSE_EMAIL_VERIFICATION,
            submitted_code=submitted_code, flask_secret_key=app.secret_key,
        )
        if not result.ok:
            db.commit()  # persists the attempt (attempts_used/invalidated_at) even on failure
            flash("Invalid or expired code.", "error")
            return redirect(url_for("profile"))

        account_service.confirm_account_email(db, account, target_email)
        recovery_service.invalidate_pending_codes(db, account.id, exclude_id=result.code_row.id)
        db.commit()

    flash("Email verified.", "info")
    return redirect(url_for("profile"))


# ---------------------------------------------------------------------------
# Forgot password — self-service recovery (task §2). The exact same
# response is shown for every ineligible case (unknown username, email
# mismatch, unverified email, inactive account) — never a distinct message
# per case (task: "non rivelare esistenza, stato o email dell'account").
# ---------------------------------------------------------------------------

_FORGOT_PASSWORD_GENERIC_MESSAGE = "If the details match an eligible account, you will receive a verification code."


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        require_csrf()
        username_raw = request.form.get("username", "")
        email_raw = request.form.get("email", "")
        normalized_username = username_raw.strip().lower()

        with SessionFactory() as db:
            account = account_service.get_account_by_username(db, normalized_username)
            eligible = (
                account is not None
                and account.status == "ACTIVE"
                and account.email_verified_at is not None
                and account.email == account_service.normalize_email(email_raw)
            )
            if eligible:
                try:
                    _issue_and_send_code(
                        db, account=account, purpose=recovery_service.PURPOSE_PASSWORD_RESET,
                        target_email=account.email, subject=_PASSWORD_RESET_EMAIL_SUBJECT,
                        body_template=_PASSWORD_RESET_EMAIL_BODY,
                    )
                except recovery_service.RateLimitedError:
                    pass  # same generic response either way — a rate limit is never revealed either

        # Stored regardless of eligibility — its mere presence proves
        # nothing (it is just "which username step 2 should check a
        # submitted code against"), and step 2 gives the identical generic
        # error for a real-but-wrong code and a nonexistent/ineligible
        # account alike.
        auth.set_pending_password_reset_username(normalized_username)
        flash(_FORGOT_PASSWORD_GENERIC_MESSAGE, "info")
        return redirect(url_for("forgot_password_code"))

    return render_template("forgot_password.html")


@app.route("/forgot-password/code", methods=["GET", "POST"])
def forgot_password_code():
    pending_username = auth.get_pending_password_reset_username()
    if not pending_username:
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        require_csrf()
        submitted_code = request.form.get("code", "")
        new_password = request.form.get("new_password", "")
        new_password_confirm = request.form.get("new_password_confirm", "")

        if not new_password or new_password != new_password_confirm:
            flash("Passwords did not match.", "error")
            return render_template("forgot_password_code.html"), 400

        with SessionFactory() as db:
            account = account_service.get_account_by_username(db, pending_username)
            if account is None:
                flash("Invalid or expired code.", "error")
                return render_template("forgot_password_code.html"), 400

            result = recovery_service.verify_and_consume_code(
                db, account_id=account.id, purpose=recovery_service.PURPOSE_PASSWORD_RESET,
                submitted_code=submitted_code, flask_secret_key=app.secret_key,
            )
            if not result.ok:
                db.commit()  # persists the attempt even on failure
                flash("Invalid or expired code.", "error")
                return render_template("forgot_password_code.html"), 400

            account_service.set_password(db, account, new_password)
            recovery_service.invalidate_pending_codes(db, account.id)
            db.commit()

            try:
                ses_email.send_email(
                    to_address=account.email, from_address=EMAIL_FROM_ADDRESS, region_name=AWS_REGION,
                    subject=_PASSWORD_CHANGED_EMAIL_SUBJECT,
                    text_body=_PASSWORD_CHANGED_EMAIL_BODY.format(username=account.username),
                )
            except ses_email.EmailSendError:
                pass

        auth.clear_pending_password_reset_username()
        flash("Your password has been reset. Please log in with your new password.", "info")
        return redirect(url_for("login"))

    return render_template("forgot_password_code.html")
