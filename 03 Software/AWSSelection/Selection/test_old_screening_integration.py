"""Old engine reuse and PDL criterion editor; disposable memory data only."""
from pathlib import Path
from types import SimpleNamespace as NS
import os,sys,json
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE.parent/'RF-One Data Store')]
os.environ['RFONE_SELECTION_ENGINE']='old';os.environ['RFONE_UI_LANGUAGE']='it'
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import sessionmaker
from flask import Flask,request
from rfone_data_store import models as m
from rfone_data_store.selection import workspace_models as ps, primary_screening_service as screening
from workspace import old_screening as old, routes, sp_queue
from workspace.schema import REQUIRED_TABLES
from local_i18n import install
sp_queue.kick=lambda:None
engine=create_engine('sqlite://')
selected=[t for name,t in m.Base.metadata.tables.items() if name in REQUIRED_TABLES or name.startswith('selection_workspace_')]
m.Base.metadata.create_all(engine,tables=selected)
Factory=sessionmaker(engine,expire_on_commit=False)
with Factory() as db:
 restaurant=m.Restaurant(name='Synthetic test',default_currency='USD');db.add(restaurant);db.flush()
 position=ps.Position(title='Test role',role_code='SERVER',location_label='Test location',timezone='America/New_York',manager_account_id=1,created_by_account_id=1,requirement_set_id=1)
 other=ps.Position(title='Other role',role_code='FOOD_RUNNER',location_label='Test location',timezone='America/New_York',manager_account_id=1,created_by_account_id=1,requirement_set_id=1)
 db.add_all([position,other]);db.flush();position_id=position.id;other_id=other.id
 levels={str(n):'Livello di prova '+str(n) for n in range(5)}
 criterion=screening.create_criterion(db,restaurant_id=restaurant.id,target_role='SERVER',name='Test criterion',coefficient=2,direction='POSITIVE',level_descriptions=levels,evidence_sources_allowed=['RESUME_FACT'])
 blocker=screening.create_criterion(db,restaurant_id=restaurant.id,target_role='SERVER',name='Test blocker',coefficient=1,direction='NEGATIVE',is_hard_disqualifier=True,hard_disqualifier_trigger_level=3,level_descriptions=levels,evidence_sources_allowed=['RESUME_FACT'])
 wrong=screening.create_criterion(db,restaurant_id=restaurant.id,target_role='FOOD_RUNNER',name='Other role criterion',level_descriptions=levels,evidence_sources_allowed=['RESUME_FACT'])
 criterion_id=criterion.id;criterion_version=criterion.version
 for name in ['First','Second','Blocked']:
  person=m.CandidatePerson(full_name=name);db.add(person);db.flush()
  candidate=m.Candidate(full_name=name,restaurant_id=restaurant.id,summary='Synthetic profile '+name);db.add(candidate);db.flush()
  app=m.Application(person_id=person.id,candidate_id=candidate.id,restaurant_id=restaurant.id,target_role='SERVER');db.add(app);db.flush()
  db.add(ps.PositionCandidate(position_id=position.id,application_id=app.id,candidate_id=candidate.id,channel='MANUAL_UPLOAD'))
 db.commit()
# Mock only the AI provider; all evidence packages, Old evaluations, snapshots, contribution/ranking and SQL are real.
def fake_ai(prompt):
 name='Blocked' if 'Blocked' in prompt else 'Second' if 'Second' in prompt else 'First'
 is_blocker='Test blocker' in prompt
 level=(4 if name=='Blocked' else 0) if is_blocker else (4 if name=='First' else 2)
 return {'status':'EVALUATED','level':level,'confidence':'HIGH','explanation':'Evidenza sintetica di prova.',
 'evidence':[{'source_type':'RESUME_FACT','source_reference':'summary','evidence_text':'Résumé summary/objective: Synthetic profile '+name}]}
