"""RF-One Selection AI — local prototype (first release).

Five functions on one position page: create position, receive applications,
evaluate, organize interviews, decide. Separate from `03 Software/Selection/`
(not modified). Reuses the RF-One Data Store's Selection services, RF-One
accounts and session helpers. All data lives in a local SQLite file outside
OneDrive (see `DATA_DIR`). Binds to 127.0.0.1 only. Never deployed.

    python app.py            # AI off
    python app.py --ai       # AI drafts positions and messages (no candidate data sent)
    python app.py --ai-cv    # AI may also read CVs and interview answers (explicit authorization)
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import mimetypes
import os
import secrets
import sys
from datetime import UTC, datetime, timedelta
from functools import wraps
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
DATA_STORE = HERE.parent / "RF-One Data Store"
sys.path.insert(0, str(DATA_STORE))
sys.path.insert(0, str(HERE))

DATA_DIR = Path(os.environ.get("RFONE_SELECTION_PROTOTYPE_DATA")
                or Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RF-One" / "SelectionPrototype")
DOCUMENTS_DIR = DATA_DIR / "documents"
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
# TEST deployment (AWS): everything comes from the environment / Secrets Manager, never from code.
PUBLIC_MODE = os.environ.get("RFONE_SELECTION_PROTOTYPE_PUBLIC") == "1"
DB_URL = (os.environ.get("RFONE_SELECTION_PROTOTYPE_DATABASE_URL")
          or f"sqlite:///{(DATA_DIR / 'selection_prototype.db').as_posix()}")
# Forced, never "setdefault": the prototype must not write to any other database.
os.environ["RFONE_DATABASE_URL"] = DB_URL
os.environ.pop("RFONE_SELECTION_DOCUMENT_BUCKET", None)

from flask import Flask, abort, flash, redirect, render_template, request, send_file, url_for  # noqa: E402
from flask import session as flask_session  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from rfone_data_store import display_format  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_svc  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402
from rfone_data_store.database import create_configured_engine, create_session_factory, run_migrations_to_head  # noqa: E402
from rfone_data_store.selection import persistence  # noqa: E402
from rfone_data_store.selection import phone_interview_service as pi_svc  # noqa: E402
from rfone_data_store.selection import requirements_service as req_svc  # noqa: E402
from rfone_data_store.selection.core import requirement_model as rm  # noqa: E402
from rfone_data_store.selection.document_store import LocalDocumentStore, S3DocumentStore  # noqa: E402
from rfone_data_store.selection.industry import restaurant as restaurant_industry  # noqa: E402
from rfone_data_store.selection.industry.restaurant_templates import (  # noqa: E402
    seed_romes_flavours_phone_interview_questions, seed_sample_templates,
)
from rfone_data_store.selection.parsing.ai_client import AIProviderUnavailable  # noqa: E402

import ai_adapter  # noqa: E402
import engine  # noqa: E402
import organization_adapter  # noqa: E402
import prototype_store as ps  # noqa: E402
from channels import CHANNEL_LABELS, CHANNELS  # noqa: E402

ai_adapter.install_guard(ai_enabled=os.environ.get("RFONE_SELECTION_PROTOTYPE_AI") == "1",
                         cv_ai_authorized=os.environ.get("RFONE_SELECTION_PROTOTYPE_AI_CV") == "1")

try:
    run_migrations_to_head(DB_URL)
except Exception:
    # Alembic's logging setup silences gunicorn's error log: print the cause before failing.
    import traceback
    traceback.print_exc()
    sys.stderr.flush()
    raise
_engine = create_configured_engine(DB_URL)
ps.Base.metadata.create_all(_engine)
SessionFactory = create_session_factory(_engine)
_bucket = (os.environ.get("RFONE_SELECTION_PROTOTYPE_DOCUMENT_BUCKET") or "").strip()
DOCUMENTS = S3DocumentStore(_bucket) if _bucket else LocalDocumentStore(str(DOCUMENTS_DIR))

SELECTION_DOMAIN = "SELECTION"
ROLE_OWNER, ROLE_SUPERVISOR, ROLE_MANAGER = "OWNER", "SUPERVISOR", "MANAGER"
ROLE_LABELS = {ROLE_OWNER: "Proprietario / amministratore", ROLE_SUPERVISOR: "Supervisione (sola lettura)",
               ROLE_MANAGER: "Responsabile delle proprie posizioni"}
CLIENT_NAME = os.environ.get("RFONE_SELECTION_PROTOTYPE_CLIENT", "Rome's Flavours")
DEFAULT_TIMEZONE = "America/New_York"
MAX_STANDARD_QUESTIONS = 6

FULL_ANALYSIS_ROLES = set(restaurant_industry.ROLE_CONFIGURATIONS)
ROLE_CHOICES = [
    ("SERVER", "Server / Cameriere"), ("FOH_SUPERVISOR", "FOH Team Leader"), ("BARTENDER", "Bartender"),
    ("HOST", "Host / Hostess"), ("BUSSER", "Busser"), ("FOOD_RUNNER", "Food runner"),
    ("FOH_MANAGER", "FOH Manager"), ("LINE_COOK", "Line cook"), ("PREP_COOK", "Prep cook"),
    ("PIZZA_COOK", "Pizzaiolo"), ("DISHWASHER", "Lavapiatti"), ("SOUS_CHEF", "Sous chef"), ("CHEF", "Chef"),
    ("BOH_MANAGER", "Kitchen manager"), ("ASSISTANT_GENERAL_MANAGER", "Assistant general manager"),
    ("GENERAL_MANAGER", "General manager"),
]
ROLE_LABEL = dict(ROLE_CHOICES)
ROLE_LABEL_EN = {"SERVER": "Server", "FOH_SUPERVISOR": "Front of House Team Leader", "PIZZA_COOK": "Pizza Cook",
                 "DISHWASHER": "Dishwasher"}
DEFAULT_QUESTIONS = (
    "Are you looking for full-time or part-time work?",
    "Are you available to work weekends?",
    "Are you available to work closing shifts?",
    "When could you start training if offered the role?",
    "Why did you leave your last job?",
)

app = Flask(__name__)
if os.environ.get("RFONE_SELECTION_PROTOTYPE_SECRET_KEY"):
    app.secret_key = os.environ["RFONE_SELECTION_PROTOTYPE_SECRET_KEY"]
else:
    _secret_file = DATA_DIR / "secret.key"
    if not _secret_file.exists():
        _secret_file.write_text(secrets.token_hex(32), encoding="utf-8")
    app.secret_key = _secret_file.read_text(encoding="utf-8").strip()
if PUBLIC_MODE:
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    app.config.update(SESSION_COOKIE_SECURE=True, PREFERRED_URL_SCHEME="https")
MIN_PASSWORD = 10 if PUBLIC_MODE else 0  # the "any length" simplification is for the local environment only
app.config.update(SESSION_COOKIE_NAME="rfone_selection_ai_session", SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", MAX_CONTENT_LENGTH=40 * 1024 * 1024)


# ---------------------------------------------------------------------------
# Accounts (RF-One's own account model, session keys and domain rule)
# ---------------------------------------------------------------------------

class Actor:
    def __init__(self, account: m.RFOneAccount, role: str):
        self.id, self.name, self.role = account.id, shared_session.account_display_name(account), role

    @property
    def is_owner(self) -> bool:
        return self.role == ROLE_OWNER

    @property
    def supervises_all(self) -> bool:
        return self.role in (ROLE_OWNER, ROLE_SUPERVISOR)

    def can_view(self, position: ps.Position) -> bool:
        return self.supervises_all or position.manager_account_id == self.id

    def can_edit(self, position: ps.Position) -> bool:
        return self.is_owner or position.manager_account_id == self.id


def _actor(db) -> Actor | None:
    account = shared_session.account_for_session(
        db, account_id=flask_session.get(shared_session.SESSION_ACCOUNT_KEY),
        session_version=flask_session.get(shared_session.SESSION_VERSION_KEY))
    if account is None or not shared_session.account_may_enter_domain(db, account, SELECTION_DOMAIN):
        return None
    row = next(r for r in account_svc.list_domain_access_for_account(db, account.id) if r.domain_code == SELECTION_DOMAIN)
    role = ROLE_OWNER if account.is_admin else (row.role_code or ROLE_MANAGER)
    return Actor(account, role if role in ROLE_LABELS else ROLE_MANAGER)


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        with SessionFactory() as db:
            if db.scalar(select(func.count()).select_from(m.RFOneAccount)) == 0:
                return redirect(url_for("setup"))
            actor = _actor(db)
            if actor is None:
                return redirect(url_for("login", next=request.full_path.rstrip("?")))
            return view(db, actor, *args, **kwargs)
    return wrapper


@app.before_request
def _csrf():
    if request.method == "POST":
        sent = request.form.get("csrf_token", "")
        if not sent or not secrets.compare_digest(sent, flask_session.get(shared_session.SESSION_CSRF_KEY, "")):
            public = request.path.startswith(("/jobs/", "/apply/", "/interview/"))
            flash("Your session expired. Please try again." if public
                  else "Sessione scaduta: il modulo non è stato salvato, riprova.")
            return redirect(request.full_path.rstrip("?") if public else (request.referrer or url_for("dashboard")))


@app.after_request
def _no_index(response):
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@app.route("/robots.txt")
def robots():
    return app.response_class("User-agent: *\nDisallow: /\n", mimetype="text/plain")


@app.context_processor
def _globals():
    return {"csrf_token": lambda: shared_session.csrf_token(flask_session), "ai_policy": ai_adapter.POLICY,
            "GROUP_LABELS": ps.GROUP_LABELS, "DECISION_LABELS": ps.DECISION_LABELS, "ROLE_LABEL": ROLE_LABEL,
            "STATUS_LABELS": engine.STATUS_LABELS, "CRITICALITY_LABELS": engine.CRITICALITY_LABELS,
            "POSITION_STATUS_LABELS": ps.POSITION_STATUS_LABELS, "SOURCE_LABELS": ps.SOURCE_LABELS,
            "KIND_LABELS": ps.KIND_LABELS, "MESSAGE_KINDS": ps.MESSAGE_KINDS,
            "APPLICATION_STATUS_LABELS": ps.APPLICATION_STATUS_LABELS, "NOT_SELECTED_REASONS": ps.NOT_SELECTED_REASONS}


@app.template_filter("local")
def _local(value, tz=None, fmt=display_format.DEFAULT_FORMAT):
    return display_format.local_datetime(value, tz or DEFAULT_TIMEZONE, fmt)


@app.template_filter("anchor")
def _anchor(ref: str | None) -> str:
    """Evidence reference -> section of the candidate page."""
    if not ref:
        return "#cv"
    if ref.startswith("work_history["):
        return "#esperienza-" + ref.split("[", 1)[1].split("]", 1)[0]
    for key, target in (("certification", "#certificazioni"), ("skill", "#competenze"), ("language", "#lingue"),
                        ("education", "#formazione"), ("availability", "#disponibilita")):
        if key in ref:
            return target
    return "#cv"


def _to_utc(local_value: str, tz: str) -> datetime | None:
    try:
        naive = datetime.fromisoformat(local_value)
    except (TypeError, ValueError):
        return None
    return naive.replace(tzinfo=ZoneInfo(tz)).astimezone(UTC).replace(tzinfo=None)


def _safe_back(value: str | None, default: str) -> str:
    return value if value and value.startswith("/") and not value.startswith("//") else default


@app.route("/accesso", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        with SessionFactory() as db:
            result = account_svc.verify_login(db, request.form.get("username", ""), request.form.get("password", ""))
            if result.account is not None:
                flask_session.clear()
                flask_session[shared_session.SESSION_ACCOUNT_KEY] = result.account.id
                flask_session[shared_session.SESSION_VERSION_KEY] = result.account.session_version
                if _actor(db) is None:
                    flask_session.clear()
                    flash("Questo account non ha accesso al Domain Selection.")
                    return redirect(url_for("login"))
                return redirect(_safe_back(request.args.get("next"), url_for("dashboard")))
            flash("Nome utente o password non validi." if result.error and "Invalid" in result.error
                  else "Account non attivo.")
    return render_template("login.html")


@app.route("/esci", methods=["POST"])
def logout():
    flask_session.clear()
    return redirect(url_for("login"))


@app.route("/primo-accesso", methods=["GET", "POST"])
def setup():
    """Only while the prototype has no account at all: creates the owner.
    In the TEST deployment it also requires the setup token (Secrets Manager)."""
    expected = os.environ.get("RFONE_SELECTION_PROTOTYPE_SETUP_TOKEN", "")
    if PUBLIC_MODE and (not expected or not secrets.compare_digest(request.args.get("token", ""), expected)):
        abort(404)
    with SessionFactory() as db:
        if db.scalar(select(func.count()).select_from(m.RFOneAccount)) > 0:
            return redirect(url_for("login"))
        if request.method == "POST":
            password = request.form.get("password", "")
            if password != request.form.get("password2"):
                flash("Le due password non coincidono.")
            elif len(password) < MIN_PASSWORD:
                flash(f"La password deve avere almeno {MIN_PASSWORD} caratteri.")
            else:
                try:
                    account = account_svc.create_account(
                        db, username=request.form.get("username", ""), display_name=request.form.get("display_name", ""),
                        password=password, is_admin=True)
                    account_svc.set_domain_access(db, account_id=account.id, domain_code=SELECTION_DOMAIN,
                                                  enabled=True, role_code=ROLE_OWNER)
                    db.commit()
                    flash("Account proprietario creato: ora puoi accedere.")
                    return redirect(url_for("login"))
                except ValueError as exc:
                    db.rollback()
                    flash(str(exc))
    return render_template("setup.html")


def _new_invite(db, account, actor) -> str:
    token = secrets.token_urlsafe(24)
    db.add(ps.Invite(account_id=account.id, token_hash=hashlib.sha256(token.encode()).hexdigest(),
                     expires_at=ps.utcnow() + timedelta(days=7), created_by_name=actor.name))
    db.commit()
    return url_for("accept_invite", token=token, _external=True)


@app.route("/invito/<token>", methods=["GET", "POST"])
def accept_invite(token):
    with SessionFactory() as db:
        invite = db.scalars(select(ps.Invite).where(
            ps.Invite.token_hash == hashlib.sha256(token.encode()).hexdigest())).first()
        if invite is None or invite.used_at or invite.expires_at < ps.utcnow():
            return render_template("message.html", title="Invito non valido",
                                   text="Il link è scaduto o è già stato usato. Chiedi un nuovo invito."), 404
        account = account_svc.get_account(db, invite.account_id)
        if request.method == "POST":
            password = request.form.get("password", "")
            if password != request.form.get("password2"):
                flash("Le due password non coincidono.")
            elif len(password) < MIN_PASSWORD:
                flash(f"La password deve avere almeno {MIN_PASSWORD} caratteri.")
            else:
                account_svc.set_password(db, account, password)
                invite.used_at = ps.utcnow()
                db.commit()
                flash("Password impostata: ora puoi accedere.")
                return redirect(url_for("login"))
        return render_template("invite.html", account=account, min_password=MIN_PASSWORD)


@app.route("/persone", methods=["GET", "POST"])
@login_required
def people(db, actor):
    if not actor.is_owner:
        abort(403)
    if request.method == "POST":
        action = request.form.get("action", "create")
        if action in ("invite", "deactivate"):
            account = account_svc.get_account(db, request.form.get("account_id", type=int) or 0)
            if account is None or account.id == actor.id:
                abort(404)
            if action == "deactivate":
                account_svc.update_account(db, account, display_name=account.display_name, status="INACTIVE")
                db.commit()
                flash(f"Account di {account.display_name} disattivato.")
            else:
                flash(f"Nuovo link d'invito per {account.display_name} (valido 7 giorni, usabile una volta): "
                      f"{_new_invite(db, account, actor)}")
            return redirect(url_for("people"))
        role = request.form.get("role")
        password = request.form.get("password", "")
        invite = PUBLIC_MODE or not password
        if role not in ROLE_LABELS:
            flash("Scegliere il ruolo.")
        else:
            try:
                account = account_svc.create_account(
                    db, username=request.form.get("username", ""), display_name=request.form.get("display_name", ""),
                    password=secrets.token_urlsafe(32) if invite else password)
                account_svc.set_domain_access(db, account_id=account.id, domain_code=SELECTION_DOMAIN, enabled=True,
                                              role_code=role)
                db.commit()
                if invite:
                    flash(f"Account creato per {account.display_name}. Invia questo link d'invito: la persona sceglierà "
                          f"la propria password (valido 7 giorni, usabile una volta): {_new_invite(db, account, actor)}")
                else:
                    flash(f"Account creato per {account.display_name}.")
            except ValueError as exc:
                db.rollback()
                flash(str(exc))
        return redirect(url_for("people"))
    rows = []
    for account in account_svc.list_accounts(db):
        access = next((r for r in account_svc.list_domain_access_for_account(db, account.id)
                       if r.domain_code == SELECTION_DOMAIN and r.enabled), None)
        rows.append((account, ROLE_OWNER if account.is_admin else (access.role_code if access else None)))
    return render_template("people.html", actor=actor, rows=rows, role_labels=ROLE_LABELS, public_mode=PUBLIC_MODE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _restaurant_id(db) -> int:
    restaurant = db.scalars(select(m.Restaurant).order_by(m.Restaurant.id)).first()
    if restaurant is None:
        restaurant = m.Restaurant(name=CLIENT_NAME, default_currency="USD")
        db.add(restaurant)
        db.commit()
    return restaurant.id


def _position(db, actor: Actor, position_id: int, *, edit: bool = False) -> ps.Position:
    position = db.get(ps.Position, position_id)
    if position is None or not actor.can_view(position):
        abort(404)
    if edit and not actor.can_edit(position):
        abort(403)
    return position


def _pc(db, position, pc_id) -> ps.PositionCandidate:
    pc = db.get(ps.PositionCandidate, pc_id)
    if pc is None or pc.position_id != position.id:
        abort(404)
    return pc


def _manager_name(db, account_id: int) -> str:
    return shared_session.account_display_name(account_svc.get_account(db, account_id))


def _company_profile(db) -> ps.CompanyProfile:
    profile = db.scalars(select(ps.CompanyProfile)).first()
    if profile is None:
        profile = ps.CompanyProfile(text="")
        db.add(profile)
        db.flush()
    return profile


def _company_facts(db, location: str) -> dict:
    organization = organization_adapter.get_context(location)
    profile_text = _company_profile(db).text.strip()
    facts = list(organization["facts"])
    if profile_text:
        facts.append("Profilo aziendale (scritto dal proprietario nel prototipo): " + profile_text)
    return {"facts": facts, "missing": organization["missing"], "source": organization["source"],
            "timezone": organization["timezone"], "profile": profile_text}


def _appointments(db, pc_ids: list[int], *, include_cancelled: bool = False) -> list[ps.Appointment]:
    if not pc_ids:
        return []
    stmt = select(ps.Appointment).where(ps.Appointment.position_candidate_id.in_(pc_ids))
    if not include_cancelled:
        stmt = stmt.where(ps.Appointment.status == "CONFIRMED")
    return list(db.scalars(stmt.order_by(ps.Appointment.starts_at)).all())


def _candidate_cards(db, position: ps.Position) -> list[dict]:
    cards = []
    pcs = db.scalars(select(ps.PositionCandidate).where(ps.PositionCandidate.position_id == position.id)
                     .order_by(ps.PositionCandidate.added_at)).all()
    now = ps.utcnow()
    for pc in pcs:
        candidate, profile, view = engine.candidate_view(db, pc, position)
        proposals = engine.current_proposals(db, pc.id)
        latest = next((w for w in profile.work_history if w.is_current), None) or (
            max((w for w in profile.work_history if w.start_date), key=lambda w: w.start_date, default=None))
        application = engine.candidate_application(db, pc.id)
        upcoming = [a for a in _appointments(db, [pc.id]) if a.starts_at >= now - timedelta(hours=2)]
        cards.append({
            "pc": pc, "name": candidate.full_name or pc.declared_name or "(nome non letto)",
            "latest_role": (f"{latest.original_job_title or '?'} · {latest.employer or '?'}" if latest else None),
            "direct_months": view.breakdown.direct_role_months if view.role_config else None,
            "proposal": engine.leading_proposal(proposals), "decision": engine.current_decision(db, pc.id),
            "channel": CHANNEL_LABELS.get(pc.channel, pc.channel), "duplicates": engine.duplicate_notes(db, pc),
            "application": application, "next_appointment": upcoming[0] if upcoming else None,
        })
    return cards


def _record_decision(db, actor, position, pc, decision, reason, note) -> None:
    lead = engine.leading_proposal(engine.current_proposals(db, pc.id))
    expected = ps.DECISION_TO_GROUP.get(decision)
    db.add(ps.Decision(
        position_candidate_id=pc.id, decision=decision, reason_code=reason if decision == ps.D_NOT_SELECTED else None,
        note=note, proposal_group=lead.group_code if lead else None, proposal_source=lead.source if lead else None,
        differs_from_proposal=bool(lead) and expected is not None and expected != lead.group_code,
        actor_account_id=actor.id, actor_name=actor.name))
    candidate = persistence.get_candidate(db, pc.candidate_id)
    detail = f"{candidate.full_name or pc.declared_name or 'Candidato'}: {ps.DECISION_LABELS[decision]}"
    if decision == ps.D_NOT_SELECTED:
        detail += f" — {ps.NOT_SELECTED_REASONS[reason]}"
    if lead and decision in ps.PRESELECTION_DECISIONS:
        detail += f" (proposta: {ps.GROUP_LABELS[lead.group_code]})"
    if note:
        detail += f". Nota: {note}"
    ps.log_event(db, position_id=position.id, position_candidate_id=pc.id, kind="DECISION", detail=detail,
                 actor_id=actor.id, actor_name=actor.name)


def _first_name(db, pc) -> str | None:
    candidate = persistence.get_candidate(db, pc.candidate_id)
    name = (candidate.full_name or pc.declared_name or "").strip()
    return name.split()[0].title() if name else None


def _draft_message(db, actor, position, pc, kind: str, facts: str = "") -> ps.Message:
    """AI draft when active (no candidate data sent), else the standard English text. Never sent automatically."""
    source = "TEMPLATE"
    body = engine.STANDARD_MESSAGES[kind].format(title=position.title, location=position.location_label,
                                                  facts=facts or "").replace("  ", " ")
    if ai_adapter.POLICY.ai_enabled:
        try:
            body = ai_adapter.draft_message(kind=kind, title=position.title, location=position.location_label,
                                            facts=facts)
            source = "AI"
        except AIProviderUnavailable as exc:
            flash(f"Bozza AI non disponibile ({exc}): usato il testo standard.")
    message = ps.Message(position_candidate_id=pc.id, kind=kind, source=source,
                         body=engine.fill_placeholders(body, first_name=_first_name(db, pc), manager_name=actor.name))
    db.add(message)
    db.flush()
    return message


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route("/")
@login_required
def dashboard(db, actor):
    positions = db.scalars(select(ps.Position).order_by(ps.Position.status.desc(), ps.Position.created_at.desc())).all()
    rows, upcoming = [], []
    now = ps.utcnow()
    for position in positions:
        if not actor.can_view(position):
            continue
        cards = _candidate_cards(db, position)
        counts = {g: 0 for g in ps.GROUP_ORDER}
        for c in cards:
            if not c["decision"] and c["proposal"]:
                counts[c["proposal"].group_code] += 1
        rows.append({"position": position, "manager": _manager_name(db, position.manager_account_id),
                     "total": len(cards), "counts": counts,
                     "hired": sum(1 for c in cards if c["decision"] and c["decision"].decision == ps.D_HIRED),
                     "to_interview": sum(1 for c in cards if c["decision"] and c["decision"].decision == ps.D_INTERVIEW)})
        for c in cards:
            a = c["next_appointment"]
            if a and a.starts_at <= now + timedelta(days=14):
                upcoming.append((a, position, c))
    upcoming.sort(key=lambda t: t[0].starts_at)
    company = _company_facts(db, "")
    db.commit()
    return render_template("dashboard.html", actor=actor, rows=rows, upcoming=upcoming, company=company)


@app.route("/profilo-aziendale", methods=["POST"])
@login_required
def company_profile(db, actor):
    if not actor.is_owner:
        abort(403)
    profile = _company_profile(db)
    profile.text = (request.form.get("text") or "").strip()
    profile.updated_by_name, profile.updated_at = actor.name, ps.utcnow()
    db.commit()
    flash("Profilo aziendale salvato.")
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------------------
# 1. CREATE POSITION
# ---------------------------------------------------------------------------

def _run_position_draft(db, actor, position, extra: str = "") -> None:
    company = _company_facts(db, position.location_label)
    try:
        draft = ai_adapter.draft_position(
            title=position.title, role=ROLE_LABEL_EN.get(position.role_code, ROLE_LABEL[position.role_code]),
            location=position.location_label, description=(position.description + "\n" + extra).strip(),
            company_facts=company["facts"], missing_facts=company["missing"])
    except AIProviderUnavailable as exc:
        flash(f"Proposta AI non disponibile: {exc}")
        return
    db.add(ps.PositionDraft(position_id=position.id, payload_json=json.dumps(draft, ensure_ascii=False),
                            provider_label=ai_adapter.POLICY.provider_label, created_by_account_id=actor.id))
    ps.log_event(db, position_id=position.id, kind="AI_DRAFT", actor_id=actor.id, actor_name=actor.name,
                 detail=f"L'AI ha proposto {len(draft['requirements'])} requisiti, numero di persone e annuncio (da approvare)")
    db.commit()


@app.route("/posizioni/nuova", methods=["GET", "POST"])
@login_required
def position_new(db, actor):
    if actor.role == ROLE_SUPERVISOR:
        abort(403)
    managers = [a for a in account_svc.list_accounts(db) if a.status == "ACTIVE"
                and shared_session.account_may_enter_domain(db, a, SELECTION_DOMAIN)]
    company = _company_facts(db, request.form.get("location", ""))
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        role_code = request.form.get("role_code", "")
        location = request.form.get("location", "").strip()
        timezone = request.form.get("timezone", "").strip() or DEFAULT_TIMEZONE
        manager_id = request.form.get("manager_account_id", type=int) if actor.is_owner else actor.id
        try:
            ZoneInfo(timezone)
        except Exception:
            timezone = ""
        if not title or role_code not in ROLE_LABEL or not location or not timezone or \
                manager_id not in {a.id for a in managers}:
            flash("Compilare titolo, ruolo, sede, fuso orario valido e responsabile.")
            return render_template("position_new.html", actor=actor, roles=ROLE_CHOICES, managers=managers,
                                   form=request.form, company=company, default_tz=DEFAULT_TIMEZONE,
                                   full_roles=FULL_ANALYSIS_ROLES)
        restaurant_id = _restaurant_id(db)
        requirement_set = req_svc.create_requirement_set(
            db, restaurant_id=restaurant_id, name=f"{title} — {location}", target_role=role_code,
            location_label=location, description=request.form.get("description", ""))
        position = ps.Position(
            title=title, role_code=role_code, location_label=location, timezone=timezone,
            description=request.form.get("description", "").strip(), manager_account_id=manager_id,
            created_by_account_id=actor.id, requirement_set_id=requirement_set.id,
            headcount=max(1, request.form.get("headcount", type=int) or 1),
            questions_json=json.dumps(list(DEFAULT_QUESTIONS)),
            organization_context_json=json.dumps({k: company[k] for k in ("facts", "missing", "source")}))
        db.add(position)
        db.flush()
        ps.log_event(db, position_id=position.id, kind="CREATED", actor_id=actor.id, actor_name=actor.name,
                     detail=f"Posizione creata: {title} ({ROLE_LABEL[role_code]}, {location}); "
                            f"responsabile {_manager_name(db, manager_id)}")
        db.commit()
        if ai_adapter.POLICY.ai_enabled:
            _run_position_draft(db, actor, position)
        return redirect(url_for("position_detail", position_id=position.id, tab="posizione"))
    return render_template("position_new.html", actor=actor, roles=ROLE_CHOICES, managers=managers, form={},
                           company=company, default_tz=DEFAULT_TIMEZONE, full_roles=FULL_ANALYSIS_ROLES)


@app.route("/posizioni/<int:position_id>")
@login_required
def position_detail(db, actor, position_id):
    position = _position(db, actor, position_id)
    tab = request.args.get("tab") or ("posizione" if position.status == ps.DRAFT else "valutazione")
    cards = _candidate_cards(db, position)
    columns = {g: [] for g in ps.GROUP_ORDER}
    pending, decided = [], {d: [] for d in ps.DECISION_LABELS}
    for card in cards:
        if card["decision"]:
            decided[card["decision"].decision].append(card)
        elif card["proposal"]:
            columns[card["proposal"].group_code].append(card)
        else:
            pending.append(card)
    seed_sample_templates(db)
    restaurant_id = _restaurant_id(db)
    seed_romes_flavours_phone_interview_questions(db, restaurant_id=restaurant_id)
    db.commit()
    standard_pool = [d.question_text for d in pi_svc.list_question_definitions(db, restaurant_id=restaurant_id)
                     if not d.is_courtesy]
    drafts = db.scalars(select(ps.PositionDraft).where(ps.PositionDraft.position_id == position.id,
                                                       ps.PositionDraft.status == "PROPOSED")
                        .order_by(ps.PositionDraft.id.desc())).all()
    events = db.scalars(select(ps.Event).where(ps.Event.position_id == position.id).order_by(ps.Event.id.desc())).all()
    pc_ids = [c["pc"].id for c in cards]
    appointments = _appointments(db, pc_ids, include_cancelled=True)
    offers = list(db.scalars(select(ps.SlotOffer).where(ps.SlotOffer.position_candidate_id.in_(pc_ids),
                                                        ps.SlotOffer.status == "OPEN")).all()) if pc_ids else []
    names = {c["pc"].id: c["name"] for c in cards}
    days: dict[str, list] = {}
    for a in appointments:
        days.setdefault(_local(a.starts_at, position.timezone, "%A %d %B %Y"), []).append(a)
    unapproved = position.approved_snapshot_id and (
        engine.requirements_changed_since_approval(db, position)
        or position.job_ad_en != (position.approved_job_ad_en or "")
        or position.questions_json != (position.approved_questions_json or "[]"))
    return render_template(
        "position.html", actor=actor, position=position, tab=tab, cards=cards, columns=columns, pending=pending,
        decided=decided, manager=_manager_name(db, position.manager_account_id),
        requirements=engine.active_requirements(db, position), drafts=drafts,
        templates=req_svc.list_templates(db), events=events, channels=CHANNELS, unapproved=unapproved,
        can_edit=actor.can_edit(position), categories=ai_adapter.CATEGORY_LABELS_IT,
        trainability=engine.TRAINABILITY_LABELS, full_analysis=position.role_code in FULL_ANALYSIS_ROLES,
        public_url=url_for("job_page", token=position.public_token, _external=True), standard_pool=standard_pool,
        days=days, offers=offers, names=names, now=ps.utcnow(),
        hired=len(decided[ps.D_HIRED]))


def _position_redirect(position, tab="posizione"):
    return redirect(url_for("position_detail", position_id=position.id, tab=tab))


@app.route("/posizioni/<int:position_id>/ai-bozza", methods=["POST"])
@login_required
def position_ai_draft(db, actor, position_id):
    position = _position(db, actor, position_id, edit=True)
    _run_position_draft(db, actor, position, request.form.get("extra", ""))
    return _position_redirect(position)


@app.route("/posizioni/<int:position_id>/bozza/<int:draft_id>", methods=["POST"])
@login_required
def position_draft_use(db, actor, position_id, draft_id):
    position = _position(db, actor, position_id, edit=True)
    draft = db.get(ps.PositionDraft, draft_id)
    if draft is None or draft.position_id != position.id or draft.status != "PROPOSED":
        abort(404)
    if request.form.get("action") == "discard":
        draft.status = "DISCARDED"
        detail = "Proposta AI scartata"
    else:
        chosen = set(request.form.getlist("item"))
        used = 0
        for index, item in enumerate(draft.payload["requirements"]):
            if str(index) not in chosen:
                continue
            description = item["description"]
            if item["cv_keywords"]:
                description = f"{description}\nParole chiave CV: {', '.join(item['cv_keywords'])}".strip()
            req_svc.add_requirement(db, position.requirement_set_id, name=item["name"], description=description,
                                    category=item["category"], criticality=item["criticality"],
                                    trainability=item["trainability"], assessment_stages=engine.DEFAULT_STAGES,
                                    guidance_notes=item.get("why") or None)
            used += 1
        if request.form.get("use_ad") and draft.payload.get("job_ad_en"):
            position.job_ad_en = draft.payload["job_ad_en"]
        if request.form.get("use_headcount") and draft.payload.get("headcount"):
            position.headcount = draft.payload["headcount"]
        draft.status = "USED"
        detail = f"Proposta AI usata: {used} requisiti" + (", annuncio" if request.form.get("use_ad") else "") + \
                 (", numero di persone" if request.form.get("use_headcount") else "") + " (da approvare)"
    ps.log_event(db, position_id=position.id, kind="AI_DRAFT", detail=detail, actor_id=actor.id, actor_name=actor.name)
    db.commit()
    return _position_redirect(position)


@app.route("/posizioni/<int:position_id>/dettagli", methods=["POST"])
@login_required
def position_details(db, actor, position_id):
    position = _position(db, actor, position_id, edit=True)
    position.headcount = max(1, request.form.get("headcount", type=int) or 1)
    position.job_ad_en = (request.form.get("job_ad_en") or "").strip()
    questions = [q.strip() for q in (request.form.get("questions") or "").splitlines() if q.strip()]
    position.questions_json = json.dumps(questions[:MAX_STANDARD_QUESTIONS])
    if len(questions) > MAX_STANDARD_QUESTIONS:
        flash(f"Tenute le prime {MAX_STANDARD_QUESTIONS} domande: l'intervista deve durare circa 5 minuti.")
    ps.log_event(db, position_id=position.id, kind="DETAILS", actor_id=actor.id, actor_name=actor.name,
                 detail=f"Dettagli aggiornati: {position.headcount} persona/e, annuncio e {len(position.questions)} domande standard")
    db.commit()
    flash("Salvato. Ricorda di approvare per renderlo effettivo.")
    return _position_redirect(position)


def _requirement_fields(form) -> dict:
    criticality, trainability, category = form.get("criticality"), form.get("trainability"), form.get("category")
    return {
        "name": (form.get("name") or "").strip(),
        "description": (form.get("description") or "").strip() or None,
        "category": category if category in ai_adapter.CATEGORY_LABELS_IT else "Other",
        "criticality": criticality if criticality in rm.CRITICALITY_LEVELS else rm.PREFERRED,
        "trainability": trainability if trainability in rm.TRAINABILITY_LEVELS else rm.TRAINABILITY_UNKNOWN,
    }


@app.route("/posizioni/<int:position_id>/requisiti/aggiungi", methods=["POST"])
@login_required
def requirement_add(db, actor, position_id):
    position = _position(db, actor, position_id, edit=True)
    fields = _requirement_fields(request.form)
    if not fields["name"]:
        flash("Il requisito deve avere un nome.")
        return _position_redirect(position)
    req_svc.add_requirement(db, position.requirement_set_id, assessment_stages=engine.DEFAULT_STAGES, **fields)
    ps.log_event(db, position_id=position.id, kind="REQUIREMENT", actor_id=actor.id, actor_name=actor.name,
                 detail=f"Requisito aggiunto: {fields['name']} ({engine.CRITICALITY_LABELS[fields['criticality']]})")
    db.commit()
    return _position_redirect(position)


@app.route("/posizioni/<int:position_id>/requisiti/<int:requirement_id>", methods=["POST"])
@login_required
def requirement_edit(db, actor, position_id, requirement_id):
    position = _position(db, actor, position_id, edit=True)
    requirement = db.get(m.Requirement, requirement_id)
    if requirement is None or requirement.requirement_set_id != position.requirement_set_id:
        abort(404)
    if request.form.get("action") == "remove":
        req_svc.deactivate_requirement(db, requirement_id)
        detail = f"Requisito rimosso: {requirement.name}"
    else:
        fields = _requirement_fields(request.form)
        if not fields["name"]:
            flash("Il requisito deve avere un nome.")
            return _position_redirect(position)
        req_svc.update_requirement(db, requirement_id, **fields)
        detail = f"Requisito modificato: {fields['name']}"
    ps.log_event(db, position_id=position.id, kind="REQUIREMENT", detail=detail, actor_id=actor.id, actor_name=actor.name)
    db.commit()
    return _position_redirect(position)


@app.route("/posizioni/<int:position_id>/requisiti/modello", methods=["POST"])
@login_required
def requirement_from_template(db, actor, position_id):
    position = _position(db, actor, position_id, edit=True)
    template = req_svc.get_template(db, request.form.get("template_id", type=int) or 0)
    if template is None:
        abort(404)
    for item in sorted(template.items, key=lambda i: i.display_order):
        if item.is_active:
            req_svc.add_requirement(
                db, position.requirement_set_id, name=item.name, description=item.description, category=item.category,
                criticality=item.criticality, trainability=item.trainability,
                assessment_stages=list(item.assessment_stages or engine.DEFAULT_STAGES),
                evidence_positive=item.evidence_positive, evidence_contrary=item.evidence_contrary,
                evidence_insufficient=item.evidence_insufficient, guidance_notes=item.guidance_notes)
    ps.log_event(db, position_id=position.id, kind="REQUIREMENT", actor_id=actor.id, actor_name=actor.name,
                 detail=f"Requisiti copiati dal modello esistente «{template.name}» (da rivedere prima dell'approvazione)")
    db.commit()
    return _position_redirect(position)


@app.route("/posizioni/<int:position_id>/approva", methods=["POST"])
@login_required
def position_approve(db, actor, position_id):
    position = _position(db, actor, position_id, edit=True)
    requirements = engine.active_requirements(db, position)
    missing = [label for label, ok in (("almeno un requisito (sezione «Requisiti» → «Aggiungi requisito»)", requirements),
                                       ("il testo dell'annuncio", position.job_ad_en.strip()),
                                       ("almeno una domanda standard", position.questions)) if not ok]
    if missing:
        flash("Non ancora approvabile: manca " + "; manca ".join(missing) + ".")
        return _position_redirect(position)
    if "[" in position.job_ad_en and "]" in position.job_ad_en:
        flash("L'annuncio contiene ancora segnaposto tra parentesi quadre: completali o rimuovili.")
        return _position_redirect(position)
    if not any(r.criticality == rm.MUST_HAVE for r in requirements):
        flash("Attenzione: nessun requisito è «Essenziale», quindi la proposta non potrà distinguere i candidati.")
    snapshot = req_svc.create_requirement_set_snapshot(db, position.requirement_set_id)
    first_approval = position.approved_snapshot_id is None
    position.approved_snapshot_id = snapshot.id
    position.approved_job_ad_en, position.approved_questions_json = position.job_ad_en, position.questions_json
    position.approved_by_account_id, position.approved_at = actor.id, ps.utcnow()
    if position.status == ps.DRAFT:
        position.status = ps.OPEN
    ps.log_event(db, position_id=position.id, kind="APPROVED", actor_id=actor.id, actor_name=actor.name,
                 detail=f"Posizione approvata (requisiti v{snapshot.version}: {len(requirements)}; "
                        f"{position.headcount} persona/e; {len(position.questions)} domande standard)")
    db.commit()
    for pc in db.scalars(select(ps.PositionCandidate).where(ps.PositionCandidate.position_id == position.id)).all():
        engine.analyze(db, position, pc, actor_id=actor.id, actor_name=actor.name)
    if first_approval:
        flash("Posizione aperta: la pagina di candidatura è attiva.")
    return _position_redirect(position, "candidature")


@app.route("/posizioni/<int:position_id>/stato", methods=["POST"])
@login_required
def position_status(db, actor, position_id):
    position = _position(db, actor, position_id, edit=True)
    if request.form.get("action") == "close":
        position.status, position.closed_at = ps.CLOSED, ps.utcnow()
        detail = "Posizione chiusa: la pagina di candidatura non accetta più candidature"
    else:
        position.status, position.closed_at = (ps.OPEN if position.approved_snapshot_id else ps.DRAFT), None
        detail = "Posizione riaperta"
    ps.log_event(db, position_id=position.id, kind="STATUS", detail=detail, actor_id=actor.id, actor_name=actor.name)
    db.commit()
    return _position_redirect(position, "decisioni")


# ---------------------------------------------------------------------------
# 2. RECEIVE APPLICATIONS (manager side)
# ---------------------------------------------------------------------------

@app.route("/posizioni/<int:position_id>/cv", methods=["POST"])
@login_required
def cv_upload(db, actor, position_id):
    position = _position(db, actor, position_id, edit=True)
    files = [f for f in request.files.getlist("cv") if f and f.filename]
    if not files:
        flash("Selezionare almeno un file.")
    for f in files:
        r = engine.import_cv(db, documents=DOCUMENTS, restaurant_id=_restaurant_id(db), position=position,
                             file_storage=f, channel=ps.MANUAL_UPLOAD, actor_id=actor.id, actor_name=actor.name)
        label = {"OK": "importato", "DUPLICATE": "già presente", "FAILED": "non importato"}[r["status"]]
        flash(f"{r['filename']}: {label}" + (f" — {r['message']}" if r.get("message") else ""))
    if files and not position.approved_snapshot_id:
        flash("I CV saranno valutati appena la posizione sarà approvata.")
    return _position_redirect(position, "valutazione" if position.approved_snapshot_id else "candidature")


@app.route("/posizioni/<int:position_id>/rianalizza", methods=["POST"])
@login_required
def reanalyze(db, actor, position_id):
    position = _position(db, actor, position_id, edit=True)
    for pc in db.scalars(select(ps.PositionCandidate).where(ps.PositionCandidate.position_id == position.id)).all():
        engine.analyze(db, position, pc, actor_id=actor.id, actor_name=actor.name)
    flash("Valutazione aggiornata con la versione approvata.")
    return _position_redirect(position, "valutazione")


# ---------------------------------------------------------------------------
# 3. EVALUATE
# ---------------------------------------------------------------------------

@app.route("/posizioni/<int:position_id>/candidati/<int:pc_id>")
@login_required
def candidate_detail(db, actor, position_id, pc_id):
    position = _position(db, actor, position_id)
    pc = _pc(db, position, pc_id)
    candidate, profile, view = engine.candidate_view(db, pc, position)
    proposals = engine.current_proposals(db, pc.id)
    decisions = db.scalars(select(ps.Decision).where(ps.Decision.position_candidate_id == pc.id)
                           .order_by(ps.Decision.id.desc())).all()
    ai = proposals.get(ps.SOURCE_AI)
    messages = db.scalars(select(ps.Message).where(ps.Message.position_candidate_id == pc.id)
                          .order_by(ps.Message.id.desc())).all()
    offers = db.scalars(select(ps.SlotOffer).where(ps.SlotOffer.position_candidate_id == pc.id)
                        .order_by(ps.SlotOffer.id.desc())).all()
    return render_template(
        "candidate.html", actor=actor, position=position, pc=pc, candidate=candidate, profile=profile, view=view,
        rules=proposals.get(ps.SOURCE_RULES), ai=ai, ai_by_id={i["id"]: i for i in ai.payload["items"]} if ai else {},
        lead=engine.leading_proposal(proposals), decision=engine.current_decision(db, pc.id), decisions=decisions,
        duplicates=engine.duplicate_notes(db, pc), channel=CHANNEL_LABELS.get(pc.channel, pc.channel),
        can_edit=actor.can_edit(position), full_analysis=view.role_config is not None,
        application=engine.candidate_application(db, pc.id), answers=engine.answers(db, pc.id),
        appointments=_appointments(db, [pc.id], include_cancelled=True), offers=offers, messages=messages,
        slot_url=lambda o: url_for("slot_page", token=o.token, _external=True), now=ps.utcnow())


def _raw_resume(db, pc) -> m.RawResume | None:
    candidate = persistence.get_candidate(db, pc.candidate_id)
    return db.get(m.RawResume, candidate.raw_resume_id) if candidate and candidate.raw_resume_id else None


@app.route("/posizioni/<int:position_id>/candidati/<int:pc_id>/cv-originale")
@login_required
def candidate_original(db, actor, position_id, pc_id):
    raw = _raw_resume(db, _pc(db, _position(db, actor, position_id), pc_id))
    data = DOCUMENTS.read(raw.storage_path) if raw else None
    if data is None:
        abort(404)
    name = raw.original_filename or "cv"
    return send_file(io.BytesIO(data), mimetype=mimetypes.guess_type(name)[0] or "application/octet-stream",
                     download_name=name, as_attachment=False)


@app.route("/posizioni/<int:position_id>/candidati/<int:pc_id>/testo")
@login_required
def candidate_text(db, actor, position_id, pc_id):
    position = _position(db, actor, position_id)
    pc = _pc(db, position, pc_id)
    raw = _raw_resume(db, pc)
    return render_template("cv_text.html", actor=actor, position=position, pc=pc,
                           candidate=persistence.get_candidate(db, pc.candidate_id),
                           text=raw.raw_text if raw else "", highlight=request.args.get("q", ""))


@app.route("/posizioni/<int:position_id>/confronto")
@login_required
def compare(db, actor, position_id):
    position = _position(db, actor, position_id)
    pcs = [_pc(db, position, int(x)) for x in request.args.getlist("pc_id") if x.isdigit()]
    if len(pcs) < 2:
        flash("Seleziona almeno due candidati da confrontare.")
        return _position_redirect(position, "valutazione")
    return render_template("compare.html", actor=actor, position=position, data=engine.comparison(db, position, pcs[:6]))


@app.route("/posizioni/<int:position_id>/decisioni", methods=["POST"])
@login_required
def record_decision(db, actor, position_id):
    position = _position(db, actor, position_id, edit=True)
    decision = request.form.get("decision")
    reason = request.form.get("reason") or None
    note = (request.form.get("note") or "").strip() or None
    pc_ids = [int(x) for x in request.form.getlist("pc_id") if x.isdigit()]
    quick = request.form.get("quick", "")  # "<pc_id>:<decision>" from a card button
    if ":" in quick and quick.split(":", 1)[0].isdigit():
        pc_ids, decision = [int(quick.split(":", 1)[0])], quick.split(":", 1)[1]
    back = _safe_back(request.form.get("back"), url_for("position_detail", position_id=position.id))
    if decision not in ps.DECISION_LABELS or not pc_ids:
        flash("Scegliere la decisione e almeno un candidato.")
        return redirect(back)
    if decision == ps.D_NOT_SELECTED and (reason not in ps.NOT_SELECTED_REASONS or (reason == "OTHER" and not note)):
        flash("Per «Non selezionato» indicare il motivo (e una nota se «Altro»).")
        return redirect(back)
    for pc_id in pc_ids:
        _record_decision(db, actor, position, _pc(db, position, pc_id), decision, reason, note)
    db.commit()
    flash(f"Decisione registrata per {len(pc_ids)} candidato/i.")
    return redirect(back)


# ---------------------------------------------------------------------------
# 4. ORGANIZE INTERVIEWS (internal calendar, no external integration)
# ---------------------------------------------------------------------------

def _conflicts(db, position: ps.Position, starts_at: datetime, duration: int, exclude_id: int | None = None) -> list:
    """Confirmed appointments of the same manager overlapping the slot."""
    ends_at = starts_at + timedelta(minutes=duration)
    positions = db.scalars(select(ps.Position.id).where(ps.Position.manager_account_id == position.manager_account_id)).all()
    pcs = db.scalars(select(ps.PositionCandidate.id).where(ps.PositionCandidate.position_id.in_(positions))).all()
    return [a for a in _appointments(db, list(pcs)) if a.id != exclude_id
            and a.starts_at < ends_at and starts_at < a.starts_at + timedelta(minutes=a.duration_min)]


def _book(db, position, pc, *, kind, starts_at, duration, place, note, booked_by, actor_id, actor_name) -> ps.Appointment:
    appointment = ps.Appointment(position_candidate_id=pc.id, kind=kind, starts_at=starts_at, duration_min=duration,
                                 place=place, note=note, booked_by=booked_by, created_by_account_id=actor_id)
    db.add(appointment)
    db.flush()
    candidate = persistence.get_candidate(db, pc.candidate_id)
    ps.log_event(db, position_id=position.id, position_candidate_id=pc.id, kind="INTERVIEW", actor_id=actor_id,
                 actor_name=actor_name,
                 detail=f"Colloquio {ps.KIND_LABELS[kind].lower()} con {candidate.full_name or pc.declared_name or 'candidato'}: "
                        f"{_local(starts_at, position.timezone)}" + (f", {place}" if place else ""))
    return appointment


@app.route("/posizioni/<int:position_id>/candidati/<int:pc_id>/colloquio", methods=["POST"])
@login_required
def interview_book(db, actor, position_id, pc_id):
    position = _position(db, actor, position_id, edit=True)
    pc = _pc(db, position, pc_id)
    back = url_for("candidate_detail", position_id=position.id, pc_id=pc.id) + "#colloquio"
    kind = request.form.get("kind")
    duration = request.form.get("duration", type=int) or 30
    place = (request.form.get("place") or "").strip() or None
    if kind not in ps.KIND_LABELS:
        flash("Scegliere colloquio telefonico o di persona.")
        return redirect(back)
    if request.form.get("mode") == "offer":
        slots = [_to_utc(v, position.timezone) for v in request.form.getlist("slot") if v]
        slots = sorted({s for s in slots if s and s > ps.utcnow()})
        if not slots:
            flash("Indicare almeno un orario futuro da proporre.")
            return redirect(back)
        offer = ps.SlotOffer(position_candidate_id=pc.id, kind=kind, duration_min=duration, place=place,
                             slots_json=json.dumps([s.isoformat(timespec="minutes") for s in slots]),
                             created_by_account_id=actor.id)
        db.add(offer)
        db.flush()
        link = url_for("slot_page", token=offer.token, _external=True)
        _draft_message(db, actor, position, pc, "SLOTS", facts=link)
        ps.log_event(db, position_id=position.id, position_candidate_id=pc.id, kind="INTERVIEW", actor_id=actor.id,
                     actor_name=actor.name, detail=f"Proposti {len(slots)} orari per colloquio {ps.KIND_LABELS[kind].lower()}")
        flash("Orari proposti. Il messaggio con il link è pronto da approvare qui sotto.")
    else:
        starts_at = _to_utc(request.form.get("starts_at", ""), position.timezone)
        if starts_at is None:
            flash("Indicare data e ora del colloquio.")
            return redirect(back)
        clash = _conflicts(db, position, starts_at, duration)
        appointment = _book(db, position, pc, kind=kind, starts_at=starts_at, duration=duration, place=place,
                            note=(request.form.get("note") or "").strip() or None, booked_by="MANAGER",
                            actor_id=actor.id, actor_name=actor.name)
        if clash:
            flash(f"Attenzione: si sovrappone ad altri {len(clash)} colloqui in calendario.")
        facts = {ps.K_PHONE: "phone", ps.K_IN_PERSON: "in-person"}[kind] + " interview"
        facts += f" on {_local(appointment.starts_at, position.timezone, '%A, %B %d at %I:%M %p')}"
        if place:
            facts += f" ({place})"
        _draft_message(db, actor, position, pc, "INVITE", facts=facts)
        flash("Colloquio registrato. Il messaggio di invito è pronto da approvare qui sotto.")
    db.commit()
    return redirect(back)


@app.route("/posizioni/<int:position_id>/colloqui/<int:appointment_id>/annulla", methods=["POST"])
@login_required
def interview_cancel(db, actor, position_id, appointment_id):
    position = _position(db, actor, position_id, edit=True)
    appointment = db.get(ps.Appointment, appointment_id)
    if appointment is None:
        abort(404)
    pc = _pc(db, position, appointment.position_candidate_id)
    appointment.status = "CANCELLED"
    ps.log_event(db, position_id=position.id, position_candidate_id=pc.id, kind="INTERVIEW", actor_id=actor.id,
                 actor_name=actor.name, detail=f"Colloquio del {_local(appointment.starts_at, position.timezone)} annullato")
    db.commit()
    return redirect(_safe_back(request.form.get("back"), url_for("position_detail", position_id=position.id, tab="colloqui")))


# ---------------------------------------------------------------------------
# 5. DECIDE — messages (always approved by the manager, never sent automatically)
# ---------------------------------------------------------------------------

@app.route("/posizioni/<int:position_id>/candidati/<int:pc_id>/messaggi", methods=["POST"])
@login_required
def message_new(db, actor, position_id, pc_id):
    position = _position(db, actor, position_id, edit=True)
    pc = _pc(db, position, pc_id)
    kind = request.form.get("kind")
    if kind in ps.MESSAGE_KINDS and kind != "SLOTS":
        _draft_message(db, actor, position, pc, kind)
        db.commit()
    return redirect(url_for("candidate_detail", position_id=position.id, pc_id=pc.id) + "#comunicazioni")


@app.route("/posizioni/<int:position_id>/messaggi/<int:message_id>", methods=["POST"])
@login_required
def message_update(db, actor, position_id, message_id):
    position = _position(db, actor, position_id, edit=True)
    message = db.get(ps.Message, message_id)
    if message is None:
        abort(404)
    pc = _pc(db, position, message.position_candidate_id)
    if request.form.get("action") == "delete" and message.status == "DRAFT":
        db.delete(message)
    elif message.status == "DRAFT":
        message.body = (request.form.get("body") or "").strip() or message.body
        message.status, message.approved_by_name, message.approved_at = "APPROVED", actor.name, ps.utcnow()
        ps.log_event(db, position_id=position.id, position_candidate_id=pc.id, kind="MESSAGE", actor_id=actor.id,
                     actor_name=actor.name, detail=f"Comunicazione approvata: {ps.MESSAGE_KINDS[message.kind]}")
    db.commit()
    return redirect(url_for("candidate_detail", position_id=position.id, pc_id=pc.id) + "#comunicazioni")


# ---------------------------------------------------------------------------
# Public pages (no RF-One login; bound to 127.0.0.1)
# ---------------------------------------------------------------------------

def _public_position(db, token) -> ps.Position:
    position = db.scalars(select(ps.Position).where(ps.Position.public_token == token)).first()
    if position is None:
        abort(404)
    return position


@app.route("/jobs/<token>", methods=["GET", "POST"])
def job_page(token):
    with SessionFactory() as db:
        position = _public_position(db, token)
        open_ = position.status == ps.OPEN
        if request.method == "POST" and open_:
            file = request.files.get("cv")
            name = (request.form.get("name") or "").strip()
            email = (request.form.get("email") or "").strip()
            if not file or not file.filename or not name or not email or not request.form.get("consent"):
                flash("Please enter your name and email, attach your résumé and accept the notice.")
            else:
                result = engine.import_cv(
                    db, documents=DOCUMENTS, restaurant_id=_restaurant_id(db), position=position, file_storage=file,
                    channel=ps.PUBLIC_LINK, actor_id=None, actor_name="Candidato (pagina pubblica)",
                    declared={"name": name, "email": email, "phone": (request.form.get("phone") or "").strip() or None})
                if result["status"] == "DUPLICATE":
                    return render_template("public_message.html", position=position,
                                           title="We already have your application",
                                           text="This résumé was already received for this position. Thank you!")
                if result["status"] == "OK":
                    application = _start_interview(db, position, result["pc"])
                    return redirect(url_for("candidate_interview", token=application.token))
                flash("We could not read this file. Please upload a PDF, DOCX or TXT résumé.")
        snapshot = req_svc.get_snapshot(db, position.approved_snapshot_id) if position.approved_snapshot_id else None
        requirements = [i for i in sorted(snapshot.items, key=lambda i: i.display_order) if i.was_active] if snapshot else []
        return render_template("job_page.html", position=position, open_=open_, client=CLIENT_NAME, requirements=requirements,
                               role_label=ROLE_LABEL_EN.get(position.role_code, ROLE_LABEL[position.role_code]))


def _start_interview(db, position, pc) -> ps.CandidateApplication:
    questions = [{"text": q, "source": "STANDARD"} for q in position.approved_questions]
    if ai_adapter.POLICY.cv_ai_authorized:
        raw = _raw_resume(db, pc)
        try:
            followups = ai_adapter.interview_followups(
                title=position.title, role=ROLE_LABEL_EN.get(position.role_code, position.role_code),
                requirements=[r.name for r in engine.active_requirements(db, position)],
                standard=position.approved_questions, cv_text=raw.raw_text if raw else "")
            questions += [{"text": q, "source": "AI"} for q in followups]
        except AIProviderUnavailable as exc:
            flash("Personalized questions are not available right now: please answer our standard questions.")
            ps.log_event(db, position_id=position.id, position_candidate_id=pc.id, kind="AI_UNAVAILABLE",
                         actor_id=None, actor_name="Sistema",
                         detail=f"Domande AI dal CV non disponibili ({exc}): usate le domande standard approvate")
    application = ps.CandidateApplication(position_candidate_id=pc.id, questions_json=json.dumps(questions))
    db.add(application)
    db.commit()
    return application


def _application_by_token(db, token) -> tuple[ps.CandidateApplication, ps.PositionCandidate, ps.Position]:
    application = db.scalars(select(ps.CandidateApplication).where(ps.CandidateApplication.token == token)).first()
    if application is None:
        abort(404)
    pc = db.get(ps.PositionCandidate, application.position_candidate_id)
    return application, pc, db.get(ps.Position, pc.position_id)


@app.route("/apply/<token>", methods=["GET", "POST"])
def candidate_interview(token):
    with SessionFactory() as db:
        application, pc, position = _application_by_token(db, token)
        questions = application.questions
        given = {a.question_index: a for a in db.scalars(select(ps.Answer).where(
            ps.Answer.candidate_application_id == application.id)).all()}
        if request.method == "POST" and application.status != ps.A_SUBMITTED:
            if request.form.get("action") == "submit":
                application.status, application.submitted_at = ps.A_SUBMITTED, ps.utcnow()
                ps.log_event(db, position_id=position.id, position_candidate_id=pc.id, kind="APPLICATION",
                             actor_id=None, actor_name="Candidato (pagina pubblica)",
                             detail=f"Candidatura completata ({len(given)} risposte su {len(questions)})")
                db.commit()
                if position.approved_snapshot_id:
                    engine.analyze(db, position, pc, actor_id=None, actor_name="Sistema")
                return redirect(url_for("candidate_interview", token=token))
            index = request.form.get("index", type=int)
            text = (request.form.get("answer") or "").strip()
            if index is not None and 0 <= index < len(questions) and text:
                answer = given.get(index) or ps.Answer(candidate_application_id=application.id, question_index=index,
                                                       question_text=questions[index]["text"],
                                                       question_source=questions[index]["source"], answer_text="")
                answer.answer_text = text[:4000]
                answer.input_mode = "VOICE" if request.form.get("input_mode") == "VOICE" else "TEXT"
                answer.answered_at = ps.utcnow()
                db.add(answer)
                db.commit()
            if request.form.get("action") == "later":
                return render_template("public_message.html", position=position, title="Saved",
                                       text="Your answers are saved. Use your personal link to continue at any time:",
                                       link=url_for("candidate_interview", token=token, _external=True))
            edit = request.form.get("edit", type=int)
            return redirect(url_for("candidate_interview", token=token, q=edit) if edit is not None
                            else url_for("candidate_interview", token=token))
        current = request.args.get("q", type=int)
        if current is None or not (0 <= current < len(questions)):
            current = next((i for i in range(len(questions)) if i not in given), None)
        return render_template("candidate_interview.html", position=position, application=application,
                               questions=questions, given=given, current=current, client=CLIENT_NAME,
                               resume_url=url_for("candidate_interview", token=token, _external=True))


@app.route("/interview/<token>", methods=["GET", "POST"])
def slot_page(token):
    with SessionFactory() as db:
        offer = db.scalars(select(ps.SlotOffer).where(ps.SlotOffer.token == token)).first()
        if offer is None:
            abort(404)
        pc = db.get(ps.PositionCandidate, offer.position_candidate_id)
        position = db.get(ps.Position, pc.position_id)
        chosen = db.get(ps.Appointment, offer.appointment_id) if offer.appointment_id else None
        available = [s for s in offer.slots if s > ps.utcnow() and not _conflicts(db, position, s, offer.duration_min)]
        if request.method == "POST" and offer.status == "OPEN":
            pick = request.form.get("slot")
            slot = next((s for s in available if s.isoformat(timespec="minutes") == pick), None)
            if slot is None:
                flash("This time is no longer available. Please choose another one.")
            else:
                chosen = _book(db, position, pc, kind=offer.kind, starts_at=slot, duration=offer.duration_min,
                               place=offer.place, note="Scelto dal candidato tramite link", booked_by="CANDIDATE",
                               actor_id=None, actor_name="Candidato (link orari)")
                offer.status, offer.appointment_id = "CHOSEN", chosen.id
                db.commit()
        return render_template("slot_page.html", position=position, offer=offer, available=available, chosen=chosen,
                               client=CLIENT_NAME)


@app.errorhandler(403)
def _forbidden(_):
    return render_template("message.html", title="Accesso non consentito",
                           text="Il tuo ruolo non permette questa operazione."), 403


@app.errorhandler(404)
def _not_found(_):
    return render_template("message.html", title="Non trovato", text="La pagina richiesta non esiste."), 404


def main() -> None:
    parser = argparse.ArgumentParser(description="RF-One Selection AI — prototipo locale")
    parser.add_argument("--port", type=int, default=5095)
    parser.add_argument("--ai", action="store_true", help="AI drafts positions and messages (no candidate data)")
    parser.add_argument("--ai-cv", action="store_true", help="AI may read CVs and interview answers")
    args = parser.parse_args()
    ai_adapter.install_guard(ai_enabled=args.ai, cv_ai_authorized=args.ai_cv)
    print(f"Selection AI prototipo: http://127.0.0.1:{args.port}/  ·  dati: {DATA_DIR}")
    print("AI posizioni/messaggi:", "ATTIVA" if ai_adapter.POLICY.ai_enabled else "non attiva",
          "· AI su CV e risposte:", "ATTIVA" if ai_adapter.POLICY.cv_ai_authorized else "non attiva")
    app.run(host="127.0.0.1", port=args.port, debug=False, threaded=False)


if __name__ == "__main__":
    main()
