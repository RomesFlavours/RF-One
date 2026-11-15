"""Disposable end-to-end need -> questions -> saved prose -> AI CV judgments."""
import os,re,json,tempfile,shutil,time,contextlib
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
TMP=tempfile.mkdtemp(prefix='selection_conversation_')
os.environ['RFONE_DATABASE_URL']='sqlite:///'+(TMP+'/test.db').replace(os.sep,'/')
os.environ['RFONE_SELECTION_UPLOAD_DIR']=TMP+'/uploads'
os.environ['RFONE_SELECTION_REQUIRE_RFONE_LOGIN']='1'
os.environ['RFONE_SELECTION_ENGINE']='conversation'
os.environ['RFONE_UI_LANGUAGE']='it'
os.environ['RFONE_WEB_BASE_URL']='http://localhost:5097'
os.environ['RFONE_FLASK_SECRET_KEY']='synthetic-conversation'
for k in ('RFONE_SELECTION_DOCUMENT_BUCKET','RFONE_PUBLIC_BASE_URL','RFONE_SELECTION_AI','RFONE_SELECTION_AI_CV'):os.environ.pop(k,None)
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'RF-One Data Store'))
from rfone_data_store.database import prepare_new_private_database,create_configured_engine
prepare_new_private_database(os.environ['RFONE_DATABASE_URL'])
from workspace.schema import provision
from workspace.criterion_copies import initialize as initialize_old_schema
setup_engine=create_configured_engine(os.environ['RFONE_DATABASE_URL'])
provision(setup_engine);initialize_old_schema(setup_engine);setup_engine.dispose()
import app
from sqlalchemy import select,func
from rfone_data_store import models as m,rfone_account_service as accounts,rfone_web_session as shared
from rfone_data_store.selection import workspace_models as ws,requirements_service as req
from workspace import routes,automations,conversational_rules as conversation,engine,old_screening
from workspace.role_catalog import JobRole
from workspace.pdl_rule_store import PDLRule
LIVE=os.environ.get('RF1_TEST_REAL_AI')=='1'
NEED='Selezionare e addestrare ha un costo: se una persona se ne va dopo un mese è un investimento perso. Mi serve continuità.'
DETAIL='Considera non in linea chi mostra più di due cambi di datore in qualsiasi periodo di 12 mesi nello storico. Conta solo impieghi successivi non stagionali, non temporanei e non stage, quando il CV lo specifica. Ignora lavori contemporanei. Non basta una sola esperienza breve. Se le date o il tipo di contratto non sono chiari, esito Da chiarire: non inventare spiegazioni. Questo è un requisito per collocare UnFit in fondo, non una preferenza.'
RULE={'title':'Continuità per proteggere l’investimento formativo','need':NEED,'instruction':DETAIL,'section':'requirements'}
CVS={
 'Unstable':"""Unstable Synthetic
unstable@example.test
EXPERIENCE
Server, Alpha Bistro | Jan 2023 - Feb 2023
Permanent employment; left for another employer.
Server, Beta Bistro | Mar 2023 - Apr 2023
Permanent employment; left for another employer.
Server, Gamma Bistro | May 2023 - Jun 2023
Permanent employment; left for another employer.
Server, Delta Bistro | Jul 2023 - Aug 2023
Permanent employment; left for another employer.
""",
 'Stable':"""Stable Synthetic
stable@example.test
EXPERIENCE
Server, Single Bistro | Jan 2020 - Dec 2023
Permanent employment. Served tables for four consecutive years.
""",
 'Unknown':"""Unknown Synthetic
unknown@example.test
EXPERIENCE
Server at Alpha Bistro and Beta Bistro. Dates and contract types not provided.
"""}
def fake(prompt):
 marker='{"task": "cv_observations"'
 if marker in prompt:
  data=json.loads(prompt[prompt.index(marker):])
  quote=data['CV'].splitlines()[0] if 'CV' in data else data['previous_summary'][0]['bullets'][0]['quotes'][0]
  return {'sections':[{'key':key,'bullets':[{'text':'Osservazione sintetica '+key,'quotes':[quote],'uncertain':False}]} for key in ('profile','strengths','limits','clarifications','conclusion')]}
 data=json.loads(prompt[prompt.index('{"PDL":'):])
 if 'conversation' in data:
  return {'reply':'Quale frequenza di cambi consideri incompatibile e come trattiamo gli incarichi temporanei?','rule':None} if len(data['conversation'])==1 else {'reply':'Ecco la regola concordata, controllala prima di salvarla.','rule':RULE}
 text=data['CV'];outcome='NON_IN_LINEA' if text.startswith('Unstable') else 'IN_LINEA' if text.startswith('Stable') else 'DA_CHIARIRE'
 return {'priority':'UNCLEAR','reason':outcome+' in base alla cronologia riportata.','rules':[{'id':r['id'],'outcome':outcome,'reason':'Cronologia lavorativa del CV.','quotes':[text.splitlines()[0]] if outcome!='DA_CHIARIRE' else []} for r in data['rules']]}
