from pathlib import Path
import zipfile,json,subprocess,hashlib
root=Path('tmp/registry-access-release');commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd='tmp/git-anagrafica-release',text=True).strip();state=json.loads((root/'release-state.json').read_text());state['commit']=commit
for service,item in state['services'].items():
 path=root/(service+'-release.zip');temp=root/(service+'-commit.zip')
 with zipfile.ZipFile(path) as original,zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as target:
  for name in original.namelist():target.writestr(name,(commit+'\n').encode() if name=='RELEASE_COMMIT' else original.read(name))
 temp.replace(path);(root/(service+'-reproduced')/'RELEASE_COMMIT').write_text(commit+'\n');item['source_sha256']=hashlib.sha256(path.read_bytes()).hexdigest();item['source_bytes']=path.stat().st_size
 if service=='selection':item['tag']='sel-'+commit[:12];item['image']=item['image'].rsplit(':',1)[0]+':'+item['tag']
(root/'release-state.json').write_text(json.dumps(state,indent=2));print('Packages stamped with verified release commit',commit)
