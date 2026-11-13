from pathlib import Path
from datetime import datetime,timezone
import zipfile,json,hashlib
root=Path.cwd();repo=root/'tmp/git-anagrafica-release';release=root/'tmp/registry-home-release';state=json.loads((release/'state.json').read_text());state['superseded_build']=state['build_id'];state['tag']='registry-home-'+datetime.now(timezone.utc).strftime('%Y%m%dt%H%M%Sz');state['expected_previous_image']='418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web:kitchen-home-e65f9b37dabb'
with zipfile.ZipFile(release/'current-kitchen-source.zip') as z:
 for name in ('RF-One Web/domain_registry.py','RF-One Web/templates/_how_works.html','RF-One Web/templates/help/myrf_home.html'):
  p=repo/'03 Software'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(name).replace(b'\r\n',b'\n'))
 home=z.read('RF-One Web/templates/home.html').decode().replace('\r\n','\n');home=home.replace('bank_available or clover_acquisition_available or employees_available','bank_available or clover_acquisition_available or can_manage_profiles').replace('{% if employees_available %}','{% if can_manage_profiles %}').replace("url_for('employee_directory_home')","url_for('role_profiles_home',tab='people')").replace('Anagrafica dipendenti <span','Registry <span').replace('Identità RF-One, sedi e collegamenti Clover.','People, roles, companies and system authorizations.');home='\n'.join(line for line in home.split('\n') if not ('home-row' in line and '<strong>Anagrafica</strong>' in line));(repo/'03 Software/RF-One Web/templates/home.html').write_text(home,encoding='utf-8')
 changed=['RF-One Web/templates/'+n for n in ('home.html','role_profiles.html','admin_accounts.html','employee_directory_detail.html')]
 with zipfile.ZipFile(release/'source.zip','w',zipfile.ZIP_DEFLATED) as out:
  for name in z.namelist():
   if name.endswith('/'):continue
   payload=(repo/'03 Software'/name).read_bytes() if name in changed else z.read(name)
   if Path(name).suffix in ('.py','.html','.js','.css','.json','.md','.txt','.ini','.yml'):payload=payload.replace(b'\r\n',b'\n')
   out.writestr(name,payload)
state['source_sha256']=hashlib.sha256((release/'source.zip').read_bytes()).hexdigest();(release/'state.json').write_text(json.dumps(state,indent=2));print('Registry integrated on current Kitchen home, preserving Kitchen and How Works')
