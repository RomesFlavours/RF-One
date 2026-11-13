"""Confirm hire, against a disposable SQLite database.

Run:  python test_training_hire_confirm.py
The course's address is never contacted (intercepted).
"""
import io
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
tmp = tempfile.TemporaryDirectory(prefix='hire-confirm-test-', ignore_cleanup_errors=True)
os.environ.update(RFONE_DATABASE_URL='sqlite:///' + str(Path(tmp.name) / 'test.db').replace('\\', '/'),
                  RFONE_FLASK_SECRET_KEY='isolated-hire-confirm-test', AWS_EC2_METADATA_DISABLED='true',
                  RFONE_PUBLIC_BASE_URL='https://rfone.example.invalid',
                  RFONE_SERVER_COURSE_URL='https://course.example.invalid')
sys.path[:0] = [str(HERE), str(HERE.parent / 'RF-One Data Store')]

from sqlalchemy import select
import auth
import db as web_db
import training_cloud
import training_integration as integration
import training_hire_confirm as hc
import training_server_course as sc
from rfone_data_store import models as m, people_registry as people, access_profiles as profiles
from rfone_data_store import rfone_account_service as accounts

m.Base.metadata.create_all(web_db._engine)
app = training_cloud.create_app(SessionFactory=web_db.SessionFactory)
app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False, WTF_CSRF_ENABLED=False)
F = web_db.SessionFactory
checks = []


def account(db, username, role=None, owner=False):
    a = m.RFOneAccount(username=username, display_name=username.title(), password_hash='!',
                       email=username + '@example.invalid', status='ACTIVE', is_admin=owner, is_owner=owner,
                       session_version=1)
    db.add(a); db.flush()
    if role:
        accounts.set_domain_access(db, account_id=a.id, domain_code='TRAINING', enabled=True, role_code=role)
        integration.create_and_link_training_identity(db, rfone_account_id=a.id, role_code=role)
    return a


with F() as db:
    lead = account(db, 'mdlead', 'trainer')
    owner = account(db, 'pino', 'trainer', owner=True)
    ids = {}
    for name in ('hailey', 'marco', 'nolink'):
        st = account(db, name, 'student')
        ids[name] = (st.id, integration.get_link_for_rfone_account(db, st.id).training_account_id)
        if name != 'nolink':
            p = people.create_identity(db, full_name=name.title(), email=name + '@example.invalid')
            db.add(people.PersonAccountLink(account_id=st.id, person_id=p.id, linked_by_id=lead.id,
                                            linked_at=datetime.now(timezone.utc)))
            ids[name] += (p.id,)
    db.commit()
    lead_id, owner_id = lead.id, owner.id

course = {}  # what the course reports, by RF-One account id
asked = []


class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


def fake_course(req, timeout=None):
    assert req.full_url == 'https://course.example.invalid/api/rfone-status' and timeout
    code = json.loads(req.data)['code']
    data = sc.read_code(app.secret_key, code)
    assert data and data['k'] == 'status'
    asked.append(data['q'])
    return _Resp(json.dumps({'trainees': {str(a): course[a] for a in data['q'] if a in course}}).encode())


def signed_in(account_id):
    c = app.test_client()
    with c.session_transaction() as s:
        s[auth.SESSION_ACCOUNT_KEY] = account_id; s[auth.SESSION_VERSION_KEY] = 1
    return c


def token(c):
    with c.session_transaction() as s:
        return s.get('csrf_token') or s.get('_csrf_token')


def students_page(c):
    with patch.object(hc.urllib.request, 'urlopen', fake_course):
        return c.get('/training/manage/students').get_data(as_text=True)


def confirm(c, who, reason=''):
    page = students_page(c)
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    with patch.object(hc.urllib.request, 'urlopen', fake_course):
        return c.post(f'/training/manage/students/{ids[who][1]}/confirm-hire', data={'csrf_token': csrf, 'reason': reason},
                      follow_redirects=True).get_data(as_text=True)


def is_employee(who):
    with F() as db:
        return 'EMPLOYEE' in people.company_statuses(db, ids[who][2])


progress = dict(units_complete=3, units_total=8, checks_done=2, checks_total=10, complete=False, signed=False,
                signed_by='', signed_date='')
course[ids['hailey'][0]] = dict(progress)
lead_c = signed_in(lead_id)
page = students_page(lead_c)
assert 'Trainee: 3 of 8 units, 2 of 10 checks' in page and 'Server Course not opened yet' in page
assert 'Not in the Registry' in page and 'Confirm hire' not in page
checks.append('Students page shows each trainee\'s course progress; no Confirm hire before the course is done')

body = confirm(lead_c, 'hailey')
assert 'opens when the course is complete' in body and not is_employee('hailey')
checks.append('A trainer cannot confirm early, even by sending the form directly')

course[ids['hailey'][0]].update(units_complete=8, checks_done=10, complete=True)
assert "waiting for the lead's sign-off" in students_page(lead_c) and 'Confirm hire' not in students_page(lead_c)
course[ids['hailey'][0]].update(signed=True, signed_by='Lead on shift')
page = students_page(lead_c)
assert 'Course complete, signed by Lead on shift' in page and 'Confirm hire' in page
checks.append('Course complete and signed by the lead: Confirm hire appears')

body = confirm(lead_c, 'hailey')
assert 'Hire confirmed' in body and is_employee('hailey')
assert 'Confirmed by Mdlead' in body
with F() as db:
    e = db.scalar(select(profiles.ProfileEvent).where(profiles.ProfileEvent.action == hc.ACTION))
    assert e.account_id == lead_id and e.details['person_id'] == ids['hailey'][2] and e.details['override'] is False
checks.append('Confirm hire makes them an Employee in the Registry, with who and when recorded')

assert 'Already an employee' in confirm(lead_c, 'hailey')
checks.append('Confirming twice changes nothing')

owner_c = signed_in(owner_id)
page = students_page(owner_c)
assert 'Confirm hire anyway' in page
assert 'Write the reason' in confirm(owner_c, 'marco', reason='') and not is_employee('marco')
body = confirm(owner_c, 'marco', reason='Worked here before, knows the floor')
assert 'Hire confirmed' in body and is_employee('marco')
with F() as db:
    e = db.scalars(select(profiles.ProfileEvent).where(profiles.ProfileEvent.action == hc.ACTION)).all()[-1]
    assert e.details['override'] is True and e.details['reason'].startswith('Worked here before')
checks.append('Owner can confirm before the course is done, only with a written reason, and it is recorded')

def down(req, timeout=None):
    raise OSError('unreachable')
with patch.object(hc.urllib.request, 'urlopen', down):
    page = signed_in(lead_id).get('/training/manage/students')
assert page.status_code == 200
checks.append('Course unreachable: the Students page still opens')

print(json.dumps({'passed': len(checks), 'checks': checks}, indent=1))
