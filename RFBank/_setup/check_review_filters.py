"""Regression: exercise actual filtered HTTP requests against the local read-only module."""
import hashlib,http.cookiejar,json,os,pathlib,re,sqlite3,urllib.parse,urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1];DB=pathlib.Path(os.environ['LOCALAPPDATA'])/'RF-One'/'RFBank'/'rfone.db'
def digest():
 with DB.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
before=digest();c=sqlite3.connect(DB.as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
records={r['id']:dict(r) for r in c.execute('select id,posting_date,payment_instrument_id,description_original from financial_transactions')}
sample=next(r for r in records.values() if (r['posting_date'] or '').startswith('2026-'))
month=int(sample['posting_date'][5:7]);instrument=sample['payment_instrument_id']
op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
results=[]
def fetch(params,fragment=False):
 q=urllib.parse.urlencode(dict(view='to_reconcile',year=2026,**params));headers={'X-Bank-Review':'rows'} if fragment else {}
 response=op.open(urllib.request.Request('http://127.0.0.1:5111/bank/review?'+q,headers=headers));text=response.read().decode()
 if fragment:text=json.loads(text)['rows']
 ids=[int(x) for x in re.findall(r'<tr id="t-(\d+)"',text)];assert response.status==200
 results.append(dict(query=q,fragment=fragment,status=response.status,rows=len(ids)));return ids
ids=fetch({'month':'','payment_instrument_id':''});assert len(ids)==100
assert all(records[i]['posting_date'].startswith('2026-') for i in ids)
second=fetch({'page':2},fragment=True);assert second and not set(second)&set(ids)
ids=fetch({'month':month});assert ids and all(int(records[i]['posting_date'][5:7])==month for i in ids)
ids=fetch({'payment_instrument_id':instrument});assert ids and all(records[i]['payment_instrument_id']==instrument for i in ids)
ids=fetch({'month':month,'payment_instrument_id':instrument});assert ids
assert all(records[i]['payment_instrument_id']==instrument and int(records[i]['posting_date'][5:7])==month for i in ids)
ids=fetch({'q':'PAYPAL'});assert ids and all('PAYPAL' in (records[i]['description_original'] or '').upper() for i in ids)
assert fetch({'q':'RFBANK_NO_MATCH_57C308'})==[]
r=op.open('http://127.0.0.1:5111/bank/review?view=reconciled&year=2026');assert r.status==200
with_who_rows=len(re.findall(r'<tr id="t-(\d+)"',r.read().decode()))
results.append(dict(query='view=reconciled&year=2026',status=200,rows=with_who_rows))
assert digest()==before
assert c.execute('select count(*) from bank_transaction_explanations').fetchone()[0]==0
assert c.execute('select count(*) from bank_transaction_allocations').fetchone()[0]==0
report=dict(cases=results,database_hash_unchanged_during_requests=True,database_sha256=before,assignments=0,allocations=0,aws_accessed=False)
(ROOT/'review-filter-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))

