from pathlib import Path
from datetime import datetime,timezone
import json,zipfile,hashlib,boto3
root=Path.cwd();old=json.loads((root/'tmp/registry-home-release/state.json').read_text());out=root/'tmp/registry-people-release';out.mkdir(exist_ok=True);s=boto3.Session(profile_name='rfone-dev-login',region_name='us-east-1');service=s.client('apprunner').describe_service(ServiceArn=old['service_arn'])['Service'];expected='418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web:'+old['tag'];assert service['SourceConfiguration']['ImageRepository']['ImageIdentifier']==expected,'AWS advanced; do not overwrite other releases'
previous=s.client('s3').get_object(Bucket='rfone-tips-deploy-418674484214',Key=old['source_s3_key'])['Body'].read();assert hashlib.sha256(previous).hexdigest()==old['source_sha256'];(out/'baseline-source.zip').write_bytes(previous)
changed=('RF-One Web/templates/role_profiles.html','RF-One Web/role_profile_routes.py')
with zipfile.ZipFile(out/'baseline-source.zip') as before,zipfile.ZipFile(out/'source.zip','w',zipfile.ZIP_DEFLATED) as after:
 for name in before.namelist():
  data=(root/'tmp/git-anagrafica-release/03 Software'/name).read_bytes().replace(b'\r\n',b'\n') if name in changed else before.read(name)
  after.writestr(name,data)
d={k:old[k] for k in ('service_arn','cluster','network','container','log_configuration')};d.update(tag='registry-people-'+datetime.now(timezone.utc).strftime('%Y%m%dt%H%M%Sz'),expected_previous_image=expected,source_sha256=hashlib.sha256((out/'source.zip').read_bytes()).hexdigest(),database_migration_required=False);(out/'state.json').write_text(json.dumps(d,indent=2))
for source,destination in [('build_registry_home_release.py','build_registry_people_release.py'),('deploy_registry_home.py','deploy_registry_people.py'),('check_registry_home_deploy.py','check_registry_people_deploy.py'),('copy_published_myrf_local.py','copy_registry_people_local.py')]:
 t=(root/'tmp'/source).read_text(encoding='utf-8-sig').replace('tmp/registry-home-release','tmp/registry-people-release');(root/'tmp'/destination).write_text(t,encoding='utf-8')
print('Packaged People-first navigation on the exact current AWS base')