old.rule_ai.generate=fake_ai
with Factory() as db:
 position=db.get(ps.Position,position_id)
 old.apply(db,position,NS(id=1,name='Test owner'))
 data,stale=old.results(db,position);assert not stale and len(data)==3
 assert all(len(v['details'])==2 for v in data.values())
 assert sum(v['unfit'] for v in data.values())==1, data
 rows=[{'pc':pc} for pc in db.scalars(select(ps.PositionCandidate).where(ps.PositionCandidate.position_id==position_id))]
 ranked=old.decorate(db,position,rows)
 names=[db.get(m.Candidate,r['pc'].candidate_id).full_name for r in ranked]
 assert names==['First','Second','Blocked'],names
 assert [v.priority_index for v in screening.list_normal_pool(db,restaurant.id)]==[8,4]
 count=db.scalar(select(func.count()).select_from(m.PrimaryScreeningRun));assert count==3
 owned_id=next(c.id for c in old.criteria(db,position) if c.name=='Test criterion')
 prior=db.scalar(select(m.PrimaryScreeningCriterionSnapshot).where(m.PrimaryScreeningCriterionSnapshot.criterion_id==owned_id))
 screening.update_criterion(db,criterion_id,coefficient=7);db.commit()
 assert old.results(db,position)[1] is False, 'Default edit leaked into research'
 screening.update_criterion(db,owned_id,coefficient=3);db.commit()
 assert prior.coefficient==2
 assert old.results(db,position)[1] is True
 assert db.scalar(select(func.count()).select_from(m.PrimaryScreeningRun))==count
# A provider failure must preserve Unknown, never fabricate level zero or erase old runs.
original_provider=old.rule_ai.generate
def unavailable(prompt):raise RuntimeError('Synthetic provider unavailable')
old.rule_ai.generate=unavailable
with Factory() as db:
 position=db.get(ps.Position,position_id)
 old.apply(db,position,NS(id=1,name='Test owner'))
 results,_=old.results(db,position)
 assert all(v['unknown'] and all(d['level'] is None for d in v['details']) for v in results.values())
 assert db.scalar(select(func.count()).select_from(m.PrimaryScreeningRun))==6
old.rule_ai.generate=original_provider
print('PASS: real Old engine priority, hard-disqualifier pool, role isolation, snapshots, stale detection and read-only results')
routes._cfg.SessionFactory=Factory
routes.current_account=lambda db:object()
routes.actor_for=lambda db,account:NS(id=1,name='Test owner',is_owner=request.headers.get('X-Test-Actor','owner')=='owner',can_view=lambda p:True,can_edit=lambda p:request.headers.get('X-Test-Actor','owner')=='owner')
http=Flask(__name__,template_folder=str(HERE/'templates'),static_folder=str(HERE/'static'));http.secret_key='memory-test';http.config['TESTING']=True
http.register_blueprint(routes.bp);install(http)
client=http.test_client()
from rfone_data_store import rfone_web_session as shared
with client.session_transaction() as session:session[shared.SESSION_CSRF_KEY]='csrf'
url='/posizioni/'+str(position_id)+'/criteri-selezione'
response=client.get(url);assert response.status_code==200,response.get_data(as_text=True)
body=response.get_data(as_text=True);assert 'Criteri di selezione' in body and 'Other role criterion' not in body
assert 'Requisiti &amp; Priorità</a>' not in body
assert client.get('/requisiti-priorita').status_code==302
assert client.post('/requisiti-priorita/proposta',data={'csrf_token':'csrf'}).status_code==404
payload={'csrf_token':'csrf','name':'Nuovo criterio test','coefficient':'0','direction':'POSITIVE','evidence_sources_allowed':['RESUME_FACT'],**{'level_description_'+str(n):str(n) for n in range(5)}}
response=client.post(url,data=payload);assert response.status_code==302,response.get_data(as_text=True)
with Factory() as db:
 created=db.scalar(select(m.PrimaryScreeningCriterion).where(m.PrimaryScreeningCriterion.name=='Nuovo criterio test'))
 assert created.coefficient==0 and created.target_role=='SERVER' and created.research_id==position_id
 cid=created.id;version=created.version
