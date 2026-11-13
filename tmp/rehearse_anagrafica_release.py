from pathlib import Path
import json,subprocess,sys,os,psycopg2
from psycopg2 import sql
root=Path.cwd();state=json.loads((root/'tmp/copy_employee_directory_aws.json').read_text());folder=Path(state['folder']);cfg=state['local_database'];name='rfone_release_rehearsal_20261110';assert cfg['host']=='127.0.0.1'
url=f"postgresql+psycopg2://{cfg['username']}@127.0.0.1:{cfg['port']}/{name}";os.environ['ALEMBIC_DATABASE_URL_OVERRIDE']=url;os.environ['RFONE_DATABASE_URL']=url
from sqlalchemy import create_engine,text
engine=create_engine(url)
with engine.connect() as db:
 before={table:db.execute(text('SELECT COUNT(*) FROM '+table)).scalar() for table in ('employees','rfone_accounts','shifts','employee_assignments','rfone_account_domain_access')}
store=root/'tmp/role-company-development/RF-One Data Store';sys.path.insert(0,str(store));from alembic.config import Config;from alembic import command
alembic=Config(str(store/'alembic.ini'));alembic.set_main_option('script_location',str(store/'migrations'));command.upgrade(alembic,'f2a120261110')
with engine.connect() as db:
 after={table:db.execute(text('SELECT COUNT(*) FROM '+table)).scalar() for table in before};assert before==after
 assert db.execute(text('SELECT version_num FROM alembic_version')).scalar()=='f2a120261110'
 assert db.execute(text('SELECT COUNT(*) FROM rfone_person_company_memberships')).scalar()==0
 assert db.execute(text('SELECT COUNT(*) FROM rfone_role_permissions')).scalar()==0
(root/'tmp/anagrafica-release/rehearsal.json').write_text(json.dumps({'database':name,'revision':'f2a120261110','legacy_counts_unchanged':after,'no_automatic_grants':True},indent=2));print('Full copied database migration rehearsal passed')
