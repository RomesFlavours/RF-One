# Run: python test_not_selected_email.py "<AWSSelection>/Selection"  (throwaway SQLite, fake people, nothing sent)
"""Automatic Not selected email: real Selection app, throwaway SQLite, nothing sent."""
import os, re, sys, tempfile
from datetime import datetime, timedelta, timezone
from io import BytesIO
SEL = sys.argv[1]
TMP = tempfile.mkdtemp(prefix='reject_')
os.environ.update(RFONE_DATABASE_URL='sqlite:///' + (TMP + '/t.db').replace(os.sep, '/'), RFONE_SELECTION_UPLOAD_DIR=TMP + '/up',
                  RFONE_SELECTION_REQUIRE_RFONE_LOGIN='1', RFONE_WEB_BASE_URL='https://rfone.example.test',
                  RFONE_FLASK_SECRET_KEY='reject-check', RFONE_SELECTION_CV_RECEIPT_CENTRAL='1', RFONE_SELECTION_AUTO_REJECTION='1')
for k in ('RFONE_SELECTION_DOCUMENT_BUCKET', 'RFONE_PUBLIC_BASE_URL', 'RFONE_SELECTION_AI', 'RFONE_SELECTION_AI_CV', 'RFONE_SMS_ORIGINATION_IDENTITY'):
    os.environ.pop(k, None)
os.chdir(SEL); sys.path[:0] = [SEL, os.path.join(os.path.dirname(SEL), 'RF-One Data Store')]
import app
from sqlalchemy import select
from rfone_data_store import models as m, rfone_account_service as accounts, rfone_web_session as shared, email_service as es
from rfone_data_store.selection import workspace_models as ws, requirements_service as req
from workspace import routes, careers, not_selected_email as nse
m.Base.metadata.create_all(app._engine)
codes = []
careers.deliver_code = lambda **k: codes.append(k['code'])
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


def apply(name, email):
    c = app.app.test_client(); job = f'/selection/jobs/{tok}'
    t = re.search(r'name="csrf_token" value="([^"]+)"', c.get(job).get_data(as_text=True)).group(1)
    c.post(f'{job}/account/code', data={'csrf_token': t, 'full_name': name, 'email': email, 'password': 'synthetic-pass-1', 'channel': 'EMAIL'})
    c.post(f'{job}/account/confirm', data={'csrf_token': t, 'email': email, 'code': codes[-1]})
    cv = f"{name}\n{email}\n\nEXPERIENCE\nServer, Trattoria Esempio, Orlando, FL | 2021 - 2024\n"
    c.post(job, data={'csrf_token': t, 'consent': '1', 'cv': (BytesIO(cv.encode()), 'resume.txt')}, content_type='multipart/form-data')
    with app.SessionFactory() as db:
        return db.scalars(select(ws.PositionCandidate.id).order_by(ws.PositionCandidate.id.desc())).first()


ana, ben, cara, dan, eve = (apply(n, e) for n, e in [('Ana Example', 'ana@example.test'), ('Ben Example', 'ben@example.test'),
                                                     ('Cara Example', 'cara@example.test'), ('Dan Example', 'dan@example.test'),
                                                     ('Eve Example', 'eve@example.test')])
staff = app.app.test_client()
with staff.session_transaction() as s:
    s[shared.SESSION_ACCOUNT_KEY] = oid; s[shared.SESSION_VERSION_KEY] = over; s[shared.SESSION_CSRF_KEY] = 'csrf-x'
dec = f'/selection/posizioni/{pid}/decisioni'
fails = 0


def check(cond, msg):
    global fails
    print(('PASS ' if cond else 'FAIL ') + msg); fails += 0 if cond else 1


def rejections(pc_id=None):
    with app.SessionFactory() as db:
        q = select(es.EmailRequest).where(es.EmailRequest.event.like('selection.not_selected:%'))
        rows = db.scalars(q).all()
        return [x for x in rows if pc_id is None or x.event.endswith(f':{pc_id}')]


