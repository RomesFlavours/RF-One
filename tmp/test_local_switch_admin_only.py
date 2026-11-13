from pathlib import Path
import json,re,sys,requests,time
root=Path.cwd();source=root/'tmp/git-anagrafica-release/03 Software';sys.path.insert(0,str(source/'RF-One Data Store'))
from rfone_data_store.database import create_configured_engine,create_session_factory
from rfone_data_store import models as m
from sqlalchemy import select
state=json.loads(Path(r'C:/Users/servi/AppData/Local/RF-One/Employee Directory/AWS-20261110T120743Z/verification.json').read_text(encoding='utf-8'));d=state['local_database']
engine=create_configured_engine(f"postgresql+psycopg2://{d['username']}@127.0.0.1:{d['port']}/{d['database']}");factory=create_session_factory(engine)
with factory() as db:
 rows=[(a.id,a.status,bool(a.is_admin or a.is_owner)) for a in db.scalars(select(m.RFOneAccount))]
base='http://127.0.0.1:5094';checks=0
for identity,status,is_admin in rows:
 c=requests.Session();c.trust_env=False
 r=c.get(base+'/local/users',timeout=30)
 assert r.status_code==200 and 'Switch user' in r.text;checks+=1
 token=re.search(r'name="csrf_token" value="([^"]+)"',r.text)[1]
 assert c.post(base+'/local/access-user',data={'account_id':identity,'csrf_token':token},allow_redirects=False,timeout=20).status_code==302;checks+=1
 chooser=c.get(base+'/local/users',timeout=20)
 if status=='ACTIVE' and is_admin:
  assert chooser.status_code==200 and 'Switch user' in chooser.text;checks+=1
 else:
  assert chooser.status_code==403 and 'Switch user' not in chooser.text;checks+=1
  denied=c.post(base+'/local/access-user',data={'account_id':identity,'csrf_token':token},allow_redirects=False,timeout=20)
  assert denied.status_code==403;checks+=1
  page=c.get(base+'/',timeout=30)
  assert 'Switch user' not in page.text;checks+=1
print(json.dumps({'accounts_checked':len(rows),'checks_passed':checks,'permissions_changed':False,'aws_changed':False}))
engine.dispose()
