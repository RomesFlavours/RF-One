"""Selection — public candidate pages (SELECTION_AI_INTEGRATION_001 §4–5).

A position's public page shows the approved job ad. Applying requires an
external candidate identity (`candidate_identity_service`): register with
full name, email and password, receive a code by email or by text message
(the candidate chooses), confirm it on the same page — or sign in again with
email and password. A verified candidate
then uploads the résumé and answers the short English interview (typing or
voice), which is saved after every answer and can be resumed after signing
in again. The application is tied to both the candidate identity and the
position; the same identity applies to any number of positions.

Candidates never reach an internal function: these routes only read and
write the candidate's own application, and the internal blueprint requires
an RF-One account on every request.

Email goes through authenticated SMTP (`technical/smtp_email.py`) — the
company mailbox on Aruba, configured by the `RFONE_SMTP_*` variables — from
`RFONE_EMAIL_FROM_ADDRESS` (default: the SMTP user name, as Aruba requires the
sender to be the authenticated mailbox). Amazon SES is no longer used here. Text messages go through `technical/sms_text.py` (AWS End
User Messaging SMS) from the registered number in
`RFONE_SMS_ORIGINATION_IDENTITY`; without one the Text Message choice is shown
as not available. Whenever a code cannot be delivered the candidate sees an
explicit error and verification cannot be bypassed.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask import session as flask_session
from sqlalchemy import select

from rfone_data_store import rfone_web_session as shared_session
from rfone_data_store.selection import candidate_identity_service as identity
from rfone_data_store.selection import requirements_service as req_svc
from rfone_data_store.selection import workspace_models as ps
from rfone_data_store.selection.parsing.ai_client import AIProviderUnavailable
from rfone_data_store.technical import smtp_email, sms_text

from . import ai_adapter, engine, position_settings, sp_queue
from .routes import (
    CLIENT_NAME, ROLE_LABEL, ROLE_LABEL_EN, _book, _cfg, _conflicts, _raw_resume, _restaurant_id, _local, external_url,
)

bp = Blueprint("careers", __name__)
log = logging.getLogger("rfone.selection.careers")

CANDIDATE_SESSION_KEY = "selection_candidate_account_id"
CANDIDATE_ACTOR = "Candidate (public page)"


class DeliveryNotAvailable(Exception):
    """The code could not be handed to the email or text-message service."""


EmailNotAvailable = DeliveryNotAvailable


def sms_available() -> bool:
    return bool((os.environ.get("RFONE_SMS_ORIGINATION_IDENTITY") or "").strip())


def deliver_sms_code(*, to_number: str, code: str) -> None:
    """Sends the verification code by text message. Replaced in tests; never logs the code."""
    try:
        sms_text.send_text(
            to_number=to_number, origination_identity=(os.environ.get("RFONE_SMS_ORIGINATION_IDENTITY") or "").strip(),
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
            body=f"{CLIENT_NAME}: your verification code is {code}. It expires in 10 minutes. Reply STOP to opt out.")
    except sms_text.SmsSendError as exc:
        raise DeliveryNotAvailable(str(exc)) from exc


def deliver_code(*, to_address: str, full_name: str, code: str) -> None:
    """Sends the verification code by email, one message per recipient.
    Replaced in tests; never logs the code, the address or the password."""
    try:
        settings = smtp_email.settings_from_environment()
    except smtp_email.SmtpSendError as exc:
        raise EmailNotAvailable(str(exc)) from None
    if settings is None:
        raise EmailNotAvailable("not configured")
    sender = (os.environ.get("RFONE_EMAIL_FROM_ADDRESS") or "").strip() or settings.username
    first = (full_name or "").split()[0] if (full_name or "").split() else "there"
    try:
        smtp_email.send_email(
            settings=settings, to_address=to_address, from_address=sender,
            subject=f"Your {CLIENT_NAME} verification code",
            text_body=(f"Hi {first},\n\nYour verification code is: {code}\n\n"
                       f"It expires in 10 minutes. If you did not request it, you can ignore this email.\n\n"
                       f"{CLIENT_NAME}"))
    except smtp_email.SmtpSendError as exc:
        raise EmailNotAvailable(str(exc)) from None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client_ip() -> str | None:
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[0].strip() if forwarded else request.remote_addr


def _csrf_ok() -> bool:
    sent = request.form.get("csrf_token", "")
    return bool(sent) and secrets.compare_digest(sent, flask_session.get(shared_session.SESSION_CSRF_KEY, ""))


@bp.before_request
def _csrf():
    if request.endpoint in ('careers.aruba_relay', 'careers.mail_claim', 'careers.mail_ack'):
        # Server-to-server only: the handler verifies a timestamped HMAC.
        return None
    if request.method == "POST" and not _csrf_ok():
        if request.path.endswith(("/account/code", "/account/confirm", "/account/cancel")):
            return jsonify(ok=False, message="Your session expired. Please reload the page and try again."), 400
        flash("Your session expired. Please try again.")
        return redirect(request.full_path.rstrip("?"))
    return None


@bp.after_request
def _no_index(response):
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@bp.context_processor
def _globals():
    return {"csrf_token": lambda: shared_session.csrf_token(flask_session), "client": CLIENT_NAME}


def _candidate(db) -> ps.CandidateAccount | None:
    account = identity.get_account(db, flask_session.get(CANDIDATE_SESSION_KEY))
    if not identity.is_verified(account):
        flask_session.pop(CANDIDATE_SESSION_KEY, None)
        return None
    return account


def _sign_in(account: ps.CandidateAccount) -> None:
    flask_session[CANDIDATE_SESSION_KEY] = account.id


def _public_position(db, token) -> ps.Position:
    position = db.scalars(select(ps.Position).where(ps.Position.public_token == token)).first()
    if position is None:
        abort(404)
    return position


def _own_position_candidate(db, position: ps.Position, account: ps.CandidateAccount) -> ps.PositionCandidate | None:
    return db.scalars(select(ps.PositionCandidate).where(
        ps.PositionCandidate.position_id == position.id,
        ps.PositionCandidate.candidate_account_id == account.id).order_by(ps.PositionCandidate.id)).first()


def _start_interview(db, position, pc) -> ps.CandidateApplication:
    questions = [{"text": q, "source": "STANDARD"} for q in position.approved_questions]
    position_settings.bind(position)
    if ai_adapter.current_policy().allows("cv_questions"):
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
                         actor_id=None, actor_name="System",
                         detail=f"AI résumé-based questions unavailable ({exc}): approved standard questions used")
    application = ps.CandidateApplication(position_candidate_id=pc.id, questions_json=json.dumps(questions))
    db.add(application)
    db.commit()
    return application


# ---------------------------------------------------------------------------
# Open positions list: one permanent page, shown inside the website's Careers
# page (romesflavours.com/careers). It lists every OPEN position, so opening
# or closing a position in Selection updates it with no other step.
# ---------------------------------------------------------------------------

# Sites allowed to show this list inside their own page (the website and the
# Wix editor/preview hosts). Nothing else may frame it.
OPENINGS_FRAME_ANCESTORS = ("'self' https://www.romesflavours.com https://romesflavours.com "
                            "https://*.filesusr.com https://*.wixsite.com https://editor.wix.com "
                            "https://*.editorx.io")


def _ad_excerpt(text: str, limit: int = 600) -> str:
    """The job ad for the Careers list. A normal ad (the Role defaults are 300 to 400 characters) shows in
    full; only a much longer one is shortened, to whole sentences up to `limit` characters, so a card
    never stops mid-sentence. The full ad is always on the job page. Only a first sentence longer than
    the limit is cut at a word, with an ellipsis."""
    plain = " ".join((text or "").split())
    if len(plain) <= limit:
        return plain
    excerpt = ""
    for sentence in re.split(r"(?<=[.!?])\s+", plain):
        candidate = f"{excerpt} {sentence}".strip()
        if len(candidate) > limit:
            break
        excerpt = candidate
    if excerpt:
        return excerpt
    return plain[:limit].rsplit(" ", 1)[0].rstrip(",;:.") + "…"


# The website's own addresses: only their pages may read the job feed from a browser.
OPENINGS_FEED_ORIGINS = ("https://www.romesflavours.com", "https://romesflavours.com")


def _open_jobs(*, absolute: bool) -> list[dict]:
    """The OPEN Jobs as shown to the public: title, location, the job ad (whole, or shortened at a
    sentence only when very long) and the link to the Job's own application page."""
    with _cfg.SessionFactory() as db:
        positions = db.scalars(select(ps.Position).where(ps.Position.status == ps.OPEN)
                               .order_by(ps.Position.location_label, ps.Position.title, ps.Position.id)).all()
        return [{"title": p.title, "location": p.location_label,
                 "role": ROLE_LABEL_EN.get(p.role_code, p.role_code),
                 "excerpt": _ad_excerpt(p.approved_job_ad_en or p.description),
                 "url": (external_url(".job_page", token=p.public_token) if absolute
                         else url_for(".job_page", token=p.public_token))} for p in positions]


