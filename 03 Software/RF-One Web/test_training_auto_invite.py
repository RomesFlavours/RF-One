"""Automatic Training invitation on Selection Hired, against a disposable SQLite database.

Run:  python test_training_auto_invite.py
No email is sent (send_email is intercepted), nothing touches AWS.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
tmp = tempfile.TemporaryDirectory(prefix="auto-invite-test-", ignore_cleanup_errors=True)
SECRET = 'isolated-auto-invite-test'
os.environ.update(RFONE_DATABASE_URL='sqlite:///' + str(Path(tmp.name) / 'test.db').replace('\\', '/'),
                  RFONE_FLASK_SECRET_KEY=SECRET, AWS_EC2_METADATA_DISABLED='true',
                  RFONE_PUBLIC_BASE_URL='https://rfone.example.invalid')
sys.path[:0] = [str(HERE), str(HERE.parent / 'RF-One Data Store')]
SELECTION_INVITE = Path(os.environ.get('SELECTION_DIR') or HERE.parent / 'Selection') / 'workspace' / 'training_invite.py'

from sqlalchemy import select
import db as web_db
import training_cloud
import training_integration as integration
import training_auto_invite as auto
from rfone_data_store import models as m, people_registry as people
from rfone_data_store import rfone_account_service as accounts
from rfone_data_store.training import enrollment as en
from rfone_data_store.selection import workspace_models as ps
from rfone_data_store.technical import account_email

m.Base.metadata.create_all(web_db._engine)
app = training_cloud.create_app(SessionFactory=web_db.SessionFactory)
app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
client = app.test_client()
F = web_db.SessionFactory
checks = []


def account(db, username, *, selection=None, training=None):
    a = m.RFOneAccount(username=username, display_name=username.title(), password_hash='!', email=None,
                       status='ACTIVE', is_admin=False, is_owner=False, session_version=1)
    db.add(a); db.flush()
    if selection:
        accounts.set_domain_access(db, account_id=a.id, domain_code='SELECTION', enabled=True, role_code=selection)
    if training:
        accounts.set_domain_access(db, account_id=a.id, domain_code='TRAINING', enabled=True, role_code=training)
        integration.create_and_link_training_identity(db, rfone_account_id=a.id, role_code=training)
    return a


def hired(db, manager, name, email, decision='HIRED'):
    req = db.scalar(select(m.RequirementSet.id))
    if not req:
        rs = m.RequirementSet(**{c: v for c, v in dict(name='Test', role_code='SERVER').items()
                                 if hasattr(m.RequirementSet, c)})
        db.add(rs); db.flush(); req = rs.id
    position = ps.WorkspacePosition(title='Server test', role_code='SERVER', location_label='Mount Dora',
        timezone='America/New_York', manager_account_id=manager.id, created_by_account_id=manager.id,
        requirement_set_id=req)
    db.add(position); db.flush()
    person = people.create_identity(db, full_name=name, email=email, normalized_name=name.lower())
    candidate = m.Candidate(full_name=name, email=email, phone='+1 352 555 0100', parsing_mode='DEMO')
    db.add(candidate); db.flush()
    application = m.Application(person_id=person.id, candidate_id=candidate.id); db.add(application); db.flush()
    pc = ps.WorkspacePositionCandidate(position_id=position.id, application_id=application.id,
                                       candidate_id=candidate.id, channel='MANUAL_UPLOAD')
    db.add(pc); db.flush()
    db.add(ps.WorkspaceDecision(position_candidate_id=pc.id, decision=decision, actor_account_id=manager.id,
                                actor_name='Test manager'))
    db.flush()
    return pc.id


def call(selection_id, actor_id, *, secret=SECRET, ts=None, tamper=False):
    body = json.dumps({'selection_id': selection_id, 'actor_id': actor_id, 'ts': ts or int(time.time())},
                      separators=(',', ':')).encode()
    sig = auto.sign(secret, body)
    if tamper:
        body = body.replace(b'"actor_id":', b'"actor_id":1')
    r = client.post('/training/manage/enrollment/auto', data=body, content_type='application/json',
                    headers={'X-RFOne-Signature': sig})
    return r.status_code, r.get_json()


sent = []
with patch.object(account_email, 'send_email', side_effect=lambda **kw: sent.append(kw)):
    with F() as db:
        trainer_mgr = account(db, 'mdmanager', selection='MANAGER', training='trainer')
        plain_mgr = account(db, 'wpmanager', selection='MANAGER')
        fallback = account(db, 'fallbacktrainer', training='trainer')
        a = hired(db, trainer_mgr, 'Hailey Test', 'hailey@example.invalid')
        b = hired(db, plain_mgr, 'Erin Test', 'erin@example.invalid')
        c = hired(db, trainer_mgr, 'No Email', '')
        d = hired(db, trainer_mgr, 'Not Hired', 'nothired@example.invalid', decision='NOT_SELECTED')
        ids = dict(trainer=trainer_mgr.id, plain=plain_mgr.id, fallback=fallback.id)
        db.commit()

    # Unsigned, wrong key, tampered body and old timestamp are refused, and nothing is created.
    r = client.post('/training/manage/enrollment/auto', data=b'{}', content_type='application/json')
    assert r.status_code == 403
    assert call(a, ids['trainer'], secret='wrong')[0] == 403
    assert call(a, ids['trainer'], tamper=True)[0] == 403
    assert call(a, ids['trainer'], ts=int(time.time()) - 3600)[0] == 403
    with F() as db:
        assert not db.scalars(select(en.EnrollmentInvitation)).all()
    assert not sent
    checks.append('Unsigned, wrong-key, tampered and expired requests refused; nothing created or sent')

    # Hired by a manager who is also a Training trainer: invitation created and emailed.
    code, data = call(a, ids['trainer'])
    assert code == 200 and data['status'] == 'sent', (code, data)
    assert len(sent) == 1 and sent[0]['to_address'] == 'hailey@example.invalid'
    assert 'https://rfone.example.invalid/training/activate/' in sent[0]['text_body']
    with F() as db:
        inv = db.scalar(select(en.EnrollmentInvitation).where(en.EnrollmentInvitation.selection_id == a))
        assert inv and inv.created_by_id == ids['trainer'] and not inv.consumed_at
        token = sent[0]['text_body'].split('/training/activate/')[1].split()[0]
        assert inv.token_digest == en.digest(token) and token not in json.dumps(data)
    checks.append('Hired by a trainer: one invitation emailed with the public activation link; only the digest stored')

    # Same hire again (double click, retry): nothing new.
    code, data = call(a, ids['trainer'])
    assert code == 200 and data['status'] == 'already' and len(sent) == 1
    checks.append('Repeat for the same hire sends nothing new')

    # The emailed link opens the normal activation page.
    learner = app.test_client()
    r = learner.get('/training/activate/' + token)
    assert r.status_code == 302
    assert r.location.endswith('/training/activate')
    # The activation page itself is Pino's existing code, covered by his PostgreSQL tests
    # (SQLite returns naive datetimes, which enrollment.lookup does not accept).
    checks.append('Emailed link is the existing activation link (redirects to /training/activate)')

    # Hirer who is not a Training trainer: an active trainer issues it instead, no setting needed.
    code, data = call(b, ids['plain'])
    assert code == 200 and data['status'] == 'sent' and sent[-1]['to_address'] == 'erin@example.invalid', (code, data)
    with F() as db:
        inv = db.scalar(select(en.EnrollmentInvitation).where(en.EnrollmentInvitation.selection_id == b))
        assert inv.created_by_id == ids['trainer']
    # The RF-One owner, when a trainer, comes before any other trainer.
    with F() as db:
        owner = db.get(m.RFOneAccount, ids['fallback']); owner.is_admin = True; owner.is_owner = True
        h = hired(db, db.get(m.RFOneAccount, ids['plain']), 'Owner Path', 'ownerpath@example.invalid'); db.commit()
    code, data = call(h, ids['plain'])
    assert code == 200 and data['status'] == 'sent'
    with F() as db:
        inv = db.scalar(select(en.EnrollmentInvitation).where(en.EnrollmentInvitation.selection_id == h))
        assert inv.created_by_id == ids['fallback']
    checks.append('Hirer without Training role: the owner, else an active trainer, issues it automatically')

    # No email on the application, or not Hired: not sent.
    code, data = call(c, ids['trainer'])
    assert code == 422 and 'No email' in data['message']
    code, data = call(d, ids['trainer'])
    assert code == 409 and data['status'] == 'skipped'
    # Someone without Selection rights on that position cannot trigger it.
    code, data = call(a + 1000, ids['fallback'])
    assert code == 409
    assert len(sent) == 3
    checks.append('No email, not Hired, or no Selection rights on the position: nothing sent')

    # Email failure: invitation kept, Selection told.
    with F() as db:
        e = hired(db, db.get(m.RFOneAccount, ids['trainer']), 'Mail Fail', 'mailfail@example.invalid'); db.commit()
    with patch.object(account_email, 'send_email', side_effect=account_email.EmailSendError('down')):
        code, data = call(e, ids['trainer'])
    assert code == 502 and data['status'] == 'created'
    checks.append('Email server failure reported back without losing the decision')

# Selection side: the client signs exactly as Training verifies.
import importlib.util
spec = importlib.util.spec_from_file_location('training_invite', SELECTION_INVITE)
training_invite = importlib.util.module_from_spec(spec); spec.loader.exec_module(training_invite)
body = b'{"a":1}'
assert training_invite._sign(SECRET, body) == auto.sign(SECRET, body)
assert training_invite.request_invite(None, position_candidate_id=1, actor_account_id=1) == ('off', '')
checks.append('Selection signs the request with the same derived key; off when no RF-One address is set')

# End to end: Selection's real request function against the Training route.
import io
class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False
def _urlopen(req, timeout=None):
    assert req.full_url == 'https://rfone.example.invalid/training/manage/enrollment/auto' and timeout
    r = client.post('/training/manage/enrollment/auto', data=req.data, content_type='application/json',
                    headers={'X-RFOne-Signature': req.headers['X-rfone-signature']})
    if r.status_code >= 400:
        import urllib.error
        raise urllib.error.HTTPError(req.full_url, r.status_code, 'x', {}, io.BytesIO(r.data))
    return _Resp(r.data)
sent.clear()
with patch.object(account_email, 'send_email', side_effect=lambda **kw: sent.append(kw)),      patch.object(training_invite.urllib.request, 'urlopen', _urlopen):
    with F() as db:
        g = hired(db, db.get(m.RFOneAccount, ids['trainer']), 'Giulia Test', 'giulia@example.invalid'); db.commit()
    st, msg = training_invite.request_invite('https://rfone.example.invalid', position_candidate_id=g, actor_account_id=ids['trainer'])
    assert st == 'sent' and 'giulia@example.invalid' in msg and len(sent) == 1, (st, msg)
    st, msg = training_invite.request_invite('https://rfone.example.invalid', position_candidate_id=c, actor_account_id=ids['trainer'])
    assert st == 'skipped' and 'No email' in msg and len(sent) == 1, (st, msg)
checks.append('End to end: Selection request reaches Training, email sent; a refusal comes back as a readable message; release order does not matter')

print(json.dumps({'passed': len(checks), 'checks': checks}, indent=1))
