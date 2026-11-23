# Run: python test_practical_test.py "<AWSSelection>/Selection" <output folder>  (throwaway SQLite, fake people, nothing sent)
"""Practical test check: real Selection app, throwaway SQLite, fake people, nothing sent."""
import os, re, sys, tempfile
from io import BytesIO
SEL = sys.argv[1]; OUT = sys.argv[2]
TMP = tempfile.mkdtemp(prefix='practest_')
os.environ.update(RFONE_DATABASE_URL='sqlite:///' + (TMP + '/t.db').replace(os.sep, '/'), RFONE_SELECTION_UPLOAD_DIR=TMP + '/up',
                  RFONE_SELECTION_REQUIRE_RFONE_LOGIN='1', RFONE_WEB_BASE_URL='https://rfone.example.test',
                  RFONE_FLASK_SECRET_KEY='practical-test-check')
for k in ('RFONE_SELECTION_DOCUMENT_BUCKET', 'RFONE_PUBLIC_BASE_URL', 'RFONE_SELECTION_AI', 'RFONE_SELECTION_AI_CV',
          'RFONE_SMS_ORIGINATION_IDENTITY', 'RFONE_SELECTION_CV_RECEIPT_CENTRAL'):
    os.environ.pop(k, None)
os.chdir(SEL); sys.path[:0] = [SEL, os.path.join(os.path.dirname(SEL), 'RF-One Data Store')]
import app
from sqlalchemy import select
from rfone_data_store import models as m, rfone_account_service as accounts, rfone_web_session as shared
from rfone_data_store.selection import workspace_models as ws, requirements_service as req
from workspace import routes, careers, mail_delivery, training_invite, schema, practical_test as pt
m.Base.metadata.create_all(app._engine)
print('PROVISION includes table:', 'selection_workspace_practical_tests' in schema.provision(app._engine))
print('VERIFY requires table:', any(t.name == 'selection_workspace_practical_tests' for t in schema.required_tables()))
codes = []; invites = []
careers.deliver_code = lambda **k: codes.append(k['code'])
mail_delivery.enqueue = lambda *a, **k: type('R', (), {'next_attempt_at': None})()


def fake_invite(base, **k):
    invites.append(k)
    return 'off', ''


training_invite.request_invite = fake_invite
with app.SessionFactory() as db:
    owner = accounts.create_account(db, username='giovanna', display_name='Giovanna Example', password='synthetic-password-1', is_admin=True)
    accounts.set_domain_access(db, account_id=owner.id, domain_code=routes.SELECTION_DOMAIN, enabled=True, role_code='OWNER')
    db.commit()
    rid = routes._restaurant_id(db)
    r = req.create_requirement_set(db, restaurant_id=rid, name='Server', target_role='SERVER')
    snap = req.create_requirement_set_snapshot(db, r.id)
    p = ws.Position(title='Server', role_code='SERVER', location_label='Mount Dora', timezone='America/New_York', status='OPEN',
                    manager_account_id=owner.id, created_by_account_id=owner.id, requirement_set_id=r.id,
                    approved_snapshot_id=snap.id, headcount=4)
    db.add(p); db.commit(); tok, pid, oid, over = p.public_token, p.id, owner.id, owner.session_version
c = app.app.test_client()
job = f'/selection/jobs/{tok}'
t = re.search(r'name="csrf_token" value="([^"]+)"', c.get(job).get_data(as_text=True)).group(1)
c.post(f'{job}/account/code', data={'csrf_token': t, 'full_name': 'Jordan Example', 'email': 'jordan@example.test',
                                     'password': 'synthetic-pass-1', 'channel': 'EMAIL'})
c.post(f'{job}/account/confirm', data={'csrf_token': t, 'email': 'jordan@example.test', 'code': codes[-1]})
cv = "Jordan Example\njordan@example.test\n\nEXPERIENCE\nServer, Trattoria Esempio, Orlando, FL | 2021 - 2024\n"
c.post(job, data={'csrf_token': t, 'consent': '1', 'cv': (BytesIO(cv.encode()), 'resume.txt')}, content_type='multipart/form-data')
with app.SessionFactory() as db:
    pc_id = db.scalars(select(ws.PositionCandidate.id)).first()
