import boto3,json
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');out={'identity':s.client('sts').get_caller_identity()['Account'],'services':[]}
a=s.client('apprunner')
for v in a.list_services()['ServiceSummaryList']:
 d=a.describe_service(ServiceArn=v['ServiceArn'])['Service'];src=d['SourceConfiguration'];out['services'].append({'name':d['ServiceName'],'arn':d['ServiceArn'],'status':d['Status'],'image':src.get('ImageRepository',{}).get('ImageIdentifier'),'url':d.get('ServiceUrl')})
out['build_projects']=s.client('codebuild').list_projects()['projects']
print(json.dumps(out,indent=2))
from pathlib import Path
p=Path('tmp/registry-access-release');p.mkdir(exist_ok=True);(p/'inventory.json').write_text(json.dumps(out,indent=2))
