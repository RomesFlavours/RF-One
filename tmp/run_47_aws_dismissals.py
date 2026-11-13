from pathlib import Path
import boto3,json,zlib,base64
root=Path('tmp/anagrafica-release');p=root/'state.json';d=json.loads(p.read_text());s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1')
snap=s.client('rds').describe_db_snapshots(DBSnapshotIdentifier=d['rds_snapshot'])['DBSnapshots'][0];assert snap['Status']=='available'
service=s.client('apprunner').describe_service(ServiceArn=d['service_arn'])['Service'];assert service['SourceConfiguration']['ImageRepository']['ImageIdentifier'].endswith(':'+d['tag'])
targets=json.loads((root/'aws-dismiss-targets.json').read_text());assert len(targets)==47
script='targets='+repr(targets)+'\n'+(root/'apply_47_inside_aws.py').read_text(encoding='utf-8-sig')
payload=base64.b64encode(zlib.compress(script.encode())).decode();command="import zlib,base64;exec(zlib.decompress(base64.b64decode('"+payload+"')))";assert len(command)<7800
r=s.client('ecs').run_task(cluster=d['cluster'],taskDefinition=d['migration_task_definition'],launchType='FARGATE',networkConfiguration=d['network'],overrides={'containerOverrides':[{'name':d['container'],'command':['-c',command]}]},startedBy='rf1-authorized-47-dismissals');assert not r.get('failures'),r.get('failures');d['dismissals_task']=r['tasks'][0]['taskArn'];p.write_text(json.dumps(d,indent=2));print(json.dumps({'task':d['dismissals_task'],'authorized_targets':47}))
