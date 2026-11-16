"""Executable CV-field rules, using synthetic profiles and disposable SQLite only."""
import sys
from pathlib import Path
from types import SimpleNamespace as NS
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'RF-One Data Store')]
from workspace import pdl_rule_engine as rules, pdl_cv_fields as cv, pdl_rule_application as application
from workspace.pdl_rule_store import PDLRule
from workspace.role_catalog import JobRole
from rfone_data_store import models as m
from rfone_data_store.selection import persistence
from rfone_data_store.selection.core.profile import CandidateCVProfile, EducationRecord, WorkHistoryRecord, CertificationRecord, LanguageRecord

def condition(field, value, op='contains'):
    return rules.validate_condition({'field':field, 'op':op, 'value':value})

profile = CandidateCVProfile(full_name='Test Person', email='test@example.test', phone='555', location='Test Town',
    summary='Test profile', linkedin_url='https://linkedin.test/test', other_profile_url='https://site.test/test',
    other_sections_text='Test projects', skills=['Test skill'],
    work_history=[WorkHistoryRecord(employer='Test Company', location='Test City', original_job_title='Test role',
      start_date_text='2020-01', end_date_text='2022-12', responsibilities='Test duties', achievements='Test results')],
    education=[EducationRecord(institution='Test School', qualification='High School', field='Test subject',
      start_date_text='2014', end_date_text='2018', completion_status='COMPLETED')],
    certifications=[CertificationRecord(name='Test Certificate', issuer='Test Issuer', date_text='2023-01-01')],
    languages_detail=[LanguageRecord(language='Test Language', proficiency='B2')])
facts = cv.profile_facts(profile)
# Every field in the actual picker has one executable, persisted fact source.
from jinja2 import Environment, FileSystemLoader
fragment=Environment(loader=FileSystemLoader(str(HERE/'templates'))).get_template('workspace/_cv_field_picker.html')
areas=fragment.make_module({'url_for':lambda *a,**k:''}).cv_areas
assert {area+' → '+field for area,_,fields in areas for field in fields} == set(cv.CHOICES)
for field in set(cv.CHOICES.values()):
    values=[v for v,_ in cv.values(facts,field) if v]
    assert values, field
    leaf=condition(field,str(values[0]),'eq')
    assert rules.evaluate(leaf,facts) is True,field
    assert rules.evaluate(leaf,{}) is None,field
    assert rules.evaluate({'op':'not','child':leaf},{}) is None,field
    assert rules.describe(leaf)
    assert rules.evaluate(condition(field,'absent unique token'),facts) is False,field
print('PASS: all 28 picker choices map to executable CV fields; missing and negated missing stay Unknown')

minimum=condition('education.qualification','HIGH_SCHOOL','education_gte')
failure=rules.validate_condition({'op':'not','child':minimum})
for qualification,expected in [('High School',False),('B.S.',False),('M.A.',False),("Bachelor of Science",False),('Master of Arts',False),('GED',False),('Licenza media',True),('Unknown diploma',None)]:
 f=cv.profile_facts(CandidateCVProfile(education=[EducationRecord(qualification=qualification)]))
 assert rules.evaluate(failure,f) is expected,(qualification,expected)
assert rules.evaluate(minimum,cv.profile_facts(CandidateCVProfile(education=[EducationRecord(qualification='Bachelor',completion_status='IN_PROGRESS')]))) is None
assert rules.evaluate(condition('skills','test','starts_with'),facts) is True
assert rules.evaluate(condition('skills','skill','ends_with'),facts) is True
assert rules.evaluate(condition('work_history.start_date_text','2020-06-01','before'),facts) is True
assert rules.evaluate(condition('work_history.start_date_text','2020-01-15','before'),facts) is None
for bad in [{'field':'__dict__','op':'eq','value':'x'},{'field':'email','op':'gte','value':3}, {'field':'education.qualification','op':'education_gte','value':'invented'}]:
 try:rules.validate_condition(bad)
 except ValueError:pass
 else:raise AssertionError(bad)
# Multiple constraints on a language must match the SAME record.
record=rules.validate_condition({'op':'record','collection':'languages_detail','condition':{'op':'all','children':[
 {'field':'languages_detail.language','op':'eq','value':'English'},
 {'field':'languages_detail.proficiency','op':'language_gte','value':'B2'}]}})
wrong=cv.profile_facts(CandidateCVProfile(languages_detail=[LanguageRecord(language='English',proficiency='A2'),LanguageRecord(language='Italian',proficiency='C2')]))
assert rules.evaluate(record,wrong) is False
assert rules.evaluate(record,cv.profile_facts(CandidateCVProfile(languages_detail=[LanguageRecord(language='English',proficiency='B2')]))) is True
assert rules.evaluate(record,cv.profile_facts(CandidateCVProfile(languages_detail=[LanguageRecord(language='English',proficiency=None)]))) is None
assert rules.evaluate(condition('languages_detail.language','inglese','eq'),cv.profile_facts(CandidateCVProfile(languages_detail=[LanguageRecord(language='English')]))) is True
print('PASS: minimum High School, higher/below/unknown/in-progress education; dates; text; same-record language; validation')

engine=create_engine('sqlite://')
for cls in (m.Candidate,m.CandidateEducation,m.CandidateWorkHistory,m.CandidateSkill,m.CandidateCertification,m.CandidateLanguage,JobRole,PDLRule):
 cls.__table__.create(engine)
