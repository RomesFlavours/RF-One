# REPORT — Shared employee selectors, step 2

Date: 2026-10-29 (America/New_York).
Status: implemented and verified locally; not deployed to AWS.
Baseline: 9764ef6 plus the preserved step 1 working-tree changes.

## 1. Scope and outcome

Employee Directory now provides the shared read-only employee_options service.
The directory's state/site grouping uses the same employee_is_active and
employee_location_ids functions. Existing permissions remain at each caller.
No migration, production writes, Clover calls or AWS deployment were performed.

## 2. Implemented behavior

- Immutable options expose canonical ID, name, relevant site IDs/names, effective
  active state and selected state. Stable sorting includes ID to distinguish
  homonyms. Pending links never become selectable employee identities.
- Operational choices default to active people. Explicit internal active state
  wins; otherwise complete absence across known source links affects display
  only. Unverified/unlinked people remain available.
- Historical/reconciliation choices include inactive people, visibly labelled.
- Selected retired IDs resolve to their canonical identity. Existing inactive
  selections can be retained without widening the supplied location scope.
- Options use a bounded number of database queries and perform no writes.
- Directory reconciliation and consolidation dropdowns use shared options,
  displaying site names and inactive status. Inactive records remain available
  for reconciliation; retired aliases never appear as duplicate choices.
- Tips Host Audit uses shared historical choices. HTML and CSV share canonical
  request resolution and reject people outside the restaurant's location scope.
- Bank cardholder employee candidates use shared operational choices, including
  site labels. Equal names no longer hide distinct employees or imply equivalence
  with human ActingIdentity records. SYSTEM identities remain excluded.

The explicit Employee/ActingIdentity relationship, and Bank persistence handling
for that relationship, remain step 3. Employee and ActingIdentity are still
separate labelled choice kinds; no automatic association was introduced.

## 3. Verification

| Final check | Passed |
| --- | ---: |
| Employee directory/consumer/selector suite | 30 |
| Employee Directory HTTP, permissions, populated migration | 7 |
| Bank cardholder and accounting deduplication regression | 37 |
| Historical tip payments regression | 7 |
| Startup artifact guard | 10 |

Selector regressions cover internal-state precedence, missing/unverified source
links, multiple sites, empty scope, inactive historical choices, selected aliases,
no scope widening, homonyms, stable sorting, bounded SELECT queries, no writes,
Bank identity-kind separation, and Tips HTML/CSV canonical scope validation.
HTTP tests check escaped names, site/inactive labels and exclusion of aliases.
Bank regression used a metadata-built disposable schema. Directory HTTP exercised
the real full migration chain and previous-head populated migration. The startup
guard ran against a normalized LF staging package. git diff --check passed.

Test-only issues corrected before final success: SQLite's explicit BEGIN is a
read-only lifecycle statement, not a data mutation; Flask context processors need
separate connections, so the new HTTP fixture uses a disposable file snapshot;
the snapshot backup connection is explicitly closed before Windows cleanup.

## 4. Files and traceability

Specification: 01 Domains/Shared Domains/Employee Directory/README.md.
Implementation: employee_directory.py; employee_directory_routes.py; directory
list/detail templates; Tips app.py and host_audit.html; Bank configuration.py and
_bank_source_modal.html. Tests extended in test_employee_directory.py and
RF-One Web/tests/test_employee_directory_http.py. Startup manifest refreshed.
Step 1 implementation and report remain preserved in the working tree.

Staged guard artifact: %TEMP%/rfone-employee-selectors-8d6lur5w.
Logs: %TEMP%/rfone-selector-directory-http.log and %TEMP%/rfone-selector-bank.log.
Recovery/reference: local diff against 9764ef6, separating the preserved step 1
changes described in EMPLOYEE_DIRECTORY_CONSUMERS_001_REPORT.md.
AWS continues to run the previously deployed release until an explicit release.
