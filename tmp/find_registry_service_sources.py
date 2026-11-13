import boto3,json
from pathlib import Path
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');cb=s.client('codebuild');out={}
for project in ['rfone-web-build','rfone-tips-build','rfone-selection-build']:
 ids=cb.list_builds_for_project(projectName=project,sortOrder='DESCENDING')['ids'][:45]
 builds=cb.batch_get_builds(ids=ids)['builds'] if ids else []
 out[project]=[{'id':b['id'],'status':b['buildStatus'],'source':b.get('source',{}).get('location'),'buildspec':b.get('source',{}).get('buildspec',''),'time':str(b['startTime'])} for b in builds]
p=Path('tmp/registry-access-release/builds.json');p.write_text(json.dumps(out,indent=2))
for project,builds in out.items():
 print(project)
 for b in builds:
  if b['status']=='SUCCEEDED':print(json.dumps({k:v for k,v in b.items() if k!='buildspec'}))
