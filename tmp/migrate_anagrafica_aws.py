from pathlib import Path
import boto3,json
root=Path('tmp/anagrafica-release');p=root/'state.json';d=json.loads(p.read_text());s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1')
snapshot=s.client('rds').describe_db_snapshots(DBSnapshotIdentifier=d['rds_snapshot'])['DBSnapshots'][0]
if snapshot['Status']!='available':print('SNAPSHOT_NOT_READY '+snapshot['Status']);raise SystemExit(2)
script='''import os,json,hashlib
from pathlib import Path
from sqlalchemy import create_engine,text
from alembic.config import Config
from alembic import command
url=os.environ['RFONE_DATABASE_URL'];e=create_engine(url)
with e.connect() as c:
 rev=list(c.execute(text('SELECT version_num FROM alembic_version')).scalars())
 assert rev==['e2c320261109'],str(rev)
 baseline={table:list(c.execute(text('SELECT id FROM '+table+' ORDER BY id')).scalars()) for table in ('employees','rfone_accounts','shifts','employee_assignments','raw_bank_transactions')}
config=Config('/app/RF-One Data Store/alembic.ini');config.set_main_option('script_location','/app/RF-One Data Store/migrations')
os.environ['ALEMBIC_DATABASE_URL_OVERRIDE']=url
command.upgrade(config,'f2a120261110')
with e.connect() as c:
 assert c.execute(text('SELECT version_num FROM alembic_version')).scalar()=='f2a120261110'
 for table,ids in baseline.items():assert set(ids).issubset(set(c.execute(text('SELECT id FROM '+table)).scalars())),table
 assert c.execute(text('SELECT COUNT(*) FROM rfone_person_company_memberships')).scalar()==0
 assert c.execute(text('SELECT COUNT(*) FROM rfone_role_permissions')).scalar()==0
 print('RF1_MIGRATION_VERIFIED '+json.dumps({'revision':'f2a120261110','preserved_rows':{k:len(v) for k,v in baseline.items()},'automatic_grants':0}),flush=True)
'''
r=s.client('ecs').run_task(cluster=d['cluster'],taskDefinition=d['migration_task_definition'],launchType='FARGATE',networkConfiguration=d['network'],overrides={'containerOverrides':[{'name':d['container'],'command':['-c',script]}]},startedBy='rf1-anagrafica-migrate');assert not r.get('failures'),r.get('failures');d['migration_task']=r['tasks'][0]['taskArn'];p.write_text(json.dumps(d,indent=2));print(json.dumps({'migration_task':d['migration_task']}))
