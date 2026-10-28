# REPORT

## 1. Delivered behavior

Employee Directory is a Shared Domain, reached from RF-One Home → Administration
→ **Anagrafica dipendenti**, at `/administration/employees`. It reuses the existing
`Employee.id`, so Sales, Tips, Compensation and Payroll continue to refer to one
identity. Full names are used for identity reconciliation; timestamps use each
Location's existing timezone.

| Requirement | Implementation |
|---|---|
| WP and MD identities | `EmployeeCloverLink`, unique merchant + external employee ID |
| Existing records | Migration seeds links without changing employee IDs or work references |
| Name/email matching | Suggestions; any candidate requires confirmation, never an automatic name merge |
| Repeated imports | External-key updates; unchanged observations do not duplicate history |
| Source provenance | Separate safe snapshots, last-seen/run, append-only change events |
| Differing sites | Visible field conflicts; exact-state human review; later changes reopen review |
| Management | Existing name, custom ID and internal state editable separately; existing role/compensation records preserved |
| Removed employees | Site review condition only, no person/shift/assignment deletion or automatic termination |
| Failed/incomplete source reads | Validated before changes; prior state preserved; work checkpoints remain unchanged |
| Automatic and manual sync | Existing active Correction Sync poller (~60 s), Live Sync and Sync Now share the importer |
| Permissions | Existing account grants; EMPLOYEES consultation, RF-One/Domain administrators for management and linking; CSRF on writes |
| MD configuration | Explicitly unconfigured until its merchant/credentials exist; WP proceeds independently |

Unknown current source records with a plausible existing person are staged for
confirmation. Work ingestion for that Location resumes after confirmation, without
advancing the checkpoint past unresolved identities. Existing separate identities
can be reconciled explicitly: foreign keys move atomically, historical source
observations remain, and retired IDs resolve through `EmployeeIdentityAlias`.
Conflicting domain constraints refuse the entire consolidation, with no partial move.

## 2. Schema and ownership

Migration `c8e1f4a7b2d6` follows the actual deployed revision `d5a120261021`.

- Creates `employee_clover_links`, `employee_directory_events`, and
  `employee_identity_aliases`; backfills Clover links from existing employees.
- Replaces the legacy globally unique source employee pair with Location-scoped
  compatibility provenance. The authoritative provider identity is merchant +
  employee ID on the link.
- Preserves/reproduces three nullable Clover-reader columns already on AWS but
  missing from the older Git migration history: `employees.source_available`,
  `employees.source_checked_at`, `order_items.source_present`.
- Initializes EMPLOYEES access only for the existing active installation owner,
  through the normal access table. Other accounts require explicit grants.
- Leaves RF-One organizational roles and compensation terms in their existing
  models. No authentication identity is inferred from a name or email.

Imports are GET-only against Clover. No Clover write or new cloud infrastructure
is introduced. Source employee PINs are excluded by an explicit snapshot allowlist.

## 3. Baseline alignment and preserved deployed work

Observed: the initial worktree (`ec9c6c4`) was older than AWS. The live DB was at
`d5a120261021`, with 64 employees and one configured Clover Location. The live web
runtime matched `feature/admin-permissions` except for its already-deployed Wines
guide. The live Tips bundle also contained unversioned historical payment views,
calendar-month acquisition windows, historical employee recovery, and line-presence
handling.

Adopted: branch `codex/employee-directory` was aligned to the current web baseline.
The already-deployed Wines/Tips views and Clover fixes were recovered from the
existing S3 source packages and retained in versioned source, rather than replaced
with the older worktree code. Employee historical recovery now resolves through
the shared source links; current source imports do not overwrite internal data.
No local Bank data was transferred or changed as part of this task.

## 4. Verification

All automated checks use disposable databases and fake Clover clients.

| Check | Result |
|---|---|
| Directory service: identity, repeated imports, cross-site linking, management preservation, conflicts, removals, failure rollback, aliases and consolidation rollback, active poller, WP/MD isolation, actual shift Location after cross-site linking | 18 passed |
| Directory HTTP: populated migration, access, owner bootstrap, read-only viewers, CSRF, management, source conflicts, job reuse, duplicate job prevention, migrated-schema consolidation | 6 passed |
| Clover acquisition safety | 40 passed |
| Clover Live Sync | 29 passed |
| Clover Correction Sync | 69 passed |
| Historical Backfill extractor | 29 passed |
| Calendar-month recovery/historical references | 4 passed |
| Source line presence | 2 passed |
| Historical paid-tip observations/views | 7 passed |
| Existing admin permissions | 39 passed |
| Existing Home layout | 34 passed |
| Container image layout/import and Tips validation routes | 2 checks passed |
| Existing worker startup integrity guard on the extracted final source package, including PostgreSQL read-only checks | 10 passed; hashes verified, no DB writes, zero orphan Shifts |

