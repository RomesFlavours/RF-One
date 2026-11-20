import pathlib,sqlite3,json,threading,time,os,subprocess
root=pathlib.Path(r'C:\Users\servi\OneDrive\AI-RF-ONE')
out=root/'RFBank'/'inventory.json'
paths=subprocess.check_output(['rg','--files','--hidden','-g','*.db','-g','!**/.git/**','-g','!**/node_modules/**',str(root)],text=True).splitlines()
results={}; lock=threading.Lock()
def check(s):
 p=pathlib.Path(s);r={'path':s,'status':'READING'}
 with lock:results[s]=r
 try:
  with p.open('rb') as f: assert f.read(16)==b'SQLite format 3\x00'
  c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)
  ts=[x[0] for x in c.execute("select name from sqlite_master where type='table'")]
  r['counts']={t:c.execute('select count(*) from "'+t+'"').fetchone()[0] for t in ts if t in ('financial_transactions','bank_occurrences','bank_transaction_reasons','bank_accounting_classifications')};c.close();r['status']='OK'
 except Exception as e:r.update(status='ERROR',error=str(e))
 with lock:
  out.write_text(json.dumps(list(results.values()),indent=2),encoding='utf-8')
  print(json.dumps(r),flush=True)
for s in paths:
 p=pathlib.Path(s)
 if 'BankMerge' in p.parts or p.name=='rfone.db':threading.Thread(target=check,args=(s,),daemon=True).start()
for i in range(180):
 time.sleep(1)
 with lock:
  if all(r['status']!='READING' for r in results.values()):break
with lock:out.write_text(json.dumps(list(results.values()),indent=2),encoding='utf-8')
os._exit(0)
