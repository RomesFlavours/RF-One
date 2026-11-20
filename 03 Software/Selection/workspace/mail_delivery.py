"""Selection owns approved messages and an outbox; Aruba only transports mail."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import timedelta

from flask import abort, jsonify
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, or_, select
from sqlalchemy.orm import Mapped, mapped_column

from rfone_data_store.models import Base
from rfone_data_store.selection import persistence, workspace_models as ws

STATUS_LABELS = {'QUEUED': 'Queued', 'LEASED': 'Preparing', 'SENDING': 'Sending',
                 'SENT': 'Accepted by mail server', 'FAILED': 'Delivery failed',
                 'UNKNOWN': 'Outcome uncertain: check before retrying'}
EMAIL = re.compile(r'^[^\s@<>\r\n]+@[^\s@<>\r\n]+\.[^\s@<>\r\n]+$')


class EmailOutbox(Base):
    __tablename__ = 'selection_workspace_email_outbox'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    position_candidate_id: Mapped[int] = mapped_column(ForeignKey('selection_workspace_position_candidates.id'), nullable=False)
    message_id: Mapped[int | None] = mapped_column(ForeignKey('selection_workspace_messages.id'), nullable=True, unique=True)
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    smtp_message_id: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default='QUEUED')
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[object] = mapped_column(DateTime, nullable=False, default=ws.utcnow)
    lease_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, nullable=False, default=ws.utcnow)
    sent_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)


def email_for(db, pc):
    account = db.get(ws.CandidateAccount, pc.candidate_account_id) if pc.candidate_account_id else None
    candidate = persistence.get_candidate(db, pc.candidate_id)
    value = account.email if account else (pc.declared_email or (candidate.email if candidate else '') or '')
    return value.strip().lower() if EMAIL.fullmatch(value.strip()) else None


def enqueue(db, *, pc, source_key, subject, body, message_id=None):
    existing = db.scalars(select(EmailOutbox).where(EmailOutbox.source_key == source_key)).first()
    if existing is not None:
        return existing
    email = email_for(db, pc)
    if not email:
        raise ValueError('The candidate does not have a valid email address.')
    if not body.strip() or len(body) > 16000 or '\r' in subject or '\n' in subject:
        raise ValueError('Check the message text (up to 16000 characters).')
    row = EmailOutbox(source_key=source_key, position_candidate_id=pc.id, message_id=message_id,
        recipient=email, subject=subject[:200], body=body.strip(),
        smtp_message_id=secrets.token_hex(20) + '@rmaed.it')
    db.add(row)
    db.flush()
    return row


def enqueue_message(db, position, pc, message):
    if message.status != 'APPROVED':
        raise ValueError('Approve the message before sending.')
    label = ws.MESSAGE_KINDS.get(message.kind, 'Message')
    return enqueue(db, pc=pc, source_key=f'message:{message.id}', message_id=message.id,
                   subject=f"Rome's Flavours — {position.title}", body=message.body)


def rows_for(db, pc_id):
    return list(db.scalars(select(EmailOutbox).where(EmailOutbox.position_candidate_id == pc_id)
                           .order_by(EmailOutbox.id.desc())).all())


def retry(row):
    if row.status not in ('FAILED', 'UNKNOWN'):
        return False
    row.status, row.attempts, row.next_attempt_at = 'QUEUED', 0, ws.utcnow()
    row.lease_hash = row.lease_expires_at = row.last_error = None
    return True


def claim(db):
    now = ws.utcnow()
    expired = list(db.scalars(select(EmailOutbox).where(
        EmailOutbox.status.in_(('LEASED', 'SENDING')), EmailOutbox.lease_expires_at <= now)
        .with_for_update(skip_locked=True)).all())
    for row in expired:
        row.status = ('QUEUED' if row.attempts < 3 else 'FAILED') if row.status == 'LEASED' else 'UNKNOWN'
        row.last_error = 'Delivery interrupted before server confirmation.' if row.status == 'UNKNOWN' else None
    db.flush()
    row = db.scalars(select(EmailOutbox).where(EmailOutbox.status == 'QUEUED',
        EmailOutbox.next_attempt_at <= now, EmailOutbox.attempts < 3)
        .order_by(EmailOutbox.id).with_for_update(skip_locked=True).limit(1)).first()
    if row is None:
        return None
    token = secrets.token_urlsafe(32)
    row.status, row.attempts = 'LEASED', row.attempts + 1
    row.lease_hash = hashlib.sha256(token.encode()).hexdigest()
    row.lease_expires_at = now + timedelta(minutes=5)
    db.flush()
    return {'id': row.id, 'lease': token, 'to': row.recipient, 'subject': row.subject,
            'body': row.body, 'message_id': row.smtp_message_id}


def acknowledge(db, data):
    row = db.scalars(select(EmailOutbox).where(EmailOutbox.id == data.get('id')).with_for_update()).first()
    token_hash = hashlib.sha256(str(data.get('lease', '')).encode()).hexdigest()
    if row is None or not row.lease_hash or not hmac.compare_digest(row.lease_hash, token_hash):
        abort(403)
    outcome = data.get('outcome')
    if row.status == 'SENT' and outcome == 'sent':
        return row
    if row.status not in ('LEASED', 'SENDING') or row.lease_expires_at <= ws.utcnow():
        abort(409)
    if outcome == 'started' and row.status == 'LEASED':
        row.status = 'SENDING'
    elif outcome == 'sent' and row.status == 'SENDING':
        row.status, row.sent_at, row.last_error = 'SENT', ws.utcnow(), None
    elif outcome == 'uncertain' and row.status == 'SENDING':
        row.status, row.last_error = 'UNKNOWN', 'The server may have accepted the email; check before retrying.'
    elif outcome == 'failed':
        row.last_error = str(data.get('error', 'Email transport error.'))[:255]
        row.status = 'QUEUED' if row.attempts < 3 and not data.get('permanent') else 'FAILED'
        row.next_attempt_at = ws.utcnow() + timedelta(minutes=2 ** row.attempts)
    else:
        abort(409)
    return row


def install():
    from . import careers
    from .aruba_bridge import relay_payload
    from .routes import _cfg

    @careers.bp.route('/candidate/bridge/mail/claim', methods=['POST'])
    def mail_claim():
        relay_payload()
        with _cfg.SessionFactory() as db:
            item = claim(db)
            db.commit()
            return jsonify(ok=True, item=item)

    @careers.bp.route('/candidate/bridge/mail/ack', methods=['POST'])
    def mail_ack():
        data = relay_payload()
        with _cfg.SessionFactory() as db:
            row = acknowledge(db, data)
            status = row.status
            db.commit()
            return jsonify(ok=True, status=status)
