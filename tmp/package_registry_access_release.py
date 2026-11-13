from pathlib import Path
import hashlib,json,zipfile,subprocess,shutil
from datetime import datetime,timezone
root=Path.cwd();out=root/'tmp/registry-access-release';repo=root/'tmp/git-anagrafica-release';commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip();manifest=json.loads((out/'final-manifest.json').read_text());stamp=datetime.now(timezone.utc).strftime('%Y%m%dt%H%M%Sz');state={'commit':commit,'schema_revision':'t9a120261110','services':{}}
for service,entry in manifest['services'].items():
 folder=out/(service+'-reproduced');(folder/'RELEASE_COMMIT').write_text(commit+'\n',encoding='utf-8',newline='\n');shutil.copyfile(repo/'03 Software/Infrastructure/deploy/registry-authorization/test_service.py',folder/'release_policy_test.py')
 p=folder/'Dockerfile';text=p.read_text(encoding='utf-8');text+='\nCOPY release_policy_test.py /app/release_policy_test.py\nRUN python "/app/RF-One Data Store/check_migration_chain.py" --aws-revision t9a120261110\nRUN python /app/release_policy_test.py '+service+' /app\n';p.write_text(text,encoding='utf-8',newline='\n')
 zip_path=out/(service+'-release.zip')
 with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
  for file in folder.rglob('*'):
   if not file.is_file() or '__pycache__' in file.parts or file.suffix in ('.pyc','.db','.sqlite','.dump') or file.name=='.env':continue
   assert file.name!='launch_local.py'
   if file.suffix in ('.py','.js','.html'):
    assert b'rfone_local_user_choice' not in file.read_bytes() and b'/local/access-user' not in file.read_bytes(),file
   z.write(file,file.relative_to(folder).as_posix())
 repo_uri=entry['previous_image'].rsplit(':',1)[0];tag='sel-'+commit[:12] if service=='selection' else 'registry-access-'+service+'-'+stamp
 state['services'][service]={'previous_image':entry['previous_image'],'service_arn':entry['service_arn'],'project':'rfone-selection-build' if service=='selection' else 'rfone-tips-build' if service=='tips' else 'rfone-web-build','image':repo_uri+':'+tag,'tag':tag,'source_s3_key':'releases/registry-access-'+stamp+'/'+service+'.zip','source_sha256':hashlib.sha256(zip_path.read_bytes()).hexdigest(),'source_bytes':zip_path.stat().st_size}
(out/'release-state.json').write_text(json.dumps(state,indent=2));print(json.dumps({'commit':commit,'packages':{k:v['source_bytes'] for k,v in state['services'].items()}}))
