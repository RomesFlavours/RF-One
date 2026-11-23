"""Tell staff about careers-page applications, so nobody is left waiting unseen.

1. New application: the moment someone uploads a résumé on the careers page,
   the job's owner and the people in RFONE_SELECTION_ALERT_ALSO get one email
   with the name, the job and a link to the candidate in Selection. No résumé
   and no contact details go in the email.
2. Morning reminder: from 8 am (Florida time), one email per person listing
   careers-page applicants who have waited WAIT_DAYS or more with no decision,
   message or interview. People in RFONE_SELECTION_ALERT_ESCALATE are copied on
   anyone waiting ESCALATE_DAYS or more.

Both go through the RF-One Email Service (domain SELECTION), like the résumé
receipt. Off unless RFONE_SELECTION_STAFF_ALERTS=1. Nothing here can block or
undo an application: any failure is logged and the application stands.

The reminder needs no scheduler of its own: Selection's mail worker calls the
outbox every minute, and that call runs `daily_reminder`, which does its work
once per day (the Email Service's dedup keys make repeats harmless).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from rfone_data_store.models import RFOneAccount
from rfone_data_store.selection import persistence, workspace_models as ps

log = logging.getLogger(__name__)

SWITCH = 'RFONE_SELECTION_STAFF_ALERTS'
ALSO = 'RFONE_SELECTION_ALERT_ALSO'          # usernames, comma separated (e.g. the Head of Selection)
ESCALATE = 'RFONE_SELECTION_ALERT_ESCALATE'  # usernames copied after ESCALATE_DAYS
DOMAIN = 'SELECTION'
EVENT_NEW = 'selection.staff_new_application:'
EVENT_REMINDER = 'selection.staff_reminder:'
LOCAL_TZ = ZoneInfo('America/New_York')
REMINDER_HOUR = 8
WAIT_DAYS = 2
ESCALATE_DAYS = 7

_done_day = None   # per process: today's reminder already handled


def enabled():
    return os.environ.get(SWITCH, '').strip() == '1'


def _usernames(var):
    return [u.strip().lower() for u in os.environ.get(var, '').split(',') if u.strip()]


def _email(account):
    value = (account.email or account.contact_email or '').strip()
    return value if value.count('@') == 1 and ' ' not in value else None


def _accounts(db, *, ids=(), usernames=()):
    """Active RF-One accounts with an email, in a stable order, no repeats."""
    rows = []
    if ids:
        rows += db.scalars(select(RFOneAccount).where(RFOneAccount.id.in_(list(ids)))).all()
    if usernames:
        rows += db.scalars(select(RFOneAccount).where(RFOneAccount.username.in_(list(usernames)))).all()
    seen, out = set(), []
    for a in sorted(rows, key=lambda a: a.id):
        if a.id in seen or (a.status or 'ACTIVE') != 'ACTIVE' or not _email(a):
            continue
        seen.add(a.id)
        out.append(a)
    return out


def recipients(db, position):
    return _accounts(db, ids=[position.manager_account_id], usernames=_usernames(ALSO))


def _name(db, pc):
    account = db.get(ps.CandidateAccount, pc.candidate_account_id) if pc.candidate_account_id else None
    candidate = persistence.get_candidate(db, pc.candidate_id)
    return ((account.full_name if account else None) or pc.declared_name
            or (candidate.full_name if candidate else None) or 'A candidate').strip()


def _local(dt):
    return dt.replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ)


def _when(dt):
    t = _local(dt)
    return f"{t:%a} {t.day} {t:%b}, {t.strftime('%I:%M %p').lstrip('0').lower()}"


def _day(dt):
    t = _local(dt)
    return f"{t.day} {t:%b}"


def _where(position):
    return f"{position.title}, {position.location_label}" if position.location_label else position.title


def _link(position_id, pc_id):
    from .routes import external_url
    return external_url('positions.candidate_detail', position_id=position_id, pc_id=pc_id)


def _finished(db, pc):
    app = db.scalars(select(ps.CandidateApplication).where(ps.CandidateApplication.position_candidate_id == pc.id)).first()
    return app is not None and app.status == ps.A_SUBMITTED


def new_application_email(name, position, applied_at, link):
    subject = f"New application: {name}, {_where(position)}"
    body = (f"{name} applied on the careers page for {position.title}"
            + (f" at {position.location_label}" if position.location_label else '')
            + f" on {_when(applied_at)}.\n\n"
            f"Open the application in Selection:\n{link}\n\n"
            "Please record a decision, a message or an interview so the candidate hears from us. "
            f"If nothing happens in {WAIT_DAYS} days, this application goes on the morning reminder.\n")
    return subject, body


def new_application(db, pc_id):
    """Email the job's owner (and ALSO) about one careers-page application. Commits. Never raises."""
    if not enabled():
        return 0
    try:
        from rfone_data_store import email_service as es
        pc = db.get(ps.PositionCandidate, pc_id)
        if pc is None or pc.channel != ps.PUBLIC_LINK:
            return 0
        position = db.get(ps.Position, pc.position_id)
        subject, body = new_application_email(_name(db, pc), position, pc.added_at, _link(position.id, pc.id))
        sent = 0
        for account in recipients(db, position):
            es.enqueue(db, domain=DOMAIN, recipient=_email(account), subject=subject[:250], body=body,
                       event=f"{EVENT_NEW}{position.id}:{pc.id}", dedup_key=f"staff_new_application:{pc.id}:{account.id}:v1")
            sent += 1
        db.commit()
        return sent
    except Exception:
        db.rollback()
        log.exception('staff_alerts: new application email not queued for position_candidate %s', pc_id)
        return 0


