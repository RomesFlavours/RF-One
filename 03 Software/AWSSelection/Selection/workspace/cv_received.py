"""Automatic "we received your résumé" email, once per person per Job.

Sent when a candidate uploads a résumé on the job page and when staff upload
résumés. It goes through the same outbox as every other candidate email, so
the existing mail worker delivers it. It never blocks or undoes an upload:
if there is no valid email address, or anything fails, the upload stands and
no email is queued.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import timedelta

from rfone_data_store.selection import persistence, workspace_models as ps
from . import mail_delivery

log = logging.getLogger(__name__)
SUBJECT = "Rome's Flavours: we received your résumé"
PREFIX = "cv-received:"
# Staff uploads wait before sending, so a CV uploaded by mistake can still be deleted (with its unsent email).
STAFF_DELAY = timedelta(minutes=15)


def _name(db, pc):
    account = db.get(ps.CandidateAccount, pc.candidate_account_id) if pc.candidate_account_id else None
    candidate = persistence.get_candidate(db, pc.candidate_id)
    full = (account.full_name if account else None) or pc.declared_name or (candidate.full_name if candidate else None) or ''
    parts = full.split()
    first = parts[0].strip(',.;:') if parts else ''
    return first.capitalize() if first.isupper() else first


def body(first_name, title, location):
    where = "Rome’s Flavours" + (f" {location}" if location else '')
    greeting = f"Hi {first_name}," if first_name else "Hello,"
    return (f"{greeting}\n\n"
            f"Thank you for your interest in joining the team at {where}! "
            f"We're delighted you took the time to apply for our {title} position.\n\n"
            "We've received your résumé, and our team will be taking a look at your experience and qualifications. "
            "If it looks like you could be a great fit for our team, we'll be in touch to discuss the next steps. "
            "If we need any additional information, we'll reach out as well.\n\n"
            "We appreciate your interest in being part of Rome’s Flavours and look forward to the possibility "
            "of welcoming you to our team!\n\n"
            "Warm regards,\n"
            "The Rome’s Flavours Team")


def source_key(position_id, email):
    return f"{PREFIX}{position_id}:{hashlib.sha256(email.encode()).hexdigest()[:40]}"


def queue(db, pc_id, delay=None):
    """Queue the email for this application and commit it. Returns True when queued now."""
    try:
        pc = db.get(ps.PositionCandidate, pc_id)
        position = db.get(ps.Position, pc.position_id) if pc else None
        email = mail_delivery.email_for(db, pc) if position else None
        if not email:
            return False
        key = source_key(position.id, email)
        if db.query(mail_delivery.EmailOutbox.id).filter_by(source_key=key).first():
            return False
        row = mail_delivery.enqueue(db, pc=pc, source_key=key, subject=SUBJECT,
                              body=body(_name(db, pc), (position.title or 'open').strip(), (position.location_label or '').strip()))
        if delay:
            row.next_attempt_at = ps.utcnow() + delay
        db.commit()
        return True
    except Exception:   # never let the courtesy email break an upload
        db.rollback()
        log.exception('cv_received: email not queued for position_candidate %s', pc_id)
        return False
