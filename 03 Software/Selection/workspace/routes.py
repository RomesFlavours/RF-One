"""Selection — the position workspace, internal side (SELECTION_AI_INTEGRATION_001).

The operational interface of the Selection Domain, transferred from the
approved Selection AI prototype: one page per open position with the five
functions — 1 Position, 2 Applications, 3 Evaluation, 4 Interviews,
5 Decisions — plus the positions list.

Access is RF-One's own: the RF-One account of the shared session, the
SELECTION Domain rule (`rfone_web_session.account_may_enter_domain`) and the
Domain role recorded on that access row in RF-One's account administration.
There is no login, account or invitation of Selection's own.

* RF-One administrator, or Selection role `OWNER`: sees and manages every
  position;
* Selection role `SUPERVISOR`: sees every position, changes nothing;
* any other enabled account: a manager, who sees and manages only the
  positions assigned to them.

Every route checks this server-side (`access_required`, `_position`), not
only the navigation. Business logic stays in the RF-One Data Store
(Selection services and `workspace_models`); this module is routing glue.
"""

from __future__ import annotations

import io
import json
import mimetypes
import secrets
from datetime import UTC, datetime, timedelta
from functools import wraps
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, url_for
from flask import session as flask_session
from sqlalchemy import select

from rfone_data_store import display_format
from rfone_data_store import models as m
from rfone_data_store import public_entry
from rfone_data_store import rfone_account_service as account_svc
from rfone_data_store import rfone_web_session as shared_session
from rfone_data_store.selection import persistence
from rfone_data_store.selection import phone_interview_service as pi_svc
from rfone_data_store.selection import requirements_service as req_svc
from rfone_data_store.selection import workspace_models as ps
from rfone_data_store.selection.core import requirement_model as rm
from rfone_data_store.selection.industry import restaurant as restaurant_industry
from rfone_data_store.selection.industry.restaurant_templates import (
    seed_romes_flavours_phone_interview_questions, seed_sample_templates,
)
from rfone_data_store.selection.parsing.ai_client import AIProviderUnavailable

from . import ai_adapter, engine, organization_adapter
from .channels import CHANNEL_LABELS, CHANNELS

bp = Blueprint("positions", __name__)


class _Config:
    """Set once by `workspace.register_workspace`."""
    SessionFactory = None
    documents = None
    rfone_web_base_url = staticmethod(lambda: None)


_cfg = _Config()

SELECTION_DOMAIN = "SELECTION"
ROLE_OWNER, ROLE_SUPERVISOR, ROLE_MANAGER = "OWNER", "SUPERVISOR", "MANAGER"
ROLE_LABELS = {ROLE_OWNER: "Proprietario / amministratore", ROLE_SUPERVISOR: "Supervisione (sola lettura)",
               ROLE_MANAGER: "Responsabile delle proprie posizioni"}
CLIENT_NAME = "Rome's Flavours"
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


# ---------------------------------------------------------------------------
# Access (RF-One account, SELECTION Domain rule and Domain role)
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


def current_account(db) -> m.RFOneAccount | None:
    return shared_session.account_for_session(
        db, account_id=flask_session.get(shared_session.SESSION_ACCOUNT_KEY),
        session_version=flask_session.get(shared_session.SESSION_VERSION_KEY))


def actor_for(db, account: m.RFOneAccount | None) -> Actor | None:
    if account is None or not shared_session.account_may_enter_domain(db, account, SELECTION_DOMAIN):
        return None
    row = next((r for r in account_svc.list_domain_access_for_account(db, account.id)
                if r.domain_code == SELECTION_DOMAIN and r.enabled), None)
    role = ROLE_OWNER if account.is_admin else ((row.role_code or "").strip().upper() if row else "")
    return Actor(account, role if role in ROLE_LABELS else ROLE_MANAGER)


def _to_rfone_login():
    base = _cfg.rfone_web_base_url()
    if base is None:
        abort(401)
    next_path = request.script_root + (request.full_path.rstrip("?") if request.method in ("GET", "HEAD") else "/")
    return redirect(f"{base}/login?{urlencode({'next': next_path})}")


