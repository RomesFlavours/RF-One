from pathlib import Path
import boto3,json
root=Path('tmp/registry-access-release');p=root/'release-state.json';state=json.loads(p.read_text());s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');ecs=s.client('ecs');prior=json.loads(Path('tmp/registry-contacts-release/state.json').read_text());old=ecs.describe_task_definition(taskDefinition=prior['migration_task_definition'])['taskDefinition'];allowed=set(ecs.meta.service_model.operation_model('RegisterTaskDefinition').input_shape.members);spec={k:v for k,v in old.items() if k in allowed};spec['family']='rfone-registry-access-check';container=spec['containerDefinitions'][0];container['image']=state['services']['web']['image'];container['entryPoint']=['python'];container['command']=['-c','print("Registry access check")'];td=ecs.register_task_definition(**spec)['taskDefinition']['taskDefinitionArn'];state['verification_task_definition']=td;state['verification_network']=prior['network'];state['verification_cluster']=prior['cluster'];state['verification_container']=container['name']
script='''import os,sys,json
sys.path.insert(0,'/app/RF-One Data Store')
from sqlalchemy import select,text,func
from rfone_data_store.database import create_configured_engine,create_session_factory
from rfone_data_store import models as m,access_profiles as p,employee_directory as directory
engine=create_configured_engine(os.environ['RFONE_DATABASE_URL']);factory=create_session_factory(engine)
with factory() as db:
 db.execute(text('SET TRANSACTION READ ONLY'))
 result={'schema':list(db.scalars(text('select version_num from alembic_version'))),'people':db.scalar(select(func.count()).select_from(m.Employee)),'dismissed':db.scalar(select(func.count()).select_from(m.Employee).where(m.Employee.active.is_(False))),'accounts':[]}
 for a in db.scalars(select(m.RFOneAccount).order_by(m.RFOneAccount.id)):
  row={'id':a.id,'username':a.username,'status':a.status,'admin':a.is_admin,'owner':a.is_owner,'person_id':directory.context_person_id(db,'RFONE_ACCOUNT',a.id),'effective':{}}
  for company in {None}|p.company_ids_for_account(db,a.id):row['effective'][str(company)]=sorted(p.effective_permissions(db,a.id,company_id=company))
  result['accounts'].append(row)
 assert result['schema']==['t9a120261110'],result['schema']
 print('REGISTRY_ACCESS_AUDIT '+json.dumps(result),flush=True)
'''
(root/'aws_readonly_audit.py').write_text(script,encoding='utf-8');r=ecs.run_task(cluster=prior['cluster'],taskDefinition=td,launchType='FARGATE',networkConfiguration=prior['network'],overrides={'containerOverrides':[{'name':container['name'],'command':['-c',script]}]},startedBy='rf1-registry-access-audit');assert not r.get('failures'),r.get('failures');state['audit_task']=r['tasks'][0]['taskArn'];p.write_text(json.dumps(state,indent=2));print('Read-only AWS Registry audit task:',state['audit_task'])
