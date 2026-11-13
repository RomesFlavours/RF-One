"""Apply verified Clover inactivity plan to the isolated local database only."""
from pathlib import Path
from datetime import datetime,timezone
import json,sys,subprocess,os
from sqlalchemy import create_engine,select,text
from sqlalchemy.orm import Session
root=Path.cwd();state=json.loads((root/'tmp/copy_employee_directory_aws.json').read_text());plan=json.loads((root/'tmp/clover_15day_local_plan.json').read_text());folder=Path(state['folder']);cfg=state['local_database']
assert cfg['host']=='127.0.0.1' and cfg['database']=='rfone_employee_directory'
assert (datetime.now(timezone.utc)-datetime.fromisoformat(plan['at'])).total_seconds()<1800
sys.path.insert(0,str(root/'tmp/role-company-development/RF-One Data Store'))
from rfone_data_store import models as m,access_profiles as p,employee_directory as d
engine=create_engine(f"postgresql+psycopg2://{cfg['username']}@127.0.0.1:{cfg['port']}/{cfg['database']}")
with engine.connect() as c:assert Path(c.execute(text('SHOW data_directory')).scalar()).resolve()==(folder/'postgres-data').resolve()
backup=folder/('before-clover-inactivity-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.dump')
env=os.environ.copy()
for key in ('PGHOST','PGPORT','PGDATABASE','PGUSER','PGPASSWORD','PGSERVICE','PGOPTIONS'):env.pop(key,None)
r=subprocess.run([str(folder/'runtime/pgsql/bin/pg_dump.exe'),'-h','127.0.0.1','-p',str(cfg['port']),'-U',cfg['username'],'-d',cfg['database'],'-Fc','--no-owner','--no-privileges','-f',str(backup)],env=env,capture_output=True)
assert r.returncode==0,'Local backup failed'
applied=[]
with Session(engine) as db:
    owner=db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.is_owner.is_(True)))
    for entry in plan['dismiss']:
        person=db.get(m.Employee,entry['id'])
        if not d.employee_is_active(person,[]):continue
        p.dismiss_profile_person(db,f'employee:{person.id}',dismissal_date=entry['dismissal_date'],actor=owner.id)
        p.event(db,'CLOVER_INACTIVITY_DISMISS',owner.id,employee_id=person.id,cutoff=plan['cutoff'],checked_at=plan['at'],last_punch=entry['last_punch'],date_basis=entry['date_basis'],rule='No Clover punch in 15 days')
        applied.append(person.id)
    db.commit()
with Session(engine) as db:
    active={v.id for v in d.employee_options(db)}
    assert not active.intersection(applied)
    assert all(e['id'] in active for e in plan['retain'])
    assert all(db.get(m.Employee,i) is not None for i in applied)
    assert db.scalar(select(m.RFOneAccount).where(m.RFOneAccount.is_owner.is_(True))).status=='ACTIVE'
result={**plan,'applied_ids':applied,'backup':str(backup),'verified_active_selector':True,'aws_database_writes':False,'clover_writes':False}
(root/'07 Tasks/Reports/CLOVER_15DAY_LOCAL_RESULT_20261110.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({'dismissed':len(applied),'retained':len(plan['retain']),'held':len(plan['skip']),'backup_saved':True,'active_selector_verified':True}))
