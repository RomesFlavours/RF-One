from pathlib import Path
import boto3,json
root=Path('tmp/registry-access-release');p=root/'release-state.json';state=json.loads(p.read_text());assert state['anthony_update_verified'];s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');script=(root/'aws_readonly_audit.py').read_text()+'''\nassert result['people']==64 and result['dismissed']==47
anthony=next(a for a in result['accounts'] if a['username']=='anthony')
assert anthony['effective']=={'None':['KITCHEN']},anthony['effective']
print('REGISTRY_ACCESS_POSTCHECK_OK',flush=True)
''';r=s.client('ecs').run_task(cluster=state['verification_cluster'],taskDefinition=state['verification_task_definition'],launchType='FARGATE',networkConfiguration=state['verification_network'],overrides={'containerOverrides':[{'name':state['verification_container'],'command':['-c',script]}]},startedBy='rf1-registry-postcheck');assert not r.get('failures');state['post_audit_task']=r['tasks'][0]['taskArn'];p.write_text(json.dumps(state,indent=2));print('Fresh read-only post-deploy verification started.')
