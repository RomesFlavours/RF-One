from pathlib import Path
import boto3,json
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');p=Path('tmp/anagrafica-release/state.json');d=json.loads(p.read_text());task=s.client('ecs').describe_tasks(cluster=d['cluster'],tasks=[d['audit_task']])['tasks'][0];print(json.dumps({'status':task['lastStatus'],'containers':[{'name':c['name'],'exitCode':c.get('exitCode'),'reason':c.get('reason')} for c in task['containers']]}))
if task['lastStatus']=='STOPPED':
 cfg=d['log_configuration']['options'];stream=cfg['awslogs-stream-prefix']+'/'+d['container']+'/'+d['audit_task'].rsplit('/',1)[1];events=s.client('logs').get_log_events(logGroupName=cfg['awslogs-group'],logStreamName=stream)['events'];print('\n'.join(e['message'] for e in events)[-2000:]);assert task['containers'][0].get('exitCode')==0
