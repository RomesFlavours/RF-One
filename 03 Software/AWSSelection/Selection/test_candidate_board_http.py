"""Synthetic HTTP regression: explicit PDL-only apply, actions and original CV."""
import os,re,tempfile,shutil
from io import BytesIO
from unittest.mock import patch
TMP=tempfile.mkdtemp(prefix='candidate_board_')
os.environ['RFONE_DATABASE_URL']='sqlite:///'+(TMP+'/test.db').replace(os.sep,'/')
os.environ['RFONE_SELECTION_UPLOAD_DIR']=TMP+'/uploads'
os.environ['RFONE_SELECTION_REQUIRE_RFONE_LOGIN']='1'
os.environ['RFONE_WEB_BASE_URL']='http://localhost:5097'
os.environ['RFONE_FLASK_SECRET_KEY']='synthetic-candidate-board'
for k in ('RFONE_SELECTION_DOCUMENT_BUCKET','RFONE_PUBLIC_BASE_URL','RFONE_SELECTION_AI','RFONE_SELECTION_AI_CV'):os.environ.pop(k,None)
import app
from sqlalchemy import select,func
from rfone_data_store import models as m,rfone_account_service as accounts,rfone_web_session as shared
from rfone_data_store.selection import workspace_models as ws,requirements_service as req
from workspace import routes,engine,ai_adapter,sp_routes
from workspace import automations
automations.initialize(app._engine)
from workspace.role_catalog import JobRole
from workspace.pdl_rule_store import PDLRule

