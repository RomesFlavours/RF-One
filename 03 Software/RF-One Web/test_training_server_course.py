"""Server Course joined to Training, against a disposable SQLite database.

Run:  python test_training_server_course.py
No email is sent and the course's address is never contacted (both intercepted).
"""
import io
import json
import os
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
tmp = tempfile.TemporaryDirectory(prefix='server-course-test-', ignore_cleanup_errors=True)
os.environ.update(RFONE_DATABASE_URL='sqlite:///' + str(Path(tmp.name) / 'test.db').replace('\\', '/'),
                  RFONE_FLASK_SECRET_KEY='isolated-server-course-test', AWS_EC2_METADATA_DISABLED='true',
                  RFONE_PUBLIC_BASE_URL='https://rfone.example.invalid',
                  RFONE_SERVER_COURSE_URL='https://course.example.invalid')
sys.path[:0] = [str(HERE), str(HERE.parent / 'RF-One Data Store')]

from sqlalchemy import select
import auth
import db as web_db
import training_cloud
import training_integration as integration
import training_server_course as sc
from rfone_data_store import models as m, people_registry as people
from rfone_data_store import rfone_account_service as accounts
from rfone_data_store.training import enrollment as en
from rfone_data_store.technical import account_email

m.Base.metadata.create_all(web_db._engine)
app = training_cloud.create_app(SessionFactory=web_db.SessionFactory)
app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
F = web_db.SessionFactory
checks = []


def account(db, username, email, role=None):
    a = m.RFOneAccount(username=username, display_name=username.title(), password_hash='!', email=email,
                       status='ACTIVE', is_admin=False, is_owner=False, session_version=1)
    db.add(a); db.flush()
    if role:
        accounts.set_domain_access(db, account_id=a.id, domain_code='TRAINING', enabled=True, role_code=role)
        integration.create_and_link_training_identity(db, rfone_account_id=a.id, role_code=role)
    return a


def signed_in(account_id):
    c = app.test_client()
    with c.session_transaction() as s:
        s[auth.SESSION_ACCOUNT_KEY] = account_id; s[auth.SESSION_VERSION_KEY] = 1
    return c


with F() as db:
    trainer = account(db, 'mdlead', 'lead@example.invalid', 'trainer')
    student = account(db, 'hailey', 'hailey@example.invalid', 'student')
    outsider = account(db, 'noaccess', 'none@example.invalid')
    db.add(m.TrainingPill(slug='visual-menu', title='Visual Menu', learning_objectives='Dishes'))
    people.create_identity(db, full_name='Known Person', email='known@example.invalid', normalized_name='known person')
    db.commit()
    ids = dict(trainer=trainer.id, student=student.id, outsider=outsider.id)
    student_training = integration.get_link_for_rfone_account(db, student.id).training_account_id

# 1. Opening the course from Training.
assert app.test_client().get('/training/courses/server').status_code == 302
r = signed_in(ids['outsider']).get('/training/courses/server')
assert r.status_code == 302 and 'course.example.invalid' not in r.location
r = signed_in(ids['student']).get('/training/courses/server')
assert r.status_code == 302 and r.location.startswith('https://course.example.invalid/rf?code=')
assert r.headers['Referrer-Policy'] == 'no-referrer'
code = urllib.parse.parse_qs(urllib.parse.urlparse(r.location).query)['code'][0]
checks.append('Signed-in student goes to the course with a code; signed out or no Training access stays in RF-One')

with F() as db:
    n = db.scalar(select(m.TrainingAssignment.id).join(m.TrainingNeed, m.TrainingNeed.id == m.TrainingAssignment.need_id)
                  .where(m.TrainingNeed.student_account_id == student_training))
    assert n
signed_in(ids['student']).get('/training/courses/server')
with F() as db:
    assert len(db.scalars(select(m.TrainingAssignment)).all()) == 1
checks.append('Visual Menu assigned to the student the first time, once only')

# 2. The course checks the code.
c = app.test_client()
r = c.post('/training/courses/server/verify', json={'code': code})
assert r.status_code == 200 and r.get_json() == {'account_id': ids['student'], 'email': 'hailey@example.invalid',
                                                 'name': r.get_json()['name']}
assert c.post('/training/courses/server/verify', json={'code': code[:-2] + 'aa'}).status_code == 403
old = sc.make_code(app.secret_key, dict(a=ids['student'], e='x', n='x', t=int(time.time()) - 600))
assert c.post('/training/courses/server/verify', json={'code': old}).status_code == 403
forged = sc.make_code('another-key', dict(a=ids['trainer'], e='x', n='x', t=int(time.time())))
assert c.post('/training/courses/server/verify', json={'code': forged}).status_code == 403
checks.append('Code verified with account and email; tampered, expired or wrongly signed codes refused')


# 3. Invitation asked for from a hire's course page.
class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


course_side = {}


def fake_course(req, timeout=None):
    assert req.full_url.startswith('https://course.example.invalid/api/training-link/') and timeout
    key = urllib.parse.unquote(req.full_url.rsplit('/', 1)[1])
    if key not in course_side:
        from urllib.error import HTTPError
        raise HTTPError(req.full_url, 404, 'Not Found', {}, io.BytesIO(b'{}'))
    return _Resp(json.dumps({'email': course_side[key]}).encode())


sent = []
good = 'a' * 20 + '.' + 'B' * 32
course_side[good] = 'newserver@example.invalid'
with patch.object(sc.urllib.request, 'urlopen', fake_course), \
     patch.object(account_email, 'send_email', side_effect=lambda **kw: sent.append(kw)):
    assert c.post('/training/courses/server/invite', json={'code': 'nope'}).status_code == 400
    assert c.post('/training/courses/server/invite', json={'code': 'c' * 20 + '.' + 'D' * 32}).status_code == 403
    assert not sent
    r = c.post('/training/courses/server/invite', json={'code': good})
    assert r.status_code == 200 and r.get_json()['status'] == 'sent', r.get_json()
    assert sent[0]['to_address'] == 'newserver@example.invalid'
    assert 'https://rfone.example.invalid/training/activate/' in sent[0]['text_body']
    with F() as db:
        inv = db.scalar(select(en.EnrollmentInvitation).where(en.EnrollmentInvitation.email == 'newserver@example.invalid'))
        assert inv and inv.created_by_id == ids['trainer'] and not inv.selection_id
    checks.append('Invitation only for a code the course confirms; email read from the course, not the request; issued by a trainer')
    known = 'e' * 20 + '.' + 'F' * 32
    course_side[known] = 'known@example.invalid'
    r = c.post('/training/courses/server/invite', json={'code': known})
    assert r.status_code == 409 and 'already in RF-One' in r.get_json()['message'] and len(sent) == 1
    checks.append('Email already belonging to someone in RF-One: no automatic merge, the manager invites')
    # The one-minute repeat limit is enroll.issue's own (PostgreSQL-tested by Pino; SQLite dates are naive).

# 4. Student home shows the card.
home = signed_in(ids['student']).get('/training')
body = home.get_data(as_text=True)
assert home.status_code == 200 and 'Open the Server Course' in body and '/training/courses/server' in body, home.status_code
checks.append('Student home shows the Server Course card')

print(json.dumps({'passed': len(checks), 'checks': checks}, indent=1))
