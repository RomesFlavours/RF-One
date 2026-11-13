import requests,time,json,sys
from pathlib import Path
s=requests.Session();s.trust_env=False;out={}
for tab in ('people','roles','areas','companies'):
 start=time.perf_counter();r=s.get('http://127.0.0.1:5094/admin/roles',params={'tab':tab},timeout=90);elapsed=time.perf_counter()-start
 assert r.status_code==200 and 'People (' in r.text if tab=='people' else r.status_code==200
 out[tab]={'seconds':round(elapsed,4),'status':r.status_code,'bytes':len(r.content)}
p=Path('tmp/registry-performance')/('local-'+sys.argv[1]+'.json');p.write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
