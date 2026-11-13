import boto3,json
from pathlib import Path
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');ecs=s.client('ecs');d=ecs.describe_clusters(clusters=['rfone-jobs'],include=['CONFIGURATIONS'])['clusters'][0];state=json.loads(Path('tmp/registry-access-release/release-state.json').read_text());td=ecs.describe_task_definition(taskDefinition=state['verification_task_definition'])['taskDefinition'];role=td.get('taskRoleArn');print(json.dumps({'ecs_exec_config':d.get('configuration',{}),'task_role':role},indent=2));iam=s.client('iam');name=role.split('/')[-1]
print('Role managed policies:',[v['PolicyName'] for v in iam.list_attached_role_policies(RoleName=name)['AttachedPolicies']])
for n in iam.list_role_policies(RoleName=name)['PolicyNames']:
 doc=iam.get_role_policy(RoleName=name,PolicyName=n)['PolicyDocument'];print('Role actions:',[v.get('Action') for v in doc.get('Statement',[])])