Factory=sessionmaker(engine)
with Factory() as db:
 db.add_all([JobRole(code='A',name='Test A',name_key='test a'),JobRole(code='B',name='Test B',name_key='test b')]);db.flush()
 db.add_all([PDLRule(role_code='A',section='requirements',title='Minimum High School',condition=failure,weight=1,conversation=[],proposal_key='test1',created_by=1),
 PDLRule(role_code='A',section='priorities',title='Test skill preferred',condition=condition('skills','Test skill'),weight=8,conversation=[],proposal_key='test2',created_by=1),
 PDLRule(role_code='B',section='requirements',title='Other role only',condition=condition('full_name','Test'),weight=1,conversation=[],proposal_key='test3',created_by=1)])
 for name,title,skills in [('Below','Licenza media',['Test skill']),('Missing',None,[]),('Valid','High School',[]),('Preferred','Bachelor of Science',['Test skill'])]:
  db.add(m.Candidate(full_name=name,education=[m.CandidateEducation(qualification=title)] if title else [],skills=[m.CandidateSkill(skill=s) for s in skills]))
 db.commit()
 persisted=list(db.scalars(select(m.Candidate).order_by(m.Candidate.id)))
 rows=[{'pc':NS(candidate_id=c.id), 'name':c.full_name, 'decision':'HUMAN_UNCHANGED'} for c in persisted]
 before=db.connection().exec_driver_sql('SELECT total_changes()').scalar()
 ordered=application.apply(db,NS(role_code='A'),rows)
 assert [r['name'] for r in ordered]==['Preferred','Missing','Valid','Below']
 assert ordered[-1]['pdl_result']['unfit'] is True
 assert ordered[1]['pdl_result']['unknown'] is True
 assert all(r['decision']=='HUMAN_UNCHANGED' for r in ordered)
 assert db.connection().exec_driver_sql('SELECT total_changes()').scalar()==before
 other=application.apply(db,NS(role_code='B'),[{'pc':NS(candidate_id=c.id),'name':c.full_name} for c in persisted])
 assert all(len(r['pdl_result']['details'])==1 for r in other)
 for rule in db.scalars(select(PDLRule).where(PDLRule.role_code=='A')):rule.is_active=False
 db.commit()
 disabled=application.apply(db,NS(role_code='A'),rows)
 assert [r['name'] for r in disabled]==[r['name'] for r in rows]
 assert not any(r['pdl_result']['active'] for r in disabled)
print('PASS: persisted CV facts, active rules, PDL isolation, UnFit-last and priority ordering, no writes/human changes, disable restores original order')

# Real HTTP signed proposal/save/toggle with the same in-memory database only.
# Updated 2026-11-15 (A7): the approved proposal flow saves natural-language rules (need, title, instruction);
# their CV evaluation is the AI read covered by test_conversational_rules_http.py.
from flask import Flask, request
from workspace import routes, sp_queue
from rfone_data_store import rfone_web_session as shared
sp_queue.kick=lambda:None
routes._cfg.SessionFactory=Factory
routes.current_account=lambda db:object()
routes.actor_for=lambda db,account:NS(id=1,is_owner=request.headers.get('X-Test-Actor','owner')=='owner')
http=Flask(__name__,template_folder=str(HERE/'templates'),static_folder=str(HERE/'static'));http.secret_key='disposable-test-key';http.config['TESTING']=True
http.register_blueprint(routes.bp)
from local_i18n import install
install(http)
client=http.test_client()
with client.session_transaction() as session:session[shared.SESSION_CSRF_KEY]='test-csrf'
original_generate=rules.rule_ai.generate
NL_RULE={'title':'HTTP diploma','need':'Titolo di studio minimo','instruction':'UnFit se il CV non riporta almeno il diploma High School.','section':'requirements'}
rules.rule_ai.generate=lambda prompt:{'reply':'Regola di prova sul titolo minimo','rule':dict(NL_RULE)}
def post(url,data,**kwargs):
 import json
 return client.post(url,data={'csrf_token':'test-csrf','payload':json.dumps(data)},**kwargs)
proposal=post('/requisiti-priorita/proposta',{'pdl':'A','section':'requirements','messages':[{'role':'user','content':'Titolo minimo High School'}]})
assert proposal.status_code==200,proposal.get_data(as_text=True)
token=proposal.json['token']
response=post('/requisiti-priorita/salva',{'token':token});assert response.status_code==200
saved_id=response.json['id']
assert post('/requisiti-priorita/salva',{'token':token}).json['id']==saved_id
assert post('/requisiti-priorita/salva',{'token':token},headers={'X-Test-Actor':'manager'}).status_code==403
assert post('/requisiti-priorita/salva',{'token':token+'tampered'}).status_code==400
from workspace import conversational_rules as conversation
with Factory() as db:
 row=db.get(PDLRule,saved_id)
 assert row.role_code=='A' and row.section=='requirements' and row.title==NL_RULE['title']
 assert row.condition['op']=='natural_language' and row.condition['need']==NL_RULE['need'] and row.condition['instruction']==NL_RULE['instruction']
 assert saved_id in [r.id for r in conversation.active(db,'A')]   # effective for its PDL only
 assert saved_id not in [r.id for r in conversation.active(db,'B')]
assert client.post('/requisiti-priorita/'+str(saved_id)+'/attivazione',data={'csrf_token':'test-csrf'}).status_code==302
with Factory() as db:assert db.get(PDLRule,saved_id).is_active is False and saved_id not in [r.id for r in conversation.active(db,'A')]
rules.rule_ai.generate=original_generate
engine.dispose()
print('PASS: real HTTP proposal validation, signed save, idempotency, owner-only writes, tamper rejection, natural-language rule persisted for its PDL only, disable')
