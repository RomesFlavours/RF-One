# REPORT

## 1. Published outcome

The authorized Clover identity confirmation correction was deployed to RF-One Web
on AWS. App Runner operation `da65196477a742d590b8340f5f2142a4` completed SUCCEEDED; the service
is RUNNING. Verified at 2026-11-11T23:12:22.036874+00:00.

Official entry: https://rfone.romesflavours.com/admin/roles#clover-identities

Registry > People & assignments now exposes Clover identities awaiting human
confirmation, location and held-shift details in location time. An administrator
chooses the corresponding RF-One person and selects Link to person, or explicitly
confirms a new person. The existing transaction attributes held work and records
an audit event. Return to Tips, recalculate the affected period and finalize it.
No real identities or tip periods were approved by this deployment.

## 2. Scope and validation

The overlay was prepared from the exact live production image, preserving today's
role-level and compensation changes. Shared UI defaults to English; the Italian
local working copy and local automatic access were preserved. Contextual Help for
Registry and Tips validation ships with the corresponding code.

Four isolated attribution/HTTP tests passed, including seven held shifts recovered,
no duplicates on repeat submission, rollback for invalid targets, explicit new
person confirmation, CSRF and access controls. Four shared policy checks passed
for grant/revoke and company separation. These tests ran again inside the final
Docker build. The unmodified How Works checker passed on the immutable overlay:
two operational pages with Help, zero missing, zero errors. Unrelated templates
are inherited unchanged from the pinned live image and are outside this overlay.

After deployment, official /login returned 200; /admin/roles and /tips/runs returned
302 to the normal login for an unauthenticated request. Direct App Runner URLs
returned 301 to the official host. Production authenticated pages were not visited
with manufactured login cookies and no identity-confirmation POST was sent.

No schema migration, local-to-AWS data synchronization, grant changes or other
service deployment was performed. Runtime environment values and secret bindings
were compared before/after and preserved except the release revision marker.

## 3. Immutable source and recovery

Source commit: `b4935d44777a7b765501bf0442a5d1efa9106bbd`
Image: `418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web:registry-clover-20261111t230758z`
Image digest: `sha256:b6cf906e5a84a40ad697017672909fc0a63958163f3bc7bbc56ce84ea6149154`
Build: `rfone-web-build:b927123a-ac9c-4d96-8a05-cc2a8f739705` (SUCCEEDED)
Source archive SHA-256: `5f4dccfdd727aa4ce7b03188ca297f93d04cbc679341a4d33be0e7655f1345e9`
Source S3 key: `releases/registry-clover-20261111t230758z/source.zip`

Rollback image: `418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web:role-level-20261111t124213z`
Rollback digest: `sha256:f7c93e4eb86f6d5501b97c301a39e902f3a870d1bc998e80b57e986a5da4ed8b`
Restore only the previous ImageIdentifier on this App Runner service while
preserving runtime configuration. This code release needs no database rollback.

Evidence directory: `C:/Users/servi/.codex/worktrees/edee/RF One/tmp/registry-clover-release`. It contains state.json,
pre-update-service.json, deployed-service.json, build.log, http-before.json,
http-after.json and the source.zip produced from the immutable Git commit.
The artifact Git repository is `C:/Users/servi/.codex/worktrees/edee/RF One/tmp/registry-clover-release/artifact`.
