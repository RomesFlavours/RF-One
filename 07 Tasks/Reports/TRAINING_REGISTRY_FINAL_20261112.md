# Training Registry final local verification — 2026-11-12

## SMTP and backup/recovery checks — read-only, November 12

Details: `STUDENT_REGISTRY_RELEASE_PLAN.md` (November 12 section) and
`output/training-registry-final-20261112/smtp-backup-verification.json`.
No deployment, migration, AWS change, resource creation or email was made.

- **SMTP configuration.** Only rfone-selection has Aruba SMTP settings. Live
  rfone-training contains no mail code; live rfone-web uses SES but has no sender
  address, so its verification/recovery emails are currently not sent (pre-existing).
  No external loader of mail settings exists in either image.
- **SMTP tests (no message sent).** Local mailbox and the AWS Selection credential
  both pass TLS 1.3, AUTH and NOOP from the local network. The local mailbox
  refuses the default sender `RFOne@romesflavours.com` (550); the AWS mailbox
  accepts it. AWS egress (NAT, SG, NACL) permits port 465 by configuration;
  a connection from App Runner and real delivery are not demonstrated.
- **Backups.** Retention 7 days; actual PITR window 2026-11-05 14:06:58 →
  2026-11-12 14:06:58 UTC; 9 automated and 50 manual snapshots available on 18.3.
  Storage, backups and snapshots are **unencrypted** (no KMS). No AWS Backup plan.
- **Restore evidence.** One snapshot restore on 2026-10-17 (temporary instance,
  read four BANK rows, deleted). It proves the mechanism, not recoverability of
  the current database; no restore test is recorded and none was performed.
  The plan now contains the full restore procedure with prerequisites, integrity
  checks and reopening criteria.

## Latest AWS outcome — supersedes the earlier access blockers

After explicit Product Owner authorization, temporary RDS ingress was limited to
the current client IP `/32` and PostgreSQL TCP 5432. Each temporary rule was
removed after the audit, including failed attempts, and initial ingress/egress
was restored and independently verified. No other network/access changes,
deployment, DDL, data update or account-permission modification was performed.

Live schema compatibility **passed** in a database-enforced read-only transaction:
PostgreSQL 18.3, revision `t9a120261110`, compatible prerequisite tables/column
types and missing new Registry tables as expected. The pending path is
`k9b120261112` then `t9b120261112`; neither migration was applied. Fingerprints
and row counts for 14 existing protected tables were unchanged across snapshots.
The successful connection used the database secret configured on the deployed
applications. The earlier separate administrative credential attempt did not
complete inspection and its network exception was also removed.

The checker initially compared generic timestamp strings with dialect-specific
timestamp strings. It now compiles both actual and expected types using the
same PostgreSQL dialect, preserving timezone distinctions; all eight apparent
timestamp differences disappeared. No live type was modified.

Evidence: `output/training-registry-final-20261112/aws-final-verification.json`,
`aws-readonly-schema.json`, `temporary-access-result.json` and paired network
snapshots. A passing compatibility inspection does not certify deployment or
email delivery. SMTP configuration/delivery and pre-release backup/recovery
validation remain outstanding release gates.

## 1. Scope and observed evidence

Local verification only. No AWS deployment/data mutation, real email, account
permission repair or historical learner update was performed. Functional tests
use the canonical PostgreSQL database; their transaction rollback removes test
rows. Sequence gaps from PostgreSQL test inserts are normal and are not reset.

Evidence directory: `output/training-registry-final-20261112` (local, uncommitted).
`browser-results.json` and screenshots record actual Microsoft Edge headless
rendering with non-loopback requests blocked. SMTP is intercepted. The existing
authorized `rfone` operator enters locally without a password; no trainer grant
is added. Learner sign-in is tested with the actual RF-One credential form.

The first browser run exposed a test isolation issue: legacy Training routes used
their independent session factory and could not see uncommitted fixture rows.
The harness now injects the same rollback factory into those imported modules;
no application authorization gate was relaxed.

## 2. Historical students — read-only findings and proposals

These are facts from the canonical local database, not a live AWS audit.

| Fact | Student 6 | Student 7 |
|---|---|---|
| Display / username | Tatiana / `tatiana ceban` | the girl / `girl` |
| Training identity | account 6, ActingIdentity 7 | account 7, ActingIdentity 10 |
| Creation | 2026-09-11 | 2026-11-03 |
| RF-One account | 8, ACTIVE, non-admin | no link |
| Email | absent/unverified | no RF-One account |
| Person/profile links | none | none |
| Training needs | 2, “Menu” | 3, “Menu”, origin `selection` |
| Assignments | 2 and 3 (2 contents) | 4 through 57 (54 contents) |
| First opening / quiz attempts | no first opening; no final/overall attempts | no first opening; no final/overall attempts |
| Current enabled grants | ORGANIZATION, SELECTED, item `interviews` | none linked |
| TRAINING grant | student, disabled | absent |

Student 6's RF-One link dates to September 11. Its Training grant was disabled
and Organization/interviews records were written on November 2 at the same
timestamp (12:55:58 UTC, 07:55:58 EST). There are no account-8 rows in
`rfone_access_profile_events`; timestamps alone cannot establish who changed
them or why. These records predate the November 12 integration. Student 7's
legacy `training_local` identity has no shared-login link; the recorded Selection
origin belongs to the need, not proof of an actual Selection candidate identity.

A local employee named **Tatiana Ceban**, Employee 46, exists without an explicit
person link. No CandidatePerson name matching Tatiana/Ceban/girl was found.
The name match is a candidate for human verification, not a proven identity.
All 54 assignments of student 7 reference withdrawn content; history must remain.

