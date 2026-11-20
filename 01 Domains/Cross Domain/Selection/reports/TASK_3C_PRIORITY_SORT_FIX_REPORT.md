# TASK 3C-MICRO-FIX — Review Queue Priority Sort Order: Implementation Report

## 1. What changed

The Review Queue's `sort_by="priority"` mode previously ordered Applications by the Review Priority category string alphabetically (so, descending, it produced `STANDARD, LOW_PRIORITY, INTERESTING, HIGH_PRIORITY` — the opposite of the operationally correct order). This was a known, explicitly documented limitation of Task 3C-FIX.

Priority sorting now uses the fixed operational order:

```
HIGH_PRIORITY -> INTERESTING -> STANDARD -> LOW_PRIORITY
```

applied to `Application.review_priority_effective` (the EFFECTIVE Review Priority — i.e. a Selezionatore override, when present, controls the queue position, not the system-proposed value). Within the same priority category, Applications are ordered by `applied_at` (newest first); if that is ever equal, `Application.id` (descending) is used as a deterministic tie-breaker. No numeric rank or position field was introduced — Applications are still never numbered 1..N, only ordered.

All other sort modes (`applied_at`, `target_role`, `status`), all existing filters (priority, workflow status, target role, application date via default sort, repeated-applicant), and all Task 2A/2B/3A/3A-FIX/3B/3C/3C-FIX behavior are unchanged.

## 2. Files changed

- `03 Software/RF-One Data Store/rfone_data_store/selection/application_service.py` — `list_applications()`: removed `"priority"` from the generic alphabetical `_SORT_COLUMNS` map; added `_REVIEW_PRIORITY_ORDER` (built from the existing `core.signal_model.REVIEW_PRIORITY_CATEGORIES` tuple, which was already defined in the correct HIGH→LOW order — reused rather than re-declared, so the two can never drift apart) and a dedicated branch that builds a SQL `CASE` expression mapping each category to its rank, sorts by that rank first, then by `applied_at` descending, then by `id` descending.
- `03 Software/RF-One Data Store/rfone_data_store/selection_validation.py` — added `_assert_selection_3c_micro_fix()` (targeted checks 3C-MICRO-FIX-A through G, described below) and registered it in `run_validation()` immediately after `_assert_selection_3c_fix()`.

No route, template, filter, or workflow-status/notes/identity-resolution code was touched. No files outside the Selection implementation were modified.

## 3. Final sort behavior

`GET /applications?sort=priority` now returns Applications ordered:

1. All `HIGH_PRIORITY` (by effective priority), newest `applied_at` first.
2. All `INTERESTING`, newest first.
3. All `STANDARD`, newest first.
4. All `LOW_PRIORITY`, newest first.

The effective priority (which reflects any Selezionatore override) drives this order, never the system-proposed priority alone; both continue to be displayed on the Review Queue as before. All other filters (priority, workflow status, target role, repeated-applicant) and sort modes are applied exactly as before this fix.

## 4. Targeted tests and results

Added `_assert_selection_3c_micro_fix()` to `selection_validation.py` (run via `run_validation()`, same synthetic-fixture/rollback pattern as every other Task 3C(-FIX) check group). It builds 5 synthetic Applications in a dedicated restaurant, sets their effective Review Priority via `human_override_priority` (with two of them given a deliberately opposite system-proposed priority to isolate effective-vs-system behavior), gives them distinct `applied_at` dates, and asserts on `list_applications(sort_by="priority")`:

- **3C-MICRO-FIX-A**: HIGH_PRIORITY Applications appear before INTERESTING ones.
- **3C-MICRO-FIX-B**: INTERESTING Applications appear before STANDARD ones.
- **3C-MICRO-FIX-C**: STANDARD Applications appear before LOW_PRIORITY ones.
- **3C-MICRO-FIX-D**: an overridden EFFECTIVE priority controls queue position even when the system-proposed priority disagrees.
- **3C-MICRO-FIX-E**: within the same priority category, the newer Application appears before the older one.
- **3C-MICRO-FIX-F**: no numeric rank/position field is introduced.
- **3C-MICRO-FIX-G**: the existing Review Priority filter still narrows the queue correctly under the corrected sort.

**Execution status: NOT RUN.** This environment has no usable Python interpreter (only an inert Windows Store `python.exe` alias, and one unrelated, inaccessible venv shim under a different user profile) — `python test_selection_engine.py` (which would run this new check group alongside all 139 pre-existing Task 2A/2B/3A/3A-FIX/3B/3C/3C-FIX checks, per Task 3C-FIX's own report) could not be executed here. This is reported as an unresolved item rather than hidden.

In place of execution, the change and the new test were verified by manual code trace: `core.signal_model.REVIEW_PRIORITY_CATEGORIES` is confirmed already defined as `(HIGH_PRIORITY, INTERESTING, STANDARD, LOW_PRIORITY)` (`core/signal_model.py:63`), so `_REVIEW_PRIORITY_ORDER` derived from it maps to ranks `0, 1, 2, 3` in that exact order; the SQLAlchemy `case(*mapping.items(), value=..., else_=...)` construct used is the documented, version-stable form for SQLAlchemy 2.0 (the version pinned in `requirements.txt`); and the fixture/assertion logic was traced step by step against `list_applications()`'s new branch to confirm the expected resulting order `[app_high_newer, app_high_older, app_interesting, app_standard, app_low]` satisfies every one of checks A–G.

**Product Owner action needed:** run `python test_selection_engine.py` (from `03 Software/RF-One Data Store`, with `RFONE_DATABASE_URL` set as usual) in an environment with the project's Python/SQLAlchemy installed, to get the actual pass/fail confirmation for the 7 new checks plus the pre-existing suite (including the existing Task 3C-FIX checks, which this change does not touch).