@bp.route("/careers.json")
def openings_feed():
    """Job feed for the website's Careers page (SELECTION_CAREERS_FEED_001): the website builds its own
    cards from it, so its list grows with the number of open Jobs. The same public information as the
    /careers list, nothing internal; not cached, not indexed."""
    response = jsonify({"jobs": [{k: j[k] for k in ("title", "location", "excerpt", "url")}
                                 for j in _open_jobs(absolute=True)]})
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    origin = request.headers.get("Origin", "")
    if origin in OPENINGS_FEED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    return response


@bp.route("/careers")
def openings():
    jobs = _open_jobs(absolute=False)
    response = current_app.make_response(render_template("careers/openings.html", jobs=jobs))
    response.headers["Content-Security-Policy"] = f"frame-ancestors {OPENINGS_FRAME_ANCESTORS}"
    response.headers["Cache-Control"] = "no-store"
    return response


# ---------------------------------------------------------------------------
# Position page: registration / sign-in, then the application
# ---------------------------------------------------------------------------

@bp.route("/jobs/<token>", methods=["GET", "POST"])
def job_page(token):
    with _cfg.SessionFactory() as db:
        position = _public_position(db, token)
        open_ = position.status == ps.OPEN
        candidate = _candidate(db)
        if candidate is None and os.environ.get('RFONE_SELECTION_ARUBA_KEY') and request.method == 'GET':
            return redirect(url_for('careers.aruba_start', job=token))
        existing = _own_position_candidate(db, position, candidate) if candidate else None
        if request.method == "POST" and open_:
            if candidate is None:
                flash("Please sign in or create your account to apply.")
                return redirect(url_for(".job_page", token=token))
            if existing is not None:
                return redirect(url_for(".candidate_interview", token=_application_for(db, position, existing).token))
            file = request.files.get("cv")
            if not file or not file.filename or not request.form.get("consent"):
                flash("Please attach your résumé and accept the notice.")
            else:
                result = engine.import_cv(
                    db, documents=_cfg.documents, restaurant_id=_restaurant_id(db), position=position,
                    file_storage=file, channel=ps.PUBLIC_LINK, actor_id=None, actor_name=CANDIDATE_ACTOR,
                    declared={"name": candidate.full_name, "email": candidate.email,
                              "phone": (request.form.get("phone") or "").strip() or None},
                    candidate_account_id=candidate.id,
                    # CV Selection SP positions: no analysis while the application is in progress (see submit).
                    analyze_after=not sp_queue.has_profile(position))
                if result["status"] == "DUPLICATE":
                    return render_template("careers/message.html", position=position, candidate=candidate,
                                           title="We already have this résumé",
                                           text="This résumé was already received for this position. Thank you!")
                if result["status"] == "OK":
                    application = _start_interview(db, position, result["pc"])
                    return redirect(url_for(".candidate_interview", token=application.token))
                flash("We could not read this file. Please upload a PDF, DOCX or TXT résumé.")
        application = _application_for(db, position, existing) if existing else None
        snapshot = req_svc.get_snapshot(db, position.approved_snapshot_id) if position.approved_snapshot_id else None
        requirements = [i for i in sorted(snapshot.items, key=lambda i: i.display_order) if i.was_active] if snapshot else []
        return render_template("careers/job_page.html", position=position, open_=open_, requirements=requirements,
                               role_label=ROLE_LABEL_EN.get(position.role_code, ROLE_LABEL[position.role_code]),
                               candidate=candidate, application=application,
                               min_password=identity.MIN_PASSWORD_LENGTH, sms_available=sms_available())


