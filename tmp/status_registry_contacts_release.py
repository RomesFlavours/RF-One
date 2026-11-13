from pathlib import Path
import boto3,json
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');root=Path('tmp/registry-contacts-release');d=json.loads((root/'state.json').read_text());b=s.client('codebuild').batch_get_builds(ids=[d['build_id']])['builds'][0];snap=s.client('rds').describe_db_snapshots(DBSnapshotIdentifier=d['rds_snapshot'])['DBSnapshots'][0];print(json.dumps({'build':b['buildStatus'],'snapshot':snap['Status']}))
