"""Actual 5094 Registry/Selection/Training proof. Local-only synthetic records."""
import sys,json,uuid,time,socket
from pathlib import Path
from sqlalchemy import create_engine,select,text,func,inspect,delete,MetaData,Table
from sqlalchemy.orm import Session
from sqlalchemy.engine import URL
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'RF-One Data Store'))
from rfone_data_store import models as m,access_profiles as profiles,employee_directory as directory
from rfone_data_store.selection import application_service as selection
from rfone_data_store.training import service as training

BASE='http://127.0.0.1:5094'
STATE=Path('C:/Users/servi/AppData/Local/RF-One/Employee Directory/AWS-20261110T120743Z/verification.json')
OUT=Path('C:/Users/servi/AppData/Local/RF-One/Backups/registry-training-selection-20261112')


def run():
    state=json.loads(STATE.read_text(encoding='utf-8'));cfg=state['local_database']
    assert cfg['host']=='127.0.0.1' and cfg['database']=='rfone_employee_directory' and state['web_port']==5094
    for attempt in range(30):
        try:
            with socket.create_connection(('127.0.0.1',5094),timeout=1):break
        except OSError:time.sleep(1)
    engine=create_engine(URL.create('postgresql+psycopg2',username=cfg['username'],host=cfg['host'],port=cfg['port'],database=cfg['database']))
    name='ZZ QA Shared '+uuid.uuid4().hex[:10];email=uuid.uuid4().hex+'@example.test'
    person_id=account_id=training_id=acting_id=candidate_id=facet_id=None
    watch=['employees','rfone_accounts','candidate_persons','candidates','applications','training_accounts','training_needs','training_assignments','training_pills','rfone_account_domain_access','rfone_person_company_memberships','rfone_role_profile_assignments','employee_context_links','person_qualifications']
    def digest(c):return {t:c.scalar(text("SELECT md5(string_agg(row_to_json(t)::text,'|' ORDER BY row_to_json(t)::text)) FROM "+t+' t')) for t in watch}
    with engine.connect() as c:
        before=digest(c);event_start=c.scalar(text('select coalesce(max(id),0) from rfone_access_profile_events'))
    checks=[]
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True)
            context=browser.new_context(viewport={'width':1440,'height':1000},locale='it-IT')
            context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(BASE+'/') else r.abort())
            page=context.new_page();errors=[];page.on('pageerror',lambda exc:errors.append(str(exc)))
            assert page.goto(BASE+'/admin/roles',wait_until='networkidle').status==200
            page.locator('[data-new-person]').click();modal=page.locator('#person-dialog')
            modal.locator('[name=name]').fill(name);modal.locator('[name=email]').fill(email)
            modal.get_by_role('checkbox',name='Dipendente',exact=True).check()
            modal.locator('[name=account_status]').select_option('ACTIVE')
            with page.expect_navigation():modal.get_by_role('button',name='Salva',exact=True).click()
            payload=page.locator('#profile-data').evaluate('(el)=>JSON.parse(el.textContent)')
            row=next(r for r in payload['people'] if r['name']==name);person_id=int(row['key'].split(':')[1])
            with Session(engine) as db:
                rf=profiles.profile_account(db,f'employee:{person_id}');account_id=rf.id;password_hash=rf.password_hash
                assert db.scalar(select(func.count()).select_from(m.Employee).where(m.Employee.display_name==name))==1
            assert page.goto(BASE+'/training-trainer/students/new',wait_until='networkidle').status==200
            page.locator('#registry-person').select_option(str(person_id))
            assert page.locator('#display-name').input_value()==name
            assert not page.locator('#new-credentials').is_visible()
            with page.expect_navigation():page.get_by_role('button',name='Iscrivi a Training').click()
            assert '/training-trainer/students' in page.url
            with Session(engine) as db:
                rf=db.get(m.RFOneAccount,account_id);assert rf.password_hash==password_hash
                link=db.scalar(select(m.RFOneTrainingIdentityLink).where(m.RFOneTrainingIdentityLink.rfone_account_id==account_id));assert link
                training_id=link.training_account_id;learner=db.get(m.TrainingAccount,training_id);acting_id=learner.acting_identity_id
                assert directory.context_person_id(db,'TRAINING',training_id)==person_id
                assert db.scalar(text('select count(*) from person_qualifications'))==0
            # Repeat the actual enrollment POST using the existing Registry selection.
            page.goto(BASE+'/training-trainer/students/new');page.locator('#registry-person').select_option(str(person_id))
            with page.expect_navigation():page.get_by_role('button',name='Iscrivi a Training').click()
            with Session(engine) as db:
                assert db.scalar(select(m.RFOneTrainingIdentityLink.training_account_id).where(m.RFOneTrainingIdentityLink.rfone_account_id==account_id))==training_id
                candidate=m.Candidate(full_name=name,email=email,parsing_mode='DEMO',source='LOCAL_QA',target_role='SERVER')
                db.add(candidate);db.flush();candidate_id=candidate.id
                application=selection.create_application(db,candidate_id=candidate.id,restaurant_id=None,target_role='SERVER');facet_id=application.person_id
                assert directory.context_person_id(db,'CANDIDATE',facet_id)==person_id
                repeat=selection.create_application(db,candidate_id=candidate.id,restaurant_id=None,target_role='SERVER');assert repeat.id==application.id
                owner=db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.username=='rfone'))
                trainer_id=db.scalar(select(m.RFOneTrainingIdentityLink.training_account_id).where(m.RFOneTrainingIdentityLink.rfone_account_id==owner.id))
                pill=db.scalar(select(m.TrainingPill).order_by(m.TrainingPill.id))
                need=training.create_need(db,student_account_id=training_id,text='Synthetic Registry verification',origin=None,created_by_account_id=trainer_id)
                assignment=training.assign_pill(db,need_id=need.id,pill_id=pill.id,assigned_by_account_id=trainer_id);assignment_id=assignment.id;title=pill.title
                db.commit()
            checks.append('Actual Registry and Training POSTs reuse one person, login and learning identity; repeated enrollment keeps credentials and IDs; no STUDENT qualification exists.')
            response=page.goto(BASE+f'/selection/candidate/{candidate_id}',wait_until='networkidle')
            assert response.status==200,(response.status,page.url)
            assert name in page.locator('body').inner_text()
            page.goto(BASE+'/admin/roles');payload=page.locator('#profile-data').evaluate('(el)=>JSON.parse(el.textContent)')
            assert len([r for r in payload['people'] if r['name']==name])==1
            checks.append('Selection application service and actual Selection HTTP view share the same Registry person; repeated application creation is idempotent.')
            page.locator('form[action="/local/access-user"] select').select_option(str(account_id))
            with page.expect_navigation():page.locator('form[action="/local/access-user"] button').click()
            response=page.goto(BASE+f'/training/assignments/{assignment_id}',wait_until='networkidle')
            assert response.status==200,(response.status,page.url)
            assert title in page.locator('body').inner_text()
            with engine.connect() as c:assert c.scalar(text('select count(*) from person_qualifications'))==0
            checks.append('The Registry employee opens assigned course content over HTTP 5094 with zero STUDENT qualifications.')
            assert not errors,errors
            context.close();browser.close()
    finally:
        with engine.begin() as c:
            # Recover only this uniquely named fixture after an interrupted assertion.
            ids=c.execute(text('select id from employees where display_name=:name'),{'name':name}).scalars().all();assert len(ids)<=1
            if ids:
                person_id=ids[0]
                account_id=c.scalar(text('select rfone_account_id from employee_context_links where employee_id=:id and rfone_account_id is not null'),{'id':person_id})
                training_id=c.scalar(text('select training_account_id from rfone_training_identity_links where rfone_account_id=:id'),{'id':account_id})
                if training_id:
                    acting_id=c.scalar(text('select acting_identity_id from training_accounts where id=:id'),{'id':training_id})
                    c.execute(text('delete from training_assignments where need_id in (select id from training_needs where student_account_id=:id)'),{'id':training_id})
                    c.execute(text('delete from training_needs where student_account_id=:id'),{'id':training_id})
                if candidate_id:
                    c.execute(text('delete from person_match_candidates where application_id in (select id from applications where candidate_id=:id)'),{'id':candidate_id})
                    c.execute(text('delete from applications where candidate_id=:id'),{'id':candidate_id})
                c.execute(text('delete from employee_context_links where employee_id=:id'),{'id':person_id})
                if candidate_id:c.execute(text('delete from candidates where id=:id'),{'id':candidate_id})
                if facet_id:c.execute(text('delete from candidate_persons where id=:id'),{'id':facet_id})
                for event in c.execute(text('select id,details from rfone_access_profile_events where id>:start'),{'start':event_start}):
                    if event.details.get('target')==f'employee:{person_id}' or event.details.get('employee_id')==person_id or event.details.get('account_id')==account_id:
                        c.execute(text('delete from rfone_access_profile_events where id=:id'),{'id':event.id})
                c.execute(text('delete from employee_directory_events where employee_id=:id'),{'id':person_id})
                c.execute(text('delete from rfone_person_company_statuses where employee_id=:id'),{'id':person_id})
                c.execute(text('delete from rfone_account_domain_access where account_id=:id'),{'id':account_id})
                c.execute(text('delete from rfone_training_identity_links where rfone_account_id=:id'),{'id':account_id})
                if training_id:c.execute(text('delete from training_accounts where id=:id'),{'id':training_id})
                if acting_id:c.execute(text('delete from acting_identities where id=:id'),{'id':acting_id})
                c.execute(text('delete from rfone_accounts where id=:id'),{'id':account_id})
                c.execute(text('delete from employees where id=:id and display_name=:name'),{'id':person_id,'name':name})
            assert digest(c)==before,'Original watched records changed; review local test.'
        engine.dispose()
    checks.append('Synthetic records removed; original Registry, Selection, accounts, course history and grants match pre-test digests.')
    OUT.joinpath('verification.json').write_text(json.dumps({'base_url':BASE,'checks':checks},ensure_ascii=False,indent=2),encoding='utf-8')
    for check in checks:print('PASS:',check)

if __name__=='__main__':run()
