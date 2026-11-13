from pathlib import Path
import json,boto3
root=Path('tmp/anagrafica-release');d=json.loads((root/'state.json').read_text());baseline=json.loads((root/'baseline-service.json').read_text());s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');r=s.client('apprunner').update_service(ServiceArn=d['service_arn'],SourceConfiguration=baseline['SourceConfiguration']);print(json.dumps({'rollback_operation':r['OperationId']}))
