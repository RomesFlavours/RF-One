from pathlib import Path
import os,sys,json
root=Path.cwd();fixture=root/'tmp/registry-auth-synthetic-fixture.db';assert fixture.exists();identity=json.loads((root/'tmp/registry-auth-synthetic-identities.json').read_text())
for key in list(os.environ):
 if key.startswith(('RFONE_','ALEMBIC_','AWS_','CLOVER_','KITCHEN_')):os.environ.pop(key,None)
os.environ['RFONE_DATABASE_URL']='sqlite:///'+str(fixture).replace('\\','/');os.environ['RFONE_FLASK_SECRET_KEY']='kitchen-disposable-audit-only';os.environ['AWS_EC2_METADATA_DISABLED']='true'
frozen=Path('C:/Users/servi/OneDrive/AI-RF-ONE/RF One/output/kitchen-release/source/03 Software')
sys.path[:0]=[str(frozen/'RF-One Web'),str(frozen/'RF-One Data Store')]
import kitchen_cloud as kc
from db import SessionFactory,_engine
from sqlalchemy import text
kc.app.config['TESTING']=True
kc.app.add_url_rule('/kitchen/_audit',endpoint='registry_gate_probe',view_func=kc.require_domain_access('KITCHEN')(lambda:'allowed'))
c=kc.app.test_client()
with c.session_transaction() as browser:browser['rfone_account_id']=identity['id'];browser['rfone_session_version']=1;browser['rfone_company_context']=identity['company_id']
role_only=c.get('/kitchen/_audit').status_code
with _engine.begin() as db:
 role_count=db.execute(text("SELECT count(*) FROM rfone_role_permissions WHERE domain_code='KITCHEN'")).scalar();assert role_count>0
 db.execute(text("UPDATE rfone_account_domain_access SET enabled=1,scope='ALL' WHERE account_id=:id AND domain_code='KITCHEN'"),{'id':identity['id']})
direct=c.get('/kitchen/_audit').status_code
result={'source':str(frozen/'RF-One Web/kitchen_cloud.py'),'role_profile_grant_expected':200,'role_profile_grant_actual':role_only,'direct_grant_expected':200,'direct_grant_actual':direct,'source_service_uses_profile_aggregation':False,'source_service_installs_company_context':False}
(root/'tmp/registry-authorization-kitchen-audit.json').write_text(json.dumps(result,indent=2));print(json.dumps(result));_engine.dispose()
