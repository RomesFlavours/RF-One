from pathlib import Path
import json,zipfile,hashlib
root=Path.cwd();repo=root/'tmp/git-anagrafica-release';release=root/'tmp/registry-contacts-release';d=json.loads((release/'state.json').read_text());changed=['RF-One Data Store/'+n for n in ('clover_connector_release.json','rfone_data_store/models.py','rfone_data_store/access_profiles.py')]+['RF-One Web/'+n for n in ('role_profile_routes.py','templates/home.html','templates/role_profiles.html','static/js/role-profiles.js','static/css/role-profiles.css')];migration='RF-One Data Store/migrations/versions/f3b120261110_registry_contacts.py'
with zipfile.ZipFile(release/'baseline-source.zip') as previous,zipfile.ZipFile(release/'source.zip','w',zipfile.ZIP_DEFLATED) as new:
 for name in previous.namelist():
  content=(repo/'03 Software'/name).read_bytes().replace(b'\r\n',b'\n') if name in changed else previous.read(name);new.writestr(name,content)
 new.writestr(migration,(repo/'03 Software'/migration).read_bytes().replace(b'\r\n',b'\n'))
 for extra in ('RF-One Data Store/migrations/versions/k9a020261110_publish_kitchen_aws.py','RF-One Data Store/rfone_data_store/kitchen.py','RF-One Data Store/rfone_data_store/kitchen_configuration.py'):
  if extra not in previous.namelist():new.writestr(extra,(repo/'03 Software'/extra).read_bytes())
with zipfile.ZipFile(release/'source.zip') as z:
 m=json.loads(z.read('RF-One Data Store/clover_connector_release.json'));assert all(hashlib.sha256(z.read(p)).hexdigest()==h for p,h in m['files'].items())
d['source_sha256']=hashlib.sha256((release/'source.zip').read_bytes()).hexdigest();(release/'state.json').write_text(json.dumps(d,indent=2))
for src,dst in [('build_registry_people_release.py','build_registry_contacts_release.py'),('check_registry_people_deploy.py','check_registry_contacts_deploy.py'),('copy_registry_people_local.py','copy_registry_contacts_local.py')]:
 t=(root/'tmp'/src).read_text(encoding='utf-8-sig').replace('tmp/registry-people-release','tmp/registry-contacts-release');(root/'tmp'/dst).write_text(t,encoding='utf-8')
print('Contacts package prepared and guard hashes verified')
