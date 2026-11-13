# Employee Directory

Status: approved specification, revised by Product Owner on 2026-10-29, 2026-11-02 (record-level identity holds) and 2026-11-02 (EMPLOYEE_ACCOUNTS_001: positions per site, cessation, admission, one account per employee). Where an earlier rule below conflicted with EMPLOYEE_ACCOUNTS_001 it has been replaced.

The shared base directory is included in every RF-One Domain combination.
RF-One owns the reference person identity; a POS is an observation source.
The existing Employee table/ID remains the compatibility implementation of that
person identity, including candidates and external collaborators. No second registry
is introduced. This Shared Domain owns reference details and reconciliation. Administration on Home is its navigation placement, not its
conceptual owner. Workforce continues to own organizational participation;
Compensation owns compensation terms. No second personnel registry is created.

## Identity and ingestion

`Employee.id` is the existing RF-One employee identity used by every consuming
module. Clover identities are separate links keyed by merchant + employee ID.
Existing employees are backfilled without changing IDs or historical references.
Imports are Clover GET only; RF-One never writes to Clover.

Every unknown external identity stays pending, even without a name/email match.
An authorized human must link it to an RF-One person or explicitly approve a new
person. RF-One people can be created directly with no POS, location or employment.

**Admission (EMPLOYEE_ACCOUNTS_001).** A person is an *employee* only with at
least one Clover clock-in or clock-out attributed. A pending Clover name with
no clock-in or clock-out (none held in the Provider Mirror either) is kept only
as a technical observation of the synchronization: it is not shown as an
employee, it cannot be approved as a new person and it never receives an
account; it may only be linked explicitly to an existing RF-One person. Time
punches never replace the human approval: no association is made from name or
email similarity. Confirmed people without punches (created directly in RF-One,
or linked to Clover records never punched) stay in the directory as "other
RF-One people, not employees": consultable and selectable, never deleted. When
all their Clover records have left the rosters (e.g. staff whose punches predate
the acquired Shift history, which starts 2026-01-02 on AWS) they are no longer
offered by current selectors; historical selectors still include them.
Existing confirmed IDs and work history remain unchanged. Historical unknown
references follow the same approval boundary; they cannot silently create people.

A pending identity holds only the records that depend on that person, never a
Location's whole acquisition (Product Owner decision, 2026-11-02). Orders,
Payments and Refunds are still acquired, keeping the original Clover employee ID
and the raw payload, with no RF-One person attributed. A Shift requires a person,
so it waits in the raw Provider Mirror. When a human confirms the identity, the
held records are attributed through the Clover ID: only empty attributions are
filled, repeating it changes nothing, and the counts are recorded as a
`REATTRIBUTE` directory event. Tips refuses to finalize only the Business Dates
that still have held attributions. Every cycle logs the held records and why.
Runtime: `technical/connectors/clover/identity_holds.py`.

Multiple source accounts, including at one merchant, may explicitly refer to one
person. Complete source reads drive current duplicate-account anomalies. Removed
accounts disappear from current anomalies, while historical links/events remain.
Different source spellings are observations; source values do not overwrite RF-One.
A reviewed exact state stays acknowledged until its observations change.
Future outbound correction requires a concrete approved change and supported POS
operations; it remains disabled in this implementation (GET only).

Previously created duplicate identities can be consolidated only by an explicit
administrator confirmation. Declared operational employee foreign keys move as one
transaction. The old ID remains a resolvable alias and its original management
values remain retained; the target's management values are not overwritten. If
existing domain uniqueness rules conflict (payroll, roles or other historical
records), the entire consolidation is refused and all references remain unchanged.

## Ownership and reconciliation

Imported name, email, custom ID and Clover roles are source observations, kept per
link with last-seen time and append-only change history. RF-One display name, email, phone,
custom ID and directory active flag are internal fields, initialized on approval
and subsequently editable only in RF-One. Organizational roles remain existing
EmployeeAssignment/PositionAssignment records; pay remains EmployeeCompensationTerm.
No import modifies these management records. Names are full here because identity
matching requires them; timestamps use each Location's configured timezone.

