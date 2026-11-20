# GLOBAL_INTEGRITY_FIX_001 — Test/Validation Database Isolation Report

**Scope:** Finding C-4 only (`07 Tasks/Reports/RF_ONE_GLOBAL_INTEGRITY_REVIEW_001.md`, §3). No business logic, Domain behavior, architecture, Identity/Authority, or tenant scoping was touched.

---

## 1. Files Changed

**Modified:**
- `03 Software/RF-One Data Store/rfone_data_store/database.py` — added the reusable safety guard (see §3).
- `03 Software/RF-One Data Store/test_payroll_engine.py`
- `03 Software/RF-One Data Store/test_tips_engine.py`
- `03 Software/RF-One Data Store/test_restaurant_profile_bootstrap.py`
- `03 Software/RF-One Data Store/test_organization_validation.py`
- `03 Software/RF-One Data Store/test_sales_validation.py`
- `03 Software/RF-One Data Store/test_selection_engine.py`

**Created:**
- `07 Tasks/Reports/GLOBAL_INTEGRITY_FIX_001_TEST_DATABASE_ISOLATION_REPORT.md` (this file).

**Not modified (already safe — reference patterns):**
- `03 Software/RF-One Data Store/test_purchasing_engine.py`
- `03 Software/Selection/test_batch_upload.py`

**Not modified (business logic, out of scope per §11 of the task):**
- `03 Software/RF-One Data Store/rfone_data_store/selection_validation.py` and the other `*_validation.py` modules — their internal commit/assert logic is unchanged; only the entry point that invokes them was fixed (see §5).

---

## 2. Unsafe Entry Points Found

All six shared the identical risk: they called `get_database_url()`, which silently falls back to the shared operational SQLite file (`data/rfone.db`) whenever `RFONE_DATABASE_URL` is unset, and then ran (or, for Selection, committed) synthetic fixture data against whatever database that resolved to.

1. `test_payroll_engine.py` (named in the task)
2. `test_restaurant_profile_bootstrap.py` (named in the task)
3. `test_tips_engine.py` (named in the task)
4. `test_organization_validation.py` (same risk, found via repository-wide search per §8)
5. `test_sales_validation.py` (same risk, found via repository-wide search per §8)
6. `test_selection_engine.py` (same risk; also the entry point for `selection_validation.py`, §6)

A repository-wide search (`test_*.py` and `*_validation.py` under `03 Software/`) confirmed no other entry point exhibits this pattern.

---

## 3. Isolation Strategy Chosen

Added three small, reusable functions to `rfone_data_store/database.py` (the existing home of all database-resolution logic), following the "smallest reasonable correction" instruction:

- **`resolve_test_database_url(label)`** — the single function all six fixed entry points now call instead of `get_database_url()`:
  - If `RFONE_DATABASE_URL` is unset → self-provisions a fresh disposable SQLite database (Pattern A, preferred per the task) via `create_disposable_test_database_url(label)`.
  - If `RFONE_DATABASE_URL` is set but resolves (by real filesystem path, not string comparison) to the shared operational default `data/rfone.db` → raises `UnsafeTestDatabaseError` and refuses to run (Pattern B safety net, satisfies requirement D).
  - If set to anything else → used as-is (explicit safe target).
  - Deliberately does not consult a `.env`-file fallback the way `get_database_url()` does — a test entry point defaults to self-isolation, not to whatever a developer's local `.env` happens to point at.
