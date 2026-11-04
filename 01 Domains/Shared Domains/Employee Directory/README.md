# Employee Directory

Status: approved specification, revised by Product Owner on 2026-10-29, 2026-11-02 (record-level identity holds) and 2026-11-03 (employee lifecycle).

The shared base directory is included in every RF-One Domain combination.
RF-One owns the reference person identity; a POS is an observation source.
The existing Employee table/ID remains the compatibility implementation of that
employee identity. External consultants may have RF1 accounts without employee records. No second registry
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
person. A Clover identity is admissible only after at least one clock-in or clock-out.
Source-only identities remain technical observations, never employee/account registrations.
Native RF-One employees can be created directly without a POS or location.
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
custom ID (and, for native people only, the active flag) are internal fields,
initialized on approval and subsequently editable only in RF-One. Organizational roles remain existing
EmployeeAssignment/PositionAssignment records; pay remains EmployeeCompensationTerm.
No import modifies these management records. Names are full here because identity
matching requires them; timestamps use each Location's configured timezone.

Complete successful employee AND clock collections govern source employment.
Disappearance ends only the affected merchant position. Other active positions
retain their functions. After the last position ends, the person is dismissed,
with the latest clock-in as the cessation instant, even without a clock-out.
A clock-out-only person is eligible but has no invented cessation date.
Failed/partial collections and unconfigured/unverified sites never cause cessation.
Dismissed people remain in the collapsed Dismissis section and historical records,
but are excluded from new operational selections, including interview recipients.
Source reappearance reactivates employment; access is never silently re-enabled.
Native employees without POS retain RF1-managed state.

Different source values across sites produce a conflict. An explicit review
acknowledges the exact observed state; a subsequent change reopens review. RF-One
management values are never silently replaced by the latest site import.

A complete source roster records absence per link (MISSING_REVIEW). Lifecycle
decisions require a complete validated clock collection too, read before the roster.
Latest observed clocks are retained even if Clover later ages out history; a site
uses only clocks recorded for that site, never unscoped local shifts. Unknown
historical clock identities require the same explicit human attribution; no
name-based merge is introduced. While such a clock-bearing identity is pending at
a merchant, absences there stay MISSING_REVIEW ("cessation suspended"): the pending
account could belong to the same person. Presence still reactivates immediately.
Offline/file snapshots record clock evidence only and never end positions.

A person with links whose every link has a verified clock scan but no clock at all
becomes a technical observation (`directory_eligible = false`): outside the active
list and Dismissis, without an account, history retained. The RF1 `active` field now
carries employment for Clover-linked people and is maintained only by
synchronization; for native people it stays an RF1-managed choice.

Clover `/shifts` has no server-side time filter. Acquisition reads it once per run
and shares it between lifecycle and Shift ingestion. The minute Correction poller
reads the roster each cycle and the full shift history only when the roster changed,
a link was never verified, a suspended cessation can now be settled, or the newest
complete clock check is over one hour old.

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
complete-only absence review, malformed/failed collections, permissions and CSRF,
per-site and overall cessation, suspension, clock retention, owner protection,
session revocation, Training/Projects/Bank new-assignment guards and the populated
migration with indirect account conflicts.

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
active employment state as the directory. Verified disappearance from the last
active site determines dismissal. Source-only unlinked identities are not employee choices;
unverified sites cannot cause a dismissal.

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
target. Employee creation provisions a disabled RF1 account shell. Links never grant
permissions, merge candidates, change
Selection decisions, move attempts, or alter employment/payroll/Bank history.
Only directory managers with management authority for the target domain may link
or unlink; account/acting identity links require an RF-One administrator.
Each decision is audited; RF1 account links are mandatory and their provisional
shells may be explicitly replaced with an existing confirmed account.
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

## Mandatory RF1 account (approved 2026-11-03)

Every canonical employee has exactly one RF1 account; an account maps to at most
one employee. New employees receive an INACTIVE shell with an unusable password
marker, no email and no grants. An administrator may explicitly replace that shell
with the person's existing account; operational accounts are never guessed by name.
External accounts (for example Shelbi) need no employee, no clocks and are unaffected
by Clover absence. Account links cannot simply be removed from employees.
Complete dismissal blocks authentication, invalidates existing sessions (RF1 and
Training sessions, through the account session version) and keeps accounts/history.
An account re-enabled in Accounts stays blocked while its person is dismissed.
Reappearance does not restore permissions or activate accounts. Ending one site's
position never disables the account while another position stays active.

