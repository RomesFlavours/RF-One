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
_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, '..', 'RF-One Data Store'))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)
from flask import Flask, abort, flash, g, redirect, render_template, request, send_from_directory, url_for
import auth
from auth import current_account_id, get_csrf_token, load_current_account, log_in, log_out, require_admin, require_csrf, require_login
from db import SessionFactory
from domain_registry import DOMAINS, DOMAINS_BY_CODE, TIPS_HOME_URL
from rfone_data_store import display_format
from rfone_data_store import public_entry
from rfone_data_store import models as m
from sqlalchemy import select
from rfone_data_store import legal_entity_service
from rfone_data_store import rfone_account_service as account_service
from rfone_data_store import rfone_recovery_service as recovery_service
from rfone_data_store import rfone_web_session as shared_session
from rfone_data_store.technical import ses_email
from bank_routes import register_bank_routes
import bank_guided_reconciliation
app = Flask(__name__)
_TEST_SECRET_ENV_VAR = 'RFONE_WEB_TEST_SECRET_KEY'
_secret_key = os.environ.get('RFONE_FLASK_SECRET_KEY') or os.environ.get(_TEST_SECRET_ENV_VAR)
if not _secret_key:
    raise RuntimeError(f'RFONE_FLASK_SECRET_KEY is not set. RF-One Web never generates a random secret automatically. For local development/tests, set {_TEST_SECRET_ENV_VAR} explicitly instead.')
app.secret_key = _secret_key
app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')

@app.before_request
def _send_direct_visits_to_the_official_entry():
    """A person who reaches this service's technical App Runner hostname is
    sent to the same page on RF-One's official address
    (`rfone_data_store.public_entry`, UI_OFFICIAL_ENTRY_AND_LOCAL_DAYS_001)."""
    target = public_entry.official_redirect(request.method, request.headers, request.full_path)
    if target is not None:
        return redirect(target, code=301)
    return None

@app.context_processor
def inject_csrf():
    return {'csrf_token': get_csrf_token}

@app.context_processor
def inject_local_environment():
    """`local_env`: which PC, database, code and AI mode this page runs on —
    only when the server was started by the local Bank environment
    ("Avvia Bank", 03 Software/Infrastructure/Bank Local Environment), which
    sets RFONE_LOCAL_ENV_*; None everywhere else (AWS, tests)."""
    pc = os.environ.get('RFONE_LOCAL_ENV_PC')
    if not pc:
        return {'local_env': None}
    from rfone_data_store.bank_reconciliation import ai_rules
    provider, model = ai_rules.active_ai_description()
    mode = ai_rules.ai_mode()
    return {'local_env': {'pc': pc, 'kind': os.environ.get('RFONE_LOCAL_ENV_KIND', 'WORK'), 'label': os.environ.get('RFONE_LOCAL_ENV_LABEL', ''), 'db': os.environ.get('RFONE_LOCAL_ENV_DB', ''), 'generation': os.environ.get('RFONE_LOCAL_ENV_GENERATION', ''), 'code': os.environ.get('RFONE_LOCAL_ENV_CODE', ''), 'ai': 'SESSION Claude Code (VS Code) — no call to an AI provider' if mode == ai_rules.AI_MODE_SESSION else f"PROVIDER {provider} · {model or 'no model configured'}"}}

@app.context_processor
def inject_ui_language():
    """`ui_language`: the language of the human interface (UI_DEVELOPMENT_LANGUAGE_001,
    `03 Software/Shared UI/Development Language Policy.md`) — "it" only when the local
    launcher sets RFONE_UI_LANGUAGE=it; English is the shared/production default."""
    return {'ui_language': 'it' if os.environ.get('RFONE_UI_LANGUAGE', 'en').strip().lower() == 'it' else 'en'}
app.jinja_env.filters['local_dt'] = display_format.local_datetime
app.jinja_env.filters['short_name'] = display_format.employee_short_name
app.jinja_env.filters['first_name_initial'] = display_format.employee_first_name_initial
app.jinja_env.globals['zone_label'] = display_format.zone_label
app.jinja_env.globals['tips_home_url'] = TIPS_HOME_URL
app.jinja_env.globals['rfone_home_url'] = lambda: url_for('home')

