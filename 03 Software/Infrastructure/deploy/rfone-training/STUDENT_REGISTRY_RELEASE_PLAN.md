# Student Registry release readiness and recovery

## November 12 — SMTP and backup/recovery verification (read-only)

Evidence: `output/training-registry-final-20261112/smtp-backup-verification.json`.
Only read-only AWS API calls were made. SMTP sessions used AUTH, NOOP and
MAIL FROM followed by RSET; no RCPT or DATA was issued and no message was sent.
No credential or full mailbox address was printed or stored. No AWS resource,
configuration, permission or data was changed.

### SMTP — observed facts

| Item | rfone-training (live) | rfone-web (live) | rfone-selection (live) |
|---|---|---|---|
| Transport in deployed code | none (image has no SMTP adapter, no account routes) | Amazon SES (`ses_email`) | Aruba SMTP |
| `RFONE_SMTP_*` / `RFONE_EMAIL_*` in App Runner, image ENV or image files | none | none | host, port, username + secret `rfone-selection/smtp-password` |
| External loader (dotenv, Secrets Manager, file) for mail settings | none found in image layers | none found | n/a |
| IAM access to mail | none | `ses:SendEmail` | reads its SMTP secret |

- The code reads SMTP settings only from the process environment
  (`smtp_email.settings_from_environment`). Only the local launcher loads the
  DPAPI-protected file (`Selection/smtp_local_config.py`).
- **Live defect (pre-existing, not introduced here):** live rfone-web calls SES
  without `RFONE_EMAIL_FROM_ADDRESS`; `ses_email` refuses before contacting SES
  and the app silently swallows the error. Live verification and password-recovery
  emails are therefore not sent. SES itself is in production mode, healthy, with
  one verified identity and 0 messages in the last 24 h.
- Local DPAPI mailbox (domain `rmaed.it`): TLS 1.3, verified certificate, AUTH 235,
  NOOP 250. Aruba accepts only that mailbox as sender; `MAIL FROM` for the
  default sender `RFOne@romesflavours.com` is refused with **550 5.1.0**.
  Consequence: with the current local launcher, real Training/RF-One account
  mail would fail with `sender_refused_550`. Selection avoids this by defaulting
  the sender to the SMTP username; the new `account_email` defaults to
  `RFOne@romesflavours.com`. Not corrected here (verification-only mandate).
- AWS Selection credential (read only in memory, tested from the local network):
  mailbox is `RFOne@romesflavours.com`; TLS 1.3, AUTH 235, NOOP 250, and
  `MAIL FROM` for the default sender accepted (250).
- AWS egress configuration: the shared VPC connector routes 0.0.0.0/0 through an
  active NAT gateway; security groups and NACL allow all egress, so port 465 is
  not blocked by configuration.
- Secret `rfone-selection/smtp-password`: AWS-managed encryption, no rotation,
  last changed 2026-11-11, last accessed 2026-11-10 (the running Selection
  service may still hold the earlier value until its next deployment/restart).
- No Selection log line records an email send or failure in the last 60 days.

**Not demonstrated:** a TCP/TLS/AUTH session from inside App Runner, actual
delivery to any mailbox, and Training/Web access to the SMTP secret (they have
neither the reference nor the IAM permission). Release prerequisites, each a
separate configuration/permission authorization: add `RFONE_SMTP_HOST/PORT/
USERNAME`, the secret reference and `secretsmanager:GetSecretValue` on that
secret to rfone-training and rfone-web (and `RFONE_EMAIL_FROM_ADDRESS` equal to
the SMTP mailbox, or the sender default aligned with Selection), then one
message to an explicitly authorized recipient from the deployed service.

### Backup and PITR — observed facts

| Item | Value |
|---|---|
| Automated backups | active, retention 7 days, window 03:51–04:21 UTC, region target |
| Actual PITR window (`describe-db-instance-automated-backups`) | 2026-11-05 14:06:58 → 2026-11-12 14:06:58 UTC |
| Automated snapshots | 9 available (Nov 4 → Nov 12), PostgreSQL 18.3 |
| Manual snapshots | 50 available (Sep 22 → Nov 11), 18.3, none shared/public; latest `rfone-dev-pre-wines-20261111t1540z` |
| Encryption / KMS | **storage, automated backups and all snapshots unencrypted; no KMS key** |
| Deletion protection / Multi-AZ | enabled / no (single AZ, db.t4g.micro, 20 GB gp3) |
| AWS Backup | no plans, no recovery points, no restore jobs |

