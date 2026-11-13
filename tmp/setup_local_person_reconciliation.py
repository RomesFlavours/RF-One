from pathlib import Path
import sys,json,hashlib
from sqlalchemy import select,text,func,inspect
root=Path('tmp/git-anagrafica-release/03 Software');sys.path[:0]=[str(root/'RF-One Data Store'),str(root/'RF-One Web')]
from rfone_data_store.database import create_configured_engine,create_session_factory
from rfone_data_store import models as m,person_reconciliation as rec
state=json.loads(Path('C:/Users/servi/AppData/Local/RF-One/Employee Directory/AWS-20261110T120743Z/verification.json').read_text(encoding='utf-8'));v=state['local_database'];assert v['host']=='127.0.0.1' and v['database']=='rfone_employee_directory'
engine=create_configured_engine(f"postgresql+psycopg2://{v['username']}@127.0.0.1:{v['port']}/{v['database']}")
f=create_session_factory(engine);out=Path('tmp/person-reconciliation');out.mkdir(exist_ok=True)
def protected():
 with f() as db:
  db.execute(text('SET TRANSACTION READ ONLY'))
  result={}
  for model in (m.Employee,m.RFOneAccount,m.TrainingAccount,m.RFOneTrainingIdentityLink,m.RFOneAccountDomainAccess,m.RFOneAccountDomainItemAccess,m.TrainingNeed,m.TrainingAssignment,m.TrainingAttempt,m.TrainingOverallAttempt):
   rows=[dict(r) for r in db.execute(select(model.__table__)).mappings()];rows.sort(key=lambda r:json.dumps(r,sort_keys=True,default=str));result[model.__tablename__]={'count':len(rows),'sha256':hashlib.sha256(json.dumps(rows,sort_keys=True,default=str).encode()).hexdigest()}
  return result
before=protected()
with f() as db:
 db.execute(text('SET TRANSACTION READ ONLY'));report=rec.audit(db);(out/'before-audit.json').write_text(json.dumps(report,indent=2,default=str));print('Existing local identity audit:',json.dumps(report['counts']),'schema ready:',report['ready'])
# Explicit additive LOCAL schema setup only; no Alembic stamp or historical writes.
with engine.begin() as connection:
 for model in rec.TABLES:model.__table__.create(connection,checkfirst=True)
after=protected();assert before==after,'Protected data changed during additive setup'
with f() as db:
 db.execute(text('SET TRANSACTION READ ONLY'));report=rec.audit(db);(out/'local-audit.json').write_text(json.dumps(report,indent=2,default=str));print('Local schema installed; existing data unchanged:',json.dumps(report['counts']))
(out/'protected-data-check.json').write_text(json.dumps({'before':before,'after':after,'unchanged':before==after},indent=2));engine.dispose()
