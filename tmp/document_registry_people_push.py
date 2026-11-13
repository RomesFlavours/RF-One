from pathlib import Path
import json
root=Path.cwd();repo=root/'tmp/git-anagrafica-release';release=json.loads((root/'tmp/registry-people-release/state.json').read_text());metadata={k:release[k] for k in ('tag','image_digest','source_sha256','build_id','source_s3_key','deploy_operation','expected_previous_image')};metadata.update(deployment_status='SUCCEEDED',schema_changed=False,registry_http_checks=66,myrf_home_checks=36,normal_production_authentication=True,local_login_required=False)
(repo/'07 Tasks/Reports/REGISTRY_MYRF_PEOPLE_FIRST_20261110_RELEASE.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
report=f'''# REPORT — Registry People-first and MyRF Git consolidation

## 1. Behavior

People & assignments is the first Registry tab, followed by Roles, Areas and Companies. Both an omitted tab and an unknown tab open People. Explicit links to the other tabs remain valid.

This commit also records the previously published MyRF changes: one Registry entry in Administration, no duplicate in Settings, Registry page/breadcrumb labels, and the preserved concurrent Kitchen Home registration and How Works content. The original checkout's pending employee-lifecycle implementation is not overwritten or implicitly merged.

## 2. Release and local copy

AWS App Runner release {release['tag']} completed successfully (operation {release['deploy_operation']}). Image digest: {release['image_digest']}. No schema, employee data, permission or login-policy changes were needed.

The local copy is updated from the exact AWS source ZIP after successful deployment, with SHA-256 and per-file byte checks. Its existing database and loopback-only direct access remain intact. Production retains normal authentication.

## 3. Verification

66 Registry HTTP acceptance checks passed, including first-tab order, default entry and unknown-tab fallback. All 36 MyRF Home regression checks passed. The Home test now checks the actual Administration navigation block, rather than matching the word in the preserved How Works text. Source artifacts, database exports, secrets, raw employee-result JSON and private screenshots are excluded from the commit.

The working branch is codex/anagrafica-aws-20261110. Public release metadata is in REGISTRY_MYRF_PEOPLE_FIRST_20261110_RELEASE.json. Older release manifests remain historical records of their respective commits and images.

URLs:
- https://rfone.romesflavours.com/admin/roles
- https://rfone.romesflavours.com/
- http://127.0.0.1:5094/admin/roles
- http://127.0.0.1:5094/
'''
(repo/'07 Tasks/Reports/REGISTRY_MYRF_PEOPLE_FIRST_20261110_REPORT.md').write_text(report,encoding='utf-8')
p=repo/'10 System/Identity & Access/Role Profiles and Company Access.md';t=p.read_text(encoding='utf-8').replace('runs from a separate working copy against the isolated local database. No AWS writes.','runs from a separate working copy against the isolated local database. Production\nreleases retain normal RF1 authentication and use explicit deployment operations.');t+='''\n## Registry navigation (2026-11-10)\n\nThe UI module is named Registry. MyRF exposes it once in Administration, subject\nto existing platform administrator/owner permissions. Settings has no duplicate.\nPeople & assignments is the first and default tab, followed by Roles, Areas and\nCompanies. An unknown tab falls back to People. Explicit tab URLs remain supported.\n''';p.write_text(t,encoding='utf-8')
print('Registry and MyRF release documentation prepared for Git')
