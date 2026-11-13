from pathlib import Path
import boto3,json
root=Path('tmp/registry-navigation-release');p=root/'state.json';d=json.loads(p.read_text());s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');b=s.client('codebuild').batch_get_builds(ids=[d['build_id']])['builds'][0];d['build_status']=b['buildStatus'];p.write_text(json.dumps(d,indent=2));print(b['buildStatus'],b.get('currentPhase'))
if b['buildStatus']=='FAILED':
 e=s.client('logs').get_log_events(logGroupName=b['logs']['groupName'],logStreamName=b['logs']['streamName'],limit=35)['events'];print(''.join(v['message'] for v in e)[-5000:])

