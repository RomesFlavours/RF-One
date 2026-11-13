import boto3,json
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');d=json.loads(s.client('s3').get_object(Bucket='rfone-tips-deploy-418674484214',Key='schema/aws_applied_revision.json')['Body'].read());print(json.dumps({'revision':d['revision']}));from pathlib import Path;Path('tmp/registry-access-release/aws-schema.json').write_text(json.dumps(d,indent=2))
