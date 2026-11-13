from pathlib import Path
import json,psycopg2
p=Path(r'C:/Users/servi/AppData/Local/RF-One/Employee Directory/AWS-20261110T120743Z/verification.json');s=json.loads(p.read_text(encoding='utf-8'));d=s['local_database'];c=psycopg2.connect(host='127.0.0.1',port=d['port'],dbname=d['database'],user=d['username'],options='-c default_transaction_read_only=on')
with c.cursor() as q:
 q.execute('SELECT id,period_start,period_end FROM payroll_calculation_runs ORDER BY period_start DESC,id DESC LIMIT 5');rows=q.fetchall();print(json.dumps({'local_runs':rows},default=str))
c.close()