def access_required(view):
    """RF-One login + SELECTION Domain, checked on every internal request."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        with _cfg.SessionFactory() as db:
            account = current_account(db)
            if account is None:
                return _to_rfone_login()
            actor = actor_for(db, account)
            if actor is None:
                abort(403)
            return view(db, actor, *args, **kwargs)
    return wrapper


@bp.before_request
def _csrf():
    if request.method == "POST":
        sent = request.form.get("csrf_token", "")
        if not sent or not secrets.compare_digest(sent, flask_session.get(shared_session.SESSION_CSRF_KEY, "")):
            flash("Sessione scaduta: il modulo non è stato salvato, riprova.")
            return redirect(request.referrer or url_for(".dashboard"))
    return None


@bp.after_request
def _no_index(response):
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@bp.context_processor
def _globals():
    return {"csrf_token": lambda: shared_session.csrf_token(flask_session), "ai_policy": ai_adapter.POLICY,
            "GROUP_LABELS": ps.GROUP_LABELS, "DECISION_LABELS": ps.DECISION_LABELS, "ROLE_LABEL": ROLE_LABEL,
            "STATUS_LABELS": engine.STATUS_LABELS, "CRITICALITY_LABELS": engine.CRITICALITY_LABELS,
            "POSITION_STATUS_LABELS": ps.POSITION_STATUS_LABELS, "SOURCE_LABELS": ps.SOURCE_LABELS,
            "KIND_LABELS": ps.KIND_LABELS, "MESSAGE_KINDS": ps.MESSAGE_KINDS,
            "APPLICATION_STATUS_LABELS": ps.APPLICATION_STATUS_LABELS, "NOT_SELECTED_REASONS": ps.NOT_SELECTED_REASONS}


@bp.app_template_filter("local")
def _local(value, tz=None, fmt=display_format.DEFAULT_FORMAT):
    return display_format.local_datetime(value, tz or DEFAULT_TIMEZONE, fmt)


@bp.app_template_filter("anchor")
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


def external_url(endpoint: str, **values) -> str:
    """An absolute link to give to a candidate: RF-One's official address
    when one is configured (`RFONE_PUBLIC_BASE_URL`), else this request's."""
    base = public_entry.public_base_url()
    if base:
        return base + url_for(endpoint, **values)
    return url_for(endpoint, _external=True, **values)


def _to_utc(local_value: str, tz: str) -> datetime | None:
    try:
        naive = datetime.fromisoformat(local_value)
    except (TypeError, ValueError):
        return None
    return naive.replace(tzinfo=ZoneInfo(tz)).astimezone(UTC).replace(tzinfo=None)


def _safe_back(value: str | None, default: str) -> str:
    return value if value and value.startswith("/") and not value.startswith("//") else default


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
    organization = organization_adapter.get_context(db, location)
    profile_text = _company_profile(db).text.strip()
    facts = list(organization["facts"])
    if profile_text:
        facts.append("Profilo aziendale (scritto dal proprietario in Selection): " + profile_text)
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

@bp.route("/")
@access_required
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
    return render_template("workspace/dashboard.html", actor=actor, rows=rows, upcoming=upcoming, company=company)


@bp.route("/profilo-aziendale", methods=["POST"])
@access_required
def company_profile(db, actor):
    if not actor.is_owner:
        abort(403)
    profile = _company_profile(db)
    profile.text = (request.form.get("text") or "").strip()
    profile.updated_by_name, profile.updated_at = actor.name, ps.utcnow()
    db.commit()
    flash("Profilo aziendale salvato.")
    return redirect(url_for(".dashboard"))


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


@bp.route("/posizioni/nuova", methods=["GET", "POST"])
@access_required
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
            return render_template("workspace/position_new.html", actor=actor, roles=ROLE_CHOICES, managers=managers,
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
        return redirect(url_for(".position_detail", position_id=position.id, tab="posizione"))
    return render_template("workspace/position_new.html", actor=actor, roles=ROLE_CHOICES, managers=managers, form={},
                           company=company, default_tz=DEFAULT_TIMEZONE, full_roles=FULL_ANALYSIS_ROLES)


@bp.route("/posizioni/<int:position_id>")
@access_required
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
        "workspace/position.html", actor=actor, position=position, tab=tab, cards=cards, columns=columns, pending=pending,
        decided=decided, manager=_manager_name(db, position.manager_account_id),
        requirements=engine.active_requirements(db, position), drafts=drafts,
        templates=req_svc.list_templates(db), events=events, channels=CHANNELS, unapproved=unapproved,
        can_edit=actor.can_edit(position), categories=ai_adapter.CATEGORY_LABELS_IT,
        trainability=engine.TRAINABILITY_LABELS, full_analysis=position.role_code in FULL_ANALYSIS_ROLES,
        public_url=external_url("careers.job_page", token=position.public_token), standard_pool=standard_pool,
        days=days, offers=offers, names=names, now=ps.utcnow(),
        hired=len(decided[ps.D_HIRED]))


