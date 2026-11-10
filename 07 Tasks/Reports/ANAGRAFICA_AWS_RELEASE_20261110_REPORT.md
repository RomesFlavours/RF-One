# REPORT — Anagrafica AWS release, 2026-11-10

## 1. Scope

Deploy the locally reviewed Anagrafica role/area/company and personal-authorization interface to RF1 Web, preserving the actual running AWS application as the integration base. Local authentication bypass, local launcher, local database dump and local environment settings are excluded from the production image.

This release publishes code and additive schema only. It does not replace production data with the local database. In particular, the local 47-person inactivity update and interactive local role/company assignments are not silently replayed on production. The pending separate employee automatic-lifecycle branch remains outside this release.

## 2. Artifacts and tests

Immutable image tag: anagrafica-20261110t144835z.
ECR digest: sha256:44235a8208c86e29c93349dde6a43ede4f080de151dd58b68bcb00eb504f7817.
CodeBuild: rfone-web-build:2b07197f-d6a5-46ad-b565-d8aa79e5a2ac, SUCCEEDED.

58 HTTP acceptance checks, 15 service tests, and 16 source-artifact/connector checks passed. Migration rehearsed against the existing full AWS snapshot in the separate local database rfone_release_rehearsal_20261110, with all checked legacy counts unchanged and no inferred grants.

## 3. Database and safeguards

Internal ECS audit confirmed production revision e2c320261109 and 64 employees. RDS snapshot rfone-before-anagrafica-20261110t144835z was available before migration. The migration task completed successfully and advanced to f2a120261110. It preserved all pre-existing IDs for 64 employees, 6 accounts, 3,554 shifts, 15 Workforce assignments and 3,234 raw Bank transactions. No person memberships or role grants were inferred.

The initially proposed temporary RDS ingress/export procedure was rejected by automatic approval review and was not executed. The successful alternative used the existing AWS network and ECS roles, an internal RDS snapshot, and the already-authorized existing local snapshot for rehearsal. No Security Group change or new database export was performed for this release.

## 4. Deployment and rollback

App Runner update operation: 6d2f5927ca5f4190a73f2c3c6df213be. Deployment status and production smoke evidence are retained under tmp/anagrafica-release/state.json and production-smoke.json.

Production URL: https://rfone.romesflavours.com/admin/roles?tab=people

Rollback restores the previous SourceConfiguration/image using tmp/rollback_anagrafica_web.py. Leave the additive schema in place to preserve recorded profile history; do not downgrade destructively. A complete database recovery is available through the internal RDS snapshot if necessary.

The isolated release source ZIP is under releases/anagrafica-20261110t144835z/source.zip in the existing deploy bucket. Shared source ZIP and latest tag were not overwritten. Runtime environment variables, secret references and service configuration were preserved. No commit or main-branch merge was made.

## 5. Final deployment outcome

App Runner operation SUCCEEDED; service RUNNING. The public login remained available and protected routes redirected anonymous clients to login. Authenticated production browser verification was not completed: automatic approval review rejected constructing a signed session from the AWS secret, and computer use could not confidently establish the current Edge URL. That rejected smoke test was not executed. No authentication bypass was deployed.

After the code release, the Product Owner separately authorized application of the exact 47 local dismissals to AWS. The internal ECS operation re-read Clover, committed all 47 and retained all 64 employee records. See CLOVER_47_AWS_DISMISSALS_20261110_REPORT.md. Raw employee IDs, database snapshots, runtime secrets and screenshots are deliberately not included in this Git release.