def decide(pcs, decision, reason='', note=''):
    data = {'csrf_token': 'csrf-x', 'pc_id': pcs, 'decision': decision, 'reason': reason, 'note': note, 'back': '/selection/'}
    return staff.post(dec, data=data)


r = decide([ana], 'NOT_SELECTED', 'OTHER_CANDIDATE_CHOSEN')
rows = rejections(ana)
check(len(rows) == 1 and rows[0].status == 'QUEUED' and rows[0].recipient == 'ana@example.test', 'Not selected queues one email to the candidate')
avail = rows[0].available_at if rows[0].available_at.tzinfo else rows[0].available_at.replace(tzinfo=timezone.utc)
check(timedelta(minutes=110) < avail - datetime.now(timezone.utc) <= timedelta(minutes=121), 'it waits about 2 hours before going out')
check('Hi Ana,' in rows[0].body and 'Server position at Rome' in rows[0].body and 'Mount Dora' in rows[0].body, 'greets by first name, names job and location')
check('Another candidate' not in rows[0].body and 'OTHER' not in rows[0].body, 'the internal reason is never in the email')
check('—' not in rows[0].body and '—' not in rows[0].subject, 'no em dashes')
print('---- EMAIL ----\nSubject: ' + rows[0].subject + '\n' + rows[0].body + '\n---------------')
decide([ana], 'UNDECIDED', note='Rejection withdrawn: back in the ranking')
check([x.status for x in rejections(ana)] == ['CANCELLED'], 'changing the decision within 2 hours cancels it')
decide([ana], 'NOT_SELECTED', 'OTHER_CANDIDATE_CHOSEN')
check(sorted(x.status for x in rejections(ana)) == ['CANCELLED', 'QUEUED'], 'rejected again: a new email is queued')
decide([ana], 'NOT_SELECTED', 'POSITION_FILLED')
check(len(rejections(ana)) == 2, 'recording Not selected twice does not send twice')
decide([ben], 'NOT_SELECTED', 'CANDIDATE_DECLINED')
check(rejections(ben) == [], 'no email when the candidate declined')
with app.SessionFactory() as db:
    db.add(ws.Message(position_candidate_id=cara, kind='REJECTION', body='Hand-written note', source='TEMPLATE', status='APPROVED',
                      approved_by_name='Giovanna', approved_at=ws.utcnow())); db.commit()
decide([cara], 'NOT_SELECTED', 'OTHER_CANDIDATE_CHOSEN')
check(rejections(cara) == [], 'no automatic email when a Not selected message was already approved by hand')
r = decide([dan, eve], 'NOT_SELECTED', 'POSITION_FILLED')
d, e = rejections(dan), rejections(eve)
check(len(d) == 1 and len(e) == 1, 'bulk decision queues one email each')
gap = abs((e[0].available_at - d[0].available_at).total_seconds())
check(25 <= gap <= 35, f'bulk emails are spaced out ({gap:.0f} s apart)')
os.environ['RFONE_SELECTION_AUTO_REJECTION'] = '0'
decide([ben], 'NOT_SELECTED', 'OTHER_CANDIDATE_CHOSEN')
check(rejections(ben) == [], 'switched off: nothing is sent')
os.environ['RFONE_SELECTION_AUTO_REJECTION'] = '1'
with app.SessionFactory() as db:
    ev = [x.detail for x in db.scalars(select(ws.WorkspaceEvent).where(ws.WorkspaceEvent.kind == 'NOT_SELECTED_EMAIL'))]
check(any('queued' in x for x in ev) and any('cancelled' in x for x in ev), 'job history shows queued and cancelled')
with app.SessionFactory() as db:
    decided = {pcid: x for pcid, x in [(d_.position_candidate_id, d_.decision) for d_ in db.scalars(select(ws.Decision).order_by(ws.Decision.id))]}
check(decided.get(ben) == 'NOT_SELECTED' and decided.get(dan) == 'NOT_SELECTED', 'decisions are always saved, email or not')
print('FAILURES', fails)
sys.exit(1 if fails else 0)