def waiting(db, now):
    """Careers-page applications on open jobs, WAIT_DAYS or older, that nobody has acted on."""
    cutoff = now - timedelta(days=WAIT_DAYS)
    acted = set()
    for model in (ps.Decision, ps.Message, ps.Appointment, ps.SlotOffer):
        acted.update(db.scalars(select(model.position_candidate_id)).all())
    rows = db.execute(select(ps.PositionCandidate, ps.Position)
                      .join(ps.Position, ps.Position.id == ps.PositionCandidate.position_id)
                      .where(ps.PositionCandidate.channel == ps.PUBLIC_LINK, ps.Position.status == ps.OPEN,
                             ps.PositionCandidate.added_at <= cutoff)
                      .order_by(ps.PositionCandidate.added_at)).all()
    out = []
    for pc, position in rows:
        if pc.id in acted:
            continue
        days = (_local(now).date() - _local(pc.added_at).date()).days
        out.append({'pc': pc, 'position': position, 'name': _name(db, pc), 'days': days,
                    'finished': _finished(db, pc), 'link': _link(position.id, pc.id)})
    return out


def reminder_email(items, *, escalation=False):
    n = len(items)
    subject = (f"Selection: {n} careers application{'s' if n != 1 else ''} waiting "
               + (f"{ESCALATE_DAYS}+ days" if escalation else "for a decision"))
    lines = [f"These people applied on the careers page {ESCALATE_DAYS} or more days ago and still have no answer:"
             if escalation else
             f"These people applied on the careers page and have had no decision, message or interview for {WAIT_DAYS} days or more:", ""]
    for i in items:
        note = '' if i['finished'] else ' (résumé only, questions not finished)'
        lines += [f"- {i['name']}, {_where(i['position'])}: applied {_day(i['pc'].added_at)}, waiting {i['days']} days{note}",
                  f"  {i['link']}"]
    lines += ["", "Record a decision, a message or an interview and they drop off this list.",
              "This reminder comes every morning while anyone is waiting."]
    return subject, "\n".join(lines) + "\n"


def daily_reminder(db, now=None):
    """Queue today's reminders once, from REMINDER_HOUR local time. Returns how many emails were queued."""
    global _done_day
    if not enabled():
        return 0
    now = now or ps.utcnow()
    local = _local(now)
    if local.hour < REMINDER_HOUR or _done_day == local.date():
        return 0
    from rfone_data_store import email_service as es
    items = waiting(db, now)
    per = {}   # account id -> (account, items, escalation)
    for i in items:
        for account in recipients(db, i['position']):
            per.setdefault((account.id, False), (account, [], False))[1].append(i)
    late = [i for i in items if i['days'] >= ESCALATE_DAYS]
    if late:
        for account in _accounts(db, usernames=_usernames(ESCALATE)):
            if (account.id, False) in per:   # already gets the full list
                continue
            per[(account.id, True)] = (account, late, True)
    queued = 0
    for account, its, escalation in per.values():
        subject, body = reminder_email(its, escalation=escalation)
        try:
            es.enqueue(db, domain=DOMAIN, recipient=_email(account), subject=subject[:250], body=body,
                       event=f"{EVENT_REMINDER}{local.date().isoformat()}",
                       dedup_key=f"staff_reminder:{local.date().isoformat()}:{account.id}:v1")
            db.commit()
            queued += 1
        except ValueError:
            # Another instance already queued today's reminder for this person (different minute, same day).
            db.rollback()
    _done_day = local.date()
    return queued


def run_daily_reminder(factory):
    """Called from the mail worker's every-minute request. Never raises."""
    if not enabled():
        return
    try:
        with factory() as db:
            daily_reminder(db)
    except Exception:
        log.exception('staff_alerts: daily reminder failed')
