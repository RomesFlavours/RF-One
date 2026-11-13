from pathlib import Path
import boto3,json,sys
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');p=Path('tmp/registry-contacts-release/state.json');d=json.loads(p.read_text());name=sys.argv[1] if len(sys.argv)>1 else 'migration_task';task=s.client('ecs').describe_tasks(cluster=d['cluster'],tasks=[d[name]])['tasks'][0];print(json.dumps({'task':name,'status':task['lastStatus'],'exitCode':task['containers'][0].get('exitCode'),'reason':task.get('stoppedReason')}))
if task['lastStatus']=='STOPPED':
 cfg=d['log_configuration']['options'];stream=cfg['awslogs-stream-prefix']+'/'+d['container']+'/'+d[name].rsplit('/',1)[1]
 events=s.client('logs').get_log_events(logGroupName=cfg['awslogs-group'],logStreamName=stream)['events'];messages='\n'.join(e['message'] for e in events);Path('tmp/registry-contacts-release/'+name+'.log').write_text(messages,encoding='utf-8');print(messages[-2000:]);assert task['containers'][0].get('exitCode')==0