The earlier statement "earliest restorable time absent" came from
`describe-db-instances`; the automated-backup resource reports the actual
window above. A reported window proves that AWS holds backups and logs for that
interval, not that a restore produces a complete, consistent, usable database.

### Restore evidence

CloudTrail (90 days) records exactly one restore: on 2026-10-17 snapshot
`rfone-dev-pre-bank-removal-20261014t021458z` was restored to the temporary
instance `rfone-tmp-bank-access-read`, used to read four BANK access rows
(`BANK_REINSTALL_001`), and deleted about eight minutes later. No PITR restore,
snapshot copy or export exists. That event shows the snapshot-restore mechanism
works for this instance and engine; it recorded no integrity checks, row counts,
duration, application connection or current-schema validation, and used a
snapshot that no longer reflects the current schema. **It is not sufficient as
a pre-release recovery test. No restore was performed in this task.**

Still unproven, requiring separate authorization (creates and deletes AWS
resources, costs money): a restore of the pre-release snapshot (and one PITR
restore) to a temporary, non-public instance, followed by the integrity checks
of the restore procedure below and deletion of the instance.

## Current status — live read-only verification completed November 12

The Product Owner subsequently authorized **only** temporary RDS ingress from the
current client IP, followed by restoration. That narrowly scoped authorization
was exercised: TCP 5432 from `104.145.102.78/32` only. Each temporary rule was
removed in `finally`; initial ingress and egress rules were compared with the
final live rules and independently re-read. No deployment, database/schema write,
account/grant change, snapshot creation or restore was performed.

Using the **deployed application database secret** (not the separate administrative
password secret), the database accepted an encrypted connection with read-only
mode enforced in connection startup and a repeatable-read read-only transaction.
The inspection confirmed PostgreSQL **18.3**, live Alembic revision
**`t9a120261110`**, required person/login/Training columns and types, existing
identity primary keys and the employee FK prerequisite. All four Registry tables
to be created by t9b are absent. The k9b elapsed-preparation column is absent.
The pending migration path is therefore **k9b120261112 → t9b120261112**.
The exact pending DDL was not executed on AWS.

**Schema compatibility check: passed.** Row counts and deterministic fingerprints
of 14 existing protected tables matched across the live read-only snapshots.
The local transactional rehearsal used the same PostgreSQL version. The earlier
authentication/network blockers below are historical and are superseded by this
successful check and the evidence in
`output/training-registry-final-20261112/aws-final-verification.json`,
`aws-readonly-schema.json` and `temporary-access-result.json`.

This is not deployment approval. English artifact verification, an actual
pre-release backup/recovery validation, SMTP configuration/authorized delivery
and release execution remain separate gates. The existing deployed App Runner
configuration has no RFONE_SMTP/RFONE_EMAIL keys; live email readiness has not
been demonstrated. The local database's later Kitchen revisions must not be
included automatically in a scoped Training release.

Prepared 2026-11-12. Planning only: no deployment, AWS data write, snapshot creation,
identity permission change or historical reconciliation is authorized by this
document. The temporary network exception above was explicitly user-authorized
and has been removed.

## Evidence and compatibility boundary

`t9b120261112_student_registry.py` has parent `k9b120261112`, whose parent is
`t9a120261110`. The intervening Kitchen migration adds the nullable numeric
`kitchen_recipes.elapsed_preparation_minutes` column. Do not jump directly from
`t9a120261110` to the new Registry revision or manually stamp the new revision.

The canonical local PostgreSQL database began this audit at `t9b120261112` and
advanced concurrently through the separate Kitchen revisions `k9c120261112` and
`k9d120261112` (both descend from t9b). This task did not apply those revisions.
An already-applied t9b must not be reapplied or restamped backwards. A transactional
scratch-schema rehearsal on PostgreSQL 18.3 created all four Registry link and
qualification tables, ran the upgrade twice, verified foreign keys/unique keys,
preserved prerequisite rows and rolled back the whole scratch schema. Functional
and Edge renderer tests use the canonical database with rolled-back test rows.
These establish PostgreSQL compatibility, not compatibility with an uninspected
current AWS schema or a different server version.

Historical release evidence in `output/training-release-20261110/schema-marker.json`
records AWS revision `t9a120261110` on November 10. It is not current evidence.
A read-only RDS inspection attempted on November 12 returned
`LoginRefreshRequired`; no live schema/database inspection was possible in this
session. Current AWS engine version, revision, existing-table definitions and
backup readiness remain unverified. Release is NOT approved/ready until the
following preflight has passed using refreshed AWS access.

## Read-only preflight, before authorization to deploy

### November 12 follow-up: authentication renewed, database route unavailable