def _application_for(db, position, pc) -> ps.CandidateApplication:
    application = engine.candidate_application(db, pc.id)
    return application if application is not None else _start_interview(db, position, pc)


@bp.route("/jobs/<token>/account/code", methods=["POST"])
def account_code(token):
    """Registration step 1 (JSON, no page change): create or refresh the
    unverified identity and send a code by the channel the candidate chose
    (EMAIL or SMS)."""
    channel = (request.form.get("channel") or ps.CHANNEL_EMAIL).upper()
    if channel == ps.CHANNEL_SMS and not sms_available():
        return jsonify(ok=False, message="Text messages are not available yet. Please choose Email."), 503
    with _cfg.SessionFactory() as db:
        _public_position(db, token)
        try:
            account, code, target = identity.start_registration(
                db, full_name=request.form.get("full_name", ""), email=request.form.get("email", ""),
                password=request.form.get("password", ""), secret_key=current_app.secret_key,
                request_ip=_client_ip(), channel=channel, phone=request.form.get("phone"))
        except identity.CandidateIdentityError as exc:
            db.rollback()
            return jsonify(ok=False, message=str(exc), already_registered=isinstance(exc, identity.AlreadyRegistered))
        db.commit()
        try:
            if channel == ps.CHANNEL_SMS:
                deliver_sms_code(to_number=target, code=code)
            else:
                deliver_code(to_address=target, full_name=account.full_name, code=code)
        except DeliveryNotAvailable as exc:
            log.warning("Selection candidate verification %s not sent (%s)", channel, exc)
            identity.withdraw_code(db, account)
            db.commit()
            if channel == ps.CHANNEL_SMS:
                message = "We could not send the text message. Please check the number, or choose Email."
            elif str(exc) == "not configured":
                message = "Email delivery is not configured yet, so we cannot send verification codes. Please try again later."
            else:
                message = "We could not send the verification email. Please check the address or try again later."
            return jsonify(ok=False, message=message), 503
        where = identity.masked_phone(target) if channel == ps.CHANNEL_SMS else target
        return jsonify(ok=True, email=account.email,
                       message=f"We sent a 6-digit code to {where}. It expires in 10 minutes.")


