import boto3,json
from pathlib import Path
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');logs=s.client('logs');prefix='/aws/apprunner/rfone-web/07524815436944e3a05c600c5486f951';groups=logs.describe_log_groups(logGroupNamePrefix=prefix)['logGroups']
for group in groups:
 streams=logs.describe_log_streams(logGroupName=group['logGroupName'],orderBy='LastEventTime',descending=True,limit=2)['logStreams']
 for stream in streams:
  events=logs.get_log_events(logGroupName=group['logGroupName'],logStreamName=stream['logStreamName'],limit=8)['events']
  print(json.dumps({'group':group['logGroupName'].rsplit('/',1)[-1],'stream':stream['logStreamName'],'messages':[e['message'] for e in events]},ensure_ascii=True))
