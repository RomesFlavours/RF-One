from pathlib import Path
import boto3,json
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');b=s.client('codebuild');ids=b.list_builds_for_project(projectName='rfone-web-build',sortOrder='DESCENDING')['ids'][:6]
for v in b.batch_get_builds(ids=ids)['builds']:print(json.dumps({'id':v['id'],'status':v['buildStatus'],'source':v.get('source',{}).get('location'),'buildspec':v.get('source',{}).get('buildspec','')[:550],'start':str(v['startTime'])}))
