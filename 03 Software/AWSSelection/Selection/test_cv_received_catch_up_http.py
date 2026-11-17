"""Synthetic, disposable HTTP test: the one-time "we received your résumé" catch-up page (Owner only).

    python test_cv_received_catch_up_http.py
"""
import os, re, tempfile
from datetime import datetime, timedelta
from io import BytesIO
TMP = tempfile.mkdtemp(prefix='selection_cv_catch_up_')
os.environ['RFONE_DATABASE_URL'] = 'sqlite:///' + (TMP + '/test.db').replace(os.sep, '/')
os.environ['RFONE_SELECTION_UPLOAD_DIR'] = TMP + '/uploads'
os.environ['RFONE_SELECTION_REQUIRE_RFONE_LOGIN'] = '1'
os.environ['RFONE_WEB_BASE_URL'] = 'http://localhost:5097'
os.environ['RFONE_FLASK_SECRET_KEY'] = 'synthetic-catch-up'
for key in ('RFONE_SELECTION_DOCUMENT_BUCKET', 'RFONE_PUBLIC_BASE_URL', 'RFONE_SELECTION_AI', 'RFONE_SELECTION_AI_CV'):
    os.environ.pop(key, None)
import app
from sqlalchemy import select, func, delete
from rfone_data_store import rfone_account_service as accounts, rfone_web_session as shared
from rfone_data_store.selection import workspace_models as ws, requirements_service as req
from workspace import routes, mail_delivery, cv_received

failures = []
def check(label, ok, detail=''):
    print(('PASS ' if ok else 'FAIL ') + label + ('' if ok or not detail else f'  [{detail}]'))
    if not ok: failures.append(label)

def cv(name, email):
    return f"{name}\n{email}\n(407) 555-0101\n\nEXPERIENCE\nServer, Trattoria Esempio, Orlando, FL | Jan 2020 - Dec 2023\n- Served tables.\n"

try:
    app.app.config['TESTING'] = True
    with app.SessionFactory() as db:
        owner = accounts.create_account(db, username='synthetic-owner', display_name='Synthetic Owner', password='synthetic-password-1', is_admin=True)
        mgr = accounts.create_account(db, username='synthetic-mgr', display_name='Synthetic Manager', password='synthetic-password-1', is_admin=False)
        for a in (owner, mgr):
            accounts.set_domain_access(db, account_id=a.id, domain_code='SELECTION', enabled=True, role_code=None)
        rid = routes._restaurant_id(db)
        jobs = {}
        for key, created in (('new', None), ('old', datetime(2026, 11, 10, 15, 0))):
            r = req.create_requirement_set(db, restaurant_id=rid, name='Synthetic ' + key, target_role='SERVER')
            snap = req.create_requirement_set_snapshot(db, r.id)
            p = ws.Position(title='Server', role_code='SERVER', location_label='Mount Dora', timezone='America/New_York', status='OPEN',
                            manager_account_id=owner.id, created_by_account_id=owner.id, requirement_set_id=r.id, approved_snapshot_id=snap.id)
            db.add(p); db.flush()
            if created: p.created_at = created
            jobs[key] = p.id
        db.commit()
        auth = {'owner': (owner.id, owner.session_version), 'mgr': (mgr.id, mgr.session_version)}

    def client(who):
        c = app.app.test_client()
        with c.session_transaction() as s:
            s[shared.SESSION_ACCOUNT_KEY], s[shared.SESSION_VERSION_KEY] = auth[who]
        return c
    own = client('owner')

    def upload(pid, files):
        page = own.get(f'/selection/posizioni/{pid}/sp/upload?modal=1').get_data(as_text=True)
        t = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        own.post(f'/selection/posizioni/{pid}/sp/upload', content_type='multipart/form-data',
                 data={'csrf_token': t, 'modal': '1', 'cv': [(BytesIO(b.encode()), n) for n, b in files]})

    upload(jobs['new'], [('a.txt', cv('Alice Waiting', 'alice@example.test')), ('b.txt', cv('Bruno Decided', 'bruno@example.test')),
                         ('c.txt', cv('Carla Noemail', ''))])
    upload(jobs['old'], [('d.txt', cv('Dario Oldjob', 'dario@example.test'))])
    with app.SessionFactory() as db:
        # These CVs arrived before the email existed: no receipt was queued for them.
        db.execute(delete(mail_delivery.EmailOutbox)); db.commit()
        pcs = {pc.declared_name or db.get(__import__('rfone_data_store.models', fromlist=['m']).Candidate, pc.candidate_id).full_name: pc
               for pc in db.scalars(select(ws.PositionCandidate))}
        bruno = next(pc for n, pc in pcs.items() if n and n.startswith('Bruno'))
        db.add(ws.Decision(position_candidate_id=bruno.id, decision='ON_HOLD', reason_code=None, note=None, proposal_group=None,
                           proposal_source=None, differs_from_proposal=False, actor_account_id=auth['owner'][0], actor_name='synthetic'))
        db.commit()

    check('a Manager who is not Owner cannot open the catch-up page', client('mgr').get('/selection/cv-received/catch-up').status_code == 403)
    page = own.get('/selection/cv-received/catch-up').get_data(as_text=True)
    check('the list shows only the candidate who never heard from us (new Job, has an email, no decision)',
          'alice@example.test' in page and 'bruno@example.test' not in page and 'dario@example.test' not in page
          and '<strong>1</strong> candidates' in page, re.findall(r'[\w.]+@example\.test', page))
    with app.SessionFactory() as db:
        check('opening the page sends nothing', db.scalar(select(func.count()).select_from(mail_delivery.EmailOutbox)) == 0)
    t = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    refused = own.post('/selection/cv-received/catch-up', data={})
    with app.SessionFactory() as db:
        none_sent = db.scalar(select(func.count()).select_from(mail_delivery.EmailOutbox)) == 0
    check('Send without the security token is refused and sends nothing', refused.status_code == 302 and none_sent)
    r = own.post('/selection/cv-received/catch-up', data={'csrf_token': t}, follow_redirects=True)
    with app.SessionFactory() as db:
        rows = list(db.scalars(select(mail_delivery.EmailOutbox)))
        events = db.scalar(select(func.count()).select_from(ws.Event).where(ws.Event.kind == 'CV_RECEIVED_CATCH_UP'))
    check('Send queues exactly one email, to Alice, with the warm text, and logs it in the Job history',
          len(rows) == 1 and rows[0].recipient == 'alice@example.test' and rows[0].body.startswith('Hi Alice,')
          and 'Mount Dora' in rows[0].body and events == 1 and '1 emails queued' in r.get_data(as_text=True),
          [x.recipient for x in rows])
    page2 = own.get('/selection/cv-received/catch-up').get_data(as_text=True)
    own.post('/selection/cv-received/catch-up', data={'csrf_token': t})
    with app.SessionFactory() as db:
        n = db.scalar(select(func.count()).select_from(mail_delivery.EmailOutbox))
    check('pressing Send again sends nothing more; the page says nobody is waiting', n == 1 and 'Nobody is waiting' in page2, n)
    check('the catch-up starts from 14 Nov 2026 in Florida', cv_received.CATCH_UP_FROM_UTC == datetime(2026, 11, 14, 5, 0))
finally:
    app._engine.dispose()
print('ALL PASSED' if not failures else f'{len(failures)} FAILED: {failures}')
