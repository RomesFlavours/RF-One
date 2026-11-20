"""Synthetic-only automation configuration, versioning, retry and SMTP ack tests."""
import os,re,json,tempfile,shutil
from io import BytesIO
from unittest.mock import patch
TMP=tempfile.mkdtemp(prefix='selection_automations_')
os.environ['RFONE_DATABASE_URL']='sqlite:///'+(TMP+'/test.db').replace(os.sep,'/')
os.environ['RFONE_SELECTION_UPLOAD_DIR']=TMP+'/uploads'
os.environ['RFONE_SELECTION_REQUIRE_RFONE_LOGIN']='1'
os.environ['RFONE_WEB_BASE_URL']='http://localhost:5097'
os.environ['RFONE_FLASK_SECRET_KEY']='synthetic-automations'
for k in ('RFONE_SELECTION_DOCUMENT_BUCKET','RFONE_PUBLIC_BASE_URL','RFONE_SELECTION_AI','RFONE_SELECTION_AI_CV'):os.environ.pop(k,None)
# Provision the current local model in this disposable fixture, including the
# additive local-only criterion columns (production migrations are not involved).
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'RF-One Data Store'))
from sqlalchemy import create_engine
from workspace.schema import required_tables
from rfone_data_store.models import Base
fixture_engine=create_engine(os.environ['RFONE_DATABASE_URL'])
Base.metadata.create_all(fixture_engine)
fixture_engine.dispose()
import app
from sqlalchemy import select,func
from rfone_data_store import models as m,rfone_account_service as accounts,rfone_web_session as shared
from rfone_data_store.selection import workspace_models as ws,requirements_service as req
from workspace import routes,automations,mail_delivery
from workspace.action_models import AutomationItem,ActionRun

def post(path,payload):return client.post(path,data={'csrf_token':token,'payload':json.dumps(payload)})
def configure(kind,name,**kw):
 r=post('/selection/configurazioni/automazioni/salva',dict(kind=kind,name=name,description='Synthetic only',active=True,**kw))
 assert r.status_code==200,r.get_data(as_text=True)
 return r.json['code']
