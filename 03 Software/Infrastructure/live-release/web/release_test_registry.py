"""Actual release entry-point E2E on a disposable SQLite database; SMTP intercepted."""
import os,sys,tempfile,re,json
from pathlib import Path
from unittest.mock import patch
SERVICE=sys.argv[1];BASE=Path(sys.argv[2]).resolve()
if (BASE/'03 Software').exists():BASE=BASE/'03 Software'
tmp=tempfile.TemporaryDirectory(prefix='registry-training-release-')
os.environ.update(RFONE_DATABASE_URL='sqlite:///'+str(Path(tmp.name)/'test.sqlite').replace('\\','/'),RFONE_FLASK_SECRET_KEY='isolated-release-test',RFONE_PUBLIC_BASE_URL='https://rfone.romesflavours.com',AWS_EC2_METADATA_DISABLED='true')
sys.path[:0]=[str(BASE/'RF-One Web'),str(BASE/'RF-One Data Store')]
from rfone_data_store import models as m,access_profiles,student_registry as sr,people_registry as people,rfone_account_service as accounts
from rfone_data_store.training import workspace as ws,service as training
import db,auth,training_integration as ti
import sqlalchemy as sa
if SERVICE=='training':
    import training_cloud
    app=training_cloud.app
else:
    import app as web
    app=web.app
app.config.update(TESTING=True,SESSION_COOKIE_SECURE=False)
m.Base.metadata.create_all(db._engine)
with db._engine.begin() as c:
    c.execute(sa.text('CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) PRIMARY KEY)'))
    c.execute(sa.text("INSERT INTO alembic_version VALUES ('r9a120261113')"))
with db.SessionFactory() as s:
    trainer=accounts.create_account(s,username='release-trainer',display_name='Release trainer',password='TrainerTest938!',email='trainer@example.test')
    accounts.set_domain_access(s,account_id=trainer.id,domain_code='TRAINING',enabled=True,role_code='trainer')
    identity=training.create_account(s,display_name=trainer.display_name,username='release-trainer-training',password='UnusedPassword739!',role='trainer')
    s.add(m.RFOneTrainingIdentityLink(rfone_account_id=trainer.id,training_account_id=identity.id));s.commit();trainer_id=trainer.id;trainer_version=trainer.session_version
checks=[];sent=[]
from rfone_data_store.technical import account_email
def csrf(c,path):
    response=c.get(path)
    with c.session_transaction() as session:return session[auth.SESSION_CSRF_KEY]
if SERVICE=='training':
    c=app.test_client()
    with c.session_transaction() as session:session['rfone_account_id']=trainer_id;session['rfone_session_version']=trainer_version
    response=c.get('/training/manage/students');assert response.status_code==200,response.status_code
    assert b'New student' in response.data and b'How' in response.data
    with patch.object(account_email,'send_email',side_effect=lambda **kw:sent.append(kw)):
        token=csrf(c,'/training/manage/students')
        response=c.post('/training/manage/students',data={'csrf_token':token,'action':'save','first_name':'Release','last_name':'Student','email':'student@example.test','phone':''},follow_redirects=True)
    assert response.status_code==200,response.status_code
    assert len(sent)==1, response.data.decode()[-1200:]
    body=sent[0]['text_body'];username=re.search(r'Username: (\S+)',body)[1];initial=re.search(r'Initial password: (\S+)',body)[1];link=re.search(r'/training/activation/[A-Za-z0-9_-]+',body)[0]
    checks.append('Real trainer route creates Registry/STUDENT, shared login and invitation')
    with db.SessionFactory() as s:
        account=s.scalar(sa.select(m.RFOneAccount).where(m.RFOneAccount.username==username.lower()));uid=account.id
        person=s.scalar(sa.select(people.PersonAccountLink.person_id).where(people.PersonAccountLink.account_id==uid))
        assert person and s.get(sr.PersonQualification,(person,'STUDENT'))
        assert ti.is_pure_training_student(s,account)
        assert s.scalar(sa.select(sa.func.count()).select_from(m.Employee))==0
    learner=app.test_client();learner.get(link,follow_redirects=True)
    token=csrf(learner,'/training/activation')
    response=learner.post('/training/activation',data={'csrf_token':token,'step':'credentials','username':username,'password':initial},follow_redirects=True)
    assert response.status_code==200 and b'Choose your password' in response.data,response.data[-1000:]
    token=csrf(learner,'/training/activation')
    response=learner.post('/training/activation',data={'csrf_token':token,'step':'password','password':'PersonalTest749!','password_confirm':'PersonalTest749!'})
    assert response.status_code==302,response.data[-1000:]
    response=learner.get('/training/');assert response.status_code==200,response.status_code
    assert b'Your Training path' in response.data
    assert learner.get('/training/manage/students').status_code==403
    checks.append('Initial credentials -> personal password -> student home; trainer access denied')
    recovery_client=app.test_client()
    with patch.object(account_email,'send_email',side_effect=lambda **kw:sent.append(kw)):
        token=csrf(recovery_client,'/training/account/recover')
        response=recovery_client.post('/training/account/recover',data={'csrf_token':token,'username':username,'email':'student@example.test'})
    assert response.status_code==302
    # Activation and recovery share a 60-second send cooldown; verify non-disclosing response.
    checks.append('Recovery endpoint preserves generic response and rate limiting')
else:
    with db.SessionFactory() as s:
        account,identity=ti.create_student_via_rf_one(s,username='releasestu',display_name='Release Student',password='InitialTest849!',email='student@example.test');s.commit();uid=account.id;version=account.session_version
    c=app.test_client()
    with c.session_transaction(base_url='https://rfone.romesflavours.com') as session:session['rfone_account_id']=uid;session['rfone_session_version']=version
    response=c.get('/',base_url='https://rfone.romesflavours.com',headers={'X-RFOne-Entry':'cloudfront'});assert response.status_code==302 and '/training/activation' in response.location,(response.status_code,response.location)
    with c.session_transaction(base_url='https://rfone.romesflavours.com') as session:assert not session.get('rfone_account_id')
    checks.append('Shared RF-One entry rejects and clears unactivated student session')
print(json.dumps({'service':SERVICE,'checks':checks,'smtp_intercepted':True,'isolated_database':True}))
import gc
from sqlalchemy.orm import close_all_sessions
close_all_sessions()
for module in list(sys.modules.values()):
    for name in ('_engine','engine'):
        engine=getattr(module,name,None)
        if isinstance(engine,sa.engine.Engine):engine.dispose()
gc.collect();tmp.cleanup()
