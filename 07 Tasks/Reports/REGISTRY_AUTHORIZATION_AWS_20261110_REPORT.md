# REPORT — Registry authorization AWS release, 2026-11-10

## 1. Published result

All five production services now use the shared Registry effective authorization
policy: RF1 Web (including the shell modules), Tips, Selection, Training and Kitchen.
Source commit: `d903a2edc250b77ec39992eb0db4a59985b88c31` on `codex/registry-access-local`.

| Service | New image tag | Deployment |
| --- | --- | --- |
| web | registry-access-web-20261110t173829z | SUCCEEDED / RUNNING |
| tips | registry-access-tips-20261110t173829z | SUCCEEDED / RUNNING |
| selection | sel-d903a2edc250 | SUCCEEDED / RUNNING |
| training | registry-access-training-20261110t173829z | SUCCEEDED / RUNNING |
| kitchen | registry-access-kitchen-20261110t173829z | SUCCEEDED / RUNNING |

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
