from pathlib import Path
import boto3,json
root=Path('tmp/compensation-aws-copy');p=root/'state.json';state=json.loads(p.read_text());s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');b=s.client('codebuild').batch_get_builds(ids=[state['export_tool']['build_id']])['builds'][0];state['export_tool']['build_status']=b['buildStatus'];p.write_text(json.dumps(state,indent=2));print('Export tool build:',b['buildStatus'],b.get('currentPhase'))
if b['buildStatus']=='FAILED':
 logs=b['logs'];events=s.client('logs').get_log_events(logGroupName=logs['groupName'],logStreamName=logs['streamName'],limit=40)['events'];print(''.join(v['message'] for v in events)[-5000:])
