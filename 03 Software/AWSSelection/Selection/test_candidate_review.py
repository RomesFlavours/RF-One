"""Disposable review HTTP tests; SMTP is mocked, no real messages are sent."""
from pathlib import Path
import json
import os
import sys
import tempfile
from types import SimpleNamespace as NS
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / 'RF-One Data Store')]
os.environ['RFONE_SELECTION_ENGINE'] = 'conversation'; os.environ['RFONE_UI_LANGUAGE'] = 'it'
from flask import Flask, request
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from rfone_data_store import models as m, rfone_web_session as shared
from rfone_data_store.selection import workspace_models as ps
from rfone_data_store.technical import smtp_email
from workspace import routes, candidate_review as review, conversational_rules as conversation
from workspace import incremental_rules as inc, position_settings
from workspace.pdl_rule_store import PDLRule
from workspace.mail_delivery import EmailOutbox
from workspace.schema import REQUIRED_TABLES
from workspace.candidate_board import board_rows

with tempfile.TemporaryDirectory(prefix='selection_review_') as tmp:
    engine = create_engine('sqlite:///' + str(Path(tmp) / 'test.db'), poolclass=NullPool)
    m.Base.metadata.create_all(engine, tables=[t for name, t in m.Base.metadata.tables.items()
        if name in REQUIRED_TABLES or name.startswith('selection_workspace_')])
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        position = ps.Position(title='Synthetic role', role_code='TEST', location_label='Synthetic', timezone='America/New_York', manager_account_id=1, created_by_account_id=1, requirement_set_id=1)
        db.add(position); db.flush(); pid = position.id
        other = ps.Position(title='Other', role_code='TEST', location_label='Synthetic', timezone='America/New_York', manager_account_id=1, created_by_account_id=1, requirement_set_id=1); db.add(other); db.flush(); other_id = other.id
        rules = []
        for n in range(3):
            r = PDLRule(role_code=None, title='Clarification ' + str(n), section='priorities', condition={'op':'natural_language','need':'Synthetic','instruction':'Clarify item ' + str(n)}, weight=1, conversation=[], proposal_key='rule'+str(n), created_by=1)
            db.add(r); db.flush(); rules.append(r)
        pcs = []
        for name in ('First', 'Second'):
            raw = m.RawResume(source_type='LOCAL_UPLOAD',original_filename='synthetic.pdf',storage_path='synthetic.pdf', raw_text='Synthetic CV with dates 2017 to 2024 and CompanyXYZ'); db.add(raw); db.flush()
            candidate = m.Candidate(full_name=name, email=name.lower()+'@example.test', phone='+14075550188', raw_resume_id=raw.id); db.add(candidate); db.flush()
            person = m.CandidatePerson(full_name=name); db.add(person); db.flush()
            application = m.Application(person_id=person.id, candidate_id=candidate.id, target_role='TEST'); db.add(application); db.flush()
            pc = ps.PositionCandidate(position_id=pid, application_id=application.id, candidate_id=candidate.id, channel='MANUAL_UPLOAD'); db.add(pc); db.flush(); pcs.append(pc)
        base = {'active':True,'natural_language':True,'priority':2,'qualitative_priority':'Media','unfit':False,'unknown':True,'status':'Da chiarire',
            'reason':'2017 to 2024 at CompanyXYZ. Repeated CV data.',
            'details':[{'id':r.id,'title':r.title,'section':r.section,'condition':r.condition['instruction'],'outcome':None,'ai_outcome':'DA_CHIARIRE','reason':'Uncertain item '+str(r.id),'quotes':[]} for r in rules]}
        run = {'mode':'natural_language','incremental_version':1,'state':'COMPLETED','role_code':'TEST','signature':conversation.signature(rules),
            'rules':conversation.snapshot(rules),'results':{str(pc.id):base for pc in pcs},'cv_hashes':{str(pc.id):inc.cv_input(db,pc)[1] for pc in pcs}}
        position.organization_context_json=json.dumps({'pdl_filter_run':run}); db.commit()
        pcid=pcs[0].id; candidate_id=pcs[0].candidate_id; raw_id=db.get(m.Candidate,candidate_id).raw_resume_id
    routes._cfg.SessionFactory=factory
    routes._cfg.documents=NS(exists=lambda path:True,read=lambda path:b'%PDF-1.4\nSynthetic original PDF')
    routes.current_account=lambda db:object()
    routes.actor_for=lambda db,account:NS(id=1,name='Synthetic reviewer',role='OWNER',is_owner=True,can_view=lambda p:True,can_edit=lambda p:request.headers.get('X-Read-Only')!='1')
    app=Flask(__name__,template_folder=str(HERE/'templates'),static_folder=str(HERE/'static'));app.secret_key='synthetic-review';app.config['TESTING']=True;app.register_blueprint(routes.bp)
    from local_i18n import install
    install(app)
    client=app.test_client()
    with client.session_transaction() as session:session[shared.SESSION_CSRF_KEY]='csrf'
    url=f'/posizioni/{pid}/candidati/{pcid}/revisione-ai'
    def load():
        response=client.get(url);assert response.status_code==200,response.get_data(as_text=True);return response.json
    def payload(value,action='save'):
        return {'version':value['version'],'priority':'LOW','channel':value.get('channel','EMAIL'),'custom_questions':value.get('custom_questions',[]),'action':action,'items':[{k:item[k] for k in ('id','mode','answer','question')} for item in value['items']]}
    def post(data,**kwargs):return client.post(url,data={'csrf_token':'csrf','payload':json.dumps(data)},**kwargs)
    value=load();assert len(value['items'])==3
    assert value['phone']=='+14075550188' and value['reading_url'].endswith('/sintesi-cv')
    reading=client.get(value['reading_url']);assert reading.status_code==200 and 'non è ancora stata salvata' in reading.get_data(as_text=True)
    original_pdf=client.get(f'/posizioni/{pid}/candidati/{pcid}/cv-originale')
    assert original_pdf.status_code==200 and original_pdf.mimetype=='application/pdf' and original_pdf.data.startswith(b'%PDF')
    from workspace import cv_observations
    with factory() as db:
        position=db.get(ps.Position,pid);context=position_settings.context(position)
        state={'cv_hash':inc.cv_input(db,db.get(ps.PositionCandidate,pcid))[1],'role_code':'TEST','result':base}
        summary_context={'role_code':'TEST','title':position.title,'location':position.location_label,'description':position.description}
        state['cv_observations']={'signature':cv_observations.signature(state,conversation.snapshot(rules),summary_context),
            'sections':[{'key':key,'title':title,'bullets':[{'text':'Osservazione salvata '+key,'quotes':['CompanyXYZ'],'uncertain':False}]} for key,title in cv_observations.SECTIONS]}
        context['pdl_filter_run']['rule_cache']={str(pcid):state}
        position.organization_context_json=json.dumps(context);db.commit()
    with patch.object(conversation.rule_ai,'generate',side_effect=AssertionError('Summary GET called AI')):
        for _ in range(2):
            reading=client.get(value['reading_url']);assert reading.status_code==200
            assert 'Osservazione salvata profile' in reading.get_data(as_text=True) and 'CompanyXYZ' not in reading.get_data(as_text=True)
    assert 'CompanyXYZ' not in value['analysis'] and '2017' not in value['analysis']
    value['items'][0].update(mode='ANSWER',answer='Private direct answer')
    value['items'][1].update(mode='IGNORE')
    value['items'][2].update(mode='ASK',question='ONLY SELECTED QUESTION?')
    original_payload=payload(value)
    with patch.object(review,'smtp_settings',return_value=NS(username='sender@example.test')),patch.object(smtp_email,'send_email') as send:
        assert post(original_payload).status_code==200
        assert not send.called
        assert post(original_payload).status_code==409
        with factory() as db:
            position=db.get(ps.Position,pid);pc=db.get(ps.PositionCandidate,pcid)
            original=position_settings.context(position)['pdl_filter_run']['results'][str(pcid)]
            assert original==base,'Human review modified AI result'
            effective=review.effective(db,position,pc,original)
            assert effective['priority']==1 and effective['unknown']
            assert sum(d.get('review_resolution') in ('ANSWER','IGNORE') for d in effective['details'])==2
            assert not list(db.scalars(select(ps.Decision)))
            assert db.scalar(select(func.count()).select_from(EmailOutbox))==0
        with app.test_request_context('/'):
            with factory() as db:assert board_rows(db,db.get(ps.Position,pid))[0]['pc'].id==pcs[1].id
        assert post(payload(load(),'accept')).status_code==422
        keep=payload(load());keep['priority']='';assert post(keep).status_code==200
        assert load()['accepted'] and load()['items'][2]['mode']=='ASK'
        assert post(payload(load(),'send')).json['delivery']=='SENT'
        assert send.call_count==1
        sent=send.call_args.kwargs
        assert sent['to_address']=='first@example.test'
        assert 'ONLY SELECTED QUESTION?' in sent['text_body'] and 'Private direct answer' not in sent['text_body']
        assert 'Uncertain item '+str(rules[1].id) not in sent['text_body']
        assert post(payload(load(),'send')).json['delivery']=='SENT'
        assert send.call_count==1
        with factory() as db:assert db.scalar(select(func.count()).select_from(EmailOutbox))==1
        value=load();value['items'][2].update(mode='IGNORE')
        assert post(payload(value,'send')).status_code==422
        assert post(payload(value)).status_code==200
        with factory() as db:
            effective=review.effective(db,db.get(ps.Position,pid),db.get(ps.PositionCandidate,pcid),base)
            assert not effective['unknown'] and effective['status']=='Revisionata'
        value=load();value['items'][2].update(mode='ASK',question='SECOND SELECTED QUESTION?')
        with patch.object(smtp_email,'send_email',side_effect=TimeoutError):
            assert post(payload(value,'send')).json['delivery']=='UNKNOWN'
        assert post(payload(load(),'send')).json['delivery']=='UNKNOWN'
        assert send.call_count==1,'Uncertain batch was resent'
    with patch.object(review,'smtp_settings',return_value=NS(username='sender@example.test')),patch.object(smtp_email,'send_email') as send:
        value=load()
        for item in value['items']:item['mode']='IGNORE'
        value['custom_questions']=['PERSONAL QUESTION ONLY?'];value['channel']='TEXT'
        assert post(payload(value)).status_code==200
        assert load()['channel']=='TEXT' and load()['custom_questions']==['PERSONAL QUESTION ONLY?']
        assert post(payload(load(),'send')).status_code==422 and not send.called
        value=load();value['channel']='EMAIL'
        assert post(payload(value,'send')).json['delivery']=='SENT'
        assert send.call_count==1 and 'PERSONAL QUESTION ONLY?' in send.call_args.kwargs['text_body']
        assert 'SECOND SELECTED QUESTION?' not in send.call_args.kwargs['text_body']
        assert post(payload(load(),'send')).json['delivery']=='SENT' and send.call_count==1
        forged=payload(load());forged['custom_questions']=['too long']*21
        assert post(forged).status_code==422
    # Reuse AWS transport only for explicitly selected Text; never real sends.
    from workspace import review_text
    app.config['RFONE_LOCAL_OPERATOR']='synthetic'
    with patch.dict(os.environ,{'RFONE_SMS_ORIGINATION_IDENTITY':'+18005550100','RFONE_SMS_AWS_PROFILE':'synthetic-profile'}),patch.object(review_text.sms_text,'send_text',return_value='synthetic-aws-message') as sms,patch.object(smtp_email,'send_email') as email:
        assert load()['text_available'] is True
        value=load();value['channel']='TEXT'
        value['items'][0].update(mode='ANSWER',answer='PRIVATE TEXT ANSWER')
        value['items'][1].update(mode='IGNORE')
        value['items'][2].update(mode='ASK',question='ONLY SELECTED TEXT?')
        value['custom_questions']=['AND PERSONAL TEXT?']
        assert post(payload(value,'send')).json['delivery']=='SENT'
        assert sms.call_count==1 and not email.called
        args=sms.call_args.kwargs
        assert args['to_number']=='+14075550188' and args['profile_name']=='synthetic-profile'
        assert 'ONLY SELECTED TEXT?' in args['body'] and 'AND PERSONAL TEXT?' in args['body']
        assert 'PRIVATE TEXT ANSWER' not in args['body']
        assert post(payload(load(),'send')).json['delivery']=='SENT' and sms.call_count==1
        value=load();value['custom_questions']=['x'*1600]
        assert post(payload(value,'send')).status_code==422 and sms.call_count==1
        with factory() as db:db.get(m.Candidate,candidate_id).phone='invalid';db.commit()
        assert post(payload(load(),'send')).status_code==422 and sms.call_count==1
        with factory() as db:db.get(m.Candidate,candidate_id).phone='(407) 555-0188';db.commit()
        value=load();value['custom_questions']=['DIFFERENT TEXT BATCH?']
        def concurrently_delivered(**kwargs):
            with factory() as db:
                position=db.get(ps.Position,pid);context=position_settings.context(position)
                assert any(b['status']=='SENDING' and 'DIFFERENT TEXT BATCH?' in b['body'] for b in context['candidate_text_outbox'].values())
                context['concurrent_review_marker']='preserved'
                position.organization_context_json=json.dumps(context);db.commit()
            return 'synthetic-second-message'
        with patch.object(review_text.sms_text,'send_text',side_effect=concurrently_delivered):
            assert post(payload(value,'send')).json['delivery']=='SENT'
        with factory() as db:assert position_settings.context(db.get(ps.Position,pid))['concurrent_review_marker']=='preserved'
        value=load();value['custom_questions']=['UNCERTAIN TEXT BATCH?']
        with patch.object(review_text.sms_text,'send_text',side_effect=TimeoutError):
            assert post(payload(value,'send')).json['delivery']=='UNKNOWN'
        assert post(payload(load(),'send')).json['delivery']=='UNKNOWN' and sms.call_count==1
    assert post(payload(load()),headers={'X-Read-Only':'1'}).status_code==403
    assert client.get(url,headers={'X-Read-Only':'1'}).json['can_edit'] is False
    assert client.get(f'/posizioni/{other_id}/candidati/{pcid}/revisione-ai').status_code==404
    assert client.get(f'/posizioni/{other_id}/candidati/{pcid}/sintesi-cv').status_code==404
    value=load();forged=payload(value);forged['items'][0]['id']=99999;assert post(forged).status_code==422
    assert client.post(url,data={'csrf_token':'wrong','payload':json.dumps(payload(value))}).status_code==302
    with factory() as db:db.get(m.RawResume,raw_id).raw_text='Changed after review';db.commit()
    assert client.get(url).status_code==422
    assert post(payload(value)).status_code==422
    engine.dispose()
print('PASS: conclusion-only analysis; per-item answer/ignore/selected send; independent priority and ranking; unchanged AI results; acceptance; exact email content; no duplicate/uncertain resend; scope, permissions, concurrency and changed-CV protection. No real mail sent.')