def ids(html):return [int(i) for i in re.findall(r'<tr id="candidate-(\d+)"',html)]
try:
 app.app.config['TESTING']=True
 with app.SessionFactory() as db:
  owner=accounts.create_account(db,username='board-owner',display_name='Synthetic Owner',password='synthetic-password-1',is_admin=True)
  accounts.set_domain_access(db,account_id=owner.id,domain_code='SELECTION',enabled=True,role_code=None)
  sup=accounts.create_account(db,username='board-supervisor',display_name='Synthetic Supervisor',password='synthetic-password-1',is_admin=False)
  accounts.set_domain_access(db,account_id=sup.id,domain_code='SELECTION',enabled=True,role_code='SUPERVISOR')
  auth=(owner.id,owner.session_version);supervisor=(sup.id,sup.session_version);rid=routes._restaurant_id(db)
  positions=[]
  for role in ('SERVER','FOOD_RUNNER'):
   db.add(JobRole(code=role,name=role,name_key=role.lower(),active=True,version=1))
   r=req.create_requirement_set(db,restaurant_id=rid,name='Synthetic '+role,target_role=role)
   p=ws.Position(title='Synthetic '+role,role_code=role,location_label='Synthetic location',timezone='America/New_York',status='OPEN',manager_account_id=owner.id,created_by_account_id=owner.id,requirement_set_id=r.id)
   db.add(p);db.flush();positions.append(p.id)
  for code,section,condition,weight in [('SERVER','requirements',{'field':'direct_months','op':'lt','value':12},1),('SERVER','priorities',{'field':'direct_months','op':'gte','value':24},5),('FOOD_RUNNER','requirements',{'field':'direct_months','op':'gte','value':0},1)]:
   db.add(PDLRule(role_code=code,section=section,title='Synthetic '+section,condition=condition,weight=weight,conversation=[],proposal_key=code+section,created_by=owner.id))
  db.commit()
 client=app.app.test_client()
 with client.session_transaction() as sess:sess[shared.SESSION_ACCOUNT_KEY],sess[shared.SESSION_VERSION_KEY]=auth
 pid=positions[0];page=client.get(f'/selection/posizioni/{pid}?tab=candidature').get_data(as_text=True)
 token=re.search(r'name="csrf_token" value="([^"]+)"',page).group(1)
 with patch.object(engine,'analyze',side_effect=AssertionError('Legacy engine called')) as old,patch.object(ai_adapter,'_REAL_GENERATE_JSON',side_effect=AssertionError('AI called')) as ai,patch.object(sp_routes,'_queue',side_effect=AssertionError('SP queue called')) as queue:
  for name,dates in [('Low','Jan 2023 - Mar 2023'),('Middle','Jan 2020 - Dec 2021'),('High','Jan 2020 - Dec 2023'),('Unknown','')]:
   cv=f'{name} Synthetic\n{name.lower()}@example.test\n\nEXPERIENCE\nServer, Bistro Prova, Orlando, FL'+(' | '+dates if dates else '')+'\n- Served tables\n'
   response=client.post(f'/selection/posizioni/{pid}/sp/upload',data={'csrf_token':token,'modal':'1','cv':(BytesIO(cv.encode()),name+'.txt')},content_type='multipart/form-data')
   assert response.status_code==200,response.get_data(as_text=True)
  page=client.get(f'/selection/posizioni/{pid}?tab=candidature').get_data(as_text=True)
  original=ids(page);assert len(original)==4
  assert 'Filtri e regole non ancora applicati' in page
  assert 'href="/selection/posizioni/'+str(pid)+'/valutazione' not in page.split('</nav>')[0]
  applied=client.post(f'/selection/posizioni/{pid}/applica-regole-pdl',data={'csrf_token':token},follow_redirects=True)
  assert applied.status_code==200
  html=applied.get_data(as_text=True);order=ids(html)
  assert order==[original[2],original[1],original[3],original[0]],order
  assert 'UnFit' in html and 'Da chiarire' in html
  assert ids(client.get(f'/selection/posizioni/{pid}?tab=candidature').get_data(as_text=True))==order
  pc=original[2];action=f'/selection/posizioni/{pid}/candidati/{pc}/azione'
  response=client.post(action,data={'csrf_token':token,'action':'INTERVIEW'},follow_redirects=True);assert response.status_code==200
  assert 'Eseguita' in response.get_data(as_text=True)
  client.post(action,data={'csrf_token':token,'action':'INTERVIEW'})
  with app.SessionFactory() as db:assert db.scalar(select(func.count()).select_from(ws.Decision))==1
  client.post(action,data={'csrf_token':token,'action':'ON_HOLD'})
  with app.SessionFactory() as db:assert db.scalar(select(func.count()).select_from(ws.Decision))==2
  assert client.post(action,data={'csrf_token':token,'action':'NOT_A_REAL_ACTION'}).status_code==400
  assert client.post(f'/selection/posizioni/{positions[1]}/candidati/{pc}/azione',data={'csrf_token':token,'action':'INTERVIEW'}).status_code==404
  client.post(f'/selection/posizioni/{pid}/applica-regole-pdl',data={'csrf_token':token})
  with app.SessionFactory() as db:
   assert db.scalar(select(func.count()).select_from(ws.Decision))==2
   assert db.scalar(select(func.count()).select_from(ws.Proposal))==0
   assert db.scalar(select(func.count()).select_from(m.FitAssessment))==0
  details=client.get(f'/selection/posizioni/{pid}/resume/{pc}/dati?include_original=1').get_data(as_text=True)
  assert 'CV originale caricato' in details and '<iframe' in details and 'high@example.test' in details
  assert client.get(f'/selection/posizioni/{pid}/sp').status_code==302
  with app.SessionFactory() as db:
   db.add(ws.Decision(position_candidate_id=original[1],decision='DEEPEN',reason_code=None,note=None,proposal_group=None,proposal_source=None,differs_from_proposal=False,actor_account_id=auth[0],actor_name='Synthetic Owner'))
   db.commit()
  html=client.get(f'/selection/posizioni/{pid}?tab=candidature').get_data(as_text=True)
  block=html.split(f'id="candidate-{original[1]}"')[1].split('</tr>')[0]
  assert 'class="action-executed" >Eseguita' in block or 'class="action-executed"' in block and 'DEEPEN' in block
  client.post(f'/selection/posizioni/{pid}/candidati/{original[1]}/azione',data={'csrf_token':token,'action':'DEEPEN'})
  with app.SessionFactory() as db:assert db.scalar(select(func.count()).select_from(ws.Decision))==3
  old.assert_not_called();ai.assert_not_called();queue.assert_not_called()
 viewer=app.app.test_client()
 with viewer.session_transaction() as sess:sess[shared.SESSION_ACCOUNT_KEY],sess[shared.SESSION_VERSION_KEY]=supervisor
 page=viewer.get(f'/selection/posizioni/{pid}?tab=candidature').get_data(as_text=True)
 assert 'candidate-action-button' not in page.split('</style>')[-1]
 t=re.search(r'<meta name="csrf-token" content="([^"]+)"',page).group(1)
 assert viewer.post(f'/selection/posizioni/{pid}/applica-regole-pdl',data={'csrf_token':t}).status_code==403
 print('PASS: explicit apply, correct PDL isolation/order/unknowns, persisted results, decisions preserved, real idempotent actions, original CV, no legacy/AI/queue, readonly enforcement')
finally:
 app._engine.dispose();shutil.rmtree(TMP)
