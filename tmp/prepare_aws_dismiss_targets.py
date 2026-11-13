from pathlib import Path
import json,psycopg2
root=Path.cwd();state=json.loads((root/'tmp/copy_employee_directory_aws.json').read_text());cfg=state['local_database'];result=json.loads((root/'07 Tasks/Reports/CLOVER_15DAY_LOCAL_RESULT_20261110.json').read_text());assert len(result['applied_ids'])==47
c=psycopg2.connect(host=cfg['host'],port=cfg['port'],dbname=cfg['database'],user=cfg['username']);targets=[]
with c.cursor() as q:
 for item in result['dismiss']:
  q.execute('SELECT merchant_id,external_employee_id FROM employee_clover_links WHERE employee_id=%s ORDER BY merchant_id,external_employee_id',(item['id'],));links=q.fetchall();assert links
  targets.append({'id':item['id'],'date':item['dismissal_date'],'date_basis':item['date_basis'],'links':[list(v) for v in links]})
c.close();(root/'tmp/anagrafica-release/aws-dismiss-targets.json').write_text(json.dumps(targets,indent=2));print('Prepared exactly 47 explicit employee identities')
