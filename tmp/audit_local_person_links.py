from pathlib import Path
import sys,json,os
root=Path('tmp/git-anagrafica-release/03 Software');sys.path[:0]=[str(root/'RF-One Data Store'),str(root/'RF-One Web')]
s=json.loads(Path('C:/Users/servi/AppData/Local/RF-One/Employee Directory/AWS-20261110T120743Z/verification.json').read_text(encoding='utf-8'));v=s['local_database'];assert v['host']=='127.0.0.1' and v['database']=='rfone_employee_directory'
os.environ['RFONE_DATABASE_URL']=f"postgresql+psycopg2://{v['username']}@127.0.0.1:{v['port']}/{v['database']}"
from rfone_data_store.person_reconciliation_audit import main
sys.argv=['audit','--output','tmp/person-reconciliation/local-audit.json'];main()