assert client.post(url,data={**payload,'name':''}).status_code==422
assert client.post(url,data=payload,headers={'X-Test-Actor':'manager'}).status_code==403
assert client.post(url,data={**payload,'criterion_id':cid,'version':version-1}).status_code==422
assert client.post('/posizioni/'+str(other_id)+'/criteri-selezione',data={**payload,'criterion_id':cid,'version':version}).status_code==404
assert client.post(url,data={'csrf_token':'bad','action':'toggle','criterion_id':cid,'version':version}).status_code==302
with Factory() as db:assert db.get(m.PrimaryScreeningCriterion,cid).is_active
assert client.post(url,data={'csrf_token':'csrf','action':'toggle','criterion_id':cid,'version':version}).status_code==302
with Factory() as db:assert not db.get(m.PrimaryScreeningCriterion,cid).is_active
print('PASS: PDL-scoped Italian tab; real criterion creation, zero coefficient, validation, role/owner/CSRF/concurrency protection, disable and parked new-rule endpoints')
# Default and research scopes are independent, including empty and nested copies.
from workspace import criterion_copies
from workspace.role_catalog import JobRole
with Factory() as db:
 db.add(JobRole(code='SERVER',name='Synthetic PDL',name_key='synthetic pdl',active=True))
 db.add(JobRole(code='EMPTY',name='Empty PDL',name_key='empty pdl',active=True))
 db.commit()
 position=db.get(ps.Position,position_id)
 peer=ps.Position(title='Peer research',role_code='SERVER',location_label='Test location',timezone='America/New_York',manager_account_id=1,created_by_account_id=1,requirement_set_id=1)
 empty=ps.Position(title='Empty research',role_code='EMPTY',location_label='Test location',timezone='America/New_York',manager_account_id=1,created_by_account_id=1,requirement_set_id=1)
 db.add_all([peer,empty]);db.flush()
 criterion_copies.ensure_research(db,peer,restaurant_id=restaurant.id)
 criterion_copies.ensure_research(db,empty,restaurant_id=restaurant.id)
 db.commit();peer_id=peer.id;empty_id=empty.id
 own=next(c for c in old.criteria(db,position) if c.name=='Test criterion')
 peer_copy=next(c for c in old.criteria(db,peer) if c.name=='Test criterion')
 source=db.get(m.PrimaryScreeningCriterion,criterion_id)
 assert len({own.id,peer_copy.id,source.id})==3
 assert own.coefficient==3 and peer_copy.coefficient==source.coefficient==7
 screening.update_criterion(db,source.id,coefficient=9,level_descriptions={'0':'Default changed','1':'1','2':'2','3':'3','4':'4'},is_active=False)
 db.commit()
 assert own.coefficient==3 and peer_copy.coefficient==7
 assert own.level_descriptions['0']!='Default changed' and peer_copy.level_descriptions['0']!='Default changed'
 assert own.is_active and peer_copy.is_active
 screening.update_criterion(db,own.id,coefficient=5,level_descriptions={'0':'Only research A','1':'1','2':'2','3':'3','4':'4'},evidence_sources_allowed=['APPLICATION'])
 db.commit()
 assert peer_copy.level_descriptions['0']!='Only research A' and source.level_descriptions['0']=='Default changed'
 assert peer_copy.evidence_sources_allowed==['RESUME_FACT'] and source.evidence_sources_allowed==['RESUME_FACT']
 assert not old.criteria(db,empty)
 screening.create_criterion(db,restaurant_id=restaurant.id,target_role='EMPTY',name='Later default',level_descriptions=levels,evidence_sources_allowed=['RESUME_FACT'])
 criterion_copies.ensure_research(db,empty,restaurant_id=restaurant.id);db.commit()
 assert not old.criteria(db,empty), 'Empty research acquired later defaults'
 later=ps.Position(title='Later research',role_code='EMPTY',location_label='Test location',timezone='America/New_York',manager_account_id=1,created_by_account_id=1,requirement_set_id=1)
 db.add(later);db.flush();criterion_copies.ensure_research(db,later,restaurant_id=restaurant.id);db.commit()
 assert len(old.criteria(db,later))==1
 assert all(c.research_id is None for c in screening.list_criteria(db,active_only=False)), 'Private research leaked into Old default catalogue'
