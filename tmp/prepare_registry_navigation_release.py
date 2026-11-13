from pathlib import Path
import json,boto3,shutil
out=Path('tmp/registry-navigation-release');artifact=out/'artifact';d=json.loads(Path('tmp/registry-performance-release/state.json').read_text());s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');service=s.client('apprunner').describe_service(ServiceArn=d['service_arn'])['Service'];assert service['Status']=='RUNNING';assert service['SourceConfiguration']['ImageRepository']['ImageIdentifier']==d['image'],'Live image changed';(out/'baseline-service.json').write_text(json.dumps(service,default=str,indent=2));(out/'baseline.json').write_text(json.dumps({'service_arn':d['service_arn'],'previous_image':d['image'],'previous_digest':d['image_digest']},indent=2))
# Apply only reviewed navigation transformations to the exact production files.
# This preserves unrelated local-versus-production differences in other sections.
source=Path('tmp/fix_registry_navigation.py').read_text(encoding='utf-8');start=source.index("(root/'registry_navigation.py').write_text");script="from pathlib import Path\nroot=Path('/app/RF-One Web')\n"+source[start:]
script += "\n"+Path('tmp/preserve_registry_drafts.py').read_text(encoding='utf-8').split("root=Path('tmp/git-anagrafica-release/03 Software/RF-One Web')",1)[1]
script += '''
import compileall
assert compileall.compile_file(str(root/'app.py'),quiet=1)
assert compileall.compile_file(str(root/'registry_navigation.py'),quiet=1)
assert compileall.compile_file(str(root/'role_profile_routes.py'),quiet=1)
from jinja2 import Environment
for name in ('admin_account_access','admin_account_form','admin_account_training_link','role_profiles'):
    text=(root/'templates'/(name+'.html')).read_text(encoding='utf-8')
    Environment().parse(text)
    if name.startswith('admin_account_'):assert "url_for('admin_accounts')" not in text
print('Registry navigation transformations and templates verified')
'''
nav=artifact/'navigation';nav.mkdir(exist_ok=True);(nav/'apply.py').write_text(script,encoding='utf-8',newline='\n')
# Syntax-check without executing against /app on the local host.
compile(script,'apply.py','exec')
for name in ('test_registry_navigation.py','test_role_company_http.py'):
 shutil.copyfile(Path('tmp/git-anagrafica-release/03 Software/RF-One Web/tests')/name,nav/name)
(artifact/'Dockerfile').write_text('FROM '+d['image'].rsplit(':',1)[0]+'@'+d['image_digest']+'\nRUN --mount=type=bind,source=navigation,target=/navigation,ro python /navigation/apply.py\nARG RFONE_RELEASE_REVISION\nLABEL org.opencontainers.image.revision=$RFONE_RELEASE_REVISION\n',encoding='utf-8',newline='\n')
(artifact/'RELEASE.md').write_text('''# Registry navigation repair

Build from the pinned currently deployed Registry performance image. The read-only build mount applies only navigation changes to inherited source files, preserving other published code and all runtime settings. No migration, credential operation, identity confirmation or permission change runs during build or deployment.

Save, cancel and account/training/password return paths resolve an explicitly validated canonical person. Legacy Accounts entry redirects to Registry. Returned pages reopen that person's editor. Errors retain the account/person context; invalid password fields are never reflected. Browser tests run locally against disposable fixture data. Build repeats HTTP navigation, 192 Registry workflow checks, performance/attribution and release policy checks in isolated SQLite fixtures. Production checks remain read-only.

Restore the previous image identifier to roll back; no database rollback is required. The navigation source transformer is intentionally applied to the inherited live files rather than copying an unrelated working tree.
''',encoding='utf-8')
print('Pinned baseline confirmed; navigation-only build prepared')