@app.context_processor
def inject_site_timezone():
    """`tz`: the zone every time on an RF-One Web page is shown in, unless
    the page sets its own (RF-One UI Rules §1) — the IANA timezone of the
    Restaurant's own Clover Location, the same Location Tips and Clover
    Acquisition use. None -> the formatter shows UTC and says so."""
    with SessionFactory() as db:
        restaurant = db.scalars(select(m.Restaurant).order_by(m.Restaurant.id)).first()
        if restaurant is None:
            return {'tz': None}
        tz_name = db.scalars(select(m.Location.timezone).join(m.RestaurantLocation, m.RestaurantLocation.location_id == m.Location.id).join(m.SourceSystem, m.SourceSystem.id == m.Location.source_system_id).where(m.RestaurantLocation.restaurant_id == restaurant.id, m.SourceSystem.code == 'CLOVER')).first()
        return {'tz': tz_name}
EMAIL_FROM_ADDRESS = os.environ.get('RFONE_EMAIL_FROM_ADDRESS', '')
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
_VERIFICATION_EMAIL_SUBJECT = 'Your RF-One verification code'
_VERIFICATION_EMAIL_BODY = 'Your RF-One verification code is: {code}\n\nThis code expires in 10 minutes. If you did not request this, you can ignore this email.'
_PASSWORD_RESET_EMAIL_SUBJECT = 'Your RF-One password reset code'
_PASSWORD_RESET_EMAIL_BODY = 'Your RF-One password reset code is: {code}\n\nThis code expires in 10 minutes. If you did not request a password reset, you can ignore this email — your password has not been changed.'
_PASSWORD_CHANGED_EMAIL_SUBJECT = 'Your RF-One password was changed'
_PASSWORD_CHANGED_EMAIL_BODY = 'This is a confirmation that the password for your RF-One account (username: {username}) was just changed. If you did not make this change, contact an RF-One administrator immediately.'

def _client_ip() -> str | None:
    """App Runner terminates TLS at the edge and proxies to the container;
    the first `X-Forwarded-For` entry is the real client. Used only as a
    soft rate-limit signal (`recovery_service`'s per-IP cap) — never for
    any access-control decision."""
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr

def _issue_and_send_code(db, *, account: 'm.RFOneAccount', purpose: str, target_email: str, subject: str, body_template: str) -> None:
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
    code = recovery_service.issue_code(db, account=account, purpose=purpose, target_email=target_email, flask_secret_key=app.secret_key, request_ip=_client_ip())
    db.commit()
    try:
        ses_email.send_email(to_address=target_email, from_address=EMAIL_FROM_ADDRESS, region_name=AWS_REGION, subject=subject, text_body=body_template.format(code=code))
    except ses_email.EmailSendError:
        pass
_SHARED_UI_DIR = os.path.normpath(os.path.join(BASE_DIR, '..', 'Shared UI'))
_SHARED_BRAND_LOGOS_DIR = os.path.join(_SHARED_UI_DIR, 'brand', 'logos')

def _brand_logo_filename() -> str | None:
    if not os.path.isdir(_SHARED_BRAND_LOGOS_DIR):
        return None
    for name in sorted(os.listdir(_SHARED_BRAND_LOGOS_DIR)):
        if name == '.gitkeep':
            continue
        if os.path.isfile(os.path.join(_SHARED_BRAND_LOGOS_DIR, name)):
            return name
    return None

@app.route('/shared-brand/logos/<path:filename>')
def shared_brand_logo(filename: str):
    return send_from_directory(_SHARED_BRAND_LOGOS_DIR, filename)

@app.context_processor
def inject_brand_logo():
    return {'brand_logo_filename': _brand_logo_filename()}
_TRAINING_DIR = os.path.normpath(os.path.join(BASE_DIR, '..', 'Training'))

def _safe_next(target: str | None) -> str | None:
    """A post-login destination inside this application only: a local path
    ("/..."), never another host ("//host", "http://..."), so `next` can
    never send a person elsewhere (CLOVER_ACQUISITION_IDENTITY_001 §3)."""
    if not target or not target.startswith('/') or target.startswith('//') or ('\\' in target):
        return None
    return target

@app.route('/login', methods=['GET', 'POST'])
def login():
    next_target = _safe_next(request.values.get('next'))
    if current_account_id() is not None:
        return redirect(next_target or url_for('home'))
    if request.method == 'POST':
        require_csrf()
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        with SessionFactory() as db:
            result = account_service.verify_login(db, username, password)
        if result.account is None:
            flash(result.error or 'Invalid username or password.', 'error')
            return (render_template('login.html', next_target=next_target), 401)
        log_in(result.account.id, result.account.session_version)
        return redirect(next_target or url_for('home'))
    return render_template('login.html', next_target=next_target)

