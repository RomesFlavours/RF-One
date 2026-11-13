ROOT='C:\\Users\\servi\\.codex\\worktrees\\edee\\RF One'
RUNTIME='C:\\Users\\servi\\AppData\\Local\\RF-One\\Employee Directory\\AWS-20261110T120743Z\\development-source'
TIPS='C:\\Users\\servi\\.codex\\worktrees\\edee\\RF One\\03 Software\\Tips'
from pathlib import Path
import os,sys,json,tempfile,importlib.util
for key in list(os.environ):
 if key.startswith(('RFONE_','ALEMBIC_','AWS_','CLOVER_')):os.environ.pop(key,None)
root=Path(ROOT);temp=tempfile.TemporaryDirectory(prefix='tips-permission-audit-',dir=root/'tmp',ignore_cleanup_errors=True)
os.environ['RFONE_DATABASE_URL']='sqlite:///'+str(Path(temp.name)/'test.db').replace('\\','/')
os.environ['RFONE_FLASK_SECRET_KEY']='local-disposable-permission-audit-only'
sys.path[:0]=[str(Path(RUNTIME)/'RF-One Data Store'),TIPS]
from rfone_data_store import models as m,access_profiles as p
from rfone_data_store.database import create_configured_engine,create_session_factory
engine=create_configured_engine(os.environ['RFONE_DATABASE_URL']);m.Base.metadata.create_all(engine);factory=create_session_factory(engine)
with factory() as db:
 user=m.RFOneAccount(username='no-domain-audit',display_name='No Domain audit',password_hash='!',status='ACTIVE',is_admin=False,is_owner=False,session_version=1);db.add(user);db.commit();identity=user.id
spec=importlib.util.spec_from_file_location('tips_local_permission_audit',str(Path(TIPS)/'app.py'));tips=importlib.util.module_from_spec(spec);sys.modules[spec.name]=tips;spec.loader.exec_module(tips);tips.app.config['TESTING']=True
anonymous=tips.app.test_client();c=tips.app.test_client()
with c.session_transaction() as session:session['rfone_account_id']=identity;session['rfone_session_version']=1
results=[]
for path in ('/','/tips-configuration','/roles'):
 response=c.get(path);results.append({'path':path,'expected_without_TIPS_grant':403,'actual':response.status_code})
result={'anonymous_status':anonymous.get('/').status_code,'tests':results,'source':str(Path(TIPS)/'app.py')}
(root/'tmp/registry-authorization-tips-audit.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
engine.dispose();tips._engine.dispose();temp.cleanup()
