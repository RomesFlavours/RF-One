from pathlib import Path
import boto3,json
root=Path('tmp/registry-access-release');p=root/'release-state.json';state=json.loads(p.read_text());s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');cb=s.client('codebuild');builds={v['id']:v for v in cb.batch_get_builds(ids=[v['build_id'] for v in state['services'].values()])['builds']}
for name,v in state['services'].items():
 b=builds[v['build_id']];v['build_status']=b['buildStatus'];v['build_logs']=b.get('logs',{});print(name,b['buildStatus'],b.get('currentPhase'))
 if b['buildStatus'] in ('FAILED','FAULT','TIMED_OUT'):
  group=b.get('logs',{}).get('groupName');stream=b.get('logs',{}).get('streamName')
  if group and stream:
   events=s.client('logs').get_log_events(logGroupName=group,logStreamName=stream,limit=60)['events'];text=''.join(e['message'] for e in events);(root/(name+'-failed-build.log')).write_text(text);print(text[-4200:])
p.write_text(json.dumps(state,indent=2))
