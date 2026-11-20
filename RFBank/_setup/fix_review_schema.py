"""Explicit additive fix for the filtered Review query on the clean RFBank DB."""
import hashlib,json,os,pathlib,sqlite3
ROOT=pathlib.Path(__file__).resolve().parents[1];DB=pathlib.Path(os.environ['LOCALAPPDATA'])/'RF-One'/'RFBank'/'rfone.db'
c=sqlite3.connect(DB);c.execute('PRAGMA foreign_keys=ON')
def fingerprint(table):
 cols=[r[1] for r in c.execute('pragma table_info("'+table+'")')];names=','.join('"'+x+'"' for x in cols);h=hashlib.sha256();n=0
 for row in c.execute('select '+names+' from "'+table+'" order by '+names):h.update(repr(row).encode());h.update(b'\n');n+=1
 return dict(rows=n,sha256=h.hexdigest())
tables=[r[0] for r in c.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
c.execute('BEGIN IMMEDIATE');before={t:fingerprint(t) for t in tables}
assert before['financial_transaction_matches']['rows']==0,'Expected clean matches table'
existing={r[1] for r in c.execute('pragma table_info(financial_transaction_matches)')}
columns={'relationship':'VARCHAR(16)','posting_transaction_id':'INTEGER REFERENCES financial_transactions(id)','first_engine_run_id':'INTEGER REFERENCES bank_engine_runs(id)','last_engine_run_id':'INTEGER REFERENCES bank_engine_runs(id)'}
added=[]
for name,definition in columns.items():
 if name not in existing:
  c.execute('ALTER TABLE financial_transaction_matches ADD COLUMN "'+name+'" '+definition);added.append(name)
assert all(fingerprint(t)==v for t,v in before.items())
assert c.execute('pragma foreign_key_check').fetchall()==[]
assert c.execute('pragma integrity_check').fetchall()==[('ok',)]
c.commit();c.close()
r=dict(database=str(DB),cause='Filtered review loaded ORM columns absent from historical matches schema',added_nullable_columns=added,all_table_contents_unchanged=True,matches=0,integrity='ok',foreign_key_errors=[])
(ROOT/'filter-schema-verification.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r))