Proposed correction for 6, pending approval: establish the correct person and
verified email, explicitly link existing Training 6 and RF-One 8 to that person,
assign STUDENT without creating a duplicate account, and link Employee 46 only
if the identity/employment relationship is confirmed. Separately decide whether
to enable Training and whether Organization/interviews is intentional; preserve
it until that decision. Keep both existing assignments and all stable IDs.

Proposed correction for 7, pending approval: establish the person's real identity
and email, review Registry/login matches, explicitly link the existing Training 7
to the verified person and appropriate existing/new RF-One login, assign STUDENT
and authorize only the intended Training access. Issue activation only after that
review. Preserve need 3 and all 54 assignments, even though their content is
withdrawn; do not replace them with new assignments automatically.

## 3. Documentation and UI changes

Added `RF-One Web/STUDENT_REGISTRY.md` and the scoped AWS readiness/backup/deploy/
rollback plan. Updated Registry documentation, trainer and learner help. Added a
RF-One-hosted student-home template using existing route data, with Italian local
labels and contextual help; content titles/materials remain stored facts. Added
page-specific help to the administrative person list/detail and registered the
three affected pages. No identity schema or authorization architecture changed.

## 4. Help audit

The current baseline had 53 errors, not 25. No earlier complete checker output
was available to identify which individual errors formed the reported 25.
Baseline distribution: Selection 16, RF-One Web 25, Tips 12. Within RF-One Web,
12 were unregistered pages and 13 were stale help_missing entries. Of those,
the People list and person detail are directly relevant to Registry and were
corrected by adding page-specific help/registration. Remaining errors belong to
other pages: AI Organization, Bank, employee editor, interviews, obsolete registry
entries, Selection and Tips. They were recorded, not broadly repaired.

Training workspace creation/access/activation/reset and student home have their
own help. A passing scoped page audit does not make the global checker pass.
The final global log and count are in the evidence directory.

Final count: **51** (Selection 16, RF-One Web 23, Tips 12). The full checker
continues to exit 1. `final-checks.json` identifies zero errors for the scoped
Training and Registry pages; it does not replace or suppress the global result.

## 5. AWS boundary

PostgreSQL 18.3 migration rehearsal passed (including repeat upgrade and scratch
schema rollback). Current AWS inspection failed with `LoginRefreshRequired`;
the live schema/engine and backup status are unverified. November 10 evidence
records t9a, whereas t9b requires k9b. The plan explicitly gates deployment on
current revision/shape inspection, same-version rehearsal, snapshot and English
release verification. There is no claim of AWS release readiness.

## 6. Traceability

### AWS read-only follow-up

AWS authentication was renewed successfully with `aws login --profile default`.
RDS `rfone-dev` is available on PostgreSQL 18.3, matching the local rehearsal.
Seven-day backup retention, an available November 12 automated snapshot and a
latest-restorable timestamp were confirmed. The earliest-restorable timestamp
was absent; a full PITR restore window was not certified. Training and RF-One Web are RUNNING, use matching shared
database/session-secret references and the official public base URL. CloudFront
routes `/training/*` to Training with POST allowed. Current image digests and
backup metadata are in `aws-readonly-metadata.json` in the evidence directory.

Full live schema verification remains blocked by network reachability: client
egress does not match either existing IPv4 RDS ingress CIDR, bounded TCP/PostgreSQL
connection attempts time out, and there is no existing EC2/SSM tunnel host. No
network rule or permission was changed. `aws-readonly-schema.json` records the
failed access attempt; it contains no claim of a verified live revision or schema.

No RFONE_SMTP/RFONE_EMAIL environment or secret-reference keys were found on
either deployed service. SMTP readiness therefore remains a release gate;
image-internal settings were not inspected and no delivery was attempted.
`check_student_registry_readonly.py` is prepared for the remaining audit from an
already-authorized network, with database-enforced read-only transactions and
no migrations, deployment, permission changes or resource creation. No secret
value was printed or saved in the evidence.

The local schema advanced concurrently from t9b through the separate Kitchen
k9c/k9d revisions; this task did not run those migrations. Those revisions descend
from t9b. Do not use the initial audit revision as the current database marker.
The legacy audit was read again: selected student/account/grant/history fields
remain unchanged; the revision change is intentionally excluded from that check.

Final validation: Registry functional test, Edge browser workflow (including help,
Registry views and a 390px mobile home), workspace regression, course regression
and all 32 SMTP adapter tests pass. No test account/course/upload rows remain.
The existing course regression fixtures now complete the real first-access flow
before testing course/file isolation; the password gate was not bypassed.
Screenshots were inspected directly. Legacy People list/detail still contain
pre-existing English interface labels; the new local help is Italian. A complete
Registry UI translation was not undertaken as part of this onboarding task.

- `03 Software/RF-One Web/test_student_registry_local.py`
- `03 Software/RF-One Web/test_student_registry_browser_local.py`
- `03 Software/RF-One Web/STUDENT_REGISTRY.md`
- `03 Software/Infrastructure/deploy/rfone-training/STUDENT_REGISTRY_RELEASE_PLAN.md`
- `output/training-registry-final-20261112/legacy-audit.json`
- `output/training-registry-final-20261112/migration-rehearsal.json`
- `output/training-registry-final-20261112/browser-results.json`
- `output/training-registry-final-20261112/how-works-global.log`

No new production backup was created; the plan describes the backup required
before an eventual separately authorized deployment.
