import runpy,json
from pathlib import Path
import boto3
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');expected=json.loads(Path('tmp/registry-performance-release/state.json').read_text());v=s.client('apprunner').describe_service(ServiceArn=expected['service_arn'])['Service'];print('AWS',v['Status'],v['SourceConfiguration']['ImageRepository']['ImageIdentifier']);assert v['SourceConfiguration']['ImageRepository']['ImageIdentifier']==expected['image']
x=runpy.run_path('tmp/git-anagrafica-release/03 Software/RF-One Web/tests/test_role_company_http.py');owner=x['owner'];uid=x['admin_id'];token=x['token'];key='account:'+str(uid)
checks={}
for name,path in [('own_access',f'/admin/accounts/{uid}/access?from_person={key}'),('own_edit',f'/admin/accounts/{uid}/edit'),('own_training',f'/admin/accounts/{uid}/training-link')]:
 r=owner.get(path);checks[name]={'status':r.status_code,'legacy_accounts_breadcrumb':'href="/admin/accounts"' in r.get_data(as_text=True)}
r=owner.post(f'/admin/accounts/{uid}/access',data={'csrf_token':token,'from_person':key});checks['save_own_access']={'status':r.status_code,'redirect':r.location}
r=owner.post(f'/admin/accounts/{uid}/reset-password',data={'csrf_token':token,'password':'mismatch','password_confirm':'different'});checks['invalid_password_return']={'status':r.status_code,'redirect':r.location}
r=owner.post('/admin/roles',data={'csrf_token':token,'action':'person_password','person':key,'tab':'people'});checks['registry_password_entry']={'status':r.status_code,'redirect':r.location}
Path('tmp/registry-navigation-audit.json').write_text(json.dumps(checks,indent=2));print('NAVIGATION_AUDIT',json.dumps(checks,indent=2))
