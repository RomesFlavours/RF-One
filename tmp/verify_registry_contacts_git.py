from pathlib import Path
import subprocess,zipfile,re
repo=Path('tmp/git-anagrafica-release');paths=subprocess.check_output(['git','-C',str(repo),'diff','--cached','--name-only','-z']).decode().split('\0');paths=[p for p in paths if p];raw=subprocess.check_output(['git','-C',str(repo),'cat-file','--batch'],input=''.join(':'+p+'\n' for p in paths).encode());pos=0;staged={}
for path in paths:
 end=raw.index(b'\n',pos);size=int(raw[pos:end].split()[2]);start=end+1;data=raw[start:start+size];pos=start+size+1;staged[path]=data
 assert Path(path).suffix not in ('.dump','.db','.zip','.png','.sqlite'),path
 assert not re.search(rb'AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----',data),path
with zipfile.ZipFile('tmp/registry-contacts-release/source.zip') as z:
 for path,data in staged.items():
  if path.startswith('03 Software/') and '/tests/' not in path and not path.endswith('migrations/aws_applied_revision.json') and path[12:] in z.namelist():
   assert data.replace(b'\r\n',b'\n')==z.read(path[12:]).replace(b'\r\n',b'\n'),path
print('Staged runtime changes match deployed source; no private data artifacts or credential-key patterns.')
