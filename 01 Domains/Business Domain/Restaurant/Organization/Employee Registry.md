# Employee Registry

Approved Product Owner scope, 2026-10-26.

## Shared organizational applicability

The Product Owner's 2026-11-03
[Person Organizational Applicability contract](../../../Shared%20Domains/PERSON_ORGANIZATIONAL_APPLICABILITY_001.md)
applies to this registry and every consumer. Applicability is maintained only in
the shared Anagrafica: one restaurant, several restaurants, or the entire group.
A server may work at several restaurants; an executive may serve one restaurant
or the entire group. Group-wide applicability is explicit, not a missing site.
Consumers use shared services and retain their own authorization checks; they
must not maintain competing applicability rules or configuration. This approved
rule does not assert that the current runtime already implements every case.

## Existing registry foundation

RF-One maintains its own employee register using the existing Employee identity and
EmployeeAssignment history. Clover supplies the initial population and new identities
encountered during any import. There is no second employee identity or duplicate roster.

An authorized operator can review the source name/code and current source roles beside
RF-One's values, correct name, employee code, employment status, and effective-dated
Restaurant role, and see who changed what and when. Missing source employment status
remains unknown. Source unavailability never means employment ended.

RF-One corrections take precedence over subsequent Clover imports. Imports retain
new source observations for comparison and mark reviewed records for review when
those observations change; they do not silently change protected canonical values.
Role corrections close/open EmployeeAssignments with an explicit local effective time;
no historical role is inferred from a current Clover observation. Current source roles
use the latest observation batch per employee, not the union of obsolete observations.
The initial registry bootstrap preserves existing assignments and proposes missing or
different roles for review. New employees are marked for review, never silently ignored.

The first release uses the existing administrator authorization and CSRF protection.
All writes are transactional and audited against the authenticated RF-One account.
The register is served in RF-One Web at /employees and linked from Settings.
Clover is read-only; no correction is sent back to Clover. Local trials use the one
canonical local PostgreSQL database. Isolated test databases are deleted after tests.

Acceptance: idempotent initialization; all Clover employee upsert paths register new
identities; corrected values survive subsequent imports and partial references;
source drift is visible; dated role changes preserve previous intervals; invalid,
overlapping, stale or unauthorized edits do not write; existing Tips reads the same
Employee/EmployeeAssignment facts. No AWS deployment is included in the local trial.