The populated migration test retains a Shift's employee ID and existing
Compensation Terms. Consolidation with incompatible source-role membership is
verified to roll back every reference and leave no alias behind.

## 5. AWS release and operational observations

Migration applied on AWS: `d5a120261021` → `c8e1f4a7b2d6`. The following counts
were identical immediately before and after the migration:

| Existing data | Preserved rows |
|---|---:|
| Employees | 64 |
| Shifts | 3,409 |
| Employee Assignments | 15 |
| Employee Compensation Terms | 0 |
| Orders | 13,129 |
| Payments | 14,105 |

All 64 legacy Clover links were seeded. The existing owner received EMPLOYEES
access; no other account was granted access automatically.

Operational finding resolved during rollout: the actual ECS definitions were
pinned to a digest and invoked an unversioned startup integrity guard. An initial
updated task stopped before importing because that guard file was absent. The
stable previous worker was restored while the guard and manifest were recovered,
versioned and tested on the exact packaged artifact. Final worker definitions are
`rfone-clover-acquisition-job:4` and `rfone-clover-correction-sync:4`; execution
roles, secrets, network, CPU/memory and the existing cluster/service were preserved.
No integrity check was bypassed. Final runtime verification is recorded below.

Final observations on AWS:

- Both App Runner deployment operations completed `SUCCEEDED`; `rfone-web` and
  `rfone-tips` are `RUNNING`. The active ECS poller is revision `:4` and its actual
  running image digest matches the final recorded digest below.
- Real automatic acquisition completed: **27 PRESENT**, **37 MISSING_REVIEW**,
  **0 pending identity links**, **64 employees total**. The 37 historical records
  absent from Clover's current roster are retained for review, not terminated.
- Consecutive automatic cycle runs `168390` and `168394` completed without errors.
  The repeated real imports created no duplicate employee identity.
- A before/after fingerprint of name, custom ID and internal active state for the
  64 existing employees is identical after automatic imports. No personal values
  were printed as part of that comparison.
- `/login` responds 200. Directory and retained Tips/Wines routes respond with
  the existing RF-One login redirect when unauthenticated. Authenticated list,
  detail, management, permissions and cross-site workflows were verified with
  synthetic accounts and a disposable database; no production account was
  impersonated and no real employee management edit/consolidation was used as a test.
- Local browser inspection verified the list, detail, source/internal separation
  and existing RF-One styling on synthetic data.

MD credentials were not supplied or invented. Actual MD acquisition is therefore
not claimed; its identity/linking behavior is covered by the two-merchant tests.
No real personnel consolidation or internal management edit is performed as a
deployment check.

## 6. Traceability and recovery

- Branch: `codex/employee-directory`.
- Deployed source commit: `60ff80485f4ec8a272ba4a06a2c4419022cc5757`.
- Specification: `01 Domains/Shared Domains/Employee Directory/README.md`.
- Runtime: `rfone_data_store/employee_directory.py`, `employee_directory_routes.py`.
- Migration: `03 Software/RF-One Data Store/migrations/versions/c8e1f4a7b2d6_employee_directory.py`.
- Page: `https://rfone.romesflavours.com/administration/employees` (existing RF-One login).
- Operational restore uses the recorded pre-release RDS snapshot and source-package
  backups. A downgrade does not recreate directory observations; preserve backups.
- RDS snapshot: `rfone-dev-pre-employees-20261028t160542z` (available before migration).
- Source backup bucket: `rfone-tips-deploy-418674484214`.
- Source backup keys: `backups/rfone-web-source-pre-employees-20261028t160542z.zip`
  and `backups/rfone-tips-source-pre-employees-20261028t160542z.zip`.
- Previous stable worker definitions: `rfone-clover-acquisition-job:2` and
  `rfone-clover-correction-sync:2` (kept for recovery).
- Final worker image: `rfone-tips@sha256:90020f29cbb7685891772a5e0503f8139867d87cf928f70fd4fc411031b9401a`.
- App Runner operations: web `1710f10259f54113bb532d4c8c7bfb5d`;
  Tips `33d3964b121d4e49ab29f89ce0c3a00c` (both succeeded).
- Running worker task: `f36a067c5ff541fea1d0d36d47c60644`;
  CloudWatch stream `/ecs/rfone-clover-correction-sync` /
  `poller/clover-correction-sync/f36a067c5ff541fea1d0d36d47c60644`.
