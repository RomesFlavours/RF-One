from pathlib import Path
from datetime import datetime,timezone
import boto3,json,hashlib,zipfile
root=Path('tmp/compensation-aws-copy');p=root/'state.json';state=json.loads(p.read_text());tag='compensation-copy-tool-'+datetime.now(timezone.utc).strftime('%Y%m%dt%H%M%Sz');bucket='rfone-tips-deploy-418674484214';key='releases/'+tag+'/source.zip';archive=root/'export-tool.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for file in (root/'export-tool').iterdir():
  if file.is_file() and file.suffix in ('.py','') or file.name=='Dockerfile':
   if file.is_file():z.write(file,file.name)
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');s.client('s3').upload_file(str(archive),bucket,key);image='418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web:'+tag
spec='''version: 0.2
phases:
  pre_build:
    on-failure: ABORT
    commands:
      - aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 418674484214.dkr.ecr.us-east-1.amazonaws.com
  build:
    on-failure: ABORT
    commands:
      - docker build -t '''+image+''' .
  post_build:
    on-failure: ABORT
    commands:
      - docker push '''+image+'\n'
r=s.client('codebuild').start_build(projectName='rfone-web-build',sourceLocationOverride=bucket+'/'+key,buildspecOverride=spec)
state['export_tool']={'image':image,'build_id':r['build']['id'],'source_s3_key':key,'source_sha256':hashlib.sha256(archive.read_bytes()).hexdigest()};p.write_text(json.dumps(state,indent=2));print('Read-only Compensation export tool build:',r['build']['id'])