`aws login --profile default` completed successfully. Read-only AWS API checks
confirmed account 418674484214, RDS `rfone-dev` available on PostgreSQL **18.3**
(matching the local rehearsal), seven-day automated backup retention, available
November 12 automated snapshot and a reported latest-restorable timestamp. The
earliest-restorable timestamp was absent, so the full PITR window is not certified. Existing manual
snapshots were inspected, not created or restored.

The current client egress address is outside the two existing RDS IPv4 ingress
CIDRs. Two bounded PostgreSQL connection attempts timed out before a SQL session
could be established. No EC2 instance or SSM managed node exists for an alternate
already-configured tunnel. No security group, network, permission or resource was
changed. The blocker is now network reachability, not expired AWS authentication.

Both deployed Training and RF-One Web services are RUNNING, share the database
secret and session-secret references, and set the official HTTPS public origin.
CloudFront `/training` and `/training/*` route to Training and allow POST, covering
the activation/recovery endpoints. Their image digests are recorded in local
`output/training-registry-final-20261112/aws-readonly-metadata.json`.
Neither service currently has `RFONE_SMTP*` or `RFONE_EMAIL*` configuration keys
in its App Runner environment/secret-reference maps. Therefore the currently
configured deployment does not establish SMTP readiness for the new integration;
image-internal or externally loaded settings were not inspected. No email was sent.

The actual live Alembic revision, prerequisite/table definitions, constraints and
data fingerprints remain **unverified**. Engine/version compatibility passes;
full live migration compatibility cannot be certified from control-plane metadata.
The remaining read-only audit must run from an already-authorized network path.
The prepared `check_student_registry_readonly.py` enforces read-only PostgreSQL
transactions from connection startup, reads schema/constraints/fingerprints and
never applies DDL, grants or AWS resource mutations. Run it from a host with
existing approved connectivity, using the same frozen source and AWS profile:

```powershell
python "03 Software/Infrastructure/deploy/rfone-training/check_student_registry_readonly.py" --profile default --output "output/training-registry-final-20261112/aws-readonly-schema.json"
```

No new network authorization is implied by this command or plan. A successful
schema report still requires review of the exact pending revision path and all
other release gates below; it is not deployment approval.

1. Authenticate through the approved AWS process. Record account, region, database
   identifier, engine/version, current Alembic revision(s), active RF-One/Training
   image digests, secret references, App Runner configuration and CloudFront
   configuration/ETag. Read secrets through the existing protected mechanism;
   never record values in source or evidence.
2. Use a read-only database transaction through the approved private access path.
   Inspect `candidate_persons`, `rfone_accounts`, `employees`, `training_accounts`
   and existing Registry tables. Compare columns, types, nullability, primary keys,
   uniqueness and foreign keys with the exact frozen migration models.
   `checkfirst=True` only skips an existing table; it does not certify its shape.
   Missing prerequisite tables, incompatible existing tables, unknown revisions
   or multiple unexpected heads stop release with no mutation.
3. Record protected-table counts and deterministic row fingerprints for accounts,
   grants/item grants, identity/person/employee links, qualifications, Training
   accounts/profiles, needs, assignments/version references, attempts and course
   files/revisions. Preserve all existing learners, including IDs 6 and 7.
   Examine current live records read-only; local legacy findings are not proof
   of the current live state. Rehearse the exact revision path against an approved
   disposable restore on the same PostgreSQL major version and remove it afterward.
4. Freeze a scoped source revision and record hashes/image digest. Include both
   Registry model modules (the migration imports them), SMTP/account recovery
   modules, Training routes/templates/assets/help and registry. Do not include
   local launchers, automatic sign-in, local connection files or test accounts.
   `publish_training.py` targets the earlier t9a release and also publishes course
   content; it is not the command for this migration. Do not rerun that publisher.
5. Prepare an isolated English release artifact and test it while retaining the
   Italian working copy. Run the help checker against that actual artifact and
   its live-source range. Existing global failures must be classified; do not
   waive missing help on changed/new pages or mark the whole repository green.
6. Verify shared cookie secret and session invalidation, HTTPS public base URL,
   CloudFront routing for `/training/account/*` and `/training/access`, TRAINING
   authorization and SMTP sender/configuration. Recovery email uses the same
   RF-One account. Verify SMTP egress/TLS/auth from the deployed network; a local
   intercepted message does not prove AWS delivery. Any actual message must use
   an explicitly authorized test recipient.

## Backup and deployment sequence, only after explicit authorization

