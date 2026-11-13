from pathlib import Path
import json
s=Path('tmp/setup_local_person_reconciliation.py').read_text(encoding='utf-8').split('before=protected()',1)[0];exec(compile(s,'local-readonly-check','exec'))
saved=json.loads(Path('tmp/person-reconciliation/protected-data-check.json').read_text());current=protected();assert saved['before']==current
from sqlalchemy import select,func,text
with f() as db:
 db.execute(text('SET TRANSACTION READ ONLY'));events=db.scalar(select(func.count()).select_from(rec.PersonReconciliationEvent));persons=db.scalar(select(func.count()).select_from(m.CandidatePerson));assert events==0 and persons==143
print('Final local data preserved; no real reconciliation events; 143 pre-existing central people');engine.dispose()
