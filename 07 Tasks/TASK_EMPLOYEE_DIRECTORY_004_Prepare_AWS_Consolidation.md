# Employee Directory — prepare AWS consolidation

Date: 2026-11-04. Assignee: Claude. Status: authorized preparation, no production deployment.

## Objective

Consolidate the completed local Employee Directory lifecycle implementation with
the current RF1 codebase and deliver a verified, reviewable release candidate.
The Product Owner has approved the functional decisions. Preserve them.

## Sources and integration

- Local changes: `C:\Users\servi\.codex\worktrees\edee\RF One`, branch
  `codex/employee-directory`; changes are currently uncommitted.
- Other active repository: `C:\Users\servi\OneDrive\AI-RF-ONE\RF One`.
- Inspect Git status, branches, local changes and actual deployed version before
  selecting the integration base. Use an isolated integration branch/worktree.
- Integrate relevant changes; do not copy the entire older checkout over the newer
  repository. Preserve other modules, runtime configuration and existing work.
- Check any Interview integration already implemented in the other chat. Do not
  replace it with a separate registry or duplicate lifecycle logic.

## Approved behavior to preserve

- RF1 canonical identity; explicit reconciliation of merchant + Clover employee ID,
  including multiple POS accounts belonging to one person. No name-based auto-merge.
- Disappearance ends only the affected site position. Dismiss the person when no
  active position remains. Cessation uses the last clock-in, even without clock-out.
- Clover identities without any clock-in/out remain technical observations, not
  registered employees/accounts. Do not fabricate a date for clock-out-only cases.
- Only successful complete source verification may cause cessation. Failed/partial
  reads, old file snapshots and unconfigured/unverified sites cannot do so.
- Native RF1 employees can exist without POS. Every registered employee has exactly
  one RF1 account. External accounts, such as Shelbi, need no employee record.
- Reuse confirmed account/Training/human identity bridges; never guess associations.
  Provisioned accounts are INACTIVE, with no usable credentials, invented email or
  grants. Replaced provisional accounts stay INACTIVE, unlinked and audited; they
  cannot be relinked as real accounts to another person.
- Dismissal blocks operational access and existing sessions. The owner retains
  administrative access, with OWNER_ACCESS_PROTECTED audit evidence, but the
  associated dismissed person remains excluded from operational/interview selectors.
- Workforce owns closure of organizational assignments. Directory must not close
  those records directly. Preserve all history. Rehire never silently restores access.
- Profile-driven permissions remain later work; no new automatic grants.
- Active employees grouped by site; Dismissis initially collapsed; account and site
  lifecycle visible; latest sync beside the action; current RF1 UI rules apply.
- No writes to Clover.

## Shared Interview contract

Preserve `interview_employee_options(db, location_ids=...)` and
`require_active_employee(db, employee_id, location_ids=...)` in the central service.
The former supplies only active canonical recipients; the latter revalidates at
submission and rejects dismissed/out-of-scope people, including stale page choices.
An empty site list means nobody; None means unrestricted scope and must not be used
as a fallback when authorization scope is missing. Historical interviews remain.
The page integration belongs to Codex in the chat “Prepare for an interview”.

## Migration chain

Local revision `e3f120261103` currently follows `d9e220261029`. The latest handoff
reports production revision `e1b220261102`; verify the actual runtime and migration
DAG before changing ancestry. Integrate into the current chain without accidental
branches, missing revisions or incompatible edits to applied migrations.
Align models, worker startup guard and release manifest. Preserve IDs and references.

## How Works

Reuse the current How Works registry and conventions, absent from the older
checkout. Add Employee Directory help covering active/site/dismissed state,
reconciliation, technical observations, accounts and provisional replacements,
synchronization, suspended cessations, owner exception and retained history.

## Read-only AWS audit

Audit the actual application database using the employee_directory_audit tool,
adapted to the current schema if required. Report direct/indirect person-account
conflicts, missing/deferred accounts, no-clock identities, unscoped clocks and owner
associations. Do not guess or automatically repair ambiguous associations.
Never expose credentials or unnecessary personal data in reports.

## Complete disposable PostgreSQL rehearsal

Create a complete isolated disposable copy of real data and run the migration
there. Verify stable IDs, references/history, account uniqueness, no privilege
expansion, legacy no-clock handling, per-site/final cessation, session revocation,
owner exception, external accounts and Interview filtering. Exercise repeated,
failed and incomplete imports with synthetic changes only inside the copy.
Ensure operational data, sequences and services are unchanged. Verify the exact
identity of the disposable copy before removing it after the rehearsal.

## Verification and packaging

Run appropriate checks on the final integrated implementation, distinguishing
baseline defects from regressions. Earlier Claude reports list 86 unit tests,
13 Directory HTTP tests, and successful acquisition/poller/Bank/Projects/Training
checks; these are prior results, not substitutes for final integrated verification.
Baseline issues reported separately: two Training-under-Tips failures and Projects
service check 43 expecting an obsolete migration revision.

Build with LF text files, regenerate integrity hashes, verify the actual packaged
bytes and run the worker startup check against that artifact. Do not merely verify
the source tree. Preserve newer deployed functionality and service configuration.

## Deliverables and authorization boundary

Prepare coherent commits and an English repository report under `07 Tasks/Reports/`.
Report to the Product Owner in Italian using the repository REPORT format. Include:

1. Integration branch and exact commits; conflicts and resolutions.
2. Verified AWS runtime/schema version and resulting migration chain.
3. Read-only audit findings and complete PostgreSQL rehearsal evidence.
4. Final tests, artifact hashes and startup verification.
5. Remaining blockers, if any, and explicit release-readiness conclusion.
6. Concrete deployment, backup and recovery plan, including affected services and
   workers and any schema compatibility limitations of rollback images.

Authorized now: local integration/preparation, read-only AWS inspection and the
isolated disposable rehearsal. NOT authorized: production deployment, migrations
or personnel changes in the operational database, starting new production source
synchronizations, or Clover writes. Deliver the concrete release candidate for
the Product Owner's final deployment approval.
