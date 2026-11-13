from pathlib import Path
import boto3,json
root=Path('tmp/registry-access-release');p=root/'release-state.json';state=json.loads(p.read_text());s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');ecs=s.client('ecs');task=ecs.describe_tasks(cluster=state['verification_cluster'],tasks=[state['audit_task']])['tasks'][0];print('AWS audit:',task['lastStatus'])
if task['lastStatus']=='STOPPED':
 print('Exit:',task['containers'][0].get('exitCode'))
 definition=ecs.describe_task_definition(taskDefinition=state['verification_task_definition'])['taskDefinition'];log=definition['containerDefinitions'][0]['logConfiguration']['options'];stream=log['awslogs-stream-prefix']+'/'+state['verification_container']+'/'+state['audit_task'].split('/')[-1];events=s.client('logs').get_log_events(logGroupName=log['awslogs-group'],logStreamName=stream,startFromHead=True)['events'];lines=''.join(v['message'] for v in events);(root/'aws-audit.log').write_text(lines)
 assert task['containers'][0].get('exitCode')==0,lines[-3000:]
 line=next(v['message'] for v in events if v['message'].startswith('REGISTRY_ACCESS_AUDIT '));result=json.loads(line[len('REGISTRY_ACCESS_AUDIT '):]);(root/'aws-audit.json').write_text(json.dumps(result,indent=2));state['audit_verified']=True;p.write_text(json.dumps(state,indent=2));print(json.dumps({'schema':result['schema'],'people':result['people'],'dismissed':result['dismissed'],'accounts':len(result['accounts']),'anthony':[v for v in result['accounts'] if v['username']=='anthony']},indent=2))
