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
 data=json.loads(prompt[prompt.index('{"PDL":'):])
 if 'conversation' in data:
  return {'reply':'Quale frequenza di cambi consideri incompatibile e come trattiamo gli incarichi temporanei?','rule':None} if len(data['conversation'])==1 else {'reply':'Ecco la regola concordata, controllala prima di salvarla.','rule':RULE}
 text=data['CV'];outcome='NON_IN_LINEA' if text.startswith('Unstable') else 'IN_LINEA' if text.startswith('Stable') else 'DA_CHIARIRE'
 return {'priority':'UNCLEAR','reason':outcome+' in base alla cronologia riportata.','rules':[{'id':r['id'],'outcome':outcome,'reason':'Cronologia lavorativa del CV.','quotes':[text.splitlines()[0]] if outcome!='DA_CHIARIRE' else []} for r in data['rules']]}
def post(path,data):return client.post(path,data={'csrf_token':token,'payload':json.dumps(data)})
from workspace import pdl_rule_store as store

def propose_rule(scope,rule,chosen=None):
 with patch.object(conversation.rule_ai,'generate',return_value={'reply':'Proposta di verifica','rule':rule}):
  return post('/selection/requisiti-priorita/proposta',{'pdl':scope,'messages':[{'role':'user','content':'Regola sintetica esplicitamente definita.'}],'replacement_id':chosen})
def save_rule(scope,title,target=None):
 rule=dict(RULE,title=title,replaces_rule_id=target)
 response=propose_rule(scope,rule,target)
 assert response.status_code==200,response.get_data(as_text=True)
 saved=post('/selection/requisiti-priorita/salva',{'token':response.json['token']})
 assert saved.status_code==200,saved.get_data(as_text=True)
 return saved.json['id'],response.json['token']
try:
 app.app.config['TESTING']=True;automations.initialize(app._engine);store.initialize(app._engine)
 with app.SessionFactory() as db:
  owner=accounts.create_account(db,username='scope-owner',display_name='Synthetic Owner',password='synthetic-password-1',is_admin=True)
  accounts.set_domain_access(db,account_id=owner.id,domain_code='SELECTION',enabled=True,role_code=None)
  auth=(owner.id,owner.session_version)
  for code in ('A','B'):db.add(JobRole(code=code,name='Synthetic '+code,name_key='synthetic-'+code,active=True,version=1))
  db.commit()
 client=app.app.test_client()
 with client.session_transaction() as sess:sess[shared.SESSION_ACCOUNT_KEY],sess[shared.SESSION_VERSION_KEY]=auth
 page=client.get('/selection/requisiti-priorita').get_data(as_text=True)
 assert 'Tutte le PDL' in page and 'id="need-chat"' in page
 token=re.search(r'<meta name="csrf-token" content="([^"]+)"',page).group(1)
 g1,_=save_rule('__all__','General continuity')
 g2,_=save_rule('__all__','General reliability')
 local,_=save_rule('A','A additional preference')
 override,override_token=save_rule('A','A seasonal continuity',g1)
 assert post('/selection/requisiti-priorita/salva',{'token':override_token}).json['id']==override
 with app.SessionFactory() as db:
  assert [r.id for r in conversation.active(db,'A')]==[override,g2,local]
  assert [r.id for r in conversation.active(db,'B')]==[g1,g2]
  assert [r.id for r in conversation.active(db,None)]==[g1,g2]
  assert db.get(PDLRule,g1).role_code is None and db.get(PDLRule,g1).is_active
  assert db.get(PDLRule,override).overrides_rule_id==g1
  sig=conversation.signature(conversation.active(db,'A'))
  entries=store.entries(db,'A');assert [e['origin'] for e in entries]==['Generale modificata','Generale','Specifica']
 html=client.get('/selection/requisiti-priorita?pdl=A').get_data(as_text=True)
 assert 'Generale modificata' in html and 'Sostituisce:</strong> General continuity' in html
 assert 'General continuity</h3>' not in html
 bad=dict(RULE,replaces_rule_id=g1)
 assert propose_rule('__all__',bad).status_code==422
 assert propose_rule('B',dict(RULE,replaces_rule_id=local)).status_code==422
 assert propose_rule('A',dict(RULE,replaces_rule_id=g2),g1).status_code==422
 # A later local revision supersedes only the earlier override, preserving it inactive.
 newer,_=save_rule('A','A revised seasonal continuity',g1)
 with app.SessionFactory() as db:
  assert not db.get(PDLRule,override).is_active
  assert [r.id for r in conversation.active(db,'A')]==[newer,g2,local]
  assert [r.id for r in conversation.active(db,'B')]==[g1,g2]
  assert conversation.signature(conversation.active(db,'A'))!=sig
 # Root changes invalidate a drafted replacement rather than silently replacing new text.
 drafted=propose_rule('B',dict(RULE,replaces_rule_id=g1))
 assert drafted.status_code==200
 with app.SessionFactory() as db:db.get(PDLRule,g1).title='Updated general continuity';db.commit()
 assert post('/selection/requisiti-priorita/salva',{'token':drafted.json['token']}).status_code==409
 # Disabling an override restores the general. Global deactivation suspends its local child.
 client.post(f'/selection/requisiti-priorita/{newer}/attivazione',data={'csrf_token':token})
 with app.SessionFactory() as db:assert [r.id for r in conversation.active(db,'A')]==[g1,g2,local]
 client.post(f'/selection/requisiti-priorita/{newer}/attivazione',data={'csrf_token':token})
 client.post(f'/selection/requisiti-priorita/{g1}/attivazione',data={'csrf_token':token})
 with app.SessionFactory() as db:
  assert [r.id for r in conversation.active(db,'A')]==[g2,local]
  assert [r.id for r in conversation.active(db,'B')]==[g2]
 client.post(f'/selection/requisiti-priorita/{g1}/attivazione',data={'csrf_token':token})
 with app.SessionFactory() as db:
  assert [r.id for r in conversation.active(db,'A')]==[newer,g2,local]
  assert [r.id for r in conversation.active(db,'B')]==[g1,g2]
 # Reactivating an older override cannot create two active replacements.
 client.post(f'/selection/requisiti-priorita/{override}/attivazione',data={'csrf_token':token})
 with app.SessionFactory() as db:assert not db.get(PDLRule,override).is_active
 print('PASS: general scope, specific additions, explicit local-only replacements, effective AI snapshot, superseded history, stale proposal rejection, deactivation/restoration, replacement uniqueness and PDL isolation')
finally:
 app._engine.dispose();shutil.rmtree(TMP)
