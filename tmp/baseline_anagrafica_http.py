from pathlib import Path
import boto3,json,requests
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');root=Path('tmp/anagrafica-release');d=json.loads((root/'state.json').read_text());baseline=json.loads((root/'baseline-service.json').read_text());base=baseline['SourceConfiguration']['ImageRepository']['ImageConfiguration']['RuntimeEnvironmentVariables'].get('RFONE_PUBLIC_BASE_URL') or 'https://'+baseline['ServiceUrl']
paths=['/','/login','/admin/accounts','/administration/employees','/bank/','/organization/'];results={}
for path in paths:
 try:r=requests.get(base.rstrip('/')+path,timeout=45,allow_redirects=False);results[path]={'status':r.status_code,'location':r.headers.get('Location')}
 except requests.RequestException as e:results[path]={'error':type(e).__name__}
(root/'baseline-http.json').write_text(json.dumps({'base':base,'routes':results},indent=2));print(json.dumps({'base':base,'statuses':{k:v.get('status',v.get('error')) for k,v in results.items()}}))
