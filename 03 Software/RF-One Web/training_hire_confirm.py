"""Confirm hire: Trainee to Employee in the one Registry, 13 November 2026.

Passing everything unlocks the hire, and a person confirms it.

- The Server Course keeps units, tests, practical checks and the lead's sign-off.
  Training asks it where its trainees stand (POST <course>/api/rfone-status) with a
  code signed by Training's own key; the course has Training confirm the code, as
  for opening the course, so there is no shared secret.
- On Training -> Students, a trainee whose course is complete and signed by the
  lead shows "Confirm hire" to trainers. Pressing it adds the EMPLOYEE company
  status to their Registry person; who and when is kept in the existing event log
  (rfone_access_profile_events, action 'registry.hire_confirmed').
- Before that, only the owner sees the button, and must write a reason.
- The employee record for payroll and scheduling stays a separate step.
"""
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from flask import abort, flash, redirect, request, url_for
from sqlalchemy import inspect, select

from rfone_data_store import models as m, people_registry as people
from rfone_data_store import access_profiles as profiles
from rfone_data_store.training import workspace as ws
from rfone_data_store import rfone_web_session as shared
import training_integration as integration
from training_server_course import COURSE_URL, make_code

ACTION = 'registry.hire_confirmed'
TIMEOUT = 8


def course_status(secret, trainer_account, account_ids):
    """{account_id: status} from the course, or None if it can't be reached."""
    ids = sorted({int(a) for a in account_ids if a})
    if not ids:
        return {}
    code = make_code(secret, dict(a=trainer_account.id, e='', n='', t=int(time.time()), k='status', q=ids))
    req = urllib.request.Request(COURSE_URL + '/api/rfone-status', data=json.dumps({'code': code}).encode(),
                                 method='POST', headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read() or b'{}')
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    return {int(k): v for k, v in (data.get('trainees') or {}).items()}


def person_for(db, account_id):
    link = db.scalar(select(people.PersonAccountLink).where(people.PersonAccountLink.account_id == account_id)) if account_id else None
    return link.person_id if link else None


def confirmations(db, person_ids):
    """Latest confirmation per person: {person_id: {'by': name, 'date': date}}."""
    out = {}
    if not person_ids:
        return out
    for e in db.scalars(select(profiles.ProfileEvent).where(profiles.ProfileEvent.action == ACTION)
                        .order_by(profiles.ProfileEvent.id)):
        pid = (e.details or {}).get('person_id')
        if pid in person_ids:
            out[pid] = {'by': (e.details or {}).get('by_name', ''),
                        'date': e.created_at.strftime('%b %d, %Y') if e.created_at else ''}
    return out


def hire_rows(db, secret, trainer_account, students):
    """The Hire column for Training -> Students."""
    persons = {s['id']: person_for(db, s.get('account_id')) for s in students}
    employees = {p for p in persons.values() if p and 'EMPLOYEE' in people.company_statuses(db, p)}
    confirmed = confirmations(db, employees)
    asked = [s['account_id'] for s in students if not s['archived'] and persons[s['id']] and persons[s['id']] not in employees]
    status = course_status(secret, trainer_account, asked) if asked else {}
    out = {}
    for s in students:
        p = persons[s['id']]
        if not p:
            out[s['id']] = dict(state='no_person')
        elif p in employees:
            out[s['id']] = dict(state='employee', **confirmed.get(p, {}))
        elif s['archived']:
            out[s['id']] = dict(state='archived')
        elif status is None:
            out[s['id']] = dict(state='unknown')
        else:
            c = status.get(s['account_id'])
            out[s['id']] = dict(state='ready' if c and c.get('signed') else 'training' if c else 'not_started', course=c or {})
    return out


def install(app, *, SessionFactory, auth, trainer):
    @app.post('/training/manage/students/<int:student_id>/confirm-hire')
    @trainer
    def tw_confirm_hire(student_id):
        auth.require_csrf()
        reason = ' '.join(request.form.get('reason', '').split())[:500]
        with SessionFactory() as db:
            actor = auth.load_current_account(db)
            training = db.get(m.TrainingAccount, student_id)
            account = ws.linked_account(db, student_id) if training and training.role == 'student' else None
            person = person_for(db, account.id if account else None)
            if person is None:
                flash('This trainee is not in the Registry yet, so the hire cannot be confirmed here.', 'error')
                return redirect(url_for('tw_students'))
            if 'EMPLOYEE' in people.company_statuses(db, person):
                flash('Already an employee in the Registry.', 'info')
                return redirect(url_for('tw_students'))
            if not inspect(db.connection()).has_table('person_company_statuses'):
                abort(503)
            c = (course_status(app.secret_key, actor, [account.id]) or {}).get(account.id) or {}
            override = not c.get('signed')
            if override and not actor.is_owner:
                flash('Confirm hire opens when the course is complete and the lead has signed the practical checks.', 'error')
                return redirect(url_for('tw_students'))
            if override and len(reason) < 5:
                flash('Write the reason for confirming before the course is complete.', 'error')
                return redirect(url_for('tw_students'))
            db.add(people.PersonCompanyStatus(person_id=person, code='EMPLOYEE', assigned_at=datetime.now(timezone.utc)))
            profiles.event(db, ACTION, actor=actor.id, person_id=person, training_account_id=student_id,
                           rfone_account_id=account.id, by_name=shared.account_display_name(actor),
                           override=override, reason=reason, course=c)
            db.commit()
        flash('Hire confirmed: now an Employee in the Registry. Create their employee record for payroll and '
              'scheduling as usual.', 'info')
        return redirect(url_for('tw_students'))
