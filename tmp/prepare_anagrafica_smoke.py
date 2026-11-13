from pathlib import Path
import json,psycopg2
s=json.loads(Path('tmp/copy_employee_directory_aws.json').read_text());cfg=s['local_database'];c=psycopg2.connect(host=cfg['host'],port=cfg['port'],dbname=cfg['database'],user=cfg['username'])
with c.cursor() as q:q.execute('SELECT id,session_version,status FROM rfone_accounts WHERE is_owner=true');rows=q.fetchall()
assert len(rows)==1 and rows[0][2]=='ACTIVE';Path('tmp/anagrafica-release/smoke-owner-reference.json').write_text(json.dumps({'id':rows[0][0],'session_version':rows[0][1]}));c.close();print('Owner reference loaded for read-only release smoke checks')