@bp.route("/jobs/<token>/account/confirm", methods=["POST"])
def account_confirm(token):
    """Registration step 2 (JSON): verify the code; on success the candidate is signed in."""
    with _cfg.SessionFactory() as db:
        _public_position(db, token)
        try:
            account = identity.confirm_registration(db, email=request.form.get("email", ""),
                                                    code=request.form.get("code", ""),
                                                    secret_key=current_app.secret_key)
        except identity.CandidateIdentityError as exc:
            db.commit()  # a wrong attempt is counted
            return jsonify(ok=False, message=str(exc))
        db.commit()
        _sign_in(account)
        return jsonify(ok=True, redirect=url_for(".job_page", token=token))


@bp.route("/jobs/<token>/account/cancel", methods=["POST"])
def account_cancel(token):
    with _cfg.SessionFactory() as db:
        _public_position(db, token)
        account = identity.get_account_by_email(db, request.form.get("email", ""))
        if account is not None and not identity.is_verified(account):
            identity.withdraw_code(db, account)
            db.commit()
        return jsonify(ok=True)


@bp.route("/jobs/<token>/sign-in", methods=["POST"])
def sign_in(token):
    with _cfg.SessionFactory() as db:
        _public_position(db, token)
        try:
            account = identity.authenticate(db, email=request.form.get("email", ""),
                                            password=request.form.get("password", ""))
        except identity.CandidateIdentityError as exc:
            db.commit()  # failed attempts are counted
            flash(str(exc))
            return redirect(url_for(".job_page", token=token) + "#apply")
        db.commit()
        _sign_in(account)
        return redirect(url_for(".job_page", token=token) + "#apply")


@bp.route("/jobs/<token>/sign-out", methods=["POST"])
def sign_out(token):
    flask_session.pop(CANDIDATE_SESSION_KEY, None)
    return redirect(url_for(".job_page", token=token))


