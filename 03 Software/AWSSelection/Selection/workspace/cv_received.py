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
    first = parts[0].strip(",.;:()[]'\"") if parts else ''
    # An initial ("C", "Cg") is not a name: the email then says "Hello,".
    if len(first) < 2 or not any(ch in 'aeiouyàèéìòù' for ch in first.lower()):
        return ''
    return first.capitalize() if first.isupper() or first.islower() else first


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


# ---------------------------------------------------------------------------
# One-time catch-up: the same email for CVs of Jobs opened since a date
# (candidates who applied before the email existed). Owner only; the page
# lists who would get it, and nothing is sent until the Owner presses Send.
# ---------------------------------------------------------------------------
from datetime import datetime
from flask import abort, flash, redirect, render_template_string, request, url_for
from sqlalchemy import select
from .action_models import ActionRun
from .routes import access_required, bp

CATCH_UP_FROM_UTC = datetime(2026, 11, 14, 5, 0)   # 14 Nov 2026, midnight in Florida
CATCH_UP_SPACING = timedelta(seconds=30)            # gentle on the mail server


def catch_up_list(db):
    """Candidates of Jobs created since 14 Nov who never heard from us: no email of any kind, no
    message, no decision or board action, no interview offered or booked, and a valid address.
    One row per person per Job."""
    contacted = set()
    for model in (mail_delivery.EmailOutbox, ps.Message, ps.Decision, ps.Appointment, ps.SlotOffer, ActionRun):
        contacted.update(db.scalars(select(model.position_candidate_id)).all())
    rows, seen = [], set()
    jobs = db.scalars(select(ps.Position).where(ps.Position.created_at >= CATCH_UP_FROM_UTC)).all()
    for position in jobs:
        for pc in db.scalars(select(ps.PositionCandidate).where(ps.PositionCandidate.position_id == position.id)
                             .order_by(ps.PositionCandidate.id)).all():
            if pc.id in contacted:
                continue
            email = mail_delivery.email_for(db, pc)
            if not email or (position.id, email) in seen:
                continue
            seen.add((position.id, email))
            rows.append({'pc': pc, 'position': position, 'email': email, 'name': _name(db, pc) or '(no name)'})
    return rows


_PAGE = """{% extends 'workspace/base.html' %}
{% block title %}Catch-up: we received your résumé{% endblock %}
{% block content %}
<h1>Catch-up: "we received your résumé"</h1>
<p>Candidates of Jobs created since 14 Nov 2026 who have not heard from us yet. Anyone with an email,
a message, a decision, a board action or an interview is left out. Each person gets the email once per Job.</p>
{% if rows %}
<form method="post"><input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
<p><strong>{{ rows|length }}</strong> candidates will get the email.
<button type="submit" class="btn">Send to these {{ rows|length }}</button></p></form>
<table><thead><tr><th>Job</th><th>Location</th><th>Name</th><th>Email</th><th>Added</th></tr></thead><tbody>
{% for r in rows %}<tr><td>{{ r.position.title }}</td><td>{{ r.position.location_label or '' }}</td><td>{{ r.name }}</td>
<td>{{ r.email }}</td><td>{{ r.pc.added_at.strftime('%d %b') }}</td></tr>{% endfor %}</tbody></table>
{% else %}<p>Nobody is waiting: every candidate of these Jobs has already heard from us.</p>{% endif %}
{% endblock %}"""


@bp.route('/cv-received/catch-up', methods=['GET', 'POST'])
@access_required
def cv_received_catch_up(db, actor):
    if not actor.is_owner:
        abort(403)
    if request.method == 'POST':
        rows = catch_up_list(db)   # recomputed now: never trusts the page that was shown
        sent = 0
        for i, r in enumerate(rows):
            if queue(db, r['pc'].id, delay=CATCH_UP_SPACING * i):
                sent += 1
        for position_id in sorted({r['position'].id for r in rows}):   # one history line per Job
            n = sum(1 for r in rows if r['position'].id == position_id)
            ps.log_event(db, position_id=position_id, kind='CV_RECEIVED_CATCH_UP', actor_id=actor.id, actor_name=actor.name,
                         detail=f'Catch-up "we received your résumé": email queued for {n} candidates')
        db.commit()
        flash(f'{sent} emails queued. They go out over the next {max(1, (sent * 30) // 60)} minutes.')
        return redirect(url_for('positions.cv_received_catch_up'))
    return render_template_string(_PAGE, actor=actor, rows=catch_up_list(db), section='selection')