### Product Owner decisions approved 2026-11-03

1. Owner: an owner account linked to a dismissed person keeps its RF1
   administrative access (ADMIN_PERMISSIONS_001); OWNER_ACCESS_PROTECTED records it.
   The exception covers access only: the person stays dismissed and is excluded
   from interview recipients and every new operational selection.
2. Organizational assignments: closing them belongs to Workforce. The directory
   records the cessation and exposes it to consumers; it never changes
   EmployeeAssignment rows. History is retained.
3. Replaced provisional accounts stay INACTIVE, with the unusable password marker
   and no grants, unlinked from the employee and never deleted automatically.
   ACCOUNT_REPLACED keeps previous and new account IDs. A provisional account can
   never be linked as a person's real account, so an orphaned shell gives no access.
Profile-driven authorization is a separate later change; existing grants are not
expanded here. Current domain grants do not encode per-site authorization.

## Organizational applicability (EMPLOYEE_APPLICABILITY_001)

Product Owner decision, 2026-11-03. A person has one directory identity and may
operate for a single Restaurant, several Restaurants or the whole group. The
applicability is chosen only in the Employee Directory (person record) and every
module reads it through `rfone_data_store.employee_applicability`; no module keeps
a copy or derives it on its own.

| Scope | Stored as | Rule |
|---|---|---|
| One Restaurant | `RESTAURANT` + one Restaurant | exactly one |
| Several Restaurants | `RESTAURANTS` + Restaurants | two or more |
| Whole group | `GROUP` | explicit; no Restaurant list; includes Restaurants added later |
| Not configured | no row; the service returns `NOT_CONFIGURED` | never the whole group |

The unit is the canonical Restaurant (Operational Unit), not a Clover Location.
Tables `employee_applicability` and `employee_applicability_restaurants`
(migration `e4a120261103`, additive, no backfill: everybody starts NOT_CONFIGURED).
Every change appends an `APPLICABILITY_SET` event with previous and new value.
Identity consolidation moves the rows with every other employee reference; if both
records already have an applicability, consolidation is refused rather than merged.

Applicability is distinct from:
- **active state** (`Employee.active`, `dismissed_at`, lifecycle): a dismissed person
  is excluded from new selections whatever the applicability;
- **access** (`RFOneAccountDomainAccess`, items): applicability never grants access,
  and it does not by itself decide which other people a user may select;
- **assignments** (`EmployeeAssignment`, Workforce): role/area facts per Restaurant;
- **site evidence** (Clover links, `Employee.location_id`, `employee_options(location_ids=...)`):
  where work was actually recorded, used for work history, Tips, payroll matching.

Shared service: `get_applicability`, `applicability_map`, `account_applicability`,
`set_applicability` (the only write path, used by the person record),
`restaurant_choices`, `restaurant_names`. Reads return an explicit `Applicability`;
NOT_CONFIGURED is its own value, never None, an empty list or the whole group, and
the service never assigns a value automatically.

`require_active_employee(db, id)` re-checks at submission time, resolves retired IDs
to the canonical person and refuses dismissed people; its optional `location_ids`
filters by site evidence, never by applicability.

Consumers (2026-11-04): **Interviews** lists current employees through the shared
`interview_employee_options(db, location_ids=...)` (the scope argument is mandatory:
`[]` means nobody, `None` unrestricted and only when deliberately chosen; Interviews
passes `None`) and re-checks with `require_active_employee` at submission; it does
not restrict recipients by the requester's applicability, and an applicability that is
not configured does not block a request. Permissions and CSRF are unchanged. **Projects** (responsible
person) and **Bank** (cardholders) select people for the whole company without an
organizational perimeter and use the active-state check only. **Tips** (host audit,
historical payments), **payroll ADP import** and **Restaurant profile bootstrap** read
site evidence of recorded work, which is a different fact from applicability.
Training uses the active-state access rule. Projects, Bank cardholders and Training use it (or
the same state) for new assignments only; existing tasks, holder periods, payments,
shifts and Training history keep their references and remain displayed.

Migration adds lifecycle evidence and one-account uniqueness. It refuses existing
direct or bridged multiple-account conflicts before DDL, reuses confirmed associations
and provisions INACTIVE shells for native people and people with local clock evidence.
Source-backed records without any local clock get no account until a complete clock
scan or an explicit link shows they worked. It never infers disappearance from old
database snapshots and leaves every active flag unchanged. `employee_directory_audit`
is the read-only pre-check; downgrade is refused once lifecycle/account history exists.
