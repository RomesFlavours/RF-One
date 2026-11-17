"""Synthetic, disposable HTTP test: the "we received your résumé" receipt through the RF-One Email Service.

Switch RFONE_SELECTION_CV_RECEIPT_CENTRAL=1, a throwaway SQLite database with the four Email Service
tables, and no sending at all (no worker runs here; nothing reaches the production queue).

    python test_cv_receipt_email_service_http.py
"""
import os, re, tempfile
from datetime import datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import patch
TMP = tempfile.mkdtemp(prefix='selection_cv_receipt_central_')
os.environ['RFONE_DATABASE_URL'] = 'sqlite:///' + (TMP + '/test.db').replace(os.sep, '/')
os.environ['RFONE_SELECTION_UPLOAD_DIR'] = TMP + '/uploads'
os.environ['RFONE_SELECTION_REQUIRE_RFONE_LOGIN'] = '1'
os.environ['RFONE_WEB_BASE_URL'] = 'http://localhost:5097'
os.environ['RFONE_FLASK_SECRET_KEY'] = 'synthetic-receipt-central'
os.environ['RFONE_SELECTION_CV_RECEIPT_CENTRAL'] = '1'
for key in ('RFONE_SELECTION_DOCUMENT_BUCKET', 'RFONE_PUBLIC_BASE_URL', 'RFONE_SELECTION_AI', 'RFONE_SELECTION_AI_CV'):
    os.environ.pop(key, None)
import app
from sqlalchemy import select, func, update
from rfone_data_store import models as m, email_service as es
from rfone_data_store import rfone_account_service as accounts, rfone_web_session as shared
from rfone_data_store.selection import workspace_models as ws, requirements_service as req
from workspace import routes, mail_delivery, cv_received, cv_delete, sp_routes

m.Base.metadata.create_all(app._engine, tables=es.TABLES, checkfirst=True)
failures = []


def check(label, ok, detail=''):
    print(('PASS ' if ok else 'FAIL ') + label + ('' if ok or not detail else f'  [{detail}]'))
    if not ok:
        failures.append(label)


def cv(name, email, extra=''):
    return f"{name}\n{email}\n(407) 555-0101\n\nEXPERIENCE\nServer, Trattoria Esempio, Orlando, FL | Jan 2020 - Dec 2023\n- Served tables.{extra}\n"


def central(db):
    return list(db.scalars(select(es.EmailRequest).order_by(es.EmailRequest.created_at)))


def legacy(db):
    return list(db.scalars(select(mail_delivery.EmailOutbox).where(mail_delivery.EmailOutbox.source_key.like('cv-received:%'))))


