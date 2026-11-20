"""Explicit one-time additive Bank schema preparation; never runs at app startup."""
import hashlib,json,os,pathlib,sqlite3,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
if (ROOT/'schema-compatibility.json').exists():
 raise SystemExit('Preparazione già registrata. Non sovrascrivo le verifiche dello schema iniziale.')
sys.path.insert(0,str(ROOT/'03 Software'/'RF-One Data Store'))
from sqlalchemy import create_engine
from rfone_data_store import models
DB=pathlib.Path(os.environ['LOCALAPPDATA'])/'RF-One'/'RFBank'/'rfone.db'
def fingerprint(c,t):
 cols=[x[1] for x in c.execute('pragma table_info("'+t+'")')]
 names=','.join('"'+x+'"' for x in cols);h=hashlib.sha256();n=0
 for row in c.execute('select '+names+' from "'+t+'" order by '+names):h.update(repr(row).encode());h.update(b'\n');n+=1
 return dict(rows=n,sha256=h.hexdigest())
c=sqlite3.connect(DB.as_uri()+'?mode=ro',uri=True)
existing=[x[0] for x in c.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
before={t:fingerprint(c,t) for t in existing};c.close()
missing=[t for t in models.Base.metadata.tables.values() if t.name.startswith('bank_') and t.name not in existing]
e=create_engine('sqlite:///'+DB.as_posix());models.Base.metadata.create_all(e,tables=missing);e.dispose()
c=sqlite3.connect(DB.as_uri()+'?mode=ro',uri=True)
assert all(fingerprint(c,t)==v for t,v in before.items()),'Existing table data changed'
assert all(c.execute('select count(*) from "'+t.name+'"').fetchone()[0]==0 for t in missing)
assert c.execute('pragma integrity_check').fetchall()==[('ok',)]
assert c.execute('pragma foreign_key_check').fetchall()==[]
assert c.execute('select count(*) from bank_transaction_explanations').fetchone()[0]==0
assert c.execute('select count(*) from bank_transaction_allocations').fetchone()[0]==0
report=dict(database=str(DB),added_empty_tables=[t.name for t in missing],all_existing_tables_identical=True,table_fingerprints=before,integrity='ok',foreign_key_errors=[])
(ROOT/'schema-compatibility.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='table_fingerprints'}))
