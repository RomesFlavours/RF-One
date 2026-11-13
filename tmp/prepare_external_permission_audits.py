from pathlib import Path
import json
root=Path.cwd();state=json.loads((root/'tmp/copy_employee_directory_aws.json').read_text());runtime=Path(state['development_source']);tips=root/'03 Software/Tips'
script='''from pathlib import Path
import os,sys,json,tempfile,importlib.util
for key in list(os.environ):
 if key.startswith(('RFONE_','ALEMBIC_','AWS_','CLOVER_')):os.environ.pop(key,None)
root=Path(ROOT);temp=tempfile.TemporaryDirectory(prefix='tips-permission-audit-',dir=root/'tmp')
os.environ['RFONE_DATABASE_URL']='sqlite:///'+str(Path(temp.name)/'test.db').replace('\\\\','/')
os.environ['RFONE_FLASK_SECRET_KEY']='local-disposable-permission-audit-only'
sys.path[:0]=[str(Path(RUNTIME)/'RF-One Data Store'),TIPS]
from rfone_data_store import models as m,access_profiles as p
from rfone_data_store.database import create_configured_engine,create_session_factory
engine=create_configured_engine(os.environ['RFONE_DATABASE_URL']);m.Base.metadata.create_all(engine);factory=create_session_factory(engine)
with factory() as db:
 user=m.RFOneAccount(username='no-domain-audit',display_name='No Domain audit',password_hash='!',status='ACTIVE',is_admin=False,is_owner=False,session_version=1);db.add(user);db.commit();identity=user.id
spec=importlib.util.spec_from_file_location('tips_local_permission_audit',str(Path(TIPS)/'app.py'));tips=importlib.util.module_from_spec(spec);spec.loader.exec_module(tips);tips.app.config['TESTING']=True
anonymous=tips.app.test_client();c=tips.app.test_client()
with c.session_transaction() as session:session['rfone_account_id']=identity;session['rfone_session_version']=1
results=[]
for path in ('/','/tips-configuration','/roles'):
 response=c.get(path);results.append({'path':path,'expected_without_TIPS_grant':403,'actual':response.status_code})
result={'anonymous_status':anonymous.get('/').status_code,'tests':results,'source':str(Path(TIPS)/'app.py')}
(root/'tmp/registry-authorization-tips-audit.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
engine.dispose();tips._engine.dispose();temp.cleanup()
'''
script='ROOT='+repr(str(root))+'\nRUNTIME='+repr(str(runtime))+'\nTIPS='+repr(str(tips))+'\n'+script
(root/'tmp/audit_registry_tips_local.py').write_text(script,encoding='utf-8')
p=root/'tmp/audit_registry_authorization_main.py';t=p.read_text(encoding='utf-8').replace("and not rule.arguments and getattr(","and not rule.arguments and not rule.rule.startswith('/_audit/') and getattr(")
t=t.replace("au_client.get('/training',follow_redirects=True).status_code","au_client.get('/training',follow_redirects=False).status_code")
# Keep only synthetic fixtures for the independent Kitchen-process verification.
t=t.replace("result={'baseline_http_checks_passed'",'''post(action='permissions',id=audit_role,access_KITCHEN='all')
import sqlite3
src=sqlite3.connect(str(Path(testdir.name)/'test.db'));dst=sqlite3.connect(str(Path(OUTPUT).with_name('registry-auth-synthetic-fixture.db')));src.backup(dst);dst.close();src.close()
Path(OUTPUT).with_name('registry-auth-synthetic-identities.json').write_text(json.dumps({'id':au_id,'company_id':company_id}))
result={'baseline_http_checks_passed' ''')
p.write_text(t,encoding='utf-8')
