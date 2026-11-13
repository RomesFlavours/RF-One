from pathlib import Path
import subprocess,json,hashlib,re
repo=Path('tmp/git-anagrafica-release');m=json.loads((repo/'07 Tasks/Reports/ANAGRAFICA_AWS_RELEASE_20261110_MANIFEST.json').read_text());paths={name:('03 Software/Infrastructure/deploy/rfone-web/Dockerfile' if name=='Dockerfile' else '03 Software/'+name) for name in m['files']}
names=subprocess.check_output(['git','-C',str(repo),'diff','--cached','--name-only','-z']).decode().split('\0');all_paths=list(dict.fromkeys(list(paths.values())+[n for n in names if n]));raw=subprocess.check_output(['git','-C',str(repo),'cat-file','--batch'],input=''.join(':'+p+'\n' for p in all_paths).encode());position=0;objects={}
for path in all_paths:
 end=raw.index(b'\n',position);header=raw[position:end].split();assert header[1]==b'blob';size=int(header[2]);start=end+1;objects[path]=raw[start:start+size];position=start+size+1
for name,digest in m['files'].items():
 data=objects[paths[name]];ending=m['text_endings'].get(name)
 if ending:
  data=data.replace(b'\r\n',b'\n')
  if ending=='CRLF':data=data.replace(b'\n',b'\r\n')
 assert hashlib.sha256(data).hexdigest()==digest,name
for path in filter(None,names):
 assert Path(path).suffix not in ('.db','.dump','.zip','.png','.sqlite'),path
 assert not re.search(rb'AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----',objects[path]),path
print('VERIFIED: all 855 staged runtime files match AWS artifact; no private data artifacts/key patterns.')
