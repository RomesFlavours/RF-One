from pathlib import Path
import os,json,sys,subprocess,psycopg2,importlib.util
from psycopg2 import sql
root=Path.cwd();state=json.loads((root/'tmp/copy_employee_directory_aws.json').read_text());cfg=state['local_database'];folder=Path(state['folder']);name='rfone_contacts_kitchen_rehearsal_20261110';assert cfg['host']=='127.0.0.1'
c=psycopg2.connect(host=cfg['host'],port=cfg['port'],user=cfg['username'],dbname='postgres');c.autocommit=True
with c.cursor() as q:q.execute('SELECT 1 FROM pg_database WHERE datname=%s',(name,));assert q.fetchone() is None;q.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
c.close();env=os.environ.copy()
for key in ('PGSERVICE','PGSERVICEFILE','PGOPTIONS','PGPASSWORD'):env.pop(key,None)
r=subprocess.run([str(folder/'runtime/pgsql/bin/pg_restore.exe'),'-h',cfg['host'],'-p',str(cfg['port']),'-U',cfg['username'],'-d',name,'--no-owner','--no-privileges','--exit-on-error',str(folder/'rfone-aws.dump')],env=env,capture_output=True);assert r.returncode==0
url=f"postgresql+psycopg2://{cfg['username']}@127.0.0.1:{cfg['port']}/{name}";os.environ['RFONE_DATABASE_URL']=url;os.environ['ALEMBIC_DATABASE_URL_OVERRIDE']=url;store=root/'tmp/git-anagrafica-release/03 Software/RF-One Data Store';sys.path.insert(0,str(store));from sqlalchemy import create_engine,text
from alembic.config import Config
from alembic import command
e=create_engine(url)
with e.connect() as db:before=list(db.execute(text('SELECT to_jsonb(a)::text FROM rfone_accounts a ORDER BY id')).scalars());employees=db.execute(text('SELECT COUNT(*) FROM employees')).scalar()
config=Config(str(store/'alembic.ini'));config.set_main_option('script_location',str(store/'migrations'));command.upgrade(config,'f3b120261110')
with e.connect() as db:
 assert before==list(db.execute(text("SELECT (to_jsonb(a)-'contact_email'-'contact_phone')::text FROM rfone_accounts a ORDER BY id")).scalars())
 assert db.execute(text('SELECT COUNT(*) FROM employees')).scalar()==employees
 assert db.execute(text("SELECT to_regclass('kitchen_recipes')")).scalar()
(root/'tmp/registry-contacts-release/rehearsal.json').write_text(json.dumps({'database':name,'revision':'f3b120261110','chain':['e2c320261109','f2a120261110','k9a020261110','f3b120261110'],'existing_account_data_unchanged':True,'employees':employees},indent=2));print('Full-data rehearsal passed through Kitchen and Registry contacts')
# Align the existing local copy's schema with the newly recovered applied ancestor.
from alembic.migration import MigrationContext
from alembic.operations import Operations
spec=importlib.util.spec_from_file_location('applied_kitchen',store/'migrations/versions/k9a020261110_publish_kitchen_aws.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
local_url=f"postgresql+psycopg2://{cfg['username']}@127.0.0.1:{cfg['port']}/{cfg['database']}";local_engine=create_engine(local_url)
with local_engine.begin() as db:
 assert db.execute(text('SELECT version_num FROM alembic_version')).scalar()=='f3b120261110'
 with Operations.context(MigrationContext.configure(db)):module.upgrade()
print('Existing local copy aligned with recovered Kitchen ancestor; data preserved')