def _position_redirect(position, tab="posizione"):
    return redirect(url_for(".position_detail", position_id=position.id, tab=tab))


@bp.route("/posizioni/<int:position_id>/ai-bozza", methods=["POST"])
@access_required
def position_ai_draft(db, actor, position_id):
    position = _position(db, actor, position_id, edit=True)
    _run_position_draft(db, actor, position, request.form.get("extra", ""))
    return _position_redirect(position)


@bp.route("/posizioni/<int:position_id>/bozza/<int:draft_id>", methods=["POST"])
@access_required
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


@bp.route("/posizioni/<int:position_id>/dettagli", methods=["POST"])
@access_required
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


@bp.route("/posizioni/<int:position_id>/requisiti/aggiungi", methods=["POST"])
@access_required
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


@bp.route("/posizioni/<int:position_id>/requisiti/<int:requirement_id>", methods=["POST"])
@access_required
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


@bp.route("/posizioni/<int:position_id>/requisiti/modello", methods=["POST"])
@access_required
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


@bp.route("/posizioni/<int:position_id>/approva", methods=["POST"])
@access_required
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


@bp.route("/posizioni/<int:position_id>/stato", methods=["POST"])
@access_required
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

@bp.route("/posizioni/<int:position_id>/cv", methods=["POST"])
@access_required
def cv_upload(db, actor, position_id):
    position = _position(db, actor, position_id, edit=True)
    files = [f for f in request.files.getlist("cv") if f and f.filename]
    if not files:
        flash("Selezionare almeno un file.")
    for f in files:
        r = engine.import_cv(db, documents=_cfg.documents, restaurant_id=_restaurant_id(db), position=position,
                             file_storage=f, channel=ps.MANUAL_UPLOAD, actor_id=actor.id, actor_name=actor.name)
        label = {"OK": "importato", "DUPLICATE": "già presente", "FAILED": "non importato"}[r["status"]]
        flash(f"{r['filename']}: {label}" + (f" — {r['message']}" if r.get("message") else ""))
    if files and not position.approved_snapshot_id:
        flash("I CV saranno valutati appena la posizione sarà approvata.")
    return _position_redirect(position, "valutazione" if position.approved_snapshot_id else "candidature")


@bp.route("/posizioni/<int:position_id>/rianalizza", methods=["POST"])
@access_required
def reanalyze(db, actor, position_id):
    position = _position(db, actor, position_id, edit=True)
    for pc in db.scalars(select(ps.PositionCandidate).where(ps.PositionCandidate.position_id == position.id)).all():
        engine.analyze(db, position, pc, actor_id=actor.id, actor_name=actor.name)
    flash("Valutazione aggiornata con la versione approvata.")
    return _position_redirect(position, "valutazione")


# ---------------------------------------------------------------------------
# 3. EVALUATE
# ---------------------------------------------------------------------------

@bp.route("/posizioni/<int:position_id>/candidati/<int:pc_id>")
@access_required
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
        "workspace/candidate.html", actor=actor, position=position, pc=pc, candidate=candidate, profile=profile, view=view,
        rules=proposals.get(ps.SOURCE_RULES), ai=ai, ai_by_id={i["id"]: i for i in ai.payload["items"]} if ai else {},
        lead=engine.leading_proposal(proposals), decision=engine.current_decision(db, pc.id), decisions=decisions,
        duplicates=engine.duplicate_notes(db, pc), channel=CHANNEL_LABELS.get(pc.channel, pc.channel),
        can_edit=actor.can_edit(position), full_analysis=view.role_config is not None,
        application=engine.candidate_application(db, pc.id), answers=engine.answers(db, pc.id),
        appointments=_appointments(db, [pc.id], include_cancelled=True), offers=offers, messages=messages,
        slot_url=lambda o: external_url("careers.slot_page", token=o.token), now=ps.utcnow())


def _raw_resume(db, pc) -> m.RawResume | None:
    candidate = persistence.get_candidate(db, pc.candidate_id)
    return db.get(m.RawResume, candidate.raw_resume_id) if candidate and candidate.raw_resume_id else None