## Positions and cessation (EMPLOYEE_ACCOUNTS_001, Product Owner 2026-11-02)

A **position** is a person's presence at one Clover site (WP and MD are
separate): the person's confirmed links at that site. Positions and statuses are
derived at read time from the links, their roster state and the Shifts; nothing
else stores them (`employee_directory.employment_states`).

- A position **ends** only when every confirmed link of the person at that site
  is absent (`MISSING_REVIEW`) from the site's latest **complete, validated**
  roster. Its date is the person's last **clock-in** at that site, even without
  a clock-out.
- A person **ceases** only when they are an employee and no position remains
  active. The cessation date is the last clock-in over all their Shifts. If the
  person disappears from one site but remains at the other, only the first
  position ends; functions and access at the other site are kept.
- Only a complete, successful roster import changes these states, in the same
  transaction as the import (a later failure rolls it back). Failed, partial or
  malformed reads, a wrong merchant, a site never imported (not configured, e.g.
  MD today) and an **empty** roster end nothing: a site's absences count only
  while that site has at least one present link from a complete roster.
- A ceased person stays in the directory, in the default-collapsed **Dismissis**
  section, with positions, dates and history. Person, links, account and history
  are never deleted. A person who reappears in a roster is active again; the
  position reopens, but the account stays disabled until an administrator
  reactivates it in Accounts.
- Every change is recorded as a directory event: `POSITION_END`,
  `POSITION_REOPEN`, `CEASE`, `REACTIVATE`, `ACCESS_DISABLED`, `ACCESS_KEPT`.

The directory active flag remains an explicit RF-One **manual archive** choice:
explicit false also places the person in Dismissis ("Archiviato manualmente"),
without ending positions or disabling the account. People active at no Clover
site but with punches (e.g. no Clover link) appear under "Senza sede".
Organizational assignments stay with Management / Organization and are not
closed by a cessation.

Different source values across sites produce a conflict. An explicit review
acknowledges the exact observed state; a subsequent change reopens review. RF-One
management values are never silently replaced by the latest site import.

Only a validated, complete employee collection may mark an absent link as
MISSING_REVIEW. It ends the site position as described above; it never deletes
a person, closes an organizational assignment or deletes history. Failed or
incomplete collections cannot change absence state.

## Runtime and access

`/administration/employees` and its detail pages require EMPLOYEES access through
the existing RF-One account/access system; every mutation requires CSRF. Sync Now
uses the existing Clover Acquisition job and its additional access requirement.
Management edits, identity links and conflict reviews require the existing RF-One
administrator or Domain administrator rule. Ordinary enabled accounts may consult.
The existing RF-One owner receives the initial access through the normal access
table; other accounts are granted explicitly in Accounts, never by an import.
The same import service is called from automatic Live Sync and manual acquisition.
The existing active AWS Correction Sync poller also refreshes the directory every
cycle (~60 seconds), under the existing Location lock. A directory read failure
preserves source state and leaves work cursors unchanged for retry; a pending
identity does not (see Identity and ingestion).
WP uses the existing configured connection. MD remains explicitly not configured
until its canonical Location/merchant and dedicated credentials are supplied;
it does not prevent WP imports. No merchant ID, location or credential is invented.

## Acceptance

Disposable-database tests cover legacy identity preservation, repeated imports,
cross-site linking, candidate review, management preservation, differing snapshots,
complete-only absence review, malformed/failed collections, permissions and CSRF.
EMPLOYEE_ACCOUNTS_001 adds `test_employee_accounts.py` (two sites with removal
from one, removal from the last, last clock-in without clock-out, names without
punches, failed/incomplete/empty/unconfigured imports, duplicates, one account per
employee, external accounts, session revocation, selectors and history) and the
Employee Directory HTTP tests for account creation, session end and How Works.