# ---------------------------------------------------------------------------
# Online interview (the signed-in candidate's own application only)
# ---------------------------------------------------------------------------

# Not "/apply/<token>": that address belongs to the historical Selection job-posting intake.
@bp.route("/my-application/<token>", methods=["GET", "POST"])
def candidate_interview(token):
    with _cfg.SessionFactory() as db:
        application = db.scalars(select(ps.CandidateApplication).where(ps.CandidateApplication.token == token)).first()
        if application is None:
            abort(404)
        pc = db.get(ps.PositionCandidate, application.position_candidate_id)
        position = db.get(ps.Position, pc.position_id)
        candidate = _candidate(db)
        if candidate is None:
            flash("Please sign in to continue your application.")
            return redirect(url_for(".job_page", token=position.public_token) + "#apply")
        if pc.candidate_account_id != candidate.id:
            abort(404)
        questions = application.questions
        given = {a.question_index: a for a in db.scalars(select(ps.Answer).where(
            ps.Answer.candidate_application_id == application.id)).all()}
        if request.method == "POST" and application.status != ps.A_SUBMITTED:
            if request.form.get("action") == "submit":
                application.status, application.submitted_at = ps.A_SUBMITTED, ps.utcnow()
                ps.log_event(db, position_id=position.id, position_candidate_id=pc.id, kind="APPLICATION",
                             actor_id=None, actor_name=CANDIDATE_ACTOR,
                             detail=f"Application completed ({len(given)} answers out of {len(questions)})")
                db.commit()
                if position.approved_snapshot_id:
                    engine.analyze(db, position, pc, actor_id=None, actor_name="System")
                sp_queue.on_application_completed(db, position, pc)  # CV Selection SP: queued once, never raises
                return redirect(url_for(".candidate_interview", token=token))
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
                return render_template("careers/message.html", position=position, candidate=candidate, title="Saved",
                                       text="Your answers are saved. To continue, sign in again on the position page:",
                                       link=external_url("careers.job_page", token=position.public_token))
            edit = request.form.get("edit", type=int)
            return redirect(url_for(".candidate_interview", token=token, q=edit) if edit is not None
                            else url_for(".candidate_interview", token=token))
        current = request.args.get("q", type=int)
        if current is None or not (0 <= current < len(questions)):
            current = next((i for i in range(len(questions)) if i not in given), None)
        return render_template("careers/candidate_interview.html", position=position, application=application,
                               questions=questions, given=given, current=current, candidate=candidate)


# ---------------------------------------------------------------------------
# Interview time choice (link sent by the manager in an approved message)
# ---------------------------------------------------------------------------

@bp.route("/interview/<token>", methods=["GET", "POST"])
def slot_page(token):
    with _cfg.SessionFactory() as db:
        offer = db.scalars(select(ps.SlotOffer).where(ps.SlotOffer.token == token).with_for_update()).first()
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
                               place=offer.place, note="Chosen by candidate using time-selection link", booked_by="CANDIDATE",
                               actor_id=None, actor_name="Candidate (time-selection link)")
                offer.status, offer.appointment_id = "CHOSEN", chosen.id
                from . import mail_delivery
                try:
                    mail_delivery.enqueue(db, pc=pc, source_key=f'appointment:{chosen.id}:confirmation',
                        subject=f"Rome's Flavours — interview confirmation",
                        body=f"Your interview for {position.title} is confirmed for "
                             f"{_local(chosen.starts_at, position.timezone, '%A, %B %d at %I:%M %p')} "
                             f"({position.timezone}).\n" + (f"Location / phone: {chosen.place}\n" if chosen.place else '') +
                             "\nPlease reply to this email if you need to contact us.\n\nRome's Flavours")
                except ValueError:
                    flash('Your appointment is booked, but its email confirmation could not be queued. Please contact the manager.')
                db.commit()
        return render_template("careers/slot_page.html", position=position, offer=offer, available=available,
                               chosen=chosen)


@bp.errorhandler(404)
def _not_found(_):
    return render_template("careers/message.html", position=None, candidate=None, title="Page not found",
                           text="This page does not exist or is no longer available."), 404