@app.route('/logout', methods=['POST'])
@require_login
def logout():
    require_csrf()
    log_out()
    return redirect(url_for('login'))
_HOME_WORK_IN_PROGRESS_CODES: frozenset[str] = frozenset()
_HOME_ADMINISTRATION_CODES = frozenset({'BANK', 'CLOVER_ACQUISITION'})

@app.route('/', strict_slashes=False)
@require_login
def home():
    with SessionFactory() as db:
        account = load_current_account(db)
        if account is None:
            log_out()
            return redirect(url_for('login'))
        access_rows = account_service.list_domain_access_for_account(db, account.id)
        enabled_codes = {row.domain_code for row in access_rows if row.enabled}
        domains_view = sorted((d for d in DOMAINS if d.code in enabled_codes and d.code not in _HOME_ADMINISTRATION_CODES), key=lambda d: (d.code in _HOME_WORK_IN_PROGRESS_CODES, d.display_name.casefold()))
        return render_template('home.html', account=account, domains_view=domains_view, work_in_progress_codes=_HOME_WORK_IN_PROGRESS_CODES, bank_available='BANK' in enabled_codes, clover_acquisition_available='CLOVER_ACQUISITION' in enabled_codes)

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
    protegge da solo la destinazione").

    ACCOUNT_ITEM_ACCESS_001: when the requested path belongs to one of the
    Domain's items (`domain_registry`), the account must also be allowed
    that item — the same rule the navigation uses to hide it, so a hidden
    item is closed by direct URL too, for its pages and its operations."""
    domain = DOMAINS_BY_CODE.get(domain_code)

    def decorator(view):

        @wraps(view)
        @require_login
        def wrapped(*args, **kwargs):
            with SessionFactory() as db:
                account = load_current_account(db)
                if account is None:
                    log_out()
                    return redirect(url_for('login', next=request.path))
                if not shared_session.account_may_enter_domain(db, account, domain_code):
                    abort(403)
                item = domain.item_for_path(request.path) if domain else None
                if item is not None and (not shared_session.account_may_use_domain_item(db, account, domain_code, item.code)):
                    abort(403)
            return view(*args, **kwargs)
        wrapped.rfone_domain_gate = domain_code
        return wrapped
    return decorator

def _allowed_items(domain_code: str):
    """The current account's usable items of `domain_code`, in registry
    order — computed once per request."""
    cache = g.setdefault('rfone_allowed_items', {})
    if domain_code not in cache:
        domain = DOMAINS_BY_CODE[domain_code]
        with SessionFactory() as db:
            allowed = set(shared_session.allowed_domain_items(db, load_current_account(db), domain_code, [i.code for i in domain.items]))
        cache[domain_code] = [i for i in domain.items if i.code in allowed]
    return cache[domain_code]

def domain_entry(domain_code: str) -> str | None:
    """Where a Domain is entered from Home or a breadcrumb: its first usable
    item (the Domain's own landing page when the whole Domain is granted),
    or the registry `link` for a Domain without items."""
    domain = DOMAINS_BY_CODE[domain_code]
    if not domain.items:
        return domain.link
    items = _allowed_items(domain_code)
    return url_for(items[0].endpoint) if items else None
app.jinja_env.globals.update(domain_nav=lambda code: [(i.code, i.label, url_for(i.endpoint)) for i in _allowed_items(code) if i.in_menu], domain_pages=lambda code: [(i.code, i.label, url_for(i.endpoint)) for i in _allowed_items(code)], may_use_item=lambda code, item: any((i.code == item for i in _allowed_items(code))), domain_entry=domain_entry, ui_language_global=lambda: inject_ui_language()['ui_language'])
register_bank_routes(app, require_domain_access=require_domain_access, SessionFactory=SessionFactory, load_current_account=load_current_account, require_csrf=require_csrf)
bank_guided_reconciliation.register(app, require_domain_access=require_domain_access)
clover_job_launcher = None
_ACCESS_NONE = 'none'
_ACCESS_ALL = 'all'
_ACCESS_SELECTED = 'selected'

@app.route('/profile')
@require_login
def profile():
    with SessionFactory() as db:
        account = load_current_account(db)
        if account is None:
            log_out()
            return redirect(url_for('login'))
        pending = recovery_service.get_pending_code(db, account.id, recovery_service.PURPOSE_EMAIL_VERIFICATION)
        return render_template('profile.html', account=account, pending_email=pending.target_email if pending is not None else None)
_FORGOT_PASSWORD_GENERIC_MESSAGE = 'If the details match an eligible account, you will receive a verification code.'
