# REPORT — Local role profiles and company assignments

## 1. Delivered behavior

Local page: http://127.0.0.1:5094/admin/roles

Roles, operational areas and company contexts support creation, editing, archiving and restoration. Each role opens a permission modal using the existing RF1 domain/function registry. People and external RF1 accounts can hold multiple company memberships and multiple role/area assignments, with dated withdrawal and audit history. Home, Accounts and Employee Directory expose links to this management page. Local startup retains automatic access without a login page or environment banners.

Existing RestaurantRole, OperationalArea and OperationalAreaRole catalogs are reused. Workforce payroll assignments retain their existing semantics and are not created or rewritten by access-profile management. WP and MD company contexts reference existing legal entities; RFGroup is a group operating context, not an invented legal entity. No memberships or permission assignments were inferred for real people.

## 2. Authorization

Profile permissions are recomputed from active memberships, assignments, roles and areas in the selected company. Permissions add: ALL dominates SELECTED, selected functions form a union, and domain privilege levels use their existing precedence. Profiles cannot grant platform owner/admin status. Ended assignments and dismissed people cease contributing profile permissions. External accounts can receive memberships without creating artificial employees.

Independent legacy direct grants remain additive and retain their existing global behavior. Without a selected company only direct grants apply. Company selection is checked server-side. Profile-only Employee Directory access filters people by company membership; this work does not claim that every legacy module already enforces company-level data isolation. Other operational routes remain disabled in this local copy.

## 3. Local migration and preservation

Revision f2a120261110 follows the actual copied database revision e2c320261109. It adds five access-profile tables, permits new global role/area catalog entries and records factual existing role-area relationships. Applied only to the local database on 127.0.0.1:55571. A pre-change backup is retained at:

C:\Users\servi\AppData\Local\RF-One\Employee Directory\AWS-20261110T120743Z\before-role-profiles-20261110T130111Z.dump

The original full AWS dump remains preserved. All 849 extracted AWS source files were verified unchanged. Ten legacy table fingerprints remained identical, including employee/account/direct permission records, Workforce assignments and shifts. This development made no cloud writes, commit or deployment.

The runnable source is isolated in:
C:\Users\servi\AppData\Local\RF-One\Employee Directory\AWS-20261110T120743Z\development-source

The migration artifact is retained in this report's ROLE_PROFILES_LOCAL_20261110 directory rather than inserted into the checkout's different pending lifecycle migration chain. The runnable source has the valid local migration chain. Reconcile these changes with current main and the pending employee lifecycle branch before release; the older copied AWS application does not yet contain those pending lifecycle changes.

## 4. Verification

- 15 service unit tests passed: additive permissions, company separation, precedence, revocation, direct-grant preservation, external accounts, archiving, validation and canonical account/person membership.
- 26 HTTP checks passed: authentication/authorization, CSRF, CRUD, invalid modal input, assignments, audit, company selection and preserved Workforce data.
- 16 release guard tests passed; source artifact hashes verified.
- Eight live local routes returned HTTP 200, including roles, areas, companies, assignments, accounts and Employee Directory.
- Browser inspection covered permission and area modals, company records, external account selection and membership modal. No real user grants were saved during browser inspection.

Screenshots: ROLE_PROFILES_LOCAL_20261110/roles.png and permissions.png.

## 5. Implementation traceability

New authored files:
- 03 Software/RF-One Data Store/rfone_data_store/access_profiles.py
- 03 Software/RF-One Web/role_profile_routes.py
- 03 Software/RF-One Web/templates/role_profiles.html
- 03 Software/RF-One Web/static/js/role-profiles.js
- 03 Software/RF-One Web/static/css/role-profiles.css
- 10 System/Identity & Access/Role Profiles and Company Access.md

Migration: ROLE_PROFILES_LOCAL_20261110/f2a120261110_role_profiles_companies.py.
Existing-source integration diff: tmp/role-company-existing-files.patch.
Preparation and local deployment scripts: tmp/prepare_role_company_development.py and tmp/deploy_role_company_local.py.
Tests: tmp/test_role_company_profiles.py and tmp/test_role_company_http.py.
Evidence: tmp/role-company-http-tests.log, tmp/role-company-artifact-tests.log and tmp/copy_employee_directory_aws.json.