# HTTP scope and default permissions: row IDs cannot cross either boundary.
default_url='/configurazioni/pdl/SERVER/criteri'
assert client.get(default_url).status_code==200
assert client.get(default_url,headers={'X-Test-Actor':'manager'}).status_code==200
assert client.post(default_url,data=payload,headers={'X-Test-Actor':'manager'}).status_code==403
with Factory() as db:
 source=db.get(m.PrimaryScreeningCriterion,criterion_id)
 owned=next(c for c in old.criteria(db,db.get(ps.Position,position_id)) if c.name=='Test criterion')
 source_version=source.version;owned_id=owned.id;owned_version=owned.version
assert client.post(default_url,data={**payload,'criterion_id':owned_id,'version':owned_version}).status_code==404
assert client.post(url,data={**payload,'criterion_id':criterion_id,'version':source_version}).status_code==404
assert client.post('/posizioni/'+str(peer_id)+'/criteri-selezione',data={**payload,'criterion_id':owned_id,'version':owned_version}).status_code==404
# Exercise actual new-position creation, including the post-creation settings/SP saves.
from workspace import ai_adapter
ai_adapter.install_guard(ai_enabled=False,cv_ai_authorized=False)
routes._company_facts=lambda *a,**k:{'facts':[],'missing':[],'source':'synthetic','profile':''}
routes.account_svc.list_accounts=lambda db:[NS(id=1,status='ACTIVE')]
routes.shared_session.account_may_enter_domain=lambda *a,**k:True
routes._manager_name=lambda *a:'Test manager'
# Label lookup is a read-only fixture; a second Session on SQLite's single memory
# connection would otherwise roll back the creation transaction under test.
routes.ROLE_LABEL={'SERVER':'Synthetic PDL'}
previous_actor=routes.actor_for
routes.actor_for=lambda db,account:NS(id=1,name='Test owner',role='OWNER',is_owner=True,can_view=lambda p:True,can_edit=lambda p:True)
response=client.post('/posizioni/nuova',data={'csrf_token':'csrf','role_code':'SERVER','title':'Created through route','location':'Test location','timezone':'America/New_York','manager_account_id':'1'})
assert response.status_code==302,response.get_data(as_text=True)
with Factory() as db:
 new_position=db.scalar(select(ps.Position).where(ps.Position.title=='Created through route'))
 assert new_position is not None
 copies=old.criteria(db,new_position)
 assert len(copies)==2 and all(c.research_id==new_position.id for c in copies)
 frozen=next(c for c in copies if c.name=='Test criterion')
 assert frozen.coefficient==9 and frozen.is_active is False
 assert 'old_criteria_copies' in new_position.organization_context_json
routes.actor_for=previous_actor
print('PASS: deep default/research/peer isolation, default edits and deactivation, empty-copy freeze, native catalogue isolation, cross-scope rejection, owner-only default edits and actual new-position copying')

