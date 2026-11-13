from pathlib import Path
import sys,json
sys.path.insert(0,str(Path('tmp/git-anagrafica-release/03 Software/RF-One Data Store').resolve()))
from sqlalchemy import select
from rfone_data_store import models as m, access_profiles as p, employee_directory as d
from rfone_data_store.database import create_configured_engine,create_session_factory
s=json.loads(Path(r'C:/Users/servi/AppData/Local/RF-One/Employee Directory/AWS-20261110T120743Z/verification.json').read_text());cfg=s['local_database']
e=create_configured_engine(f"postgresql+psycopg2://{cfg['username']}@127.0.0.1:{cfg['port']}/{cfg['database']}");f=create_session_factory(e)
with f() as db:
 for a in db.scalars(select(m.RFOneAccount).where((m.RFOneAccount.display_name.ilike('%anthony%')) | (m.RFOneAccount.username.ilike('%anthony%')))):
  print('ACCOUNT',a.id,a.username,a.display_name,a.status,'admin',a.is_admin,'person',d.context_person_id(db,'RFONE_ACCOUNT',a.id))
  print('DIRECT',[(x.domain_code,x.enabled,x.scope,x.role_code) for x in db.scalars(select(m.RFOneAccountDomainAccess).where(m.RFOneAccountDomainAccess.account_id==a.id))])
  for company in [None,*p.company_ids_for_account(db,a.id)]:print('EFFECTIVE',company,str(p.effective_permissions(db,a.id,company_id=company)))
 for person in db.scalars(select(m.Employee).where(m.Employee.display_name.ilike('%anthony%'))):
  print('PERSON',person.id,person.display_name,person.active)
  print('LINKS',[(x.rfone_account_id,x.training_account_id if hasattr(x,'training_account_id') else None) for x in db.scalars(select(m.EmployeeContextLink).where(m.EmployeeContextLink.employee_id==person.id))])
 for role in db.scalars(select(m.RestaurantRole)):
  grants=list(db.scalars(select(p.RolePermission).where(p.RolePermission.role_id==role.id)))
  if grants:print('ROLE',role.id,role.name,[(g.domain_code,g.scope,g.role_code) for g in grants])
e.dispose()