try:
    app.app.config['TESTING'] = True
    with app.SessionFactory() as db:
        owner = accounts.create_account(db, username='synthetic-owner', display_name='Synthetic Owner',
                                        password='synthetic-password-1', is_admin=True)
        accounts.set_domain_access(db, account_id=owner.id, domain_code='SELECTION', enabled=True, role_code=None)
        rid = routes._restaurant_id(db)
        r = req.create_requirement_set(db, restaurant_id=rid, name='Synthetic server', target_role='SERVER')
        snap = req.create_requirement_set_snapshot(db, r.id)
        p = ws.Position(title='Server', role_code='SERVER', location_label='Mount Dora', timezone='America/New_York', status='OPEN',
                        manager_account_id=owner.id, created_by_account_id=owner.id, requirement_set_id=r.id, approved_snapshot_id=snap.id)
        db.add(p); db.commit()
        pid, oid, auth = p.id, owner.id, (owner.id, owner.session_version)
    client = app.app.test_client()
    with client.session_transaction() as s:
        s[shared.SESSION_ACCOUNT_KEY], s[shared.SESSION_VERSION_KEY] = auth

    def upload(name, body):
        page = client.get(f'/selection/posizioni/{pid}/sp/upload?modal=1').get_data(as_text=True)
        t = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        html = client.post(f'/selection/posizioni/{pid}/sp/upload', content_type='multipart/form-data',
                           data={'csrf_token': t, 'modal': '1', 'cv': (BytesIO(body.encode()), name)}).get_data(as_text=True)
        return '1 nuovi CV caricati' in html or '1 new CVs uploaded' in html

    # 1. A staff upload creates one central request, held 15 minutes, and nothing in the old outbox.
    ok = upload('alice.txt', cv('Alice Example', 'alice@example.test'))
    with app.SessionFactory() as db:
        rows, old = central(db), legacy(db)
        pc = db.scalars(select(ws.PositionCandidate)).first()
        held = rows and rows[0].available_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc) + timedelta(minutes=14)
    check('upload: one central request to the candidate, Domain SELECTION, event and key from the upload, held 15 minutes; none in the old outbox',
          ok and len(rows) == 1 and not old and rows[0].domain == 'SELECTION' and rows[0].recipient == 'alice@example.test'
          and rows[0].event == f'selection.cv_received:{pid}:{pc.id}' and rows[0].dedup_key == f'cv_received:{pc.id}:v1'
          and rows[0].status == 'QUEUED' and held and rows[0].body.startswith('Hi Alice,'),
          [(r.recipient, r.event, r.status) for r in rows])
    alice_pc = pc.id

    # 2. Replays never duplicate: the same upload again, the same key directly, the same person with another CV.
    with app.SessionFactory() as db:
        again = cv_received.queue(db, alice_pc)
        r0 = central(db)[0]
        same = es.enqueue(db, domain='SELECTION', recipient=r0.recipient, subject=r0.subject, body=r0.body,
                          event=r0.event, dedup_key=r0.dedup_key); db.commit()
    upload('alice-2.txt', cv('Alice Example', 'alice@example.test', extra='\n- Trained new colleagues.'))
    with app.SessionFactory() as db:
        n = len(central(db))
    check('replay: queuing the same upload again, the same key, or the same person with a second CV creates no duplicate',
          again is False and same.id == r0.id and n == 1, n)

    # 3. Someone already emailed through the old outbox (e.g. today's catch-up) never gets a second one.
    with app.SessionFactory() as db:
        pc_b = None
    with patch.dict(os.environ, {'RFONE_SELECTION_CV_RECEIPT_CENTRAL': '0'}):
        upload('bruno.txt', cv('Bruno Example', 'bruno@example.test'))
    with app.SessionFactory() as db:
        bruno = db.scalars(select(ws.PositionCandidate).order_by(ws.PositionCandidate.id.desc())).first()
        before = len(central(db)); queued_again = cv_received.queue(db, bruno.id)
        after, old = len(central(db)), legacy(db)
    check('switch off: the old outbox is used as before; switching on later never sends that person a second email',
          len(old) == 1 and old[0].recipient == 'bruno@example.test' and queued_again is False and after == before)

    # 4. Delete CV within the 15 minutes cancels the central email; once the worker took it, the CV stays.
    upload('carla.txt', cv('Carla Example', 'carla@example.test'))
    upload('dario.txt', cv('Dario Example', 'dario@example.test'))
    with app.SessionFactory() as db:
        pcs = {db.get(m.Candidate, x.candidate_id).email: x.id for x in db.scalars(select(ws.PositionCandidate))}
        carla, dario = pcs['carla@example.test'], pcs['dario@example.test']
        blocked_before = cv_delete.blockers(db, [db.get(ws.PositionCandidate, carla)])[carla]
        db.execute(update(es.EmailRequest).where(es.EmailRequest.event == f'selection.cv_received:{pid}:{dario}')
                   .values(status='ACCEPTED', attempts=1)); db.commit()
        blocked_sent = cv_delete.blockers(db, [db.get(ws.PositionCandidate, dario)])[dario]
    res = cv_delete.delete_cv(app.SessionFactory(), documents=app.documents if hasattr(app, 'documents') else routes._cfg.documents,
                              position_id=pid, pc_id=carla, actor_id=oid, actor_name='Synthetic Owner',
                              load_state=sp_routes.state, save_state=sp_routes.save_state)
    with app.SessionFactory() as db:
        carla_req = db.scalar(select(es.EmailRequest).where(es.EmailRequest.event == f'selection.cv_received:{pid}:{carla}'))
        audit = db.scalar(select(func.count()).select_from(es.EmailAudit).where(es.EmailAudit.request_id == carla_req.id))
    check('Delete CV within 15 minutes: allowed, the central email is CANCELLED (audited), the CV is gone',
          blocked_before == [] and res['status'] == 'DELETED' and carla_req.status == 'CANCELLED' and audit == 1,
          (blocked_before, res['status'], carla_req.status))
    check('Delete CV after the worker took the email: refused, the email to the candidate is recorded',
          blocked_sent == ['messages to the candidate are recorded'], blocked_sent)

    # 5. A failure of the Email Service never blocks or undoes the upload.
    with patch.object(es, 'enqueue', side_effect=RuntimeError('service down')):
        kept = upload('emma.txt', cv('Emma Example', 'emma@example.test'))
    with app.SessionFactory() as db:
        emma = [x for x in db.scalars(select(ws.PositionCandidate)) if db.get(m.Candidate, x.candidate_id).email == 'emma@example.test']
        emma_req = db.scalar(select(func.count()).select_from(es.EmailRequest).where(es.EmailRequest.recipient == 'emma@example.test'))
    check('a failure in the Email Service keeps the upload and queues nothing (no half-written request)',
          kept and len(emma) == 1 and emma_req == 0)

    # 6. The catch-up page counts central receipts as contact and sends through the central service.
    page = client.get('/selection/cv-received/catch-up').get_data(as_text=True)
    listed = sorted(set(re.findall(r'[\w.]+@example\.test', page)))
    check('catch-up: lists only Emma (the others already have a receipt in either path)', listed == ['emma@example.test'], listed)
    t = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    client.post('/selection/cv-received/catch-up', data={'csrf_token': t})
    with app.SessionFactory() as db:
        emma_req = db.scalar(select(es.EmailRequest).where(es.EmailRequest.recipient == 'emma@example.test'))
        no_new_legacy = len(legacy(db)) == 1
    check('catch-up Send goes through the central service, not the old outbox',
          emma_req is not None and emma_req.domain == 'SELECTION' and no_new_legacy)
    check('the receipt only confirms receipt: no interview, shortlist or decision promised',
          all(w not in emma_req.body.lower() for w in ('interview', 'shortlist', 'selected', 'congratulations')))
finally:
    app._engine.dispose()
print('ALL PASSED' if not failures else f'{len(failures)} FAILED: {failures}')
