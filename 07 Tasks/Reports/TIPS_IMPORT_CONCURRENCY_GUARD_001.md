# TIPS_IMPORT_CONCURRENCY_GUARD_001 — Implementation Report

Scope: prevent accidental duplicate/concurrent execution of the same Tips Clover
import (the `sqlite3.OperationalError: database is locked` failure caused by
clicking "Import from Clover" more than once). Tips content/semantics,
distribution logic, and Clover ingestion behavior are unchanged.

---

## Files changed

- `03 Software/RF-One Data Store/rfone_data_store/models.py` — `IngestionRun`
  gains `lock_key` (nullable `String(128)`) plus a UNIQUE index on it.
- `03 Software/RF-One Data Store/migrations/versions/c4e8a1f6b3d9_add_ingestion_run_lock_key.py`
  (new) — additive migration adding the column/index; head is now `c4e8a1f6b3d9`
  (was `a7b3e9c1f5d2`).
- `03 Software/RF-One Data Store/rfone_data_store/tips/clover_import_service.py` —
  `import_clover_period` now acquires the execution guard before any Clover
  fetch and guarantees the guard is released on every exit path. New:
  `ImportAlreadyRunningError`, `_import_lock_key`, `_acquire_import_lock`,
  `_finalize_import_run`, `_safe_error_summary`.
- `03 Software/Tips/app.py` — `run_import()` catches `ImportAlreadyRunningError`
  and flashes a clean message instead of a stack trace or a second concurrent
  writer.
- `03 Software/Tips/templates/home.html` — the import form's submit is guarded
  client-side (disable + relabel + block re-submit).
- `03 Software/Tips/templates/base.html` — `button:disabled` style so the
  disabled state is visibly distinct.
- `03 Software/RF-One Data Store/rfone_data_store/tips_import_concurrency_guard_validation.py`
  (new) and `03 Software/RF-One Data Store/test_tips_import_concurrency_guard.py`
  (new) — the test suite (task §8).

## Guard implementation

`IngestionRun.lock_key` is the execution token (task §5): non-NULL only while
a run is `RUNNING`, cleared back to `NULL` the instant it reaches
`COMPLETE`/`PARTIAL`/`FAILED`. A UNIQUE index on that column makes "another
same-scope import is already running" a database-enforced constraint rather
than an application-level check-then-act race: two submissions attempting to
insert the same `lock_key` can never both succeed, even against SQLite's
single-writer file lock. The loser's `IntegrityError` is translated into
`ImportAlreadyRunningError`.

Guard scope (`_import_lock_key`): `TIPS_CLOVER_IMPORT:{restaurant_id}` — same
Restaurant/Location + import function/type, **not** also keyed on the
requested period. This is a deliberate judgment call: the failure this task
fixes is a property of the one shared SQLite *file*, not of any one period,
so scoping by period as well would still let two different-period imports
for the same restaurant collide. One RUNNING Tips Clover import per
restaurant at a time is the guard granularity that actually prevents the
reported failure.

`import_clover_period` now:
1. Resolves the Clover Location (DB-only, no network call — unchanged).
2. Calls `_acquire_import_lock`, which inserts a `RUNNING` `IngestionRun` row
   and **commits immediately**, in its own short transaction (task §7),
   before any Clover fetch. Raises `ImportAlreadyRunningError` if the insert
   collides with an existing `RUNNING` lock.
3. Runs the existing fetch/upsert logic (byte-for-byte unchanged) inside a
   `try` block.
4. On success (including the pre-existing early-return path when the
   Payments fetch itself fails, which is not an exception): `_finalize_import_run`
   sets `COMPLETE`/`PARTIAL` and clears `lock_key`.
5. On any exception: rolls back the in-progress (uncommitted) transaction —
   discarding any partial writes from that failed attempt — then marks the
   *same* `IngestionRun` row `FAILED`, stores a safe error summary
   (`_safe_error_summary`: exception type + message only, truncated, never a
   traceback), clears `lock_key`, commits, and re-raises the original
   exception so existing error propagation to the caller is unchanged.

One `IngestionRun` row per call throughout (created once, mutated through its
lifecycle) — no change to the "each import run creates its own provenance
row" invariant the existing test suite already asserted.

## UI behavior

`Tips/templates/home.html`'s submit handler (`guardImportSubmit()`) disables
the button, relabels it "Importing...", and blocks any further `submit`
event from the same page via a `data-submitting` flag — all before the
browser sends the POST, per task §2. This is a UX nicety only; it is not
relied on for correctness (task §3's explicit "Do not rely on UI protection
alone").

## Backend behavior

`Tips/app.py`'s `run_import()` catches `ImportAlreadyRunningError` specifically
and flashes "An import is already in progress. Please wait for it to finish."
— no second Clover fetch and no second write transaction occur, since the
exception is raised before either.

## Failure recovery

A `FAILED` run always has `lock_key = NULL` (set in the same commit that sets
`status = "FAILED"`), so a failed import never leaves the system permanently
locked — the very next request for that restaurant is accepted normally.
Verified by test.

## Tests / results

New suite `test_tips_import_concurrency_guard.py` — **15/15 checks passed**:
- first import request is accepted (no errors; `IngestionRun` reaches `COMPLETE`
  with `lock_key` cleared).
- a second, concurrent request for the same restaurant is rejected
  (`ImportAlreadyRunningError`) — asserted with zero Clover calls made
  (`client.calls == []`) and zero rows written (no leaked Order/Payment).
- rejecting the concurrent request never creates a second `RUNNING` row.
- the same period can be intentionally imported again once the prior run
  completes.
- a Clover fetch failure (injected via a `RaisingCloverClient` fake) is never
  silently swallowed, marks the run `FAILED`, releases `lock_key`, stores a
  safe (non-traceback) error summary, and a subsequent import for the same
  restaurant/period is then accepted — the guard was released.
- static check that the shipped `home.html` actually wires the disable/
  relabel/block-resubmit handler to the form (see limitation below).

Regression — pre-existing suites still pass unchanged:
- `test_tips_clover_import.py`: 38/38 (idempotent re-import, tip finalization,
  refunds, shifts, employee mismatches, etc. — all untouched).
- `test_tips_distribution_rules.py`: 24/24.

All three suites provision their own disposable SQLite database
(`resolve_test_database_url` / `create_disposable_test_database_url`) and
never touch the shared operational database; no test contacts Clover
production.

## Unresolved issues / limitations

- **"Button is disabled after first submit"** is verified by a static check
  on the template source (the handler exists and is wired to the form), not
  a real browser click-through — no browser/JS test runner is available in
  this environment. Manual verification in a browser is recommended before
  relying on this for a demo.
- **Crash recovery / stale locks**: if the process is killed (not merely an
  exception) between acquiring the lock and reaching either the success or
  the exception handler, the `RUNNING` row (and its `lock_key`) can be left
  stuck indefinitely — there is no lock-timeout/expiry mechanism. Task §7
  explicitly excludes queues/workers from this task's scope, and this is
  consistent with that boundary, but it is a genuine open gap if a hard
  process crash (not a Python exception) is a realistic concern in
  production. Flagging rather than hiding it, per repository instructions.
