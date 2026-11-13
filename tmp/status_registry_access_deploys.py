from pathlib import Path
import boto3,json
root=Path('tmp/registry-access-release');p=root/'release-state.json';state=json.loads(p.read_text());s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');a=s.client('apprunner')
for name,item in state['services'].items():
 svc=a.describe_service(ServiceArn=item['service_arn'])['Service'];operations=a.list_operations(ServiceArn=item['service_arn'])['OperationSummaryList'];operation=next(v for v in operations if v['Id']==item['deploy_operation']);item['deploy_status']=operation['Status'];item['service_status']=svc['Status'];item['service_url']=svc['ServiceUrl'];assert svc['SourceConfiguration']['ImageRepository']['ImageIdentifier']==item['image'],name
 print(name,operation['Status'],svc['Status'])
p.write_text(json.dumps(state,indent=2))
