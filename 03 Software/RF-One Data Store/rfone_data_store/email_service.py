"""Shared Services / Email. Transactional API; callers own commit/rollback.

No credentials, networking or web-session dependency in this module.
Domain is always part of every query, including primary-key lookups.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
import hashlib
import json
import uuid

from sqlalchemy import (Column, Integer, String, Text, DateTime, ForeignKey,
                        UniqueConstraint, CheckConstraint, select, update)
from .models import Base


def now():
    return datetime.now(timezone.utc)


class EmailRequest(Base):
    __tablename__ = "email_requests"
    __table_args__ = (
        UniqueConstraint("domain", "dedup_key"),
        CheckConstraint("status in ('QUEUED','SENDING','RETRY','ACCEPTED','FAILED','UNCERTAIN','CANCELLED')"),
    )
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    domain = Column(String(80), nullable=False, index=True)
    recipient = Column(String(254), nullable=False)
    subject = Column(String(250), nullable=False)
    body = Column(Text, nullable=False)
    event = Column(String(200), nullable=False)
    dedup_key = Column(String(200), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, default="QUEUED", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=now)
    available_at = Column(DateTime(timezone=True), nullable=False, default=now, index=True)
    error = Column(String(80))  # sanitized category/code only


class EmailAttempt(Base):
    __tablename__ = "email_attempts"
    __table_args__ = (UniqueConstraint("request_id", "number"),)
    id = Column(Integer, primary_key=True)
    request_id = Column(String(36), ForeignKey("email_requests.id"), nullable=False, index=True)
    number = Column(Integer, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, default=now)
    finished_at = Column(DateTime(timezone=True))
    outcome = Column(String(20), nullable=False, default="SENDING")
    error = Column(String(80))


class EmailAudit(Base):
    __tablename__ = "email_audit"
    id = Column(Integer, primary_key=True)
    request_id = Column(String(36), ForeignKey("email_requests.id"), nullable=False, index=True)
    actor_account_id = Column(Integer, ForeignKey("rfone_accounts.id"), nullable=False)
    action = Column(String(30), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now)


class EmailWorkerState(Base):
    __tablename__ = "email_worker_state"
    id = Column(Integer, primary_key=True)
    owner = Column(String(36))
    lease_until = Column(DateTime(timezone=True), nullable=False, default=now)
    heartbeat = Column(DateTime(timezone=True))
    next_send_at = Column(DateTime(timezone=True), nullable=False, default=now)
    mode = Column(String(20), nullable=False, default="STOPPED")


TABLES = [EmailRequest.__table__, EmailAttempt.__table__, EmailAudit.__table__, EmailWorkerState.__table__]


def enqueue(db, *, domain, recipient, subject, body, event, dedup_key):
    values = [domain, recipient, subject, body, event, dedup_key]
    if any(not isinstance(v, str) or not v.strip() for v in values):
        raise ValueError("All email fields are required")
    if (len(domain) > 80 or len(recipient) > 254 or len(subject) > 250 or
            len(body.encode('utf-8')) > 1_000_000 or len(event) > 200 or len(dedup_key) > 200):
        raise ValueError("Email field too long")
    if any(c in recipient + subject for c in '\r\n') or parseaddr(recipient)[1] != recipient or recipient.count('@') != 1:
        raise ValueError("Invalid recipient or subject")
    digest = hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()
    # Write first: avoids a SQLite deferred read-transaction upgrade race.
    # The same uniqueness contract is enforced by PostgreSQL in production.
    if db.bind.dialect.name == 'sqlite':
        from sqlalchemy.dialects.sqlite import insert
    elif db.bind.dialect.name == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        raise ValueError('Email queue supports SQLite and PostgreSQL')
    db.execute(insert(EmailRequest).values(domain=domain, recipient=recipient, subject=subject, body=body,
        event=event, dedup_key=dedup_key, payload_hash=digest).on_conflict_do_nothing(index_elements=['domain', 'dedup_key']))
    existing = db.scalar(select(EmailRequest).where(EmailRequest.domain == domain, EmailRequest.dedup_key == dedup_key))
    if existing.payload_hash != digest:
        raise ValueError("Deduplication key already used with different content")
    return existing


def get(db, domain, request_id):
    return db.scalar(select(EmailRequest).where(EmailRequest.domain == domain, EmailRequest.id == request_id))


def history(db, *, domain=None, recipient=None, status=None, start=None, end=None, offset=0):
    query = select(EmailRequest)
    for col, value in ((EmailRequest.domain, domain), (EmailRequest.status, status)):
        if value:
            query = query.where(col == value)
    if recipient:
        query = query.where(EmailRequest.recipient.contains(recipient, autoescape=True))
    if start:
        query = query.where(EmailRequest.created_at >= start)
    if end:
        query = query.where(EmailRequest.created_at < end)
    return list(db.scalars(query.order_by(EmailRequest.created_at.desc(), EmailRequest.id).limit(100).offset(offset)))


def transition(db, *, domain, request_id, action, actor_account_id):
    """Atomic against worker claims. UNCERTAIN is deliberately never resubmitted."""
    if action == "cancel":
        allowed, target = ("QUEUED", "RETRY"), "CANCELLED"
    elif action == "resend":
        allowed, target = ("FAILED",), "QUEUED"
    else:
        raise ValueError("Unknown action")
    result = db.execute(update(EmailRequest).where(EmailRequest.id == request_id,
        EmailRequest.domain == domain, EmailRequest.status.in_(allowed)).values(
            status=target, available_at=now(), updated_at=now(), error=None))
    if result.rowcount != 1:
        raise ValueError("Email is not eligible for this action")
    db.add(EmailAudit(request_id=request_id, actor_account_id=actor_account_id, action=action))


def snapshot(row):
    return {key: getattr(row, key) for key in
            ("id", "domain", "recipient", "subject", "event", "status", "attempts", "error",
             "created_at", "updated_at", "available_at")}
