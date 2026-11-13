from pathlib import Path
import boto3,json
root=Path('tmp/registry-contacts-release');p=root/'state.json';d=json.loads(p.read_text());s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');script="""import os,json
from sqlalchemy import create_engine,text
e=create_engine(os.environ['RFONE_DATABASE_URL'])
with e.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 print('LIVE_SCHEMA_AUDIT '+json.dumps({'revisions':list(c.execute(text('SELECT version_num FROM alembic_version')).scalars()),'contact_columns':list(c.execute(text(\"SELECT column_name FROM information_schema.columns WHERE table_name='rfone_accounts' AND column_name IN ('contact_email','contact_phone')\")).scalars())}),flush=True)
""";r=s.client('ecs').run_task(cluster=d['cluster'],taskDefinition=d['migration_task_definition'],launchType='FARGATE',networkConfiguration=d['network'],overrides={'containerOverrides':[{'name':d['container'],'command':['-c',script]}]},startedBy='rf1-registry-schema-audit');assert not r.get('failures');d['schema_audit_task']=r['tasks'][0]['taskArn'];d['failed_precondition_task']=d['migration_task'];p.write_text(json.dumps(d,indent=2));print(json.dumps({'task':d['schema_audit_task']}))
