from pathlib import Path
import boto3,json,copy,requests
out=Path('tmp/registry-performance-release');d=json.loads((out/'state.json').read_text());s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');v=s.client('apprunner').describe_service(ServiceArn=d['service_arn'])['Service'];old=json.loads((out/'baseline-service.json').read_text());expected=copy.deepcopy(old['SourceConfiguration']);expected['ImageRepository']['ImageIdentifier']=d['image'];assert v['SourceConfiguration']==expected;assert v['InstanceConfiguration']==old['InstanceConfiguration'];assert v['NetworkConfiguration']==old['NetworkConfiguration'];print('Runtime source settings, secrets, instance and network configuration preserved')
checks=[];client=requests.Session();client.trust_env=False
for path,status in [('/login',200),('/admin/roles?tab=people',302),('/admin/roles?tab=roles',302),('/admin/roles?tab=areas',302),('/admin/roles?tab=companies',302)]:
 r=client.get('https://rfone.romesflavours.com'+path,allow_redirects=False,timeout=40);assert r.status_code==status,(path,r.status_code);checks.append({'path':path,'status':r.status_code})
d['configuration_preserved']=True;d['public_access_checks']=checks;(out/'state.json').write_text(json.dumps(d,indent=2));print(json.dumps(checks))