try:
 app.app.config['TESTING']=True;automations.initialize(app._engine)
 with app.SessionFactory() as db:
  owner=accounts.create_account(db,username='automation-owner',display_name='Synthetic Owner',password='synthetic-password-1',is_admin=True)
  accounts.set_domain_access(db,account_id=owner.id,domain_code='SELECTION',enabled=True,role_code=None)
  auth=(owner.id,owner.session_version);rid=routes._restaurant_id(db)
  reqset=req.create_requirement_set(db,restaurant_id=rid,name='Synthetic',target_role='SERVER')
  position=ws.Position(title='Synthetic job',role_code='SERVER',location_label='Synthetic location',timezone='America/New_York',status='OPEN',manager_account_id=owner.id,created_by_account_id=owner.id,requirement_set_id=reqset.id)
  db.add(position);db.commit();pid=position.id
 client=app.app.test_client()
 with client.session_transaction() as sess:sess[shared.SESSION_ACCOUNT_KEY],sess[shared.SESSION_VERSION_KEY]=auth
 html=client.get('/selection/configurazioni').get_data(as_text=True)
 token=re.search(r'<meta name="csrf-token" content="([^"]+)"',html).group(1)
 upload=client.post(f'/selection/posizioni/{pid}/sp/upload',data={'csrf_token':token,'modal':'1','cv':(BytesIO(b'Synthetic Person\nsynthetic@example.test\n\nEXPERIENCE\nServer, Bistro Prova, Orlando, FL | Jan 2020 - Dec 2023\n- Served tables'),'synthetic.txt')},content_type='multipart/form-data')
 assert upload.status_code==200
 with app.SessionFactory() as db:pc=db.scalar(select(ws.PositionCandidate));pcid=pc.id
 steps=[{'op':'note','text':'Synthetic note'},{'op':'email','subject':'Synthetic check','body':'Hi {candidate_name}, this is a synthetic transport test.'},{'op':'set_status','status':'DEEPEN'}]
 proc=configure('procedure','Synthetic procedure',steps=steps)
 action=configure('action','Synthetic action',procedure_code=proc)
 execute=f'/selection/posizioni/{pid}/candidati/{pcid}/azione'
 r=client.post(execute,data={'csrf_token':token,'action':action});assert r.status_code==302
 with app.SessionFactory() as db:
  run=db.scalar(select(ActionRun).where(ActionRun.action_code==action));assert run.status=='WAITING';runid=run.id
  assert db.scalar(select(func.count()).select_from(ws.Decision))==0
  assert db.scalar(select(func.count()).select_from(mail_delivery.EmailOutbox))==1
  assert db.scalar(select(func.count()).select_from(ws.Event).where(ws.Event.kind=='AUTOMATION_NOTE'))==1
 client.post(execute,data={'csrf_token':token,'action':action})
 with app.SessionFactory() as db:
  assert db.scalar(select(func.count()).select_from(mail_delivery.EmailOutbox))==1
  mail=mail_delivery.claim(db);db.commit()
 with app.app.test_request_context():
  with app.SessionFactory() as db:
   mail_delivery.acknowledge(db,dict(id=mail['id'],lease=mail['lease'],outcome='started'));db.commit()
  with app.SessionFactory() as db:
   mail_delivery.acknowledge(db,dict(id=mail['id'],lease=mail['lease'],outcome='failed',permanent=True,error='Synthetic temporary failure'));db.commit()
 with app.SessionFactory() as db:assert db.get(ActionRun,runid).status=='FAILED'
 client.post(execute,data={'csrf_token':token,'action':action})
 with app.SessionFactory() as db:
  assert db.scalar(select(func.count()).select_from(mail_delivery.EmailOutbox))==1
  assert db.scalar(select(func.count()).select_from(ws.Event).where(ws.Event.kind=='AUTOMATION_NOTE'))==1
  mail=mail_delivery.claim(db);db.commit()
 with app.app.test_request_context():
  with app.SessionFactory() as db:mail_delivery.acknowledge(db,dict(id=mail['id'],lease=mail['lease'],outcome='started'));db.commit()
  with app.SessionFactory() as db:mail_delivery.acknowledge(db,dict(id=mail['id'],lease=mail['lease'],outcome='sent'));db.commit()
 with app.SessionFactory() as db:
  run=db.get(ActionRun,runid);assert run.status=='SUCCEEDED' and run.completed_at
  assert len(run.attempts)==2 and run.attempts[-1]['status']=='SUCCEEDED'
  assert db.scalar(select(func.count()).select_from(ws.Decision))==1
 client.post(execute,data={'csrf_token':token,'action':action})
 configure('action','Renamed action',code=action,version=1,procedure_code=proc)
 configure('procedure','Edited procedure',code=proc,version=1,steps=[{'op':'set_status','status':'ON_HOLD'}])
 assert post('/selection/configurazioni/automazioni/salva',dict(kind='action',code=action,version=1,name='Stale',description='',active=True,procedure_code=proc)).status_code==422
 with app.SessionFactory() as db:
  run=db.get(ActionRun,runid);assert run.action_snapshot['name']=='Synthetic action' and run.procedure_snapshot['version']==1
  assert db.scalar(select(func.count()).select_from(ws.Decision))==1
 history=client.get(f'/selection/posizioni/{pid}/candidati/{pcid}/azioni/storico').json
 assert history['runs'][0]['status']=='Eseguita' and len(history['runs'][0]['attempts'])==2
 assert client.get(f'/selection/configurazioni/automazioni/{proc}/storico').status_code==404
 with app.SessionFactory() as db:
  assert len(db.get(AutomationItem,proc).revisions)==1
  assert len(db.get(AutomationItem,action).revisions)==1
 configuration=client.get('/selection/configurazioni').get_data(as_text=True)
 assert 'data-automation-history' not in configuration and 'automation-history-dialog' not in configuration
 with patch.object(automations.rule_ai,'generate',return_value={'reply':'Proposta sintetica','steps':[{'op':'note','text':'AI test note'}]}):
  proposed=post('/selection/configurazioni/automazioni/proposta',{'messages':[{'role':'user','content':'Add a note'}]})
  assert proposed.status_code==200 and proposed.json['steps'][0]['op']=='note'
 assert post('/selection/configurazioni/automazioni/salva',dict(kind='procedure',name='Unsafe',description='',active=True,steps=[{'op':'shell','text':'echo bad'}])).status_code==422
 # Missing data with no rule evidence must fail, never send or report success.
 missing=configure('procedure','Missing-data check',steps=[{'op':'email_missing_data','subject':'Clarification','body':'Hi {candidate_name},\n{missing_data}'}])
 missing_action=configure('action','Missing-data action',procedure_code=missing)
 client.post(execute,data={'csrf_token':token,'action':missing_action})
 with app.SessionFactory() as db:
  run=db.scalar(select(ActionRun).where(ActionRun.action_code==missing_action));assert run.status=='FAILED'
  assert db.scalar(select(func.count()).select_from(mail_delivery.EmailOutbox))==1
 # UNKNOWN must not be retried automatically or displayed as success.
 unknownproc=configure('procedure','Uncertain test',steps=[{'op':'email','subject':'Uncertain','body':'Synthetic'}])
 unknownaction=configure('action','Uncertain action',procedure_code=unknownproc)
 client.post(execute,data={'csrf_token':token,'action':unknownaction})
 with app.SessionFactory() as db:mail=mail_delivery.claim(db);db.commit()
 with app.app.test_request_context():
  with app.SessionFactory() as db:mail_delivery.acknowledge(db,dict(id=mail['id'],lease=mail['lease'],outcome='started'));db.commit()
  with app.SessionFactory() as db:mail_delivery.acknowledge(db,dict(id=mail['id'],lease=mail['lease'],outcome='uncertain'));db.commit()
 client.post(execute,data={'csrf_token':token,'action':unknownaction})
 with app.SessionFactory() as db:
  run=db.scalar(select(ActionRun).where(ActionRun.action_code==unknownaction));assert run.status=='UNKNOWN' and len(run.attempts)==1
  assert db.scalar(select(func.count()).select_from(mail_delivery.EmailOutbox))==2
 # A corrected missing-data situation retries the same version and composes real questions.
 from workspace.role_catalog import JobRole
 from workspace.pdl_rule_store import PDLRule
 with app.SessionFactory() as db:
  db.add(JobRole(code='SERVER',name='Synthetic Server',name_key='synthetic-server',active=True,version=1));db.flush()
  db.add(PDLRule(role_code='SERVER',section='requirements',title='Education to clarify',condition={'field':'education.qualification','op':'education_gte','value':'HIGH_SCHOOL'},weight=1,conversation=[],proposal_key='synthetic-availability',created_by=auth[0]));db.commit()
 with patch.object(automations.rule_ai,'generate',return_value={'questions':['Have you completed high school?']}):
  client.post(execute,data={'csrf_token':token,'action':missing_action})
 with app.SessionFactory() as db:
  run=db.scalar(select(ActionRun).where(ActionRun.action_code==missing_action));assert run.status=='WAITING',(run.status,run.error)
  email=db.get(mail_delivery.EmailOutbox,run.steps[0]['outbox_id']);assert 'Have you completed high school?' in email.body and email.recipient=='synthetic@example.test'
 with app.SessionFactory() as db:
  viewer_account=accounts.create_account(db,username='automation-viewer',display_name='Synthetic Viewer',password='synthetic-password-1',is_admin=False)
  accounts.set_domain_access(db,account_id=viewer_account.id,domain_code='SELECTION',enabled=True,role_code='SUPERVISOR')
  readonly_auth=(viewer_account.id,viewer_account.session_version);db.commit()
 viewer=app.app.test_client()
 with viewer.session_transaction() as sess:sess[shared.SESSION_ACCOUNT_KEY],sess[shared.SESSION_VERSION_KEY]=readonly_auth
 readonly=viewer.get('/selection/configurazioni').get_data(as_text=True)
 assert 'data-new-automation=' not in readonly
 readonly_token=re.search(r'<meta name="csrf-token" content="([^"]+)"',readonly).group(1)
 assert viewer.post('/selection/configurazioni/automazioni/salva',data={'csrf_token':readonly_token,'payload':'{}'}).status_code==403
 assert viewer.post('/selection/configurazioni/automazioni/proposta',data={'csrf_token':readonly_token,'payload':'{}'}).status_code==403
 assert viewer.post(execute,data={'csrf_token':readonly_token,'action':action}).status_code==403
 print('PASS: configuration/version conflicts, AI allowlist, actual decision steps, WAITING until SMTP ack, failure retry without repeated steps/email, success-only Eseguita, immutable history after edits, missing-data failure, uncertain-send protection. No external email sent.')
finally:
 app._engine.dispose();shutil.rmtree(TMP)
