from pathlib import Path
import os,json,sys
from sqlalchemy import create_engine,text
from alembic.config import Config
from alembic import command
root=Path.cwd();state=json.loads((root/'tmp/copy_employee_directory_aws.json').read_text());cfg=state['local_database'];name='rfone_release_rehearsal_20261110';url=f"postgresql+psycopg2://{cfg['username']}@127.0.0.1:{cfg['port']}/{name}";os.environ['RFONE_DATABASE_URL']=url;os.environ['ALEMBIC_DATABASE_URL_OVERRIDE']=url;store=root/'tmp/git-anagrafica-release/03 Software/RF-One Data Store';sys.path.insert(0,str(store));e=create_engine(url)
with e.connect() as db:
 assert db.execute(text('SELECT version_num FROM alembic_version')).scalar()=='f2a120261110'
 before=list(db.execute(text('SELECT to_jsonb(a)::text FROM rfone_accounts a ORDER BY id')).scalars());employees=db.execute(text('SELECT COUNT(*) FROM employees')).scalar()
config=Config(str(store/'alembic.ini'));config.set_main_option('script_location',str(store/'migrations'));command.upgrade(config,'f3b120261110')
with e.connect() as db:
 after=list(db.execute(text("SELECT (to_jsonb(a)-'contact_email'-'contact_phone')::text FROM rfone_accounts a ORDER BY id")).scalars());assert before==after
 assert db.execute(text('SELECT COUNT(*) FROM employees')).scalar()==employees
 assert db.execute(text('SELECT COUNT(*) FROM rfone_accounts WHERE contact_email IS NOT NULL OR contact_phone IS NOT NULL')).scalar()==0
(root/'tmp/registry-contacts-release/rehearsal.json').write_text(json.dumps({'database':name,'revision':'f3b120261110','existing_account_data_unchanged':True,'employees':employees,'contacts_not_backfilled':True},indent=2));print('Contacts migration rehearsal passed; existing account and employee data unchanged')
