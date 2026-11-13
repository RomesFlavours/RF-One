from pathlib import Path
import os,sys,json,sqlite3,importlib.util
root=Path.cwd();state=json.loads((root/'tmp/copy_employee_directory_aws.json').read_text());runtime=Path(state['development_source']);source=root/'03 Software/Selection';fixture=root/'tmp/selection-auth-synthetic.db';src=sqlite3.connect(root/'tmp/registry-auth-synthetic-fixture.db');dst=sqlite3.connect(fixture);src.backup(dst);src.close();dst.close();identity=json.loads((root/'tmp/registry-auth-synthetic-identities.json').read_text())
for key in list(os.environ):
 if key.startswith(('RFONE_','ALEMBIC_','AWS_','CLOVER_')):os.environ.pop(key,None)
os.environ['RFONE_DATABASE_URL']='sqlite:///'+str(fixture).replace('\\','/');os.environ['RFONE_FLASK_SECRET_KEY']='selection-synthetic-audit-only';os.environ['RFONE_SELECTION_REQUIRE_RFONE_LOGIN']='1';os.environ['AWS_EC2_METADATA_DISABLED']='true'
sys.path[:0]=[str(runtime/'RF-One Data Store'),str(source)]
from rfone_data_store import models as m,access_profiles as p
from sqlalchemy import create_engine,text
e=create_engine(os.environ['RFONE_DATABASE_URL'])
with e.begin() as db:
 role=db.execute(text("SELECT role_id FROM rfone_role_permissions WHERE domain_code='KITCHEN'")).scalar();assert role
 db.execute(text("INSERT INTO rfone_role_permissions (role_id,domain_code,scope,role_code,items) VALUES (:id,'SELECTION','ALL',NULL,'[]')"),{'id':role})
 db.execute(text("UPDATE rfone_account_domain_access SET enabled=0 WHERE domain_code='SELECTION' AND account_id=:id"),{'id':identity['id']})
# The fixture was built from current metadata; mark only this disposable SQLite
# schema so the standalone app does not replay its full baseline bootstrap.
with e.begin() as db:
 db.execute(text('CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)'))
 db.execute(text('DELETE FROM alembic_version'))
 db.execute(text("INSERT INTO alembic_version(version_num) VALUES ('f3b120261110')"))
spec=importlib.util.spec_from_file_location('selection_local_audit',source/'app.py');module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module);module.app.config['TESTING']=True;module.app.add_url_rule('/_audit_gate',endpoint='selection_gate_probe',view_func=lambda:'allowed')
c=module.app.test_client()
with c.session_transaction() as browser:browser['rfone_account_id']=identity['id'];browser['rfone_session_version']=1;browser['rfone_company_context']=identity['company_id']
role_only=c.get('/_audit_gate').status_code
with e.begin() as db:db.execute(text("UPDATE rfone_account_domain_access SET enabled=1,scope='ALL' WHERE domain_code='SELECTION' AND account_id=:id"),{'id':identity['id']})
direct=c.get('/_audit_gate').status_code
result={'source':str(source/'app.py'),'rfone_login_mode':module.RFONE_LOGIN_MODE,'role_profile_grant_expected':200,'role_profile_grant_actual':role_only,'direct_grant_expected':200,'direct_grant_actual':direct}
(root/'tmp/registry-authorization-selection-audit.json').write_text(json.dumps(result,indent=2));print(json.dumps(result));e.dispose()
