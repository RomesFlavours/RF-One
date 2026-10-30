# REPORT — RF-One person foundation published on AWS

Date: 2026-10-29 (America/New_York).
Outcome: Web, Tips and Selection RUNNING; all final deployment operations SUCCEEDED.
Source commit: a195e4c385d2718b8bbcd8b4d9671595aa3fe8e4.
Page: https://rfone.romesflavours.com/administration/employees

## 1. Published scope

Published the included RF-One-owned directory, native creation without POS,
reference contacts, explicit reconciliation (including same-merchant duplicate
accounts), shared canonical selectors and the Bank/account/Training/Selection/
Projects identity integrations. Source absence is a review condition, not an
automatic directory archive, employment termination or account disablement.
Existing domain permissions remain. No outbound POS writer was enabled.

The release carries the approved cumulative steps 1–5 together. No unrelated
source changes were added. Runtime settings, secrets, roles and network settings
were preserved; the same App Runner services and ECS service remain in use.

## 2. Preflight, backup and real-data rehearsal

AWS login completed using rfone-dev-login, account 418674484214, us-east-1.
Compared the actual running image files with the deployed source archives.
Web/Selection matched; Tips used an older pinned runtime image. Its actual digest
was separately backed up rather than mistaking ECR latest for the running image.
All previous application images have immutable pre-person release tags; source
archives were copied to unique S3 backup keys before replacement.

RDS snapshot: rfone-dev-pre-person-20261029t134240z (available).
A repeatable-read copy of all 295 public tables, 885,586 rows and 649 foreign keys
was created in an isolated schema. Serial defaults were rebound to private
sequences. Migration, native person creation and a context link succeeded there;
operational employee sequence and operational schema were unchanged. The isolated
schema was verified by its ownership marker and removed. No copied personnel
data was exported or left in an extra database/schema.

## 3. Production migration and coordinated rollout

Paused/drained the automatic poller and verified there were no manual acquisition
tasks before applying d9e220261029 over c8e1f4a7b2d6 transactionally.
All existing employee values and the controlled operational counts were preserved:

| Data | Rows preserved |
| --- | ---: |
| People | 64 |
| Shifts | 3,424 |
| Assignments | 15 |
| Compensation terms | 0 |
| Orders | 13,150 |
| Payments | 14,132 |
| Bank financial transactions | 3,234 |
| Tip entitlements | 40 |
| RF-One accounts / Training accounts | 6 / 2 |
| Candidate persons | 2 |
| Projects / tasks | 2 / 30 |

No identity associations were guessed or backfilled. No real test person,
permission grant, account, payroll result or payout was created for verification.
Deployed all three applications using unique person-20261029t134240z-lf image
tags. ECS acquisition/correction definitions are revision 6, pinned to the new
Tips image digest. Poller command/startup verification was retained. The manual
worker now also performs the same read-only integrity/schema guard before
executing the launcher's argument array; a --help canary verified that contract.

## 4. Packaging correction disclosed

The first read-only worker canary stopped at the integrity check: git archive
had emitted Windows CRLF while the approved manifest requires LF bytes. It
executed no import and the poller remained stopped. The first application images
contained the intended code, but the package was not accepted for worker use.

Normalized the archives, checked EVERY manifest member before upload, rebuilt
all three images and redeployed the same source commit. The corrected archive
also passed the local packaged guard. The successful AWS canary exited 0,
reported artifact_verified=true, 10 tests and database_writes=false, and printed
the CLI help as expected. Rejected staging task definitions 5 were deregistered;
previous definitions 4 and current definitions 6 remain recorded.

## 5. Final verification

- All three final App Runner operations SUCCEEDED and services RUNNING.
- Login 200. Directory, Projects, Compensation, Bank, Training, Selection and Tips
  preserve their unauthenticated login redirects (302).
- Current Projects JavaScript is served; its CloudFront asset cache was invalidated.
- Actual running poller uses correction definition 6 and digest
  sha256:1d13878c8772e53ea617ab54c727071573c6e70ff40b03262e6750f73a5a2a5a.
- Poller startup guard passed artifact checks and read-only database checks.
- Fresh automatic cycles 173384 and 173388 COMPLETE, no errors.
- Schema d9e220261029; 64 people, 0 context links, 0 pending current identities,
  0 orphan shifts; rehearsal schema absent.

Authenticated production account impersonation was not used. The new forms,
permissions, native creation and reconciliation were covered by the local HTTP
suites and isolated real-data rehearsal; production checks verified deployment,
auth perimeter, assets, database and actual automatic synchronization.

## 6. Traceability and recovery

Exact build IDs, operation IDs, image digests, source/backup keys, snapshot,
canary tasks, task definitions and verification are in PERSON_FOUNDATION_003_RELEASE.json.
Versioned task-definition JSON files mirror the actual deployed definitions.
The implementation report remains PERSON_FOUNDATION_003_REPORT.md.

For application rollback, use the recorded pre-person image tags while preserving
current runtime configuration. Schema changes are additive; never automatically
discard people/contacts/context links created after publication. Old worker
revision 4 expects the old schema in its guard: do not blindly resume it against
d9e220261029. If a worker regression occurs, pause it and use a schema-compatible
verified repair; source checkpoints retain the pending acquisition window.
Full database restore is a separate recovery operation, not an automatic code
rollback, because it would replace newer business data.

Do not rerun the old deployment scripts without updating their source baselines.
Future packages must use git -c core.autocrlf=false archive AND verify archived
manifest bytes before build, not merely a normalized local test checkout.
