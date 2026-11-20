import json,pathlib,sqlite3,hashlib,os
ROOT=pathlib.Path(__file__).resolve().parents[1]
items=json.loads((ROOT/'inventory.json').read_text())
ok=[r for r in items if r.get('status')=='OK' and r.get('counts',{}).get('financial_transactions',0) and all(r['counts'].get(t,0)>0 for t in ('bank_occurrences','bank_transaction_reasons','bank_accounting_classifications'))]
r=max(ok,key=lambda r:(r['counts']['financial_transactions'],r['counts']['bank_transaction_reasons'],r['counts']['bank_occurrences'],r['path']))
src=pathlib.Path(r['path']);dest=pathlib.Path(os.environ['LOCALAPPDATA'])/'RF-One'/'RFBank'/'rfone.db'
assert not dest.exists(), 'Destination already exists; refusing overwrite'
dest.parent.mkdir(parents=True,exist_ok=True)
s=sqlite3.connect(src.as_uri()+'?mode=ro',uri=True);s.execute('BEGIN')
d=sqlite3.connect(dest);s.backup(d);print('COPY COMPLETE',flush=True)
tables=[x[0] for x in d.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
def cols(t):return [x[1] for x in d.execute('pragma table_info("'+t+'")')]
def digest(c,t,exclude=()):
 columns=[x[1] for x in c.execute('pragma table_info("'+t+'")') if x[1] not in exclude]
 names=','.join('"'+x+'"' for x in columns)
 h=hashlib.sha256();n=0
 for row in c.execute('select '+names+' from "'+t+'" order by '+names):
  h.update(repr(row).encode('utf-8'));h.update(b'\n');n+=1
 return {'rows':n,'sha256':h.hexdigest()}
before={t:digest(d,t) for t in tables}
clear=set(['bank_transaction_explanations','bank_transaction_allocations','financial_transaction_matches','bank_invoice_matches','bank_evidence_bypass_authorizations','bank_who_recognitions','bank_who_identifications','bank_import_reconciliations','bank_flow_artifacts','bank_ai_rule_application_items','bank_ai_rule_applications','bank_ai_rule_preview_items','bank_ai_rule_previews','bank_ai_rule_batch_results','bank_ai_test_results','bank_ai_test_runs']) & set(tables)
updates={'explanation_id':None,'classification':'UNKNOWN','review_status':'REQUIRES_REVIEW','duplicate_status':'NONE','duplicate_of_transaction_id':None,'accounting_status':'CANONICAL','accounting_canonical_transaction_id':None,'accounting_dedup_reason':None}
updates={k:v for k,v in updates.items() if k in cols('financial_transactions')}
source_tx=digest(s,'financial_transactions',updates)
source_fk=list(s.execute('pragma foreign_key_check'))
assert not source_fk, 'Source has foreign key violations'
d.execute('pragma foreign_keys=OFF');d.execute('BEGIN IMMEDIATE')
d.execute('update financial_transactions set '+','.join('"'+k+'"=?' for k in updates),list(updates.values()))
for t in clear:d.execute('delete from "'+t+'"')
# Period validation is a reconciliation result; retain configuration and source coverage.
extra={}
if 'bank_reconciliation_control_configs' in tables and 'validated_through_month' in cols('bank_reconciliation_control_configs'):
 d.execute('update bank_reconciliation_control_configs set validated_through_month=NULL');extra['bank_reconciliation_control_configs']=['validated_through_month']
if 'bank_monthly_source_periods' in tables:
 d.execute('update bank_monthly_source_periods set status=?,completed_at=NULL,completed_by_account_id=NULL,audit_log=NULL', ('OPEN',))
 extra['bank_monthly_source_periods']=['status','completed_at','completed_by_account_id','audit_log']
assert not list(d.execute('pragma foreign_key_check')), 'Foreign key violations after reset'
assert digest(d,'financial_transactions',updates)==source_tx,'Original transaction fields changed'
verified={}
for t in tables:
 if t in clear:assert d.execute('select count(*) from "'+t+'"').fetchone()[0]==0
 elif t=='financial_transactions':continue
 elif t in extra:assert digest(d,t,extra[t])==digest(s,t,extra[t])
 else:assert digest(d,t)==before[t], 'Unexpected table change '+t
for k,v in updates.items():
 assert d.execute('select count(*) from financial_transactions where "'+k+'" IS NOT ?', (v,)).fetchone()[0]==0
assert d.execute('pragma integrity_check').fetchall()==[('ok',)]
d.commit();d.execute('pragma foreign_keys=ON');d.close();s.rollback();s.close()
check=sqlite3.connect(dest.as_uri()+'?mode=ro',uri=True)
assert check.execute('pragma integrity_check').fetchall()==[('ok',)]
assert not list(check.execute('pragma foreign_key_check'))
report={'source':str(src),'destination':str(dest),'selected_counts':r['counts'],'candidates':len(items),'unreadable':[x['path'] for x in items if x['status']!='OK'],'cleared_tables':{t:before[t]['rows'] for t in sorted(clear)},'transaction_reset':updates,'preserved_catalogs':{t:before[t] for t in tables if t in ('bank_occurrences','bank_transaction_reasons','bank_accounting_classifications')},'all_other_tables_verified_unchanged':True,'original_transaction_fields_verified_unchanged':True,'integrity_check':'ok','foreign_key_check':[],'database_sha256':hashlib.file_digest(dest.open('rb'),'sha256').hexdigest(),'code_transferred':False,'aws_accessed':False}
(ROOT/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
(ROOT/'local-database.json').write_text(json.dumps({'name':'RFBank','database':str(dest),'database_url':'sqlite:///'+dest.as_posix()},indent=2),encoding='utf-8')
print(json.dumps(report,indent=2),flush=True)


