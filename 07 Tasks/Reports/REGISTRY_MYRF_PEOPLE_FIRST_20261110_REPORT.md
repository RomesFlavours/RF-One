# REPORT — Registry People-first and MyRF Git consolidation

## 1. Behavior

People & assignments is the first Registry tab, followed by Roles, Areas and Companies. Both an omitted tab and an unknown tab open People. Explicit links to the other tabs remain valid.

This commit also records the previously published MyRF changes: one Registry entry in Administration, no duplicate in Settings, Registry page/breadcrumb labels, and the preserved concurrent Kitchen Home registration and How Works content. The original checkout's pending employee-lifecycle implementation is not overwritten or implicitly merged.

## 2. Release and local copy

AWS App Runner release registry-people-20261110t153917z completed successfully (operation 1e285cff847640fe9a685de9a3c5a816). Image digest: sha256:69088f4bd2bd32bc0cd796baebb583707cd97784eb5d0f010ce227ad74c92fec. No schema, employee data, permission or login-policy changes were needed.

The local copy is updated from the exact AWS source ZIP after successful deployment, with SHA-256 and per-file byte checks. Its existing database and loopback-only direct access remain intact. Production retains normal authentication.

## 3. Verification

66 Registry HTTP acceptance checks passed, including first-tab order, default entry and unknown-tab fallback. All 36 MyRF Home regression checks passed. The Home test now checks the actual Administration navigation block, rather than matching the word in the preserved How Works text. Source artifacts, database exports, secrets, raw employee-result JSON and private screenshots are excluded from the commit.

The working branch is codex/anagrafica-aws-20261110. Public release metadata is in REGISTRY_MYRF_PEOPLE_FIRST_20261110_RELEASE.json. Older release manifests remain historical records of their respective commits and images.

URLs:
- https://rfone.romesflavours.com/admin/roles
- https://rfone.romesflavours.com/
- http://127.0.0.1:5094/admin/roles
- http://127.0.0.1:5094/
