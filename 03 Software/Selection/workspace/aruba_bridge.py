"""RMAED candidate verification relay; candidate sessions stay on Selection.

Only authenticated server-to-server calls can issue codes or tickets. The
browser visits Selection first to bind the eventual ticket to its session.
No RF-One staff account or staff permission is created by this module.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import timedelta
from urllib.parse import urlencode

from flask import abort, current_app, jsonify, redirect, render_template_string, request, url_for
from flask import session as browser_session
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import DateTime, ForeignKey, Integer, String, select, update
from sqlalchemy.orm import Mapped, mapped_column

from rfone_data_store.models import Base
from rfone_data_store.selection import candidate_identity_service as identity
from rfone_data_store.selection import workspace_models as ws
from rfone_data_store import rfone_web_session as shared_session
from . import careers
from .routes import _cfg

VERSION = 'rmaed-selection-bridge-3'
RETURN_URL = 'https://www.rmaed.it/index.php'


class CandidateBridgeTicket(Base):
    __tablename__ = 'selection_candidate_bridge_tickets'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    candidate_account_id: Mapped[int] = mapped_column(ForeignKey('selection_candidate_accounts.id'), nullable=False)
    browser_nonce: Mapped[str] = mapped_column(String(64), nullable=False)
    position_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[object] = mapped_column(DateTime, nullable=False)
    consumed_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)


def serializer():
    return URLSafeTimedSerializer(current_app.secret_key, salt='selection-aruba-browser-v1')


def state_payload(state):
    try:
        value = serializer().loads(state, max_age=1800)
        if not isinstance(value, dict) or not isinstance(value.get('nonce'), str) or len(value['nonce']) != 43:
            abort(400)
        return value
    except (BadSignature, SignatureExpired):
        abort(400, 'Your verification session expired. Please start again.')


def relay_payload():
    key = os.environ.get('RFONE_SELECTION_ARUBA_KEY', '')
    if len(key) < 48:
        abort(503)
    stamp = request.headers.get('X-RFOne-Time', '')
    body = request.get_data(cache=True)
    try:
        valid_time = abs(time.time() - int(stamp)) <= 60
    except ValueError:
        valid_time = False
    expected = hmac.new(key.encode(), stamp.encode() + b'\n' + body, hashlib.sha256).hexdigest()
    if not valid_time or len(body) > 16000 or not hmac.compare_digest(expected, request.headers.get('X-RFOne-Signature', '')):
        abort(403)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400)
    return data


def ticket_for(db, account, state):
    raw = secrets.token_urlsafe(32)
    db.add(CandidateBridgeTicket(token_hash=hashlib.sha256(raw.encode()).hexdigest(),
           candidate_account_id=account.id, browser_nonce=state['nonce'], position_token=state.get('job'),
           expires_at=ws.utcnow() + timedelta(seconds=120)))
    db.commit()
    official = os.environ.get('RFONE_PUBLIC_BASE_URL', request.host_url.rstrip('/')).rstrip('/')
    return official + url_for('careers.aruba_finish', ticket=raw)


def install():
    bp = careers.bp

    @bp.route('/candidate/bridge/health')
    def aruba_health():
        return jsonify(version=VERSION, enabled=len(os.environ.get('RFONE_SELECTION_ARUBA_KEY', '')) >= 48)

    @bp.route('/candidate/bridge/start')
    def aruba_start():
        nonce = secrets.token_urlsafe(32)
        browser_session['selection_aruba_nonce'] = nonce
        job = request.args.get('job')
        if job:
            with _cfg.SessionFactory() as db:
                careers._public_position(db, job)
        state = {'nonce': nonce, 'job': job}
        return redirect(RETURN_URL + '?' + urlencode({'state': serializer().dumps(state)}), code=302)

    @bp.route('/candidate/bridge/relay', methods=['POST'])
    def aruba_relay():
        data = relay_payload()
        action = data.get('action')
        state = state_payload(data.get('state', ''))
        with _cfg.SessionFactory() as db:
            try:
                if action == 'code':
                    account, code, target = identity.request_email_access_code(db,
                        full_name=str(data.get('full_name', ''))[:255], email=str(data.get('email', ''))[:320],
                        secret_key=current_app.secret_key, request_ip=str(data.get('ip', ''))[:64])
                    db.commit()
                    # This response goes only to the authenticated PHP server.
                    return jsonify(ok=True, delivery_code=code, email=target)
                if action == 'withdraw':
                    account = identity.get_account_by_email(db, str(data.get('email', '')))
                    if account is not None:
                        identity.withdraw_code(db, account)
                    db.commit()
                    return jsonify(ok=True)
                if action == 'confirm':
                    account = identity.confirm_registration(db, email=str(data.get('email', '')),
                        code=str(data.get('code', '')), secret_key=current_app.secret_key, allow_verified=True)
                else:
                    abort(400)
                return jsonify(ok=True, redirect=ticket_for(db, account, state))
            except identity.CandidateIdentityError as exc:
                # A failed code/login attempt must remain counted.
                if action == 'code':
                    db.rollback()
                else:
                    db.commit()
                return jsonify(ok=False, message=str(exc), already_registered=isinstance(exc, identity.AlreadyRegistered)), 400

    @bp.route('/candidate/bridge/finish', methods=['GET', 'POST'])
    def aruba_finish():
        raw = request.values.get('ticket', '')
        nonce = browser_session.get('selection_aruba_nonce', '')
        if len(raw) != 43 or not nonce:
            abort(400, 'Please start verification in the same browser.')
        with _cfg.SessionFactory() as db:
            row = db.scalars(select(CandidateBridgeTicket).where(
                CandidateBridgeTicket.token_hash == hashlib.sha256(raw.encode()).hexdigest(),
                CandidateBridgeTicket.browser_nonce == nonce,
                CandidateBridgeTicket.consumed_at.is_(None), CandidateBridgeTicket.expires_at > ws.utcnow())).first()
            if row is None:
                abort(400, 'This link has expired or has already been used. Please sign in again.')
            if request.method == 'GET':
                return render_template_string('''<!doctype html><html lang="en"><meta charset="utf-8">
                    <meta name="referrer" content="no-referrer"><title>Opening your application</title>
                    <form method="post"><input type="hidden" name="ticket" value="{{ticket}}">
                    <input type="hidden" name="csrf_token" value="{{csrf}}">
                    <button>Continue to my application</button></form>
                    <script>history.replaceState(null,'',location.pathname);document.forms[0].submit();</script></html>''',
                    ticket=raw, csrf=shared_session.csrf_token(browser_session))
            changed = db.execute(update(CandidateBridgeTicket).where(
                CandidateBridgeTicket.id == row.id, CandidateBridgeTicket.consumed_at.is_(None),
                CandidateBridgeTicket.expires_at > ws.utcnow()).values(consumed_at=ws.utcnow())).rowcount
            if changed != 1:
                db.rollback()
                abort(400)
            account = identity.get_account(db, row.candidate_account_id)
            if not identity.is_verified(account):
                abort(403)
            db.commit()
            careers._sign_in(account)
            browser_session.pop('selection_aruba_nonce', None)
            return redirect(url_for('careers.job_page', token=row.position_token) if row.position_token
                            else url_for('careers.candidate_home'), code=303)

    @bp.route('/candidate')
    def candidate_home():
        with _cfg.SessionFactory() as db:
            account = careers._candidate(db)
            if account is None:
                return redirect(url_for('careers.aruba_start'))
            positions = db.scalars(select(ws.Position).where(ws.Position.status == ws.OPEN).order_by(ws.Position.id)).all()
            return render_template_string('''{% extends "careers/base.html" %}{% block title %}Applications{% endblock %}
                {% block content %}<h1>Welcome, {{account.full_name}}</h1><p>Your email is verified.</p>
                {% for p in positions %}<p><a class="btn" href="{{url_for('careers.job_page',token=p.public_token)}}">{{p.title}}</a></p>
                {% else %}<p>There are no open positions at the moment. Please check back later.</p>{% endfor %}{% endblock %}''',
                account=account, positions=positions)

    @bp.after_request
    def bridge_response_headers(response):
        if request.path.startswith('/candidate'):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Referrer-Policy'] = 'no-referrer'
            response.headers['X-Content-Type-Options'] = 'nosniff'
        return response
