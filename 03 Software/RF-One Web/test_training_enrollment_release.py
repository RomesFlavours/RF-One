"""Rollback-only enrollment integration and browser tests; no mail/AWS writes."""
import json
import re
import secrets
import sys
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
from sqlalchemy import select, func, text
from sqlalchemy.orm import sessionmaker
import training_cloud as training_local
import os
from sqlalchemy import create_engine


def run(browser=False):
    engine = create_engine(os.environ['RFONE_TEST_DATABASE_URL'])
    from rfone_data_store import models as m, student_registry as registry, people_registry as people
    from rfone_data_store import rfone_account_service as accounts
    from rfone_data_store.training import enrollment as en, workspace as ws
    from rfone_data_store.selection import workspace_models as ps
    from rfone_data_store.technical import account_email
    from training_enrollment_routes import INVALID
    tables = ['candidate_persons','rfone_accounts','employees','training_accounts','training_enrollment_invitations','training_assignments']
    def counts(c):return {t:c.scalar(text('SELECT count(*) FROM '+t)) for t in tables}
    connection = engine.connect(); before=counts(connection); connection.rollback(); transaction=connection.begin()
    factory = sessionmaker(bind=connection,join_transaction_mode='create_savepoint',expire_on_commit=False)
    checks=[]; marker='Zven'+secrets.token_hex(4); email=marker.lower()+'@example.invalid'
    try:
        app=training_local.create_app(SessionFactory=factory)
        import training_cloud as shell, auth, db as web_db
        shell.SessionFactory=factory;auth.SessionFactory=factory;web_db.SessionFactory=factory
        for key in ('_training_internal_routes','_training_internal_auth','_training_internal_db'):
            if key in sys.modules:sys.modules[key].SessionFactory=factory
        app.config.update(TESTING=True,SESSION_COOKIE_SECURE=False)
        client=app.test_client()
        with factory() as db:
            actor=db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.username=='rfone'))
            actor_id,actor_version=actor.id,actor.session_version
        def operator(c):
            with c.session_transaction() as s:
                s[auth.SESSION_ACCOUNT_KEY]=actor_id;s[auth.SESSION_VERSION_KEY]=actor_version;s[auth.SESSION_CSRF_KEY]='enroll-test'
        def token(c):
            c.get('/training/activate')
            with c.session_transaction() as s:return s[auth.SESSION_CSRF_KEY]
        def create(data,c=client):
            operator(c)
            response=c.post('/training/manage/enrollment',data=dict(csrf_token='enroll-test',**data))
            assert response.status_code==200,response.get_data(as_text=True)
            body=response.get_data(as_text=True)
            return re.search(r'id="created-invitation-link" readonly value="[^"]+/training/activate/([A-Za-z0-9_-]+)"',body)[1]
        def newlearner(t):
            c=app.test_client();r=c.get('/training/activate/'+t);assert r.status_code==302
            r=c.get(r.location);assert r.status_code==200
            with c.session_transaction() as s:assert not s.get(auth.SESSION_ACCOUNT_KEY)
            return c
        with patch.object(account_email,'send_email',side_effect=lambda **kw: None):
            assert app.test_client().get('/training/manage/enrollment').status_code==302
            operator(client)
            assert client.post('/training/manage/enrollment',data=dict(mode='direct',email=email)).status_code in (400,403)
            t=create(dict(mode='direct',email=email))
            with factory() as db:
                invitation=en.lookup(db,t);assert invitation and invitation.token_digest!=t
                assert not db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.email==email))
                assert not db.scalar(select(m.CandidatePerson).where(m.CandidatePerson.primary_email==email))
            checks.append('Direct invitation creates no person/login; trainer authorization, CSRF and token digest enforced')
            learner=newlearner(t)
            r=learner.post('/training/activate',data=dict(csrf_token=token(learner),first_name=marker,last_name='Direct',password='too-short',password_confirm='different'))
            assert r.status_code==400
            assert learner.get('/training/manage/students').status_code==302
            r=learner.post('/training/activate',data=dict(csrf_token=token(learner),first_name=marker,last_name='Direct',phone='+1 407 555 0191',password='Chosen-Safe-Pass9',password_confirm='Chosen-Safe-Pass9',email='attacker@example.invalid'))
            assert r.status_code==302,r.get_data(as_text=True)
            with factory() as db:
                account=db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.email==email));account_id=account.id
                identity=db.get(people.PersonAccountLink,account.id);person_id=identity.person_id
                assert account.email_verified_at and not account.is_admin
                assert db.get(registry.PersonQualification,(person_id,'STUDENT'))
                assert not db.scalar(select(people.PersonEmployeeLink).where(people.PersonEmployeeLink.person_id==person_id))
                link=db.scalar(select(m.RFOneTrainingIdentityLink).where(m.RFOneTrainingIdentityLink.rfone_account_id==account.id))
                assert not ws.profile(db,link.training_account_id).must_change_password
                assert [(g.domain_code,g.role_code) for g in accounts.list_domain_access_for_account(db,account.id) if g.enabled]==[('TRAINING','student')]
                saved_password=account.password_hash;saved_username=account.username
            home=learner.get('/training')
            assert home.status_code==200 and saved_username in home.get_data(as_text=True)
            assert app.test_client().get('/training/activate/'+t,follow_redirects=True).status_code==400
            checks.append('Activation sets chosen password, immutable email, STUDENT only, one person/account, valid learner session, single use')
            # Duplicates: the operator must explicitly choose the person; existing credentials survive.
            operator(client)
            with factory() as db:
                db.scalar(select(en.EnrollmentInvitation).where(en.EnrollmentInvitation.email==email)).created_at-=timedelta(seconds=61);db.commit()
            r=client.post('/training/manage/enrollment',data=dict(csrf_token='enroll-test',mode='direct',email=email))
            assert r.status_code==400 and 'Confirm' in r.get_data(as_text=True)
            t2=create(dict(mode='direct',email=email,confirmation=f'person:{person_id}'))
            existing=newlearner(t2)
            assert 'Current RF-One password' in existing.get('/training/activate').get_data(as_text=True)
            r=existing.post('/training/activate',data=dict(csrf_token=token(existing),first_name=marker,last_name='Direct',current_password='wrong'))
            assert r.status_code==400
            r=existing.post('/training/activate',data=dict(csrf_token=token(existing),first_name=marker,last_name='Direct',current_password='Chosen-Safe-Pass9'))
            assert r.status_code==302,r.get_data(as_text=True)
            with factory() as db:
                a=db.get(m.RFOneAccount,account_id);assert a.password_hash==saved_password and a.username==saved_username
                assert db.scalar(select(func.count()).select_from(m.RFOneAccount).where(m.RFOneAccount.email==email))==1
                assert db.get(people.PersonAccountLink,a.id).person_id==person_id
            checks.append('Explicit duplicate confirmation, current-password proof and existing username/password/person preserved')
            # Expiry, rate limiting, replacement and no automatic merge on later evidence.
            expired_email=marker.lower()+'-expired@example.invalid'
            exp=create(dict(mode='direct',email=expired_email))
            with factory() as db:
                inv=en.lookup(db,exp);inv.expires_at=en.now()-timedelta(seconds=1);db.commit()
            assert app.test_client().get('/training/activate/'+exp,follow_redirects=True).status_code==400
            again=create(dict(mode='direct',email=marker.lower()+'-again@example.invalid'))
            with factory() as db:
                inv=en.lookup(db,again);againemail=inv.email;inv.created_at-=timedelta(seconds=61);db.commit()
            replacement=create(dict(mode='direct',email=againemail))
            with factory() as db:assert en.lookup(db,again) is None and en.lookup(db,replacement)
            operator(client)
            assert client.post('/training/manage/enrollment',data=dict(csrf_token='enroll-test',mode='direct',email=againemail)).status_code==400
            late=create(dict(mode='direct',email=marker.lower()+'-late@example.invalid'))
            with factory() as db:
                people.create_identity(db,full_name=marker+' Collision',email=marker.lower()+'-late@example.invalid',normalized_name=(marker+' Collision').lower());db.commit()
            lateclient=newlearner(late)
            r=lateclient.post('/training/activate',data=dict(csrf_token=token(lateclient),first_name=marker,last_name='Collision',password='Another-Safe9',password_confirm='Another-Safe9'))
            assert r.status_code==400
            checks.append('Expired/replaced links, issuance limits and identity created after invitation are safely rejected')
            # Selection: real persistence models, latest decision only, position scope.
            with factory() as db:
                accounts.set_domain_access(db,account_id=actor_id,domain_code='SELECTION',enabled=True,role_code='OWNER')
                req=db.scalar(select(m.RequirementSet.id));assert req
                position=ps.WorkspacePosition(title=marker+' test position',role_code='SERVER',location_label='Test',timezone='America/New_York',manager_account_id=actor_id,created_by_account_id=actor_id,requirement_set_id=req)
                db.add(position);db.flush()
                person=people.create_identity(db,full_name=marker+' Selected',email=marker.lower()+'-selected@example.invalid',normalized_name=(marker+' Selected').lower())
                candidate=m.Candidate(full_name=person.full_name,email=person.primary_email,phone='+1 407 555 0192',parsing_mode='DEMO')
                db.add(candidate);db.flush()
                application=m.Application(person_id=person.id,candidate_id=candidate.id);db.add(application);db.flush()
                pc=ps.WorkspacePositionCandidate(position_id=position.id,application_id=application.id,candidate_id=candidate.id,channel='MANUAL_UPLOAD');db.add(pc);db.flush()
                decision=ps.WorkspaceDecision(position_candidate_id=pc.id,decision='HIRED',actor_account_id=actor_id,actor_name='Test operator');db.add(decision);db.flush()
                selected_id,selected_person,selected_email=pc.id,person.id,person.primary_email
                assert any(r['id']==selected_id and r['phone']==candidate.phone for r in en.confirmed_candidates(db,db.get(m.RFOneAccount,actor_id)))
                db.commit()
            selected=create(dict(mode='selection',selection_id=str(selected_id),email=selected_email))
            selectedclient=newlearner(selected)
            r=selectedclient.post('/training/activate',data=dict(csrf_token=token(selectedclient),first_name=marker,last_name='Selected',phone='+1 407 555 0192',password='Selected-Pass9',password_confirm='Selected-Pass9'))
            assert r.status_code==302,r.get_data(as_text=True)
            with factory() as db:
                a=db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.email==selected_email));assert db.get(people.PersonAccountLink,a.id).person_id==selected_person
                assert db.get(m.Application,application.id).person_id==selected_person
                db.scalar(select(en.EnrollmentInvitation).where(en.EnrollmentInvitation.email==selected_email)).created_at-=timedelta(seconds=61)
                db.commit()
            withdrawn=create(dict(mode='selection',selection_id=str(selected_id),email=selected_email))
            with factory() as db:
                # A later decision supersedes HIRED even for an already-issued link.
                db.add(ps.WorkspaceDecision(position_candidate_id=selected_id,decision='NOT_SELECTED',actor_account_id=actor_id,actor_name='Test operator'))
                db.flush();assert not any(r['id']==selected_id for r in en.confirmed_candidates(db,db.get(m.RFOneAccount,actor_id)))
                db.commit()
            operator(client)
            assert client.post('/training/manage/enrollment',data=dict(csrf_token='enroll-test',mode='selection',selection_id=str(selected_id),email=selected_email)).status_code==400
            withdrawnclient=newlearner(withdrawn)
            r=withdrawnclient.post('/training/activate',data=dict(csrf_token=token(withdrawnclient),first_name=marker,last_name='Selected',current_password='Selected-Pass9'))
            assert r.status_code==400 and 'no longer available' in r.get_data(as_text=True), (r.status_code,r.get_data(as_text=True))
            with factory() as db:
                db.add(ps.WorkspaceDecision(position_candidate_id=selected_id,decision='HIRED',actor_account_id=actor_id,actor_name='Test operator'));db.flush()
                grant=db.scalar(select(m.RFOneAccountDomainAccess).where(m.RFOneAccountDomainAccess.account_id==actor_id,m.RFOneAccountDomainAccess.domain_code=='SELECTION'))
                grant.enabled=False;db.flush()
                assert not en.confirmed_candidates(db,db.get(m.RFOneAccount,actor_id))
                grant.enabled=True;db.commit()
            checks.append('Confirmed Selection CV details reuse the exact source person; latest decision supersedes HIRED')
            with factory() as db:
                for inv in db.scalars(select(en.EnrollmentInvitation).where(en.EnrollmentInvitation.email==email)):
                    inv.created_at-=timedelta(seconds=61)
                db.commit()
            limited=create(dict(mode='direct',email=email,confirmation=f'person:{person_id}'))
            limitedclient=newlearner(limited)
            for _ in range(5):
                assert limitedclient.post('/training/activate',data=dict(csrf_token=token(limitedclient),first_name=marker,last_name='Direct',current_password='wrong')).status_code==400
            with factory() as db:assert en.lookup(db,limited) is None
            denied=create(dict(mode='direct',email=marker.lower()+'-revoked@example.invalid'))
            deniedclient=newlearner(denied)
            with factory() as db:
                db.scalar(select(m.RFOneAccountDomainAccess).where(m.RFOneAccountDomainAccess.account_id==actor_id,m.RFOneAccountDomainAccess.domain_code=='TRAINING')).enabled=False;db.commit()
            r=deniedclient.post('/training/activate',data=dict(csrf_token=token(deniedclient),first_name=marker,last_name='Revoked',password='Denied-Pass9',password_confirm='Denied-Pass9'))
            assert r.status_code==400 and 'no longer authorized' in r.get_data(as_text=True)
            with factory() as db:
                db.scalar(select(m.RFOneAccountDomainAccess).where(m.RFOneAccountDomainAccess.account_id==actor_id,m.RFOneAccountDomainAccess.domain_code=='TRAINING')).enabled=True;db.commit()
            checks.append('Selection access cannot be borrowed from Training; withdrawn decisions/revoked issuer access and five wrong passwords block activation')
            if browser:
                import threading
                from werkzeug.serving import make_server
                from playwright.sync_api import sync_playwright, expect
                # Browser operator is the existing RF-One account with its actual test-session grants.
                server=make_server('127.0.0.1',0,app);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                base=f'http://127.0.0.1:{server.server_port}';os.environ['RFONE_PUBLIC_BASE_URL']=base
                dest=Path(__file__).resolve().parents[2]/'output/training-enrollment-20261113';dest.mkdir(parents=True,exist_ok=True)
                try:
                    with sync_playwright() as pw:
                        browser_instance=pw.chromium.launch(channel='msedge',headless=True)
                        context=browser_instance.new_context(viewport={'width':1440,'height':1000})
                        context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base+'/') else route.abort())
                        with app.test_request_context():
                            value=app.session_interface.get_signing_serializer(app).dumps({auth.SESSION_ACCOUNT_KEY:actor_id,auth.SESSION_VERSION_KEY:actor_version})
                        context.add_cookies([dict(name=app.config['SESSION_COOKIE_NAME'],value=value,url=base)])
                        page=context.new_page();page.goto(base+'/training/manage/students');page.get_by_role('link',name='Invite student',exact=True).click()
                        page.on('pageerror',lambda error:print('BROWSER ERROR:',str(error)))
                        page.on('console',lambda message:print('BROWSER CONSOLE:',message.text) if message.type=='error' else None)
                        page.get_by_role('radio',name='Confirmed in Selection',exact=True).check()
                        page.locator('[name=selection_id]').select_option(str(selected_id))
                        expect(page.get_by_label('Invitee email')).to_have_value(selected_email)
                        expect(page.locator('[name=phone]')).to_have_value('+1 407 555 0192')
                        page.screenshot(path=str(dest/'00-selection-prefill.png'),full_page=True)
                        page.get_by_role('radio',name='Direct invitation',exact=True).check()
                        page.locator('[name=name]').fill('');page.locator('[name=phone]').fill('')
                        page.get_by_label('Invitee email').fill(marker.lower()+'-browser@example.invalid')
                        page.get_by_role('button',name='Create invitation',exact=True).click()
                        expect(page.locator('#created-invitation-link')).to_be_visible()
                        link=page.locator('#created-invitation-link').input_value()
                        page.screenshot(path=str(dest/'01-invitation.png'),full_page=True)
                        page.goto(link);page.get_by_label('First name',exact=True).fill(marker);page.get_by_label('Surname',exact=True).fill('Browser')
                        page.get_by_label('Choose your password',exact=True).fill('Browser-Pass9');page.get_by_label('Confirm password',exact=True).fill('Browser-Pass9')
                        page.screenshot(path=str(dest/'02-activation.png'),full_page=True)
                        page.get_by_role('button',name='Confirm and activate Training',exact=True).click()
                        expect(page).to_have_url(base+'/training');page.screenshot(path=str(dest/'03-training.png'),full_page=True)
                        browser_instance.close()
                    checks.append('Edge browser: Students -> Selection prefill/direct invitation -> one activation page -> Training; only loopback resources')
                finally:server.shutdown();thread.join(timeout=5)
        print('\n'.join('PASS: '+c for c in checks))
        return checks
    finally:
        transaction.rollback();connection.close()
        with engine.connect() as c:assert counts(c)==before,'Test records leaked'
        engine.dispose()
        print('PASS: outer transaction rolled back; no test identities, invitations or mail left behind')


if __name__=='__main__':
    checks=run(browser='--browser' in sys.argv)
    dest=Path(__file__).resolve().parents[2]/'output/training-enrollment-20261113'
    dest.mkdir(parents=True,exist_ok=True)
    (dest/'test-result.json').write_text(json.dumps(dict(passed=True,checks=checks,rollback_verified=True,external_mail_sent=False),indent=2)+'\n',encoding='utf-8')
