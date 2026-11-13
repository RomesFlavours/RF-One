from pathlib import Path
import boto3,json
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');logs=s.client('logs');state=json.loads(Path('tmp/registry-access-release/release-state.json').read_text());op=state['services']['tips']['deploy_operation'];groups=logs.describe_log_groups(logGroupNamePrefix='/aws/apprunner/rfone-tips/')['logGroups']
for group in groups:
 if not group['logGroupName'].endswith('/service'):continue
 streams=logs.describe_log_streams(logGroupName=group['logGroupName'],orderBy='LastEventTime',descending=True,limit=5)['logStreams']
 for stream in streams:
  if op in stream['logStreamName']:
   events=logs.get_log_events(logGroupName=group['logGroupName'],logStreamName=stream['logStreamName'],limit=20)['events'];print(''.join(v['message'] for v in events))