def post(path,data):return client.post(path,data={'csrf_token':token,'payload':json.dumps(data)})
try:
 app.app.config['TESTING']=True;automations.initialize(app._engine)
 with app.SessionFactory() as db:
  owner=accounts.create_account(db,username='conversation-owner',display_name='Synthetic Owner',password='synthetic-password-1',is_admin=True)
  accounts.set_domain_access(db,account_id=owner.id,domain_code='SELECTION',enabled=True,role_code=None)
  auth=(owner.id,owner.session_version);rid=routes._restaurant_id(db)
  db.add(JobRole(code='TEST_PDL',name='Synthetic PDL',name_key='synthetic-pdl',active=True,version=1))
  r=req.create_requirement_set(db,restaurant_id=rid,name='Synthetic',target_role='TEST_PDL')
  p=ws.Position(title='Synthetic PDL',role_code='TEST_PDL',location_label='Synthetic',timezone='America/New_York',status='OPEN',manager_account_id=owner.id,created_by_account_id=owner.id,requirement_set_id=r.id)
  db.add(p);db.commit();pid=p.id
 client=app.app.test_client()
 with client.session_transaction() as sess:sess[shared.SESSION_ACCOUNT_KEY],sess[shared.SESSION_VERSION_KEY]=auth
 html=client.get('/selection/requisiti-priorita?pdl=TEST_PDL').get_data(as_text=True)
 assert html.index('id="need-chat"')<html.index('Regole effettive')
 assert 'data-rule-section' not in html and 'id="rule-modal"' not in html
 token=re.search(r'<meta name="csrf-token" content="([^"]+)"',html).group(1)
 with (contextlib.nullcontext() if LIVE else patch.object(conversation.rule_ai,'generate',side_effect=fake)),patch.object(engine,'analyze',side_effect=AssertionError('Old evaluator called')),patch.object(old_screening,'apply',side_effect=AssertionError('Old screening called')):
  messages=[{'role':'user','content':NEED}]
  first=post('/selection/requisiti-priorita/proposta',{'pdl':'TEST_PDL','messages':messages})
  assert first.status_code==200,first.get_data(as_text=True)
  assert first.json['rule'] is None,first.json
  messages.extend([{'role':'assistant','content':first.json['reply']},{'role':'user','content':DETAIL}])
  second=post('/selection/requisiti-priorita/proposta',{'pdl':'TEST_PDL','messages':messages})
  assert second.status_code==200 and second.json['rule'],second.get_data(as_text=True)
  saved=post('/selection/requisiti-priorita/salva',{'token':second.json['token']})
  assert saved.status_code==200;saved_id=saved.json['id']
  assert post('/selection/requisiti-priorita/salva',{'token':second.json['token']}).json['id']==saved_id
  with app.SessionFactory() as db:
   stored=db.get(PDLRule,saved_id);assert stored.role_code=='TEST_PDL' and stored.condition['op']=='natural_language' and stored.condition['need']
  for name,cv in CVS.items():
   upload=client.post(f'/selection/posizioni/{pid}/sp/upload',data={'csrf_token':token,'modal':'1','cv':(BytesIO(cv.encode()),name+'.txt')},content_type='multipart/form-data');assert upload.status_code==200
  result=client.post(f'/selection/posizioni/{pid}/applica-regole-pdl',data={'csrf_token':token})
  assert result.status_code==302
  for i in range(150 if LIVE else 80):
   status=client.get(f'/selection/posizioni/{pid}/lettura-ai/stato').json
   if status['state']!='RUNNING':break
   time.sleep(1 if LIVE else .1)
  assert status['state']=='COMPLETED',status
  with app.SessionFactory() as db:
   p=db.get(ws.Position,pid);run=json.loads(p.organization_context_json)['pdl_filter_run']
   assert run['mode']=='natural_language' and len(run['results'])==3
   for pc in db.scalars(select(ws.PositionCandidate).where(ws.PositionCandidate.position_id==pid)):
    name=db.get(m.Candidate,pc.candidate_id).full_name;judgment=run['results'][str(pc.id)]
    assert judgment['unfit']==name.startswith('Unstable'),(name,judgment)
    if name.startswith('Unknown'):assert judgment['unknown'],judgment
   assert db.scalar(select(func.count()).select_from(ws.Decision))==0
   assert db.scalar(select(func.count()).select_from(ws.Proposal))==0
  page=client.get(f'/selection/posizioni/{pid}?tab=candidature').get_data(as_text=True)
  names=re.findall(r'<td><strong>(?:<a[^>]*>)?([^<]+)(?:</a>)?</strong>',page)
  assert names==['Stable Synthetic','Unknown Synthetic','Unstable Synthetic'],names
  assert 'Priorità +' not in page
  # A second actual Apply POST with identical inputs never calls the evaluator.
  with patch.object(conversation,'evaluate',side_effect=AssertionError('Unchanged CV was reread')):
   repeated=client.post(f'/selection/posizioni/{pid}/applica-regole-pdl',data={'csrf_token':token})
   assert repeated.status_code==302
   repeated_status=client.get(f'/selection/posizioni/{pid}/lettura-ai/stato').json
   assert repeated_status['state']=='COMPLETED' and repeated_status['done']==3
 # Editing updates the selected row, not a duplicate or a rule in another scope.
 with app.SessionFactory() as db:
  general=PDLRule(role_code=None,section='priorities',title='General original',condition={'op':'natural_language','need':'General need','instruction':'General instruction'},weight=1,conversation=[],proposal_key='edit-general-fixture',created_by=auth[0])
  db.add(general);db.commit();general_id=general.id
 edited={'title':'General edited','need':'General need','instruction':'Updated general instruction','section':'priorities','replaces_rule_id':None}
 with patch.object(conversation.rule_ai,'generate',return_value={'reply':'Controlla la modifica.','rule':edited}) as provider:
  proposed=post('/selection/requisiti-priorita/proposta',{'pdl':'__all__','edit_id':general_id,'messages':[{'role':'user','content':'Update the instruction'}]})
  assert proposed.status_code==200,proposed.get_data(as_text=True)
  assert '"edit_rule": {' in provider.call_args.args[0] and 'General original' in provider.call_args.args[0]
  update_token=proposed.json['token']
  assert post('/selection/requisiti-priorita/proposta',{'pdl':'TEST_PDL','edit_id':general_id,'messages':[{'role':'user','content':'Cross scope'}]}).status_code==404
  with app.SessionFactory() as db:before_count=db.scalar(select(func.count()).select_from(PDLRule))
  response=post('/selection/requisiti-priorita/salva',{'token':update_token})
  assert response.status_code==200 and response.json['id']==general_id,response.get_data(as_text=True)
  assert post('/selection/requisiti-priorita/salva',{'token':update_token}).json['id']==general_id
  with app.SessionFactory() as db:
   assert db.scalar(select(func.count()).select_from(PDLRule))==before_count
   assert db.get(PDLRule,general_id).title=='General edited'
   assert db.get(PDLRule,saved_id).title==RULE['title']
  stale=post('/selection/requisiti-priorita/proposta',{'pdl':'__all__','edit_id':general_id,'messages':[{'role':'user','content':'Another change'}]}).json['token']
  with app.SessionFactory() as db:db.get(PDLRule,general_id).title='Concurrent change';db.commit()
  assert post('/selection/requisiti-priorita/salva',{'token':stale}).status_code==409
  local=post('/selection/requisiti-priorita/proposta',{'pdl':'TEST_PDL','edit_id':saved_id,'messages':[{'role':'user','content':'Edit local rule'}]})
  assert local.status_code==200
  assert post('/selection/requisiti-priorita/salva',{'token':local.json['token']}).json['id']==saved_id
 assert 'data-edit-rule=' in client.get('/selection/requisiti-priorita').get_data(as_text=True)
 print('PASS: edit general/local rule in place, AI receives complete original, no duplicate, cross-scope protection, stale proposal rejection and repeated-save idempotence')
 # Reject fabricated evidence rather than silently giving a conclusive result.
 with patch.object(conversation.rule_ai,'generate',return_value={'priority':'UNCLEAR','reason':'Invalid test','rules':[{'id':1,'outcome':'NON_IN_LINEA','reason':'Unsupported','quotes':['invented evidence not in the CV']}]}):
  try:conversation.evaluate([dict(RULE,id=1)],CVS['Stable'],'TEST_PDL');raise AssertionError('Fabricated evidence accepted')
  except ValueError:pass
 print('PASS: '+('REAL CHATGPT' if LIVE else 'isolated AI contract')+' need/clarification/prose save, PDL scope/idempotence, background CV reading and persistent outcomes, unknowns not rejection, evidence check, qualitative ordering, no old engine or human decisions changed')
finally:
 app._engine.dispose();shutil.rmtree(TMP)
