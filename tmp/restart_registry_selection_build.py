from pathlib import Path
import boto3,json,hashlib
root=Path('tmp/registry-access-release');p=root/'release-state.json';state=json.loads(p.read_text());item=state['services']['selection'];s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');s3=s.client('s3');bucket='rfone-tips-deploy-418674484214';key='rfone-selection-source.zip'
current=s3.get_object(Bucket=bucket,Key=key)['Body'].read();baseline=json.loads((root/'sources.json').read_text())['selection'];assert hashlib.sha256(current).hexdigest()==baseline['sha256'],'Selection source changed during build; preserve concurrent release'
backup=item['source_s3_key'].rsplit('/',1)[0]+'/selection-source-before.zip';s3.copy_object(Bucket=bucket,Key=backup,CopySource={'Bucket':bucket,'Key':key})
item['immutable_source_s3_key']=item['source_s3_key'];item['baseline_backup_s3_key']=backup;item['failed_build_ids']=[item['build_id']]
s3.upload_file(str(root/'selection-release.zip'),bucket,key);item['source_s3_key']=key
result=s.client('codebuild').start_build(projectName='rfone-selection-build');item['build_id']=result['build']['id'];item['build_status']='IN_PROGRESS';p.write_text(json.dumps(state,indent=2));print('Selection restarted using its existing authorized source key; IAM unchanged:',item['build_id'])
