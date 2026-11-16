"""Synthetic, disposable HTTP test: upload extracts facts but never evaluates."""
import os, re, tempfile, shutil
from io import BytesIO
from unittest.mock import patch
TMP=tempfile.mkdtemp(prefix='selection_upload_only_')
os.environ['RFONE_DATABASE_URL']='sqlite:///'+(TMP+'/test.db').replace(os.sep,'/')
os.environ['RFONE_SELECTION_UPLOAD_DIR']=TMP+'/uploads'
os.environ['RFONE_SELECTION_REQUIRE_RFONE_LOGIN']='1'
os.environ['RFONE_WEB_BASE_URL']='http://localhost:5097'
os.environ['RFONE_FLASK_SECRET_KEY']='synthetic-upload-only'
os.environ['RFONE_UI_LANGUAGE']='it'   # assertions use the local Italian UI labels (A7, 2026-11-15)
for key in ('RFONE_SELECTION_DOCUMENT_BUCKET','RFONE_PUBLIC_BASE_URL','RFONE_SELECTION_AI','RFONE_SELECTION_AI_CV'):
    os.environ.pop(key,None)
import app
from sqlalchemy import select,func
from rfone_data_store import models as m, rfone_account_service as accounts, rfone_web_session as shared
from rfone_data_store.selection import workspace_models as ws,requirements_service as req
from workspace import engine,sp_routes,ai_adapter,routes
CV="""Synthetic Resume Person
resume.only@example.test
(407) 555-0101
Orlando, FL

SUMMARY
Experienced hospitality worker.

EXPERIENCE
Server, Trattoria Esempio, Orlando, FL | Jan 2020 - Dec 2023
- Served tables and trained new colleagues.

EDUCATION
Example College
Diploma in Hospitality
2018 - 2019

SKILLS
Table service, POS systems

LANGUAGES
English (fluent), Italian (native)

CERTIFICATIONS
Food Safety - Example Institute - 2022
"""
try:
    app.app.config['TESTING']=True
    with app.SessionFactory() as db:
        owner=accounts.create_account(db,username='synthetic-owner',display_name='Synthetic Owner',password='synthetic-password-1',is_admin=True)
        accounts.set_domain_access(db,account_id=owner.id,domain_code='SELECTION',enabled=True,role_code=None)
        rid=routes._restaurant_id(db)
        auth=(owner.id,owner.session_version)
        positions=[]
        for role in ('SERVER','FOOD_RUNNER'):
            r=req.create_requirement_set(db,restaurant_id=rid,name='Synthetic '+role,target_role=role)
            snap=req.create_requirement_set_snapshot(db,r.id)
            p=ws.Position(title='Synthetic '+role,role_code=role,location_label='Synthetic location',timezone='America/New_York',status='OPEN',manager_account_id=owner.id,created_by_account_id=owner.id,requirement_set_id=r.id,approved_snapshot_id=snap.id,
                organization_context_json='{"configuration":{"cv_evaluation":true,"cv_questions":true}}')
            db.add(p);db.flush();positions.append(p.id)
        db.commit()
    client=app.app.test_client()
    with client.session_transaction() as sess:
        sess[shared.SESSION_ACCOUNT_KEY],sess[shared.SESSION_VERSION_KEY]=auth
        sess[routes.CURRENT_JOB_KEY]=positions[1]
    ai_adapter.POLICY.ai_enabled=ai_adapter.POLICY.cv_ai_authorized=True
    with patch.object(engine,'analyze',side_effect=AssertionError('Evaluation forbidden')) as analysis,patch.object(sp_routes,'_queue',side_effect=AssertionError('Queue forbidden')) as queue,patch.object(ai_adapter,'_REAL_GENERATE_JSON',side_effect=AssertionError('AI forbidden')) as ai:
        for pid in positions:
            page=client.get(f'/selection/posizioni/{pid}/sp/upload?modal=1')
            assert page.status_code==200,page.status_code
            token=re.search(r'name="csrf_token" value="([^"]+)"',page.get_data(as_text=True)).group(1)
            response=client.post(f'/selection/posizioni/{pid}/sp/upload',data={'csrf_token':token,'modal':'1','cv':(BytesIO(CV.encode()),'synthetic.txt')},content_type='multipart/form-data')
            assert response.status_code==200,response.get_data(as_text=True)
            assert '1 nuovi CV caricati' in response.get_data(as_text=True)
            duplicate=client.post(f'/selection/posizioni/{pid}/sp/upload',data={'csrf_token':token,'modal':'1','cv':[(BytesIO(CV.encode()),'synthetic.txt'),(BytesIO(b'invalid'),'invalid.exe')]},content_type='multipart/form-data')
            html=duplicate.get_data(as_text=True)
            assert '1 duplicati ignorati' in html and '1 file non caricati' in html
        with app.SessionFactory() as db:
            pcs=list(db.scalars(select(ws.PositionCandidate).order_by(ws.PositionCandidate.id)))
            for pc in pcs:
                details=client.get(f'/selection/posizioni/{pc.position_id}/resume/{pc.id}/dati')
                assert details.status_code==200
                assert 'resume.only@example.test' in details.get_data(as_text=True)
                assert 'Table service' in details.get_data(as_text=True)
                original=client.get(f'/selection/posizioni/{pc.position_id}/candidati/{pc.id}/cv-originale?modal=1')
                assert original.status_code==200
                assert original.data==CV.encode()
                wrong=positions[1] if pc.position_id==positions[0] else positions[0]
                assert client.get(f'/selection/posizioni/{wrong}/resume/{pc.id}/dati').status_code==404
        upload_html=client.get(f'/selection/posizioni/{positions[0]}/sp/upload?modal=1').get_data(as_text=True)
        assert '<th>Ultima esperienza</th>' not in upload_html and '<th>File</th>' not in upload_html
        assert 'Apri CV originale' in upload_html and 'data-resume-details' in upload_html
        analysis.assert_not_called();queue.assert_not_called();ai.assert_not_called()
    with client.session_transaction() as sess:
        assert sess[routes.CURRENT_JOB_KEY]==positions[1]
    with app.SessionFactory() as db:
        assert db.scalar(select(func.count()).select_from(ws.Proposal))==0
        assert db.scalar(select(func.count()).select_from(m.FitAssessment))==0
        assert db.scalar(select(func.count()).select_from(ws.PositionCandidate))==2
        candidate=db.scalars(select(m.Candidate)).first()
        assert candidate.email=='resume.only@example.test'
        assert candidate.work_history and candidate.skills and candidate.language_records and candidate.certifications
        assert db.get(m.RawResume,candidate.raw_resume_id).raw_text==CV.strip()
    dashboard=client.get('/selection/').get_data(as_text=True)
    assert dashboard.count('>Carica Resume</a>')==2 and dashboard.count('>Modifica</a>')==2 and dashboard.count('>Seleziona e valorizza la PDL</a>')==2
    assert client.get(f'/selection/posizioni/{positions[0]}/sp/upload').status_code==200
    client.get(f'/selection/posizioni/{positions[0]}/job?modal=1')
    with client.session_transaction() as sess:
        assert sess[routes.CURRENT_JOB_KEY]==positions[1]
    print('PASS: actual extraction and storage, both SP and ordinary PDL, duplicate/error handling, no evaluation/queue/AI, context preserved, three row actions')
finally:
    app._engine.dispose()
    shutil.rmtree(TMP)
