from pathlib import Path
import json,shutil
root=Path('tmp/registry-access-release');repo=Path('tmp/git-anagrafica-release');state=json.loads((root/'release-state.json').read_text())
# Remove only disposable databases created by the completed acceptance suite.
for p in repo.glob('role-company-http-*'):
 if p.is_dir():
  assert p.resolve().parent==repo.resolve() and not p.is_symlink();shutil.rmtree(p)
# Prepare a final report only after every required verification is recorded.
if not state.get('anthony_update_verified'):
 print('Release report waiting for the Anthony transaction verification.')
 raise SystemExit(0)
assert all(v['deploy_status']=='SUCCEEDED' and v['service_status']=='RUNNING' for v in state['services'].values())
assert state['cloudfront_invalidation_status']=='Completed'
http=json.loads((root/'http-checks.json').read_text());assert all(v['passed'] for v in http)
receipt={'source_commit':state['commit'],'schema_revision':state['schema_revision'],'migrations_executed':False,'services':{name:{k:item[k] for k in ('image','image_digest','build_id','source_sha256','deploy_operation','deploy_status','service_status','previous_image')} for name,item in state['services'].items()},'people':64,'dismissed':47,'anthony':{'effective_permissions':['KITCHEN'],'identities_merged':False},'public_http_checks':http,'cloudfront_invalidation':state['cloudfront_invalidation'],'cloudfront_invalidation_status':'Completed','local_switch_user_deployed':False}
reports=repo/'07 Tasks/Reports';(reports/'REGISTRY_AUTHORIZATION_AWS_20261110_RELEASE.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8',newline='\n')
rows='\n'.join('| '+name+' | '+item['tag']+' | SUCCEEDED / RUNNING |' for name,item in state['services'].items())
report='''# REPORT — Registry authorization AWS release, 2026-11-10

## 1. Published result

All five production services now use the shared Registry effective authorization
policy: RF1 Web (including the shell modules), Tips, Selection, Training and Kitchen.
Source commit: `'''+state['commit']+'''` on `codex/registry-access-local`.

| Service | New image tag | Deployment |
| --- | --- | --- |
'''+rows+'''

The source of each current service was recovered and hash-pinned before patching,
so newer Tips rules, Selection workspace/candidate bridge and Training course/
first-password functionality were retained. Reproducible overlays, source/file
hashes and packaging guards are committed under
`03 Software/Infrastructure/deploy/registry-authorization`.
The original worktree's unpublished employee lifecycle changes remain separate.

## 2. Verification and data

- All five builds succeeded, including actual service authorization tests inside
  the Linux images before push: grant, revocation in an existing session, company
  separation, Training downgrade and the preserved Selection workspace/bridge.
- Canonical Registry HTTP acceptance: 192 checks passed. The earlier local policy,
  standalone component and Training regression checks remain recorded in the local
  report. Five overlays were independently reproduced with all hashes verified.
- New Web image read the AWS schema and all account/company permissions in a
  read-only ECS transaction: schema `t9a120261110`, 64 people, 47 dismissed.
- All five App Runner deployment operations succeeded and services are RUNNING.
  Image digests and previous images are recorded in the release receipt.
- Nine public HTTP checks passed: production login is required for internal
  Registry, Kitchen, Training, Tips and Selection pages; login renders normally;
  Training/Kitchen health report the release commit; Selection bridge version
  `rmaed-selection-bridge-3` remains available.
- CloudFront cache invalidation completed. Runtime secrets, roles, network and
  routing were preserved; only the image and release revision were updated.

No database migration was run. Sources include the already-applied Training
ancestor/schema definitions for compatibility. No Clover writes, person merges,
account reactivation, credential edits or production authentication bypass occurred.

## 3. Anthony

The Product Owner's locally verified correction was applied to the active login
`anthony`: KITCHEN is its only effective permission. The previous nine direct
legacy grants were disabled atomically, preserving their metadata and recording
the previous values in a Registry audit event. Preconditions checked that the
account remained active, nonadmin/nonowner, unlinked and without new company
assignments, so a concurrent identity/permission change would prevent overwrite.
The separate Anthony Watler person/inactive account was not merged or modified.
Other account grants were not changed.

## 4. Local versus production

Switch user remains a local-only administrator tool. The private launcher,
its cookies and authentication shortcut are excluded from every production
package; normal RF1 authentication remains in place on AWS. The original local
source/dump and the pending lifecycle worktree are preserved.

Registry: https://rfone.romesflavours.com/admin/roles?tab=people

## 5. Recovery and build provenance

Each service's previous image/configuration is retained. Revert only the target
image if necessary; no schema downgrade is needed. The release receipt records
all image digests and operation IDs. Source archives are SHA-256 pinned. Selection's
build role only allowed its existing S3 source key: an immutable backup was made
and checked before replacing that source object. No IAM policy or release guard
was weakened. A source-download failure was retried through the authorized path.

Git publication follows the completed deployment and is recorded in the final
chat handoff; no force push or merge into unrelated work is required.
'''
(reports/'REGISTRY_AUTHORIZATION_AWS_20261110_REPORT.md').write_text(report,encoding='utf-8',newline='\n')
p=repo/'PROJECT_STATE.md';text=p.read_text(encoding='utf-8');marker='# PROJECT_STATE\n';entry='''
## Registry authorization — published 2026-11-10

RF1 Web, Tips, Selection, Training and Kitchen now enforce the shared Registry
policy per request and company, including role revocation and Training downgrade.
All five AWS deployments and image guards succeeded. Shared schema remains
`t9a120261110`; no migrations were executed. AWS retains 64 people and 47 dismissals.
The active login anthony now has KITCHEN-only access, without merging identities.
Switch user remains local-only and RF1-administrator-only. See
`07 Tasks/Reports/REGISTRY_AUTHORIZATION_AWS_20261110_REPORT.md` and its release receipt.
''';p.write_text(text.replace(marker,marker+entry,1),encoding='utf-8',newline='\n')
p=repo/'10 System/Identity & Access/Role Profiles and Company Access.md';text=p.read_text(encoding='utf-8');text=text.replace('This change is local only, pending Product Owner acceptance before AWS publishing.','Published to the five AWS services after Product Owner local acceptance on 2026-11-10. See `07 Tasks/Reports/REGISTRY_AUTHORIZATION_AWS_20261110_REPORT.md`.');p.write_text(text,encoding='utf-8',newline='\n')
print('Final AWS report and immutable release receipt written.')
