import boto3,json
from pathlib import Path
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');projects=s.client('codebuild').batch_get_projects(names=['rfone-web-build','rfone-tips-build','rfone-selection-build'])['projects'];out={}
for p in projects:
 out[p['name']]={'buildspec':p['source'].get('buildspec',''),'ecr':[{k:v for k,v in e.items() if k in ('name','value','type')} for e in p['environment']['environmentVariables'] if e['name'] in ('ECR_URI','IMAGE_TAG','IMAGE_REPO_NAME','AWS_REGION')]}
Path('tmp/registry-access-release/build-projects.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
