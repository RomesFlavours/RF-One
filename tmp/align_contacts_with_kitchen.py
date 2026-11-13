from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,shutil
root=Path.cwd();repo=root/'tmp/git-anagrafica-release';store=repo/'03 Software/RF-One Data Store';frozen=Path('C:/Users/servi/OneDrive/AI-RF-ONE/RF One/output/kitchen-release/source/03 Software/RF-One Data Store')
for name in ('migrations/versions/k9a020261110_publish_kitchen_aws.py','rfone_data_store/kitchen.py','rfone_data_store/kitchen_configuration.py'):
 p=store/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((frozen/name).read_bytes().replace(b'\r\n',b'\n'))
p=store/'migrations/versions/f3b120261110_registry_contacts.py';t=p.read_text(encoding='utf-8').replace("down_revision='f2a120261110'","down_revision='k9a020261110'");p.write_text(t,encoding='utf-8')
p=store/'clover_connector_release.json';m=json.loads(p.read_text())
for name in ('migrations/versions/f3b120261110_registry_contacts.py','migrations/versions/k9a020261110_publish_kitchen_aws.py','rfone_data_store/kitchen.py','rfone_data_store/kitchen_configuration.py'):m['files']['RF-One Data Store/'+name]=''
for name in m['files']:
 f=repo/'03 Software'/name;content=f.read_bytes().replace(b'\r\n',b'\n');f.write_bytes(content);m['files'][name]=hashlib.sha256(content).hexdigest()
p.write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
p=root/'tmp/registry-contacts-release/state.json';d=json.loads(p.read_text());d['superseded_builds']=[d['build_id']];d['tag']='registry-contacts-'+datetime.now(timezone.utc).strftime('%Y%m%dt%H%M%Sz');d['expected_database_revision']='k9a020261110';p.write_text(json.dumps(d,indent=2))
p=root/'tmp/package_registry_contacts.py';t=p.read_text(encoding='utf-8');t=t.replace("new.writestr(migration,(repo/'03 Software'/migration).read_bytes().replace(b'\\r\\n',b'\\n'))", """new.writestr(migration,(repo/'03 Software'/migration).read_bytes().replace(b'\\r\\n',b'\\n'))
 for extra in ('RF-One Data Store/migrations/versions/k9a020261110_publish_kitchen_aws.py','RF-One Data Store/rfone_data_store/kitchen.py','RF-One Data Store/rfone_data_store/kitchen_configuration.py'):
  if extra not in previous.namelist():new.writestr(extra,(repo/'03 Software'/extra).read_bytes())""");p.write_text(t,encoding='utf-8')
p=root/'tmp/migrate_registry_contacts_aws.py';t=p.read_text(encoding='utf-8').replace("=='f2a120261110'","=='k9a020261110'");p.write_text(t,encoding='utf-8')
print('Registry migration aligned after the already-applied Kitchen revision')
