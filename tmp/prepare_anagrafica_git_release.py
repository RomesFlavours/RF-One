from pathlib import Path
import zipfile,json,shutil,hashlib
root=Path.cwd();target=root/'tmp/git-anagrafica-release';release=root/'tmp/anagrafica-release';state=json.loads((release/'state.json').read_text());hashes={}
with zipfile.ZipFile(release/'source.zip') as z:
 for name in z.namelist():
  if name=='Dockerfile':destination=target/'03 Software/Infrastructure/deploy/rfone-web/Dockerfile'
  else:destination=target/'03 Software'/name
  assert destination.resolve().is_relative_to(target.resolve())
  destination.parent.mkdir(parents=True,exist_ok=True);payload=z.read(name);destination.write_bytes(payload);hashes[name]=hashlib.sha256(payload).hexdigest()
unit=(root/'tmp/test_role_company_profiles.py').read_text(encoding='utf-8-sig').replace("ROOT=Path(__file__).resolve().parent/'role-company-development'","ROOT=Path(__file__).resolve().parents[1]")
(target/'03 Software/RF-One Data Store/test_role_company_profiles.py').write_text(unit,encoding='utf-8')
http=(root/'tmp/test_role_company_http.py').read_text(encoding='utf-8-sig').replace("ROOT=Path(__file__).resolve().parent/'role-company-development'","ROOT=Path(__file__).resolve().parents[2]")
(target/'03 Software/RF-One Web/tests/test_role_company_http.py').write_text(http,encoding='utf-8')
for rel in ('10 System/Identity & Access/Role Profiles and Company Access.md','07 Tasks/Reports/ANAGRAFICA_AWS_RELEASE_20261110_REPORT.md','07 Tasks/Reports/CLOVER_47_AWS_DISMISSALS_20261110_REPORT.md'):
 destination=target/rel;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/rel,destination)
r=target/'07 Tasks/Reports/ANAGRAFICA_AWS_RELEASE_20261110_REPORT.md';text=r.read_text(encoding='utf-8');text+='''\n## 5. Final deployment outcome\n\nApp Runner operation SUCCEEDED; service RUNNING. The public login remained available and protected routes redirected anonymous clients to login. Authenticated production browser verification was not completed: automatic approval review rejected constructing a signed session from the AWS secret, and computer use could not confidently establish the current Edge URL. That rejected smoke test was not executed. No authentication bypass was deployed.\n\nAfter the code release, the Product Owner separately authorized application of the exact 47 local dismissals to AWS. The internal ECS operation re-read Clover, committed all 47 and retained all 64 employee records. See CLOVER_47_AWS_DISMISSALS_20261110_REPORT.md. Raw employee IDs, database snapshots, runtime secrets and screenshots are deliberately not included in this Git release.\n''';r.write_text(text,encoding='utf-8')
r=target/'07 Tasks/Reports/CLOVER_47_AWS_DISMISSALS_20261110_REPORT.md';text=r.read_text(encoding='utf-8').replace('Machine-readable result: CLOVER_47_AWS_DISMISSALS_20261110_RESULT.json.','Machine-readable employee result remains in the authorized private workspace, excluded from Git.').replace('Detailed task output: tmp/anagrafica-release/dismissals_task.log.','Detailed task output remains in the private workspace and AWS CloudWatch.').replace('Source implementation: tmp/anagrafica-release/apply_47_inside_aws.py.','Source operation remains in the private release workspace.');r.write_text(text,encoding='utf-8')
manifest={'release':state['tag'],'image_digest':state['image_digest'],'source_zip_sha256':state['source_sha256'],'schema_revision':'f2a120261110','deployment_operation':state['deploy_operation'],'deployment_status':'SUCCEEDED','files':hashes,'excluded_from_git':['database dumps','credentials','employee exports','screenshots','local authentication wrapper']}
(target/'07 Tasks/Reports/ANAGRAFICA_AWS_RELEASE_20261110_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print('Packaged production source and portable tests; sensitive/local-only artifacts excluded')
