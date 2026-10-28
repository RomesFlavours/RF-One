# Employee Directory

Status: approved implementation specification (Product Owner, 2026-10-28).

This Shared Domain owns the reusable employee identity and external identity
reconciliation. Administration on Home is its navigation placement, not its
conceptual owner. Workforce continues to own organizational participation;
Compensation owns compensation terms. No second personnel registry is created.

## Identity and ingestion

`Employee.id` is the existing RF-One employee identity used by every consuming
module. Clover identities are separate links keyed by merchant + employee ID.
Existing employees are backfilled without changing IDs or historical references.
Imports are Clover GET only; RF-One never writes to Clover.

A previously unknown external record creates an employee only when no name/email
candidate exists. Any candidate, including an exact email match, requires human
confirmation. Pending links are visible and may be attached to an existing
employee or explicitly confirmed as a new person. Pending employees cannot be
attributed to work until resolved; acquisitions report that condition explicitly
and do not advance their work-data checkpoints until the identities are confirmed.
Repeated imports use the external key, never the name, as identity.

Previously created duplicate identities can be consolidated only by an explicit
administrator confirmation. Declared operational employee foreign keys move as one
transaction. The old ID remains a resolvable alias and its original management
values remain retained; the target's management values are not overwritten. If
existing domain uniqueness rules conflict (payroll, roles or other historical
records), the entire consolidation is refused and all references remain unchanged.

## Ownership and reconciliation

Imported name, email, custom ID and Clover roles are source observations, kept per
link with last-seen time and append-only change history. RF-One display name,
custom ID and active flag are internal fields, initialized once for a new person
and subsequently editable only in RF-One. Organizational roles remain existing
EmployeeAssignment/PositionAssignment records; pay remains EmployeeCompensationTerm.
No import modifies these management records. Names are full here because identity
matching requires them; timestamps use each Location's configured timezone.

The employee list displays active people grouped by site. Non-active records are
inside a default-collapsed **Dismissis** section. An explicit RF-One internal state
takes precedence; without one, presence in the current Clover roster determines
the display group. Only records absent from every known site go to Dismissis;
unverified/unlinked records remain visible. This is presentation, never an
automatic employment termination or a write to internal employee state.

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
