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

The populated migration test retains a Shift's employee ID and existing
Compensation Terms. Consolidation with incompatible source-role membership is
verified to roll back every reference and leave no alias behind.

## 5. AWS release and operational observations

Release preparation completed; operational outcome and recovery identifiers are
recorded here after the controlled snapshot/migration/build/deploy verification.

MD credentials were not supplied or invented. Actual MD acquisition is therefore
not claimed; its identity/linking behavior is covered by the two-merchant tests.
No real personnel consolidation or internal management edit is performed as a
deployment check.

## 6. Traceability and recovery

- Branch: `codex/employee-directory`.
- Specification: `01 Domains/Shared Domains/Employee Directory/README.md`.
- Runtime: `rfone_data_store/employee_directory.py`, `employee_directory_routes.py`.
- Migration: `03 Software/RF-One Data Store/migrations/versions/c8e1f4a7b2d6_employee_directory.py`.
- Page: `https://rfone.romesflavours.com/administration/employees` (existing RF-One login).
- Operational restore uses the recorded pre-release RDS snapshot and source-package
  backups. A downgrade does not recreate directory observations; preserve backups.