@bp.route("/posizioni/<int:position_id>/candidati/<int:pc_id>/cv-originale")
@access_required
def candidate_original(db, actor, position_id, pc_id):
    raw = _raw_resume(db, _pc(db, _position(db, actor, position_id), pc_id))
    data = _cfg.documents.read(raw.storage_path) if raw else None
    if data is None:
        abort(404)
    name = raw.original_filename or "cv"
    return send_file(io.BytesIO(data), mimetype=mimetypes.guess_type(name)[0] or "application/octet-stream",
                     download_name=name, as_attachment=False)


@bp.route("/posizioni/<int:position_id>/candidati/<int:pc_id>/testo")
@access_required
def candidate_text(db, actor, position_id, pc_id):
    position = _position(db, actor, position_id)
    pc = _pc(db, position, pc_id)
    raw = _raw_resume(db, pc)
    return render_template("workspace/cv_text.html", actor=actor, position=position, pc=pc,
                           candidate=persistence.get_candidate(db, pc.candidate_id),
                           text=raw.raw_text if raw else "", highlight=request.args.get("q", ""))


@bp.route("/posizioni/<int:position_id>/confronto")
@access_required
def compare(db, actor, position_id):
    position = _position(db, actor, position_id)
    pcs = [_pc(db, position, int(x)) for x in request.args.getlist("pc_id") if x.isdigit()]
    if len(pcs) < 2:
        flash("Seleziona almeno due candidati da confrontare.")
        return _position_redirect(position, "valutazione")
    return render_template("workspace/compare.html", actor=actor, position=position, data=engine.comparison(db, position, pcs[:6]))


@bp.route("/posizioni/<int:position_id>/decisioni", methods=["POST"])
@access_required
def record_decision(db, actor, position_id):
    position = _position(db, actor, position_id, edit=True)
    decision = request.form.get("decision")
    reason = request.form.get("reason") or None
    note = (request.form.get("note") or "").strip() or None
    pc_ids = [int(x) for x in request.form.getlist("pc_id") if x.isdigit()]
    quick = request.form.get("quick", "")  # "<pc_id>:<decision>" from a card button
    if ":" in quick and quick.split(":", 1)[0].isdigit():
        pc_ids, decision = [int(quick.split(":", 1)[0])], quick.split(":", 1)[1]
    back = _safe_back(request.form.get("back"), url_for(".position_detail", position_id=position.id))
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


@bp.route("/posizioni/<int:position_id>/candidati/<int:pc_id>/colloquio", methods=["POST"])
@access_required
def interview_book(db, actor, position_id, pc_id):
    position = _position(db, actor, position_id, edit=True)
    pc = _pc(db, position, pc_id)
    back = url_for(".candidate_detail", position_id=position.id, pc_id=pc.id) + "#colloquio"
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
        link = external_url("careers.slot_page", token=offer.token)
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


@bp.route("/posizioni/<int:position_id>/colloqui/<int:appointment_id>/annulla", methods=["POST"])
@access_required
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
    return redirect(_safe_back(request.form.get("back"), url_for(".position_detail", position_id=position.id, tab="colloqui")))


# ---------------------------------------------------------------------------
# 5. DECIDE — messages (always approved by the manager, never sent automatically)
# ---------------------------------------------------------------------------

@bp.route("/posizioni/<int:position_id>/candidati/<int:pc_id>/messaggi", methods=["POST"])
@access_required
def message_new(db, actor, position_id, pc_id):
    position = _position(db, actor, position_id, edit=True)
    pc = _pc(db, position, pc_id)
    kind = request.form.get("kind")
    if kind in ps.MESSAGE_KINDS and kind != "SLOTS":
        _draft_message(db, actor, position, pc, kind)
        db.commit()
    return redirect(url_for(".candidate_detail", position_id=position.id, pc_id=pc.id) + "#comunicazioni")


@bp.route("/posizioni/<int:position_id>/messaggi/<int:message_id>", methods=["POST"])
@access_required
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
    return redirect(url_for(".candidate_detail", position_id=position.id, pc_id=pc.id) + "#comunicazioni")


@bp.errorhandler(403)
def _forbidden(_):
    return render_template("workspace/message.html", title="Accesso non consentito",
                           text="Il tuo ruolo in Selection non permette questa operazione."), 403


@bp.errorhandler(404)
def _not_found(_):
    return render_template("workspace/message.html", title="Non trovato", text="La pagina richiesta non esiste."), 404
