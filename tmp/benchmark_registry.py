from pathlib import Path
import sys,time,json,hashlib,importlib.util
from sqlalchemy import event
root=Path('tmp/git-anagrafica-release/03 Software/RF-One Web').resolve();sys.path.insert(0,str(root/'tests'))
from test_registry_clover_confirmation import RegistryCloverTest
from rfone_data_store import models as m,access_profiles as p
from sqlalchemy import select
case=RegistryCloverTest();case.setUp()
try:
 with case.factory() as db:
  for i in range(40):
   person=m.Employee(display_name=f'Person {i:03}',location_id=case.loc,active=i%7!=0)
   account=m.RFOneAccount(username=f'fixture-{i}',display_name=f'Person {i:03}',password_hash='!',status='ACTIVE',is_admin=False,is_owner=False,session_version=1)
   db.add_all([person,account]);db.flush();db.add(m.EmployeeContextLink(employee_id=person.id,rfone_account_id=account.id))
  db.commit()
 output={}
 for tab in ('people','roles','areas','companies'):
  queries=[]
  def count(conn,cursor,statement,parameters,context,executemany):queries.append(statement)
  event.listen(case.engine,'before_cursor_execute',count)
  start=time.perf_counter();response=case.client.get('/admin/roles?tab='+tab);elapsed=time.perf_counter()-start
  event.remove(case.engine,'before_cursor_execute',count)
  assert response.status_code==200,response.data[:500]
  output[tab]={'queries':len(queries),'seconds':round(elapsed,4),'html_sha256':hashlib.sha256(response.data).hexdigest()}
 out=Path('tmp/registry-performance')/(sys.argv[1]+'.json');out.write_text(json.dumps(output,indent=2));print(json.dumps(output,indent=2))
finally:case.tearDown()
