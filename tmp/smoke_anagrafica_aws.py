from pathlib import Path
from urllib.parse import urlparse
import json,boto3,requests
from flask import Flask
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');root=Path('tmp/anagrafica-release');d=json.loads((root/'state.json').read_text());assert d.get('deployment_verified')
service=s.client('apprunner').describe_service(ServiceArn=d['service_arn'])['Service'];cfg=service['SourceConfiguration']['ImageRepository']['ImageConfiguration'];base=cfg['RuntimeEnvironmentVariables']['RFONE_PUBLIC_BASE_URL'].rstrip('/');raw=s.client('secretsmanager').get_secret_value(SecretId=cfg['RuntimeEnvironmentSecrets']['RFONE_FLASK_SECRET_KEY'])['SecretString']
try:
 v=json.loads(raw);raw=v if isinstance(v,str) else v.get('RFONE_FLASK_SECRET_KEY',v.get('value',''))
except json.JSONDecodeError:pass
assert raw
owner=json.loads((root/'smoke-owner-reference.json').read_text());app=Flask('release-smoke');app.secret_key=raw;cookie=app.session_interface.get_signing_serializer(app).dumps({'rfone_account_id':owner['id'],'rfone_session_version':owner['session_version']});http=requests.Session();http.cookies.set('session',cookie,domain=urlparse(base).hostname,path='/')
results={}
for path in ('/','/admin/roles?tab=roles','/admin/roles?tab=areas','/admin/roles?tab=companies','/admin/roles?tab=people','/admin/accounts','/administration/employees',f"/admin/accounts/{owner['id']}/access?from_person=account:{owner['id']}"):
 r=http.get(base+path,timeout=60,allow_redirects=False);assert r.status_code==200,f'{path}: {r.status_code}'
 if path.startswith('/admin/roles?'):assert '<h1>Anagrafica</h1>' in r.text
 results[path]=r.status_code
 print('Verified '+path,flush=True)
r=requests.get(base+'/admin/roles',timeout=30,allow_redirects=False);assert r.status_code==302 and '/login' in r.headers.get('Location','');results['anonymous_roles']=302
(root/'production-smoke.json').write_text(json.dumps({'base':base,'routes':results,'real_grants_modified':False},indent=2));http.cookies.clear();print('PRODUCTION_SMOKE_PASSED',flush=True)
