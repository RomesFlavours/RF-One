from pathlib import Path
from datetime import datetime,timezone
import zipfile,json,hashlib
root=Path.cwd();out=root/'tmp/registry-home-release';out.mkdir(exist_ok=True);previous=json.loads((root/'tmp/anagrafica-release/state.json').read_text());tag='registry-home-'+datetime.now(timezone.utc).strftime('%Y%m%dt%H%M%Sz')
changed=['RF-One Web/templates/'+name for name in ('home.html','role_profiles.html','admin_accounts.html','employee_directory_detail.html')]
with zipfile.ZipFile(root/'tmp/anagrafica-release/source.zip') as old,zipfile.ZipFile(out/'source.zip','w',zipfile.ZIP_DEFLATED) as new:
 for name in old.namelist():
  payload=(root/'tmp/git-anagrafica-release/03 Software'/name).read_bytes().replace(b'\r\n',b'\n') if name in changed else old.read(name)
  new.writestr(name,payload)
d={k:previous[k] for k in ('service_arn','cluster','network','container','log_configuration')};d.update(tag=tag,expected_previous_image='418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web:'+previous['tag'],source_sha256=hashlib.sha256((out/'source.zip').read_bytes()).hexdigest(),database_migration_required=False);(out/'state.json').write_text(json.dumps(d,indent=2))
script=(root/'tmp/build_anagrafica_release.py').read_text(encoding='utf-8-sig').replace('tmp/anagrafica-release','tmp/registry-home-release');(root/'tmp/build_registry_home_release.py').write_text(script,encoding='utf-8')
