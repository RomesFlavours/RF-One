from pathlib import Path
import boto3,json,requests
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');root=Path('tmp/registry-home-release');p=root/'state.json';d=json.loads(p.read_text());r=s.client('ecr').describe_images(repositoryName='rfone-web',imageIds=[{'imageTag':d['tag']}])['imageDetails'][0];d['image_digest']=r['imageDigest'];checks={}
for path in ('/','/login','/admin/roles?tab=people'):
 response=requests.get('https://rfone.romesflavours.com'+path,timeout=45,allow_redirects=False);checks[path]=response.status_code
assert checks['/login']==200 and checks['/admin/roles?tab=people']==302
(root/'public-http.json').write_text(json.dumps(checks,indent=2));p.write_text(json.dumps(d,indent=2));print(json.dumps({'image_digest':d['image_digest'],'public_http':checks}))
