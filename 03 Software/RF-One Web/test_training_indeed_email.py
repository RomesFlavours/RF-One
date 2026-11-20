"""Indeed forwarding addresses never get a Training invitation, against a disposable SQLite database.

Run:  python test_training_indeed_email.py
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
tmp = tempfile.TemporaryDirectory(prefix="indeed-email-test-", ignore_cleanup_errors=True)
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
from rfone_data_store import models as m, people_registry as people, student_registry as sreg
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
        mgr = account(db, 'mdmanager', selection='MANAGER', training='trainer')
        relay = hired(db, mgr, 'Indeed Applicant', 'abc123def456@indeedemail.com')
        relay_upper = hired(db, mgr, 'Upper Case', ' XYZ@Mail.IndeedEmail.com ')
        real = hired(db, mgr, 'Real Email', 'real.person@example.invalid')
        mgr_id = mgr.id
        db.commit()

    # The rule itself.
    assert en.is_forwarding_email('abc@indeedemail.com')
    assert en.is_forwarding_email(' ABC@IndeedEmail.COM ')
    assert en.is_forwarding_email('abc@mail.indeedemail.com')
    assert not en.is_forwarding_email('someone@indeed.com')
    assert not en.is_forwarding_email('someone@notindeedemail.com')
    assert not en.is_forwarding_email('someone@gmail.com')
    checks.append('Only @indeedemail.com (and its subdomains) counts as a forwarding address')

    # Selection's Hired: no invitation to the Indeed address, a clear message, still a Trainee.
    code, data = call(relay, mgr_id)
    assert code == 422 and data['status'] == 'skipped', (code, data)
    assert data['message'] == 'This is an Indeed forwarding address. Ask for their real email.', data
    code, data = call(relay_upper, mgr_id)
    assert code == 422 and 'Indeed forwarding address' in data['message'], data
    assert not sent
    with F() as db:
        assert not db.scalars(select(en.EnrollmentInvitation)).all()
        pc = db.get(ps.WorkspacePositionCandidate, relay)
        person = db.get(m.Application, pc.application_id).person_id
        assert db.get(sreg.PersonQualification, (person, 'STUDENT')) is not None
    checks.append('Hired with an Indeed address: nothing sent, readable message back to Selection, still a Trainee in the Registry')

    # A real email still works exactly as before.
    code, data = call(real, mgr_id)
    assert code == 200 and data['status'] == 'sent' and sent[-1]['to_address'] == 'real.person@example.invalid', (code, data)
    checks.append('A real email is invited and emailed as before')

    # Invite student (by hand), same candidate: the Indeed address is refused, the real one works.
    with F() as db:
        actor = db.get(m.RFOneAccount, mgr_id)
        try:
            en.issue(db, actor=actor, email='abc123def456@indeedemail.com', selection_id=relay)
            raise AssertionError('Indeed address accepted')
        except ValueError as exc:
            assert 'Indeed forwarding address' in str(exc)
        db.rollback()
        try:
            en.issue(db, actor=actor, email='walkin@indeedemail.com', name='Walk In')
            raise AssertionError('Indeed address accepted for a direct invitation')
        except ValueError as exc:
            assert 'Indeed forwarding address' in str(exc)
        db.rollback()
        inv, token = en.issue(db, actor=actor, email='their.real.email@example.invalid', selection_id=relay)
        assert inv.email == 'their.real.email@example.invalid' and inv.selection_id == relay
        db.commit()
    checks.append('Invite student: Indeed address refused for Selection and direct invitations; the real email for the same candidate works')

# The form warns before sending.
js = (HERE / 'static' / 'js' / 'training-enrollment.js').read_text(encoding='utf-8')
assert 'indeedemail.com' in js and 'setCustomValidity' in js and 'This is an Indeed forwarding address. Ask for their real email.' in js
checks.append('Invite student form warns on an Indeed address and will not submit it')

print(json.dumps({'passed': len(checks), 'checks': checks}, indent=1))
