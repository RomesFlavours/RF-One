"""Explicit local-only backup, additive migration and working-source activation."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,shutil,subprocess,sys
import psycopg2
from psycopg2 import sql

ROOT=Path(__file__).resolve().parent.parent
statefile=ROOT/'tmp/copy_employee_directory_aws.json';d=json.loads(statefile.read_text())
folder=Path(d['folder']);local=d['local_database'];assert local['host']=='127.0.0.1' and local['database']=='rfone_employee_directory'
dev=ROOT/'tmp/role-company-development';store=dev/'RF-One Data Store'
url=f"postgresql+psycopg2://{local['username']}@127.0.0.1:{local['port']}/{local['database']}"
os.environ['RFONE_DATABASE_URL']=url;os.environ['ALEMBIC_DATABASE_URL_OVERRIDE']=url
sys.path.insert(0,str(store))
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic import command
cfg=Config(str(store/'alembic.ini'));cfg.set_main_option('script_location',str(store/'migrations'))
assert ScriptDirectory.from_config(cfg).get_heads()==['f2a120261110']

def connect():return psycopg2.connect(host=local['host'],port=local['port'],dbname=local['database'],user=local['username'])
def fingerprint(table):
    c=connect()
    with c.cursor() as q:
        q.execute(sql.SQL('SELECT to_jsonb(t)::text FROM {} t ORDER BY to_jsonb(t)::text COLLATE "C"').format(sql.Identifier(table)))
        h=hashlib.sha256();count=0
        for row in q:h.update(row[0].encode());h.update(b'\n');count+=1
    c.close();return {'rows':count,'sha256':h.hexdigest()}

c=connect()
with c.cursor() as q:
    q.execute('SHOW data_directory');assert Path(q.fetchone()[0]).resolve()==(folder/'postgres-data').resolve()
    q.execute('SELECT version_num FROM alembic_version');revision=q.fetchone()[0]
c.close()
baseline={table:fingerprint(table) for table in ('employees','rfone_accounts','rfone_account_domain_access','rfone_account_domain_item_access','employee_assignments','shifts','legal_entities','restaurants','restaurant_roles','operational_areas')}
if revision=='e2c320261109':
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');backup=folder/f'before-role-profiles-{stamp}.dump'
    env=os.environ.copy()
    for key in ('PGHOST','PGPORT','PGDATABASE','PGUSER','PGPASSWORD','PGSERVICE','PGSERVICEFILE','PGOPTIONS'):env.pop(key,None)
    result=subprocess.run([str(folder/'runtime/pgsql/bin/pg_dump.exe'),'-h','127.0.0.1','-p',str(local['port']),'-U',local['username'],
        '-d',local['database'],'-Fc','--no-owner','--no-privileges','-f',str(backup)],env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    print('Local pre-development database backup saved',flush=True)
    command.upgrade(cfg,'f2a120261110')
    d['role_company_development']={'backup':str(backup),'revision':'f2a120261110'}
elif revision!='f2a120261110':raise RuntimeError('Unexpected LOCAL schema revision; nothing migrated')
after={table:fingerprint(table) for table in baseline};assert baseline==after,'Legacy data changed during additive migration'
d.setdefault('role_company_development',{})['legacy_data_preserved']=after
target=folder/'development-source'
shutil.copytree(dev,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
d['development_source']=str(target)
d['role_company_development']['url']=f"http://127.0.0.1:{d['web_port']}/admin/roles"
d['role_company_development']['profiles_inferred']=False
launcher=folder/'launch_local.py';t=launcher.read_text(encoding='utf-8')
t=t.replace("source=ROOT/'source'","source=Path(state.get('development_source',str(ROOT/'source')))")
t=t.replace("prefixes=('/administration/employees','/admin/accounts','/static/','/shared-brand/')", "prefixes=('/administration/employees','/admin/accounts','/admin/roles','/admin/access-company','/static/','/shared-brand/')")
launcher.write_text(t,encoding='utf-8')
for file in (statefile,folder/'verification.json'):file.write_text(json.dumps(d,indent=2),encoding='utf-8')
print('Local working source activated; no AWS calls or writes.',flush=True)
