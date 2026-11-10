# Role profiles and company access

Status: approved by the Product Owner, 2026-11-10. Local implementation only.

People may hold multiple roles in different areas and companies. Permissions add
together; changing, archiving or removing a role contribution takes effect on the
next authorization check. Existing direct account permissions remain explicit and
additive, never silently overwritten by a role profile.

## Existing catalogs and boundaries

Reuse RestaurantRole, OperationalArea and OperationalAreaRole identifiers. Their
compatibility table names remain; new platform-wide entries may omit restaurant_id.
Existing restaurant-specific entries and references remain intact. Do not create a
parallel role/area registry. Role profiles are access-policy associations, not new
payroll/shift EmployeeAssignment facts; the latter's source-specific single-role
policy and history are not altered.

Company contexts reference existing LegalEntity IDs where applicable. WP and MD
use their existing legal entities. RFGroup is a GROUP operating context, not an
invented legal entity or an implicit grant to its subsidiaries. Company membership
is explicit and many-to-many. External RF1 accounts can participate without being
manufactured as employees; confirmed account/person links resolve to one target.

## Permission composition

Use the existing Domain registry and NONE / ALL / SELECTED item choices and Domain
roles. ALL dominates SELECTED; otherwise selected item sets unite. Domain admin
dominates ordinary access; Training uses admin > trainer > student. Profiles never
grant platform owner/admin flags. Active role, area, company membership and person
state are required. Archiving preserves IDs, assignments and audit history.

Company-specific checks consider only the selected company, not a Cartesian union
of roles and companies. A person's aggregate summary may show all their companies,
but a grant in WP does not imply the same grant in MD or RFGroup. Manual grants
remain the legacy global policy. Consumers must use the company-aware shared APIs
and membership scope for data filtering; do not advertise universal company row
isolation in legacy modules that have not integrated it.

## UI and access

Administration exposes Roles, Areas, Companies and People assignments. Create,
edit, archive and restore use existing modal conventions, CSRF and row return.
Each role opens its permission modal using the same Domain/item definitions as
Accounts. People assignments record company membership and any number of role/area
profiles. Employee detail and Account pages link to those same central operations.
Only an existing RF1 platform administrator/owner may configure policy or assign
profiles. Existing domain administrators do not acquire policy-management powers.

Local UI remains direct-access without login or environment banners, loopback-only,
with outbound integrations disabled. Keep the immutable AWS source/dump; development
runs from a separate working copy against the isolated local database. Production
releases retain normal RF1 authentication and use explicit deployment operations.

## Acceptance

Verify role/item unions, Training precedence, company separation, manual grant
preservation, external accounts, multiple areas, membership withdrawal, archive/
restore, stale POST validation, CSRF, privilege escalation rejection, audit history,
and unchanged legacy workforce assignments. Verify the UI in a browser and preserve
the initial dump as the recovery point.

## Registry navigation (2026-11-10)

The UI module is named Registry. MyRF exposes it once in Administration, subject
to existing platform administrator/owner permissions. Settings has no duplicate.
People & assignments is the first and default tab, followed by Roles, Areas and
Companies. An unknown tab falls back to People. Explicit tab URLs remain supported.

## Registry contact details and password administration (2026-11-10)

MyRF no longer lists Accounts in Settings. Its existing routes and platform-admin
permission checks remain available; Registry supplies a Reset password entry for
the explicitly linked RF1 account. It opens the existing reset form in another
tab, retaining unsaved person input. New people must be saved first. An account
shell, if needed, remains inactive and receives no credentials or grants merely
from opening this action. Password resets retain existing password policy and
session revocation and do not reactivate an inactive account.

Registry edits optional Email and Phone fields. Employees reuse the canonical
Employee.email/phone fields and management audit. Unlinked external RF1 accounts
store contacts in RFOneAccount.contact_email/contact_phone. Those fields are
separate from account.email/email_verified_at, which remain the existing recovery
channel. Saving Registry contacts sends no message, enrolls no recovery channel,
does not verify addresses, and does not change credentials or permissions. Empty
input clears contact data; omitted fields preserve existing values. Imports and
contact use policies are not redefined by this change.

The shared chain includes already-applied Kitchen revision k9a020261110 before
Registry contacts revision f3b120261110. Existing identities, account data and
dismissals are preserved.
