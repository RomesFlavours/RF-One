from pathlib import Path
import json,sys
from sqlalchemy import create_engine,select
from sqlalchemy.orm import Session
root=Path.cwd();s=json.loads((root/'tmp/copy_employee_directory_aws.json').read_text());sys.path.insert(0,str(Path(s['development_source'])/'RF-One Data Store'));from rfone_data_store import models as m,access_profiles as p,employee_directory as d
c=s['local_database'];e=create_engine(f"postgresql+psycopg2://{c['username']}@127.0.0.1:{c['port']}/{c['database']}")
with Session(e) as db:
 db.connection().exec_driver_sql('SET TRANSACTION READ ONLY')
 result=[]
 for a in db.scalars(select(m.RFOneAccount).order_by(m.RFOneAccount.id)):
  companies=p.company_ids_for_account(db,a.id)
  result.append({'name':a.display_name,'status':a.status,'admin':a.is_admin,'owner':a.is_owner,'person_id':d.context_person_id(db,'RFONE_ACCOUNT',a.id),'direct':[{'domain':g.domain_code,'scope':g.scope,'level':g.role_code} for g in db.scalars(select(m.RFOneAccountDomainAccess).where(m.RFOneAccountDomainAccess.account_id==a.id,m.RFOneAccountDomainAccess.enabled.is_(True)))],'companies':sorted(companies),'effective':{str(company):sorted(p.effective_permissions(db,a.id,company_id=company)) for company in companies}})
 print(json.dumps(result,indent=2))
 (root/'tmp/registry-local-real-accounts-audit.json').write_text(json.dumps(result,indent=2))
