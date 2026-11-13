from pathlib import Path
import boto3,json
s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');p=Path('tmp/anagrafica-release/state.json');d=json.loads(p.read_text());r=s.client('rds').create_db_snapshot(DBInstanceIdentifier='rfone-dev',DBSnapshotIdentifier='rfone-before-'+d['tag']);d['rds_snapshot']=r['DBSnapshot']['DBSnapshotIdentifier'];p.write_text(json.dumps(d,indent=2));print(json.dumps({'snapshot':d['rds_snapshot'],'status':r['DBSnapshot']['Status']}))
