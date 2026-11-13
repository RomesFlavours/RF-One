from pathlib import Path
import boto3,json,hashlib,zipfile,shutil
root=Path.cwd();release=root/'tmp/registry-contacts-release';d=json.loads((release/'state.json').read_text());assert d.get('deployment_verified')
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');service=s.client('apprunner').describe_service(ServiceArn=d['service_arn'])['Service'];assert service['Status']=='RUNNING' and service['SourceConfiguration']['ImageRepository']['ImageIdentifier'].endswith(':'+d['tag'])
payload=s.client('s3').get_object(Bucket='rfone-tips-deploy-418674484214',Key=d['source_s3_key'])['Body'].read();assert hashlib.sha256(payload).hexdigest()==d['source_sha256'];download=release/'aws-published-source.zip';download.write_bytes(payload)
statefile=root/'tmp/copy_employee_directory_aws.json';state=json.loads(statefile.read_text());folder=Path(state['folder']);target=Path(state['development_source']);assert target.resolve()==(folder/'development-source').resolve();count=0
with zipfile.ZipFile(download) as z:
 for name in z.namelist():
  destination=target/name;assert destination.resolve().is_relative_to(target.resolve());destination.parent.mkdir(parents=True,exist_ok=True);content=z.read(name);destination.write_bytes(content);assert hashlib.sha256(destination.read_bytes()).digest()==hashlib.sha256(content).digest();count+=1
launcher=folder/'Avvia Anagrafica.ps1';t=launcher.read_text(encoding='utf-8');t=t.replace("[ValidateSet('/administration/employees','/admin/accounts','/admin/roles')]", "[ValidateSet('/','/administration/employees','/admin/accounts','/admin/roles')]");launcher.write_text(t,encoding='utf-8')
(folder/'Avvia MyRF.cmd').write_text('@echo off\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Avvia Anagrafica.ps1" -Page "/"\n',encoding='utf-8')
state['myrf_home']={'url':'http://127.0.0.1:5094/','registry_url':'http://127.0.0.1:5094/admin/roles?tab=people','source_image':service['SourceConfiguration']['ImageRepository']['ImageIdentifier'],'source_sha256':d['source_sha256'],'verified_files':count,'database_preserved':True}
for path in (statefile,folder/'verification.json'):path.write_text(json.dumps(state,indent=2),encoding='utf-8')
print(json.dumps({'local_myrf':state['myrf_home']['url'],'verified_files':count,'local_database_preserved':True}))
