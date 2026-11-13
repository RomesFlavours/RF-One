from pathlib import Path
import boto3,json,copy,time
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');root=Path.cwd();out=root/'tmp/anagrafica-release';out.mkdir(exist_ok=True)
a=s.client('apprunner');arn=json.loads((root/'tmp/anagrafica_deploy_audit.json').read_text())['service_arn'];service=a.describe_service(ServiceArn=arn)['Service'];cfg=service['SourceConfiguration']['ImageRepository']['ImageConfiguration'];ecs=s.client('ecs');task=ecs.describe_task_definition(taskDefinition=cfg['RuntimeEnvironmentVariables']['RFONE_CLOVER_JOB_ECS_TASK_DEFINITION'])['taskDefinition'];(out/'baseline-service.json').write_text(json.dumps(service,default=str));(out/'baseline-task.json').write_text(json.dumps(task,default=str))
script="""import os,json
from sqlalchemy import create_engine,text
e=create_engine(os.environ['RFONE_DATABASE_URL'])
with e.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 rev=list(c.execute(text('SELECT version_num FROM alembic_version')).scalars())
 count=c.execute(text('SELECT COUNT(*) FROM employees')).scalar()
 print('RF1_RELEASE_AUDIT '+json.dumps({'revisions':rev,'employees':count}),flush=True)
 assert rev==['e2c320261109']
"""
network={'awsvpcConfiguration':{'subnets':cfg['RuntimeEnvironmentVariables']['RFONE_CLOVER_JOB_ECS_SUBNETS'].split(','),'securityGroups':cfg['RuntimeEnvironmentVariables']['RFONE_CLOVER_JOB_ECS_SECURITY_GROUPS'].split(','),'assignPublicIp':'ENABLED'}}
run=ecs.run_task(cluster=cfg['RuntimeEnvironmentVariables']['RFONE_CLOVER_JOB_ECS_CLUSTER'],taskDefinition=task['taskDefinitionArn'],launchType='FARGATE',networkConfiguration=network,overrides={'containerOverrides':[{'name':task['containerDefinitions'][0]['name'],'command':['python','-c',script]}]},startedBy='rf1-anagrafica-audit')
assert not run.get('failures'),str(run.get('failures'))
state={'service_arn':arn,'network':network,'cluster':cfg['RuntimeEnvironmentVariables']['RFONE_CLOVER_JOB_ECS_CLUSTER'],'audit_task':run['tasks'][0]['taskArn'],'container':task['containerDefinitions'][0]['name'],'log_configuration':task['containerDefinitions'][0].get('logConfiguration')};(out/'state.json').write_text(json.dumps(state,indent=2));print(json.dumps({'audit_task':state['audit_task']}))
