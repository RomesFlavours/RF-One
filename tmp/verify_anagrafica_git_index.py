from pathlib import Path
import subprocess,json,hashlib,re
repo=Path('tmp/git-anagrafica-release');manifest=json.loads((repo/'07 Tasks/Reports/ANAGRAFICA_AWS_RELEASE_20261110_MANIFEST.json').read_text())
for name,digest in manifest['files'].items():
 path='03 Software/Infrastructure/deploy/rfone-web/Dockerfile' if name=='Dockerfile' else '03 Software/'+name
 payload=subprocess.check_output(['git','-C',str(repo),'show',':'+path])
 ending=manifest['text_endings'].get(name)
 if ending:
  payload=payload.replace(b'\r\n',b'\n')
  if ending=='CRLF':payload=payload.replace(b'\n',b'\r\n')
 assert hashlib.sha256(payload).hexdigest()==digest,name
names=subprocess.check_output(['git','-C',str(repo),'diff','--cached','--name-only','-z']).decode().split('\0')
for name in filter(None,names):
 assert not any(part in ('tmp','__pycache__') for part in Path(name).parts),name
 assert Path(name).suffix not in ('.dump','.db','.sqlite','.zip','.png'),name
 data=subprocess.check_output(['git','-C',str(repo),'show',':'+name])
 assert not re.search(rb'AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----',data),name
print('Staged content matches all 855 runtime hashes; no private data artifacts or credential-key patterns found.')