## Canonical consumers and location scope

Tips, role bootstrap and payroll consume canonical Employee IDs. Location
selection includes explicit Clover links (including historical missing links),
Workforce-owned assignment sites and legacy origin evidence, without returning retired aliases. Work records
retain their own Location; an employee's origin is not their only workplace.
Imported order/payment/shift displays use their RF-One employee foreign keys,
never an unscoped external Clover ID. Role evidence is scoped by SourceRole
location; a new assignment receives a location only when that evidence is unique.
Existing payroll matching policy and immutable approved results remain unchanged.

## Shared employee selectors

`employee_options` is the shared read-only selector for employee choices. It
returns canonical RF-One IDs, names, relevant sites and the same effective
active state as the directory: **ceased** people (EMPLOYEE_ACCOUNTS_001) and
manually archived people are inactive. A person whose position ended at one site
remains active, with only the sites where a position is still active.
Unverified or unlinked people, and people without punches, remain available,
unless all their Clover records left the rosters.

Operational selectors default to active people. Historical audit and identity
reconciliation explicitly include inactive people. An existing selected identity
may be retained, including an inactive person; retired IDs resolve to their
canonical ID. Retaining a selection never widens the caller's location scope.
Selectors never grant access: callers retain their existing permission gates and
must pass their authorized scope. No matching/deduplication by name is performed.

The Bank employee candidate portion consumes this selector. Equal names do not
hide choices or imply a shared person. Its explicit ActingIdentity association
remains step 3 work; employee and human-account choices retain distinct labels.

## Domain context links and ownership (approved 2026-10-29)

EmployeeContextLink explicitly links a canonical person to an RF-One account,
human ActingIdentity, Training account, CandidatePerson or ProjectResponsible.
The database enforces one context target per link and unique ownership of each
target.

**One account per employee (EMPLOYEE_ACCOUNTS_001).** Every employee has
exactly one RF-One account and an account refers to at most one employee:
`rfone_account_id` is unique and a person has at most one account link
(partial unique index, migration `f1a220261102`). An employee without an account
is shown as missing; an RF-One administrator creates it from the employee's page
(Accounts form prefilled with the directory's name and email, username and
password chosen by the administrator, linked in the same transaction) or links
an existing unlinked account. RF-One never invents emails, credentials or
associations. Accounts without a person are **external accounts** (e.g. a
consultant such as Shelbi): they need no directory record and Clover cessations
never affect them. On overall cessation the linked account becomes INACTIVE and
its sessions end (`10 System/Identity & Access/README.md`); linking an account to
an already ceased person disables it in the same step. Ending one site's
position never changes access. Identity consolidation is refused when both
identities have an account. Links never grant access, create accounts, merge candidates, change
Selection decisions, move attempts, or alter employment/payroll/Bank history.
Only directory managers with management authority for the target domain may link
or unlink; account/acting identity links require an RF-One administrator.
Each decision is audited; reassignment requires explicit unlink and relink.
No matching on names or email automatically creates these associations.

Bank resolves linked human identities/retired person IDs when creating a holder
assignment. Existing holder periods remain untouched. Projects retain external
responsibles and their local/history label; explicitly linked responsibles use
the RF-One reference name when displayed. Selection and Training retain their
own records, with canonical person lookup provided by the shared bridge. A
candidate becomes linked only through explicit confirmation, never a name match
or an automatically interpreted selection outcome.

The bridge is part of the included directory, not Identity & Access authority
model development. No authorization grant or profile is created or widened; the
only access effect is the account status change on cessation described above.
Per-site access does not exist yet: Domain access is not scoped by Location, so
profiles management will govern continuous permission updates.

Open manual RF-One assignments are never closed or replaced by POS role bootstrap.
Workforce site evidence is read, not copied: current choices use current assignments,
while historical choices retain former assignment sites.
