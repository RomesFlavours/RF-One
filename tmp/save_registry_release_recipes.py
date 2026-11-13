from pathlib import Path
import zipfile,hashlib,json,difflib
root=Path('tmp/registry-access-release');repo=Path('tmp/git-anagrafica-release');target=repo/'03 Software/Infrastructure/deploy/registry-authorization';(target/'patches').mkdir(parents=True,exist_ok=True)
info=json.loads((root/'sources.json').read_text());inventory=json.loads((root/'inventory.json').read_text());manifest={'schema_revision':'t9a120261110','services':{}}
for service in ('web','tips','selection','training','kitchen'):
 folder=root/(service+'-source')
 with zipfile.ZipFile(root/(service+'-baseline.zip')) as z:before={n:z.read(n) for n in z.namelist() if not n.endswith('/')}
 def relevant(n):return '__pycache__' not in n.split('/') and not n.endswith(('.pyc','.db','.sqlite','.dump')) and Path(n).name!='.env'
 after={p.relative_to(folder).as_posix():p.read_bytes() for p in folder.rglob('*') if p.is_file() and relevant(p.relative_to(folder).as_posix())}
 patches=[];changes={}
 for name in sorted(set(before)|set(after)):
  if not relevant(name):continue
  old,new=before.get(name),after.get(name)
  if old==new:continue
  if new is not None:
   new=new.decode('utf-8').replace('\r\n','\n').encode('utf-8');(folder/name).write_bytes(new)
  oldlines=old.decode('utf-8').splitlines() if old is not None else [];newlines=new.decode('utf-8').splitlines() if new is not None else []
  changes[name]={'before':hashlib.sha256(old).hexdigest() if old is not None else None,'after':hashlib.sha256(new).hexdigest() if new is not None else None,'newline':bool(new and new.endswith(b'\n'))}
  patches+=list(difflib.unified_diff(oldlines,newlines,fromfile='a/'+name,tofile='b/'+name,lineterm=''))
 p=target/'patches'/(service+'.patch');p.write_text('\n'.join(patches)+'\n',encoding='utf-8',newline='\n')
 name='rfone-'+service;item=next(v for v in inventory['services'] if v['name']==name)
 manifest['services'][service]={'baseline':info[service],'previous_image':item['image'],'service_arn':item['arn'],'patch_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'changes':changes,'checks':json.loads((root/(service+'-test.json')).read_text())}
 print(service,len(changes),'patch bytes',p.stat().st_size)
(target/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8',newline='\n');(root/'final-manifest.json').write_text(json.dumps(manifest,indent=2))

