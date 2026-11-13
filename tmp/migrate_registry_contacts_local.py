from pathlib import Path
import os,json,sys,subprocess,psycopg2
from datetime import datetime,timezone
root=Path.cwd();state=json.loads((root/'tmp/copy_employee_directory_aws.json').read_text());cfg=state['local_database'];folder=Path(state['folder']);assert cfg['host']=='127.0.0.1' and cfg['database']=='rfone_employee_directory'
c=psycopg2.connect(host=cfg['host'],port=cfg['port'],dbname=cfg['database'],user=cfg['username'])
with c.cursor() as q:q.execute('SHOW data_directory');assert Path(q.fetchone()[0]).resolve()==(folder/'postgres-data').resolve();q.execute('SELECT version_num FROM alembic_version');assert q.fetchone()[0]=='f2a120261110'
c.close();backup=folder/('before-registry-contacts-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.dump');env=os.environ.copy()
for key in ('PGSERVICE','PGSERVICEFILE','PGOPTIONS','PGPASSWORD'):env.pop(key,None)
r=subprocess.run([str(folder/'runtime/pgsql/bin/pg_dump.exe'),'-h',cfg['host'],'-p',str(cfg['port']),'-U',cfg['username'],'-d',cfg['database'],'-Fc','--no-owner','--no-privileges','-f',str(backup)],env=env,capture_output=True);assert r.returncode==0
url=f"postgresql+psycopg2://{cfg['username']}@127.0.0.1:{cfg['port']}/{cfg['database']}";os.environ['RFONE_DATABASE_URL']=url;os.environ['ALEMBIC_DATABASE_URL_OVERRIDE']=url;store=root/'tmp/git-anagrafica-release/03 Software/RF-One Data Store';sys.path.insert(0,str(store));from alembic.config import Config;from alembic import command
config=Config(str(store/'alembic.ini'));config.set_main_option('script_location',str(store/'migrations'));command.upgrade(config,'f3b120261110');(root/'tmp/registry-contacts-release/local-migration.json').write_text(json.dumps({'revision':'f3b120261110','backup':str(backup)},indent=2));print('Local Registry database migrated with backup; records preserved')