# Contextual groups, AI inputs, immutable run context, and scope isolation.
from workspace import screening_context
from rfone_data_store.selection import primary_screening_ai_evaluator as evaluator
with Factory() as db:
 position=db.get(ps.Position,position_id)
 source=db.get(m.PrimaryScreeningCriterion,criterion_id)
 screening.update_criterion(db,source.id,criterion_group='PERSON')
 own=next(c for c in old.criteria(db,position) if c.name=='Test criterion')
 assert own.criterion_group=='ROLE_RESEARCH', 'Default grouping leaked into research'
 screening.update_criterion(db,own.id,criterion_group='PERSON')
 assert next(c for c in old.criteria(db,db.get(ps.Position,peer_id)) if c.name=='Test criterion').criterion_group=='ROLE_RESEARCH'
 person_snapshot=screening.get_or_create_criterion_snapshot(db,own.id)
 assert person_snapshot.criterion_group=='PERSON'
 pc=db.scalar(select(ps.PositionCandidate).where(ps.PositionCandidate.position_id==position_id))
 app=db.get(m.Application,pc.application_id)
 online=ps.CandidateApplication(position_candidate_id=pc.id);db.add(online);db.flush()
 db.add(ps.Answer(candidate_application_id=online.id,question_index=0,question_source='STANDARD',
  question_text='Perché questa opportunità?',answer_text='Voglio applicare le mie competenze in sala.'))
 db.flush()
 position.description='Documented role tasks'
 ctx=screening_context.for_candidate(db,position,pc)
 ctx['research']['conditions']='Unique research condition'
 person_package=evaluator.build_evidence_package(db,app,person_snapshot,ctx)
 person_prompt=evaluator.build_prompt(person_snapshot,person_package,ctx)
 assert 'CRITERION GROUP: PERSON' in person_prompt
 assert 'Unique research condition' not in person_prompt and 'Documented role tasks' not in person_prompt
 assert 'FIT_ASSESSMENT' not in person_package and 'SELECTION_SIGNAL' not in person_package
 assert 'Voglio applicare le mie competenze in sala.' in person_prompt
 blocker=next(c for c in old.criteria(db,position) if c.name=='Test blocker')
 role_snapshot=screening.get_or_create_criterion_snapshot(db,blocker.id)
 role_prompt=evaluator.build_prompt(role_snapshot,evaluator.build_evidence_package(db,app,role_snapshot,ctx),ctx)
 assert 'Unique research condition' in role_prompt and 'Documented role tasks' in role_prompt
 assert 'requires BOTH' in role_prompt and 'INSUFFICIENT_EVIDENCE' in role_prompt
 # Every contextual criterion is interpreted even if a signal mapping exists.
 saved_shortcut=screening._auto_evaluate_from_signal
 screening._auto_evaluate_from_signal=lambda *args:(_ for _ in ()).throw(AssertionError('Context bypassed'))
 run=screening.create_screening_run(db,app.id,research_id=position.id,evaluation_context=ctx,
   criterion_ids=[blocker.id],ai_generate_json_fn=lambda prompt:{'status':'INSUFFICIENT_EVIDENCE','level':None,
   'confidence':'UNKNOWN','explanation':'Orari mancanti.', 'missing_information':['Orari richiesti'], 'evidence':[]})
 screening._auto_evaluate_from_signal=saved_shortcut
 assert run.evaluation_context['research']['conditions']=='Unique research condition'
 ctx['research']['conditions']='Changed after evaluation'
 assert run.evaluation_context['research']['conditions']=='Unique research condition'
 ev=screening.list_evaluations(db,run.id)[0]
 assert ev.effective_level is None and ev.status=='INSUFFICIENT_EVIDENCE' and 'Da chiarire' in ev.explanation
 try:
  evaluator.evaluate_criterion_with_ai(db,app,role_snapshot,evaluation_context=ctx,generate_json_fn=lambda prompt:
    {'status':'EVALUATED','level':4,'confidence':'HIGH','explanation':'Fabrication','evidence':[
    {'source_type':'RESUME_FACT','source_reference':'imagined','evidence_text':'Invented fact'}]})
  raise AssertionError('Fabricated evidence accepted')
 except evaluator.AIEvaluationUnavailable:pass
 db.commit()
 context_version=screening_context.version(position)
 context_before=screening_context.values(position)
 payload_context={'csrf_token':'csrf','action':'save_context','context_version':context_version,
  'context_schedule':'Friday evening','context_tasks':'Serving tables'}
 assert client.post(default_url,data=payload_context).status_code==400
 assert client.post(url,data=payload_context,headers={'X-Test-Actor':'manager'}).status_code==403
 response=client.post(url,data=payload_context);assert response.status_code==302,response.get_data(as_text=True)
 assert client.post(url,data=payload_context).status_code==422
 with Factory() as fresh:
  current=fresh.get(ps.Position,position_id)
  assert screening_context.values(current)['schedule']=='Friday evening'
  assert screening_context.values(fresh.get(ps.Position,peer_id))['schedule']==''
  assert old.results(fresh,current)[1] is True
 body=client.get(url).get_data(as_text=True)
 assert 'criteria-group-PERSON' in body and 'criteria-group-ROLE_RESEARCH' in body
 assert 'Contesto del ruolo e della ricerca' in body
print('PASS: person/role groups, private defaults, context/answer contract, missing evidence, citation validation, snapshot context, research context permissions/concurrency/stale detection')

if '--serve' in sys.argv:
 http.run(host='127.0.0.1',port=5115,use_reloader=False,threaded=False)
else:engine.dispose()
