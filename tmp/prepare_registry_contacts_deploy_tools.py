from pathlib import Path
root=Path('tmp')
for src,dst in [('check_anagrafica_task.py','check_registry_contacts_task.py'),('deploy_registry_people.py','deploy_registry_contacts_web.py')]:
 t=(root/src).read_text(encoding='utf-8-sig').replace('tmp/anagrafica-release','tmp/registry-contacts-release').replace('tmp/registry-people-release','tmp/registry-contacts-release')
 if dst=='deploy_registry_contacts_web.py':t=t.replace("if b['buildStatus']=='SUCCEEDED':", "if b['buildStatus']=='SUCCEEDED':\n assert 'REGISTRY_CONTACTS_MIGRATION_VERIFIED' in (root/'migration_task.log').read_text(encoding='utf-8')")
 (root/dst).write_text(t,encoding='utf-8')
