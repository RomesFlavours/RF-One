from pathlib import Path
import boto3,json
root=Path('tmp/registry-contacts-release');p=root/'state.json';d=json.loads(p.read_text());s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');assert s.client('rds').describe_db_snapshots(DBSnapshotIdentifier=d['rds_snapshot'])['DBSnapshots'][0]['Status']=='available';service=s.client('apprunner').describe_service(ServiceArn=d['service_arn'])['Service'];assert service['SourceConfiguration']['ImageRepository']['ImageIdentifier']==d['expected_previous_image']
script='''import os,json
from sqlalchemy import create_engine,text
from alembic.config import Config
from alembic import command
engine=create_engine(os.environ['RFONE_DATABASE_URL'])
with engine.connect() as c:
 assert c.execute(text('SELECT version_num FROM alembic_version')).scalar()=='k9a020261110'
 before=list(c.execute(text('SELECT to_jsonb(a)::text FROM rfone_accounts a ORDER BY id')).scalars())
 people=set(c.execute(text('SELECT id FROM employees')).scalars())
 dismissed=set(c.execute(text('SELECT id FROM employees WHERE active=false')).scalars())
config=Config('/app/RF-One Data Store/alembic.ini');config.set_main_option('script_location','/app/RF-One Data Store/migrations');os.environ['ALEMBIC_DATABASE_URL_OVERRIDE']=os.environ['RFONE_DATABASE_URL'];command.upgrade(config,'f3b120261110')
with engine.connect() as c:
 after=list(c.execute(text("SELECT (to_jsonb(a)-'contact_email'-'contact_phone')::text FROM rfone_accounts a ORDER BY id")).scalars());assert before==after
 assert people==set(c.execute(text('SELECT id FROM employees')).scalars())
 assert dismissed==set(c.execute(text('SELECT id FROM employees WHERE active=false')).scalars())
 assert c.execute(text('SELECT COUNT(*) FROM rfone_accounts WHERE contact_email IS NOT NULL OR contact_phone IS NOT NULL')).scalar()==0
 print('REGISTRY_CONTACTS_MIGRATION_VERIFIED '+json.dumps({'revision':'f3b120261110','account_records_preserved':len(before),'employees_preserved':len(people),'dismissed_preserved':len(dismissed),'recovery_and_credentials_unchanged':True}),flush=True)
'''
r=s.client('ecs').run_task(cluster=d['cluster'],taskDefinition=d['migration_task_definition'],launchType='FARGATE',networkConfiguration=d['network'],overrides={'containerOverrides':[{'name':d['container'],'command':['-c',script]}]},startedBy='rf1-registry-contacts-migrate');assert not r.get('failures'),r.get('failures');d['migration_task']=r['tasks'][0]['taskArn'];p.write_text(json.dumps(d,indent=2));print(json.dumps({'migration_task':d['migration_task']}))