1. Schedule a bounded write pause. Record a recovery point and take an encrypted
   manual RDS snapshot; wait until `available`, record snapshot ARN/time and
   retention decision. Confirm automated backup/PITR coverage and the restore
   procedure. Historical snapshot `rfone-dev-pre-training-f3-24f64624fd38` is only
   a November 10 reference, not a new or sufficient pre-release backup.
2. Export protected routing/service configuration, prior image digests and source
   references. Record pre-release database fingerprints under the write pause.
3. Run only the reviewed pending revision path in an explicit administrative
   transaction, with bounded lock/statement timeouts and an exclusive version
   check. Apply k9b first only if actually pending and authorized; do not replay
   its ADD COLUMN if already present. Run t9b and update the revision only after
   successful DDL/shape checks. Never migrate at worker startup or synchronize
   local rows to AWS. No legacy identity backfill is part of this migration.
4. Compare protected rows/counts and FK/unique constraints, then release only
   the scoped application artifact. Follow deployment to its terminal status.
   Run readiness, shared login, instructor creation, student activation/access,
   course access, recovery and cross-module denial checks. Keep production
   account permissions and existing course/history IDs unchanged.
5. Resume writes only after acceptance; record image/revision/routing references,
   authorized test-message outcome and test-data cleanup method.

## Rollback

- Before DDL commit: rollback the transaction on any failed version/shape/data
  check; retain the previous application.
- After DDL commit: restore the prior Training/RF-One image and routing only for
  services changed in this release. Retain the additive tables, links,
  qualifications and any newly created student history. The migration's
  downgrade deliberately raises; do not drop tables or falsify alembic_version.
  Validate that the previous image ignores the additions during rehearsal.
- If data corruption requires restore: follow the operational restore procedure
  below. Never overwrite the live instance blindly or restore local test data
  into AWS.

## Operational restore procedure

Every step that creates, modifies or deletes AWS resources requires explicit
Product Owner authorization at the time. Snapshots and backups are unencrypted,
so the restored instance is unencrypted too; encryption would need a separate
encrypted copy decision.

**Prerequisites**

1. Recovery point chosen: the manual pre-release snapshot ARN/time, or a PITR
   timestamp inside the current restore window (check
   `describe-db-instance-automated-backups` at that moment; the window moves).
2. Pre-release evidence available: Alembic revision, row counts and
   deterministic fingerprints of the 14 protected tables plus the four Registry
   tables, recorded under the write pause (`check_student_registry_readonly.py`).
3. Approved network path to the restored instance (no new public ingress by
   default), restore parameters fixed in advance: same engine 18.3, class,
   subnet group, `default.postgres18` parameter group, `PubliclyAccessible=false`,
   deletion protection off for the temporary instance, a unique identifier.
4. Application writes stopped (services paused or set to maintenance) before a
   restore intended to replace production; previous image digests recorded.

**Procedure**

1. Restore to a **new** instance (`restore-db-instance-from-db-snapshot` or
   `restore-db-instance-to-point-in-time`); never restore over `rfone-dev`.
2. Wait for `available`; record duration, instance ARN and engine version.
3. Integrity checks, in a read-only transaction: Alembic revision equals the
   expected one; expected tables, primary/foreign/unique keys present; row
   counts and fingerprints equal the pre-release evidence (snapshot) or are
   explainable by writes up to the PITR timestamp; protected learners
   (students 6 and 7), their assignments and needs present and unchanged;
   `rfone_accounts`/grants present; no invalid indexes; sample login hash
   and course/version references resolvable.
4. Smoke check from an unexposed application copy, if authorized: shared login,
   Training home, a course page and the Registry views.
5. Reconcile explicitly any writes made after the recovery point; nothing is
   discarded silently.

**Reopening criteria (all required)**

- every integrity check passes and the result is recorded;
- the Product Owner authorizes switching `RFONE_DATABASE_URL` (secret) to the
  restored instance, or confirms the restore was only a test;
- after switching: `/health`, login, Training access, recovery page and
  cross-module denial checks pass on the public URL;
- the failed instance is kept (deletion protection on) for investigation until
  the Product Owner decides; temporary test instances are deleted and their
  deletion verified.

## Acceptance and outstanding gate

Local onboarding/access/reset, migration rehearsal and live schema preflight pass.
SMTP credentials/TLS were verified from the local network only (see the
November 12 SMTP section); backup existence and the PITR window were verified.
Still open as deployment gates: an actual restore test, SMTP configuration of
rfone-training/rfone-web plus sender alignment, delivery from the deployed
service to an authorized recipient, and the English release artifact. Reconciliation of students 6 and 7 requires a
separate explicit approval and is not required to apply this additive schema.