Local shortcut: Avvia Ruoli.cmd in the private local copy directory. No AWS publication is included.

## 6. People editor update — 2026-11-10

Replaced the single-person picker with a collapsed people table: Name, Company, Role, Actions. Each data column has an independent, combinable dropdown filter. Company plus role filtering matches the role in that same company. One row per canonical person or unlinked external account.

Edit opens one modal for the centralized name, multiple company memberships and multiple company/role/area rows. Saving is transactional: rejected input rolls back name, membership and assignment changes together. Removed memberships and roles end their validity while preserving history. Repeated unchanged assignments reuse current records. Name changes reuse Employee Directory management updates for people, without changing imported Clover snapshots. The Other system authorizations button is visible and disabled, with no authorization effect.

No new migration required. Existing local database retained, no real people's roles or grants changed during verification. Browser interaction tested filtering, modal initialization, current membership, dynamic role areas, disabled button and cancellation. Screenshot: ROLE_PROFILES_LOCAL_20261110/person-editor.png.

Acceptance suite now passes 35 HTTP checks, including two-company edit, canonical account rename, invalid-input rollback and company removal revocation. Global local-development authorization recorded in C:/Users/servi/.codex/AGENTS.md, preserving production separation and enforced tool permissions.

## 7. RF1 wide modal, creation and manual dismissal — 2026-11-10

The person modal now uses a wide responsive panel, consistent RF1 form controls, soft section cards, olive accents and a sticky action footer. Add person is outside the collapsed table and opens the same modal empty. Creation uses the central Employee Directory and provisions a linked inactive account shell without credentials or grants when the older local source lacks the lifecycle helper. Companies and roles save atomically with the new person.

Existing employees have a dismissal date and Dismiss person action. Empty/invalid date disables the button; the server independently rejects missing, malformed and future dates. Dismissal sets canonical active=false, stores the selected date in durable Employee Directory and profile audit events, invalidates non-owner linked accounts/sessions, and preserves all records, assignments and history. Owner administration remains protected. Where the integrated lifecycle schema provides dismissed_at, the same operation also sets that field. In the older running AWS-copy schema the manual date is held in the existing audit records; no parallel person registry or destructive migration was introduced. Workforce assignment closure remains Workforce's responsibility. External accounts do not expose employee dismissal.

Dismissed employees appear in the closed Dismissis section and are excluded by the existing active-person selector. The automatic Clover lifecycle branch still requires the previously documented reconciliation before production release.

Validation: 49 HTTP checks passed, including create with multiple associations, inactive account shell, missing/invalid/future dismissal dates, stored date, active-selector exclusion, prevention of new assignments and full creation rollback on invalid role. Browser checks confirmed the blank creation modal, wide layout, date-empty disabled state, enablement on a valid date and re-disablement on clearing it. Browser actions were cancelled; no real copied person was dismissed or created. Screenshot: ROLE_PROFILES_LOCAL_20261110/person-editor-rf1.png. Local source activated and server restarted. No AWS changes or publication.

## 8. Personal system authorizations — 2026-11-10

Other system authorizations now opens the existing Account Domain Access editor in a separate browser tab. The original person modal remains intact, retaining unsaved input. The target is resolved using explicit Employee Directory/account links; an unlinked active employee receives one inactive, credential-free account shell on the CSRF-protected POST, reused on subsequent openings. Multiple confirmed accounts fail closed. New people must be saved first.

The canonical Domain Access editor reads and saves the same direct account grants used elsewhere; role grants remain additive and unchanged. The originating person reference is validated against the target account. Save retains the account/person context and the page offers Back to person. Platform admin/owner protections and CSRF remain in force. No new permission tables or migration added.

HTTP acceptance evidence: tmp/person-authorizations-http-tests.log. Covers access page, mismatched identity rejection, personal-grant persistence, non-admin rejection, account-shell provisioning and idempotent reopening, alongside prior lifecycle/profile checks. Browser verified Shelbi opens account 6 Domain Access and the original modal remains open. No real grants were changed during browser verification. Screenshot: ROLE_PROFILES_LOCAL_20261110/person-domain-access.png. Local source only; no AWS deployment.
