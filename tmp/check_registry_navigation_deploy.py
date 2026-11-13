from pathlib import Path
import boto3,json
p=Path('tmp/registry-navigation-release/state.json');d=json.loads(p.read_text());s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');a=s.client('apprunner');ops=a.list_operations(ServiceArn=d['service_arn'])['OperationSummaryList'];o=next(x for x in ops if x['Id']==d['operation_id']);v=a.describe_service(ServiceArn=d['service_arn'])['Service'];d['deployment_status']=o['Status'];p.write_text(json.dumps(d,indent=2));print(o['Status'],v['Status']);print(v['SourceConfiguration']['ImageRepository']['ImageIdentifier'])

