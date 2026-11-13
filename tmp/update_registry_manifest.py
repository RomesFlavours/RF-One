from pathlib import Path
import json
base=Path(r'tmp/git-anagrafica-release/03 Software')
p=base/'RF-One Data Store/clover_connector_release.json';data=json.loads(p.read_text(encoding='utf-8'));modified=[]
import hashlib
for name in data['files']:
 current=hashlib.sha256((base/name).read_bytes()).hexdigest()
 if data['files'][name]!=current:data['files'][name]=current;modified.append(name)
p.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8',newline='\n')
print('Manifest hashes updated:',modified)
