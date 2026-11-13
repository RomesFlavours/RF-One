from pathlib import Path
from datetime import datetime,timezone
import boto3,json,hashlib,zipfile,socket
root=Path.cwd();out=root/'tmp/compensation-aws-copy';out.mkdir(exist_ok=True);s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');old=json.loads((root/'tmp/registry-access-release/release-state.json').read_text());entry=old['services']['web'];svc=s.client('apprunner').describe_service(ServiceArn=entry['service_arn'])['Service'];image=svc['SourceConfiguration']['ImageRepository']['ImageIdentifier'];assert image==entry['image'],'Current Web release changed; inspect and locate its matching source before copying'
folder=Path(r'C:/Users/servi/AppData/Local/RF-One/Compensation')/('AWS-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));folder.mkdir(parents=True,exist_ok=False)
payload=s.client('s3').get_object(Bucket='rfone-tips-deploy-418674484214',Key=entry['source_s3_key'])['Body'].read();assert hashlib.sha256(payload).hexdigest()==entry['source_sha256'];(folder/'aws-source.zip').write_bytes(payload)
source=folder/'source';source.mkdir()
with zipfile.ZipFile(folder/'aws-source.zip') as z:
 for name in z.namelist():assert (source/name).resolve().is_relative_to(source.resolve())
 z.extractall(source)
assert (source/'RF-One Web/compensation_routes.py').exists()
port=5095
with socket.socket() as probe:probe.bind(('127.0.0.1',port))
state={'folder':str(folder),'source':str(source),'source_image':image,'source_digest':entry['image_digest'],'source_sha256':entry['source_sha256'],'source_s3_key':entry['source_s3_key'],'web_port':port,'url':f'http://127.0.0.1:{port}/compensation','started_at':datetime.now(timezone.utc).isoformat(),'aws_database_writes':False,'aws_application_changes':False,'status':'COPYING','data_scope':'Compensation, Payroll, consumed Tips and shifts, shared Registry and FK reference dependencies; full public schema, scoped row data'}
(folder/'verification.json').write_text(json.dumps(state,indent=2),encoding='utf-8');(out/'state.json').write_text(json.dumps(state,indent=2));print(json.dumps({'source_verified':True,'folder':str(folder),'local_url':state['url']}))
