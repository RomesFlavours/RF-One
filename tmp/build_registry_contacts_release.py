from pathlib import Path
import boto3,json
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');root=Path('tmp/registry-contacts-release');p=root/'state.json';d=json.loads(p.read_text());key='releases/'+d['tag']+'/source.zip';bucket='rfone-tips-deploy-418674484214';s.client('s3').upload_file(str(root/'source.zip'),bucket,key)
buildspec='''version: 0.2
phases:
  pre_build:
    commands:
      - aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_URI
  build:
    commands:
      - docker build -t $ECR_URI:'''+d['tag']+''' .
  post_build:
    commands:
      - docker push $ECR_URI:'''+d['tag']+'\n'
r=s.client('codebuild').start_build(projectName='rfone-web-build',sourceLocationOverride=bucket+'/'+key,buildspecOverride=buildspec);d.update(build_id=r['build']['id'],source_s3_key=key);p.write_text(json.dumps(d,indent=2));print(json.dumps({'build_id':d['build_id'],'tag':d['tag']}))
