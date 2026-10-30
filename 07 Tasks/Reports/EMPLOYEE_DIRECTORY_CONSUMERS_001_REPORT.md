# REPORT — Canonical employee consumers, step 1

Date: 2026-10-29 (America/New_York).
Status: implemented and verified locally; not deployed to AWS.
Baseline: 9764ef6, branch codex/employee-directory.

## 1. Authorized scope

Complete canonical identity consumption in Tips, role bootstrap and payroll.
No account/Bank/Selection identity redesign. No Clover writes.

## 2. Changes

- Employee Directory exposes employees_for_locations(): canonical people only,
  selected by explicit source links or legacy origin, without multiplying rows.
  Missing links remain usable historical evidence; pending links assign no person.
- Tips imported orders, payments and shifts, plus order drill-down, display names
  through RF-One employee foreign keys rather than unscoped Clover IDs.
- Host audit and historical payment imports use canonical location membership.
- ADP matching searches all canonical people with evidence in restaurant locations;
  existing mappings resolve retired IDs. Existing exact-name matching policy is
  preserved; no fuzzy identity merge added.
- Profile bootstrap selects shared people, isolates roles belonging to other
  linked workplaces, and derives new assignment location from role evidence.
  Ambiguous multi-site role evidence leaves location unspecified. Existing
  one-active-role-per-person-per-restaurant rule and history are preserved.
- Fresh snapshot comparison uses source employee links for each role location.
- Updated approved specification and startup artifact manifest. No new migration.

## 3. Verification

All final checks passed on isolated local databases:

| Check | Passed |
| --- | ---: |
| Employee directory, including four new consumer regressions | 22 |
| Historical tip payments | 7 |
| Profile bootstrap validation | 14 |
| Payroll engine (full migration path) | 52 |
| Imported Clover data HTTP | 27 |
| Tips access and order drill-down HTTP | 61 |
| Startup guard on normalized staged release artifact | 10 |

New regressions cover second-site visibility, duplicate-free selection, empty
scope, SQL scope, retained missing links, retired aliases, ADP second-restaurant
matching, repeatable role bootstrap with a distinct source role at the other
site, and identical external employee IDs at different merchants.

The final cross-merchant HTTP regression and drill-down suite used metadata-built
throwaway schemas. The original imported HTTP suite and payroll suite also ran
through the full existing migration chain. Profile final validation used a fresh
in-memory schema. git diff --check passed.

Initial test failures were corrected: historical evidence fixtures needed the
new shared link table; a new role fixture lacked source_system_id; an overly
broad role filter suppressed the pre-existing unlinked-foreign-role anomaly.
Final behavior preserves that anomaly while ignoring legitimate other-site roles.

## 4. Delivery and recovery

No AWS resources, production records, payroll approvals, payments or source
snapshots were changed. No migration or production backup was needed.
Changes remain reviewable in the local working tree against baseline 9764ef6.
Guard staging: %TEMP%/rfone-canonical-consumers-cuokyfgx.
HTTP logs: %TEMP%/rfone-shared-tips-http.log and
%TEMP%/rfone-canonical-drilldown.log.

Future deployment must package normalized LF source files as verified by the
startup manifest, rebuild the consuming apps and preserve current worker startup
verification. This task does not certify a running AWS release.
