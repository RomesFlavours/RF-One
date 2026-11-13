from pathlib import Path
import boto3,json
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');p=Path('tmp/registry-contacts-release/state.json');d=json.loads(p.read_text());a=s.client('apprunner');op=next(v for v in a.list_operations(ServiceArn=d['service_arn'])['OperationSummaryList'] if v['Id']==d['deploy_operation']);service=a.describe_service(ServiceArn=d['service_arn'])['Service'];print(json.dumps({'operation':op['Status'],'service':service['Status'],'image':service['SourceConfiguration']['ImageRepository']['ImageIdentifier']}))
if op['Status']=='SUCCEEDED':d['deployment_verified']=True;p.write_text(json.dumps(d,indent=2))
