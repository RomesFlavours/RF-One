from pathlib import Path
import json
root=Path.cwd();d=json.loads((root/'tmp/registry-home-release/state.json').read_text());local=json.loads((root/'tmp/copy_employee_directory_aws.json').read_text())['myrf_home']
report=f'''# REPORT — MyRF Home Registry placement and local copy

## 1. Delivered behavior

The new employee/role/company module is named Registry in its page title, breadcrumb and management links. MyRF Home exposes a single Registry entry under Administration, pointing to /admin/roles?tab=people. The duplicate Settings entry and the legacy Directory Home entry are removed. Existing administrator/owner permissions are retained; no grants are invented.

Production Home: https://rfone.romesflavours.com/
Production Registry: https://rfone.romesflavours.com/admin/roles?tab=people
Local MyRF Home: http://127.0.0.1:5094/
Local Registry: http://127.0.0.1:5094/admin/roles?tab=people

## 2. Concurrent release preservation

The initial candidate was not deployed because AWS had advanced to kitchen-home-e65f9b37dabb. Registry was rebuilt on that exact Kitchen build source, retaining the Kitchen registry entry and Home How Works implementation. The latest-image precondition prevented an overwrite of the concurrent release.

## 3. AWS release

Image tag: {d['tag']}
Image digest: {d['image_digest']}
CodeBuild: {d['build_id']} (SUCCEEDED)
App Runner operation: {d['deploy_operation']} (SUCCEEDED)
Service: RUNNING
Source ZIP SHA-256: {d['source_sha256']}

No database migration, employee update, account mutation, security-group change or authentication bypass was performed. The 47 dismissals were not modified by this release. Public checks confirmed login HTTP 200 and protected Registry HTTP 302 to normal login.

## 4. Local copy and verification

After successful AWS deployment, downloaded the exact immutable source ZIP from the release's S3 key and checked its SHA-256. Copied and byte-verified {local['verified_files']} files into the isolated local development source. Original AWS snapshot source and the local database were preserved. Existing local direct access remains without a login/signature page or environment banners. Added Avvia MyRF.cmd beside the existing private local shortcuts.

63 HTTP acceptance checks passed, including Registry placement, absence from Settings, old-link removal, Registry title and authorization filtering. Packaged Clover guard file hashes were verified. Browser inspection confirmed MyRF loads without login, Registry appears under Administration and opens the new Registry page. Local Registry still shows the closed Dismissis section with 47 records. Existing local permissions are retained; a source copy does not copy additional live AWS grants.

Screenshot (private workspace, not for Git): MYRF_REGISTRY_LOCAL_20261110.png.
Release evidence: tmp/registry-home-release/state.json, public-http.json and downloaded aws-published-source.zip.
Working source for the integrated release: tmp/git-anagrafica-release/03 Software. Pending lifecycle work in the original checkout remains separate and untouched.
'''
path=root/'07 Tasks/Reports/MYRF_REGISTRY_AWS_LOCAL_20261110_REPORT.md';path.write_text(report,encoding='utf-8');(root/'tmp/git-anagrafica-release/07 Tasks/Reports/MYRF_REGISTRY_AWS_LOCAL_20261110_REPORT.md').write_text(report,encoding='utf-8')
print('Registry AWS/local release report saved')
