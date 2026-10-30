# Employee Directory

Status: approved specification, revised by Product Owner on 2026-10-29.

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
Existing confirmed IDs and work history remain unchanged. Historical unknown
references follow the same approval boundary; they cannot silently create people.

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

The directory active flag is an explicit RF-One visibility/archive choice, not
employment status, account access or POS presence. Only explicit false goes into
the default-collapsed Dismissis section. Unknown state remains visible. Source
absence remains a separate review condition. People without a site appear under
"Senza sede". Employment and organizational assignment stay with Workforce.

Different source values across sites produce a conflict. An explicit review
acknowledges the exact observed state; a subsequent change reopens review. RF-One
management values are never silently replaced by the latest site import.

Only a validated, complete employee collection may mark an absent link as
MISSING_REVIEW. This is a site-level review condition, never termination,
deletion of a person, assignment closure, or deletion of history. Failed or
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
preserves source state and leaves work cursors unchanged for retry.
WP uses the existing configured connection. MD remains explicitly not configured
until its canonical Location/merchant and dedicated credentials are supplied;
it does not prevent WP imports. No merchant ID, location or credential is invented.

## Acceptance

Disposable-database tests cover legacy identity preservation, repeated imports,
cross-site linking, candidate review, management preservation, differing snapshots,
complete-only absence review, malformed/failed collections, permissions and CSRF.

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
active state as the directory. Only explicit RF-One false makes a person inactive in the directory;
POS absence never determines this state.
Unverified or unlinked people remain available. Source absence is not termination.

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
target. Links never grant access, create accounts, merge candidates, change
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
model development. No authentication/authorization table or grant is changed.

Open manual RF-One assignments are never closed or replaced by POS role bootstrap.
Workforce site evidence is read, not copied: current choices use current assignments,
while historical choices retain former assignment sites.
