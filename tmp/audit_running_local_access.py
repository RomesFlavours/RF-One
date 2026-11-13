from pathlib import Path
import urllib.request,urllib.error,json
result={}
for path in ('/','/admin/roles','/compensation','/projects','/bank','/admin/organization','/restaurant/wines','/selection','/tips/runs'):
 try:
  response=urllib.request.urlopen('http://127.0.0.1:5094'+path,timeout=40);result[path]=response.status
 except urllib.error.HTTPError as exc:result[path]=exc.code
Path('tmp/registry-local-running-server-audit.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
