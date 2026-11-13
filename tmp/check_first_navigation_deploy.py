import boto3,json
from pathlib import Path
p=Path('tmp/registry-navigation-release/first-deployment-state.json');d=json.loads(p.read_text());a=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1').client('apprunner');o=next(v for v in a.list_operations(ServiceArn=d['service_arn'])['OperationSummaryList'] if v['Id']==d['operation_id']);print('First navigation deployment:',o['Status']);d['deployment_status']=o['Status'];p.write_text(json.dumps(d,indent=2))
