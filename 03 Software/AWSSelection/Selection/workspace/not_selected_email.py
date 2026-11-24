"""Automatic, kind email when a candidate is marked Not selected.

When staff record "Not selected", the candidate gets one polite email after a
2-hour grace period. If the decision is changed within those 2 hours (for
example "Rejection withdrawn"), the waiting email is cancelled and never sent.

- No reason is ever given to the candidate (the reason stays internal).
- Not sent when the reason is "Candidate declined": they withdrew themselves.
- Not sent when someone already queued or sent a "Not selected" message by
  hand for this application, or when this application already got this email.
- Large batches are spaced out so the mail server is not flooded.

Goes through the RF-One Email Service (domain SELECTION) when that is on, like
the résumé receipt; otherwise through Selection's own outbox. Off unless
RFONE_SELECTION_AUTO_REJECTION=1. It never blocks or undoes a decision: any
failure is logged and the decision stands.
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime as _dt, timedelta, timezone as _tz

from sqlalchemy import select

from rfone_data_store.selection import workspace_models as ps
from . import cv_received, mail_delivery

log = logging.getLogger(__name__)

SWITCH = 'RFONE_SELECTION_AUTO_REJECTION'
GRACE = timedelta(hours=2)
SPACING = timedelta(seconds=30)
EVENT = 'selection.not_selected:'
PREFIX = 'not-selected:'
SKIP_REASONS = {'CANDIDATE_DECLINED'}


def enabled():
    return os.environ.get(SWITCH, '').strip() == '1'


def subject(title):
    return f"Rome's Flavours: your application for {title}"


def body(first_name, title, location):
    where = "Rome's Flavours" + (f" {location}" if location else '')
    greeting = f"Hi {first_name}," if first_name else "Hello,"
    return (f"{greeting}\n\n"
            f"Thank you for your interest in joining the team at {where}.\n\n"
            "After reviewing your application, we've decided to move forward with other candidates at this time.\n\n"
            "We appreciate your interest and the time you took to apply. We encourage you to check back for future opportunities.\n\n"
            "We wish you all the best!\n\n"
            "Warm regards,\n"
            "The Rome's Flavours Team")


def _event(pc):
    return f"{EVENT}{pc.position_id}:{pc.id}"


def _central_rows(db, pc):
    from rfone_data_store import email_service as es
    return list(db.scalars(select(es.EmailRequest).where(
        es.EmailRequest.domain == cv_received.CENTRAL_DOMAIN, es.EmailRequest.event == _event(pc))))


def _outbox_rows(db, pc):
    E = mail_delivery.EmailOutbox
    return list(db.scalars(select(E).where(E.position_candidate_id == pc.id, E.source_key.like(PREFIX + '%'))))


def _already_handled(db, pc):
    """This application already got (or is getting) a Not selected email, automatic or by hand."""
    if any(r.status != 'CANCELLED' for r in _central_rows(db, pc)):
        return True
    if _outbox_rows(db, pc):
        return True
    manual = db.scalars(select(ps.Message.id).where(ps.Message.position_candidate_id == pc.id,
                                                    ps.Message.kind == 'REJECTION', ps.Message.status == 'APPROVED')).first()
    return manual is not None


def queue(db, pc_id, *, reason=None, decision_id=None, delay=GRACE):
    """Queue the email to go out after `delay`. Commits. Returns True when queued now. Never raises."""
    if not enabled() or reason in SKIP_REASONS:
        return False
    try:
        pc = db.get(ps.PositionCandidate, pc_id)
        position = db.get(ps.Position, pc.position_id) if pc else None
        email = mail_delivery.email_for(db, pc) if position else None
        if not email or _already_handled(db, pc):
            return False
        title = (position.title or 'open').strip()
        text = body(cv_received._name(db, pc), title, (position.location_label or '').strip())
        when = _dt.now(_tz.utc) + delay
        if cv_received.central_enabled():
            from rfone_data_store import email_service as es
            from sqlalchemy import update as _update
            request = es.enqueue(db, domain=cv_received.CENTRAL_DOMAIN, recipient=email, subject=subject(title), body=text,
                                 event=_event(pc), dedup_key=f"not_selected:{pc.id}:{decision_id or 0}:v1")
            db.execute(_update(es.EmailRequest).where(es.EmailRequest.id == request.id, es.EmailRequest.status == 'QUEUED',
                                                     es.EmailRequest.attempts == 0).values(available_at=when))
        else:
            key = f"{PREFIX}{pc.id}:{hashlib.sha256(email.encode()).hexdigest()[:32]}"
            row = mail_delivery.enqueue(db, pc=pc, source_key=key, subject=subject(title), body=text)
            row.next_attempt_at = ps.utcnow() + delay
        ps.log_event(db, position_id=position.id, position_candidate_id=pc.id, kind='NOT_SELECTED_EMAIL',
                     detail=f"Not selected email to the candidate queued; it goes out in {int(delay.total_seconds() // 60)} minutes unless the decision changes.",
                     actor_id=None, actor_name='Selection')
        db.commit()
        return True
    except Exception:
        db.rollback()
        log.exception('not_selected_email: not queued for position_candidate %s', pc_id)
        return False


def cancel(db, pc_id, *, actor_id=None):
    """Cancel a Not selected email that has not gone out yet. Commits. Returns how many were cancelled. Never raises."""
    try:
        pc = db.get(ps.PositionCandidate, pc_id)
        if pc is None:
            return 0
        n = 0
        if cv_received.central_enabled():
            from rfone_data_store import email_service as es
            for r in _central_rows(db, pc):
                if r.status in ('QUEUED', 'RETRY'):
                    try:
                        es.transition(db, domain=cv_received.CENTRAL_DOMAIN, request_id=r.id, action='cancel',
                                      actor_account_id=actor_id)
                        n += 1
                    except ValueError:
                        pass   # the worker took it meanwhile: it may already be sent
        for r in _outbox_rows(db, pc):
            if r.status == 'QUEUED' and r.attempts == 0:
                db.delete(r)
                n += 1
        if n:
            ps.log_event(db, position_id=pc.position_id, position_candidate_id=pc.id, kind='NOT_SELECTED_EMAIL',
                         detail='Not selected email cancelled before it went out (decision changed).',
                         actor_id=actor_id, actor_name='Selection')
        db.commit()
        return n
    except Exception:
        db.rollback()
        log.exception('not_selected_email: cancel failed for position_candidate %s', pc_id)
        return 0


def after_decisions(db, pc_ids, decision, reason, actor_id):
    """Called once the decisions are saved. Returns how many emails were queued."""
    if not enabled():
        return 0
    queued = 0
    for i, pc_id in enumerate(pc_ids):
        if decision == ps.D_NOT_SELECTED:
            last = db.scalars(select(ps.Decision.id).where(ps.Decision.position_candidate_id == pc_id)
                              .order_by(ps.Decision.id.desc())).first()
            if queue(db, pc_id, reason=reason, decision_id=last, delay=GRACE + SPACING * queued):
                queued += 1
        else:
            cancel(db, pc_id, actor_id=actor_id)
    return queued