print('candidate created:', pc_id)
staff = app.app.test_client()
with staff.session_transaction() as s:
    s[shared.SESSION_ACCOUNT_KEY] = oid
    s[shared.SESSION_VERSION_KEY] = over
    s[shared.SESSION_CSRF_KEY] = 'csrf-x'
cand = f'/selection/posizioni/{pid}/candidati/{pc_id}'
fails = 0


def check(cond, msg):
    global fails
    print(('PASS ' if cond else 'FAIL ') + msg)
    fails += 0 if cond else 1


def decisions():
    with app.SessionFactory() as db:
        return [d.decision for d in db.scalars(select(ws.Decision))]


def tests():
    with app.SessionFactory() as db:
        return [(x.result, x.menu_faq_ok) for x in pt.history(db, pc_id)]


def flashes(resp):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', staff.get(resp.headers['Location']).get_data(as_text=True)))


html = staff.get(cand).get_data(as_text=True)
check('Practical selection test' in html, 'candidate page shows the Practical selection test card')
check(re.search(r'value="HIRED"[^>]*disabled', html) is not None, 'Send to Training is disabled before the test')
open(os.path.join(OUT, '1-before.html'), 'w', encoding='utf-8').write(html)
dec = f'/selection/posizioni/{pid}/decisioni'
r = staff.post(dec, data={'csrf_token': 'csrf-x', 'pc_id': pc_id, 'decision': 'HIRED', 'back': cand})
check(decisions() == [] and 'needs an approved practical selection test' in flashes(r), 'Send to Training refused without a test, even if forced')
staff.post(dec, data={'csrf_token': 'csrf-x', 'quick': f'{pc_id}:HIRED', 'back': cand})
check(decisions() == [], 'quick card button refused too')
url = f'{cand}/prova-pratica'
base = {'csrf_token': 'csrf-x', 'test_date': '2026-11-23', 'evaluator': 'Tatiana', 'note': 'Friendly with guests, a bit slow clearing.'}
r = staff.post(url, data={**base, 'result': 'APPROVED'})
check(tests() == [] and 'Menu and FAQs box ticked' in flashes(r), 'Approved refused without Menu and FAQs')
staff.post(url, data={**base, 'result': 'APPROVED', 'menu_faq_ok': '1', 'test_date': '2099-01-01'})
check(tests() == [], 'future date refused')
staff.post(url, data={**base, 'result': 'APPROVED', 'menu_faq_ok': '1', 'note': ''})
check(tests() == [], 'missing attitude note refused')
staff.post(url, data={**base, 'result': 'NOT_APPROVED'})
check(tests() == [('NOT_APPROVED', False)], 'Not approved recorded')
staff.post(dec, data={'csrf_token': 'csrf-x', 'pc_id': pc_id, 'decision': 'HIRED', 'back': cand})
check(decisions() == [], 'Send to Training still refused after Not approved')
staff.post(url, data={**base, 'result': 'APPROVED', 'menu_faq_ok': '1', 'note': 'Retest: calm, knew the specials and the FAQs.'})
check(tests()[0] == ('APPROVED', True), 'Approved recorded, newest counts')
html = staff.get(cand).get_data(as_text=True)
check(re.search(r'value="HIRED"[^>]*disabled', html) is None, 'Send to Training unlocked after approval')
open(os.path.join(OUT, '2-approved.html'), 'w', encoding='utf-8').write(html)
staff.post(dec, data={'csrf_token': 'csrf-x', 'pc_id': pc_id, 'decision': 'HIRED', 'back': cand})
check(decisions() == ['HIRED'] and len(invites) == 1, 'Send to Training works and asks Training for the invitation')
with app.SessionFactory() as db:
    ev = [e.detail for e in db.scalars(select(ws.WorkspaceEvent).where(ws.WorkspaceEvent.kind == 'PRACTICAL_TEST'))]
check(len(ev) == 2 and 'by Tatiana' in ev[-1], 'job history records each result: ' + (ev[-1][:100] if ev else ''))
other = app.app.test_client()
other.post(url, data={**base, 'result': 'APPROVED', 'menu_faq_ok': '1'})
check(len(tests()) == 2, 'not signed in: nothing recorded')
print('FAILURES', fails)
