# REPORT

## 1. Cause and correction

Registry replaced the directory navigation without exposing Clover identity
confirmation. The existing attribution service was intact. Registry now displays
pending identities, location and individual held shifts in location time. Explicit
confirmation calls the existing `employee_directory.attach_link` transaction,
including attribution and audit. It never guesses identities or grants access.
Tips blockers now name Registry and link administrators to the confirmation queue.
Both pages have updated contextual Help using the shared component.

## 2. Verification

Four isolated HTTP/integration tests pass: seven held shifts recovered, duplicate
confirmation rejected without duplicate shifts, invalid person rolls back,
explicit new-person confirmation succeeds, CSRF and access enforced. Displayed
times are verified in America/New_York. Disposable databases were removed.

The existing local runtime at http://127.0.0.1:5094/admin/roles returns 200 and
shows six pending identities, shift details and Help. Home, Bank, Compensation,
Projects, Organization, Wines, Tips and Selection also return 200. Kitchen returns
403 (outside this change). No actual identities were confirmed on the user's behalf.

The How Works checker introduces no new errors and resolves Registry coverage.
Its full run still reports 16 unrelated discrepancies for interview/wine pages
and missing visual-menu/training templates. A global release check is not passing.
Tracked changed files pass `git diff --check`.

## 3. Scope and references

Local development only. No publication, AWS modification, grant changes or Tips
finalization. Existing unrelated edits were preserved. The local launcher now
selects Italian for the added content; shared default remains English.

Runtime source: `C:/Users/servi/.codex/worktrees/edee/RF One/tmp/git-anagrafica-release/03 Software`.
Implementation: `RF-One Web/role_profile_routes.py`, `registry_clover.py`,
`templates/_registry_clover.html`, `templates/_registry_help.html`,
`templates/help/registry.html`, `templates/help/tips_validation.html`,
`templates/tips_validation_run.html`, and
`RF-One Data Store/rfone_data_store/tips/calculation_run_service.py`.
Test: `RF-One Web/tests/test_registry_clover_confirmation.py`.
Functional documentation: `01 Domains/Shared Domains/Employee Directory/README.md`.

Operator journey: Registry → choose the correct person for each Clover identity →
confirm → recalculate the affected Tips period → finalize the recalculated period.