- **`create_disposable_test_database_url(label)`** — creates a throwaway SQLite file under the OS temp directory (never under this project's `data/` folder), migrates it to the current Alembic head, and returns its URL. Mirrors `test_purchasing_engine.py`'s "own disposable file" pattern and `test_batch_upload.py`'s `tempfile.mkstemp()` pattern, generalized into one helper.
- **`cleanup_disposable_test_database_url(url)`** — best-effort removal of a disposable file (plus `-wal`/`-shm`/`-journal` siblings) after a run. It only ever deletes files carrying the `rfone_test_` prefix this module itself generates, so it is always safe to call unconditionally — it is a no-op for a caller-supplied `RFONE_DATABASE_URL`.
- **`is_default_operational_database(url)`** — the underlying check, comparing resolved filesystem paths (not raw strings) so a differently-spelled URL pointing at the same file cannot bypass the guard.

Each of the six fixed `test_*.py` files now:
```python
url = resolve_test_database_url("<label>")
engine = create_configured_engine(url)
try:
    ...
    result = run_validation(session_factory)
finally:
    engine.dispose()
    cleanup_disposable_test_database_url(url)
```

Stale docstrings/warnings instructing the operator to manually set `RFONE_DATABASE_URL` were removed and replaced with a short note describing the new automatic behavior.

---

## 4. Safety Guard Behavior

| Scenario | Behavior |
|---|---|
| `RFONE_DATABASE_URL` unset | Fresh disposable SQLite DB auto-provisioned in the OS temp dir, migrated to head, used, then deleted. |
| `RFONE_DATABASE_URL` set to the shared default (`data/rfone.db`), any equivalent spelling | `UnsafeTestDatabaseError` raised before any session/engine touches it; process exits non-zero. |
| `RFONE_DATABASE_URL` set to any other (disposable/staging) path | Used as-is, no auto-provisioning, not deleted by the test (caller-owned). |

---

## 5. Selection Validation Handling

Per the task's explicit instruction not to rewrite `selection_validation.py`'s internals (its ~20 `_assert_*` helpers still perform real `session.commit()` calls with manual delete-based cleanup — unchanged), the fix was applied at its **only caller**, `test_selection_engine.py` (confirmed via repository-wide search — no other file imports `selection_validation.run_validation`). That entry point now runs the suite against a self-provisioned disposable database via `resolve_test_database_url("selection")`, and the disposable file is deleted afterward regardless of outcome (`finally` block). This satisfies the primary requirement (database isolation): even if an exception strikes between one of its internal commits and its own cleanup code, the entire disposable database file is discarded, so nothing can leak into a database that matters.

---

## 6. Other Test Suites Corrected

Beyond the three named in the task, the repository-wide search required by §8 found three more entry points with the identical risk, fixed identically:
- `test_organization_validation.py`
- `test_sales_validation.py`
- `test_selection_engine.py` (also covers §6/Selection)

No other `test_*.py`/`*_validation.py` file under `03 Software/` was found to depend on `RFONE_DATABASE_URL`/`get_database_url()` without already self-isolating.

---

## 7. Verification Performed

- Syntax-checked all seven changed files (`ast.parse`).
- Ran each of the six fixed entry points with `RFONE_DATABASE_URL` **unset**, confirming: a disposable SQLite file was created under the OS temp directory (visible in the printed, redacted "Database URL" line), migrations ran against it, and the file was removed afterward (no `rfone_test_*` files left in the temp directory post-run).
- Ran `test_payroll_engine.py` with `RFONE_DATABASE_URL` **explicitly set to the shared default** (`.../data/rfone.db`, several equivalent path spellings tried) and confirmed `UnsafeTestDatabaseError` is raised and the process exits non-zero before any engine/session is created against it.
- Ran with `RFONE_DATABASE_URL` explicitly set to a different, non-default path and confirmed it passes through unmodified (no auto-provisioning, no rejection).
- Recorded the shared operational database's (`data/rfone.db`) file size and modification time before running any test and again after all runs (including the rejected-unsafe-target attempt): **identical byte-for-byte (same size, same mtime)** — confirming zero writes ever reached it.
- Re-ran `test_purchasing_engine.py` and `Selection/test_batch_upload.py` unmodified to confirm the reference patterns still pass.

---

## 8. Test Results

| Suite | Result |
|---|---|
| `test_payroll_engine.py` (no env var) | SUCCESS — 52/52 checks passed |
| `test_tips_engine.py` (no env var) | SUCCESS — 54/54 checks passed |
| `test_restaurant_profile_bootstrap.py` (no env var) | SUCCESS — 14/14 checks passed |
| `test_organization_validation.py` (no env var) | SUCCESS — 14/14 checks passed |
| `test_sales_validation.py` (no env var) | SUCCESS — 27/27 checks passed |
| `test_selection_engine.py` (no env var) | SUCCESS — 633/633 checks passed |
| `test_purchasing_engine.py` (unmodified) | SUCCESS — 24/24 checks passed |
| `Selection/test_batch_upload.py` (unmodified) | SUCCESS — 38/38 checks passed |
| `test_payroll_engine.py` with `RFONE_DATABASE_URL` = shared default | Correctly refused (`UnsafeTestDatabaseError`), exit code 1 |

All required verification items (A–K, task §10) are satisfied.

---

## 9. Confirmation: Normal Operational Database Untouched

The shared local SQLite file (`03 Software/RF-One Data Store/data/rfone.db`) was checked for file size and modification time immediately before this task's changes were verified and again after every test run described in §7–8, including the deliberate attempt to point `RFONE_DATABASE_URL` at it. **Size and modification timestamp are unchanged.** No production/operational data was read from, written to, or migrated by any change in this task.

---

## 10. Limitations

- `resolve_test_database_url()`'s unsafe-target rejection only recognizes the shared file when the URL scheme is `sqlite:///...`; it does not (and, given this task's scope, should not) attempt to guess whether a non-SQLite `RFONE_DATABASE_URL` (e.g. a future PostgreSQL URL) is "the real one" — that determination is out of scope for this fix and would require an explicit environment/deployment convention, not a path comparison.
- `selection_validation.py`'s own internal commit/manual-cleanup pattern (§15/C-4 of the integrity review) is unchanged, as instructed; isolation is achieved by always running it against a disposable, discarded database rather than by making its internals transactionally pure. This is the outcome the task explicitly accepted as sufficient.
- No changes were made to `get_database_url()` or any other normal-runtime database resolution behavior.
