# CLOVER_DATA_ACQUISITION_ARCHITECTURE_001 — Implementation Report

> **Superseded structural note (TECHNICAL_CONNECTORS_STRUCTURE_001):** this
> report's framing of Clover acquisition as "outside Tips" / "Restaurant-
> level shared acquisition" has been corrected. Clover acquisition is a
> **Technical cross-domain connector** (`rfone_data_store/technical/
> connectors/clover/`, not `ingestion/clover/`), with no concept of
> Restaurant at all — its unit of ownership is `Location`/`Merchant`/
> `SourceSystem`. See `07 Tasks/Reports/TECHNICAL_CONNECTORS_STRUCTURE_001.md`
> for the correction; this report's own historical content below (what was
> built, and why, at the time) is left unchanged.

## 1. Current problem found

- **Architectural**: Clover data acquisition (`import_clover_period`, its idempotent
  fetch/upsert logic, and its concurrency guard) lived entirely inside
  `rfone_data_store/tips/clover_import_service.py`, imported and triggered only by
  the Tips Flask UI's "Import from Clover" button. There was no operational path for
  near-real-time data at all — every module (Server Copilot, Server Performance,
  Sales) that would need current Clover facts had no acquisition mechanism except
  manually clicking a button inside Tips.
- **Concrete, live incident** (confirmed by direct read-only inspection of
  `data/rfone.db` before any code change): `ingestion_runs` row **id=5** was
  `status='RUNNING'`, `lock_key='TIPS_CLOVER_IMPORT:1'`, `finished_at=NULL`,
  started `2026-09-06 02:11:10` — exactly the manually-interrupted import
  described in the task. This row was permanently blocking every future Tips
  Clover import for restaurant_id=1 (the concurrency guard added by
  TIPS_IMPORT_CONCURRENCY_GUARD_001 has no self-recovery mechanism of its own).
  A stray `rfone.db-journal` file (1MB) also sat next to the database.
  - Verified via `PRAGMA integrity_check` (`ok`), zero Orders/Payments created
    after the run's start time, and the journal file's header already zeroed
    (SQLite's own "safely rolled back" marker, `journal_mode=delete`) — **no
    partial/corrupt data, no duplicate records**. The design that keeps the
    RUNNING-row commit in its own short transaction, separate from the heavy
    fetch/upsert work, is exactly why a hard kill left no partial writes:
    nothing but the lock row itself was ever committed.
  - The only real defect confirmed was the **orphaned RUNNING row / locked
    status** itself — item 9's other three concerns (corrupt data, duplicates)
    did **not** occur.

## 2. Files changed

**New — central acquisition layer (outside Tips):**
- `rfone_data_store/ingestion/clover/acquisition.py` — the central Clover data
  acquisition service (moved, not duplicated, from `tips/clover_import_service.py`).
- `rfone_data_store/ingestion/clover/live_sync.py` — near-real-time polling loop.
- `clover_live_sync.py` (top-level CLI) — runs the Live Sync loop.
- `clover_acquisition_status.py` (top-level CLI) — read-only status report +
  explicit manual recovery.

**New — tests:**
- `rfone_data_store/clover_acquisition_validation.py` + `test_clover_acquisition.py`
  (renamed/relocated from `tips_clover_import_validation.py` /
  `test_tips_clover_import.py` — same content, new import paths).
- `rfone_data_store/clover_live_sync_validation.py` + `test_clover_live_sync.py`.
- `rfone_data_store/tips_import_concurrency_guard_validation.py` — extended in
  place with staleness-recovery and status-report tests (kept its existing name;
  the guard it tests is generalized, but a full rename was judged unnecessary
  churn for this task).

**Removed:**
- `rfone_data_store/tips/clover_import_service.py` (moved to `acquisition.py`).

**Modified:**
- `03 Software/Tips/app.py` — imports the central module; `/import` route
  renamed to `/historical-backfill` (function `run_import` →
  `run_historical_backfill`), passes `mode=MODE_BACKFILL` explicitly; the
  "recent runs" query now matches the new `CLOVER_ACQUISITION...` notes prefix.
- `03 Software/Tips/templates/home.html`, `base.html` — "Import from Clover" →
  "Historical Backfill", with an explicit "not the normal way Clover data
  reaches RF-One" notice.
- `rfone_data_store/tips/distribution_engine.py` — imports
  `get_order_settlement_time` from the new central location (function itself
  unchanged; kept as a generic derived-fact helper, not Tips-private, since
  other future modules can equally need "when did this Order settle").
- `PROJECT_STATE.md` — new "Clover Data Acquisition" status bullet.

**Untouched (per task's explicit DO-NOT list):** Tips calculation logic
(`distribution_engine.py`'s actual algorithm), Server Copilot, `ingest_clover.py`'s
full historical bulk pipeline, `mapping.py`/`ingest.py` (reused as-is).

## 3. Live-sync architecture implemented

- **Single shared acquisition path**: `ingestion.clover.acquisition.import_clover_period()`
  is now the ONE fetch/mapping/upsert/guard implementation. Historical Backfill
  and Live Sync call it identically, differing only in how `period_start`/
  `period_end` are chosen and how often the call happens (`mode=` is recorded
  only for observability).
- **Live Sync** (`ingestion/clover/live_sync.py`): `compute_next_sync_window()`
  resumes from the last COMPLETE/PARTIAL acquisition run's own
  `source_window_end` (Backfill or a prior Live Sync cycle — both populate this
  identically, so a manual Backfill naturally advances Live Sync's own
  checkpoint) minus a 2-minute overlap buffer; falls back to `now - 1 hour` on
  the very first cycle. Default poll interval 15 seconds (`--interval-seconds`
  configurable; `--once` for cron/Task-Scheduler-style invocation instead of a
  long-running process).
- **Webhooks vs. polling (task §6)**: this repository has **no public HTTPS
  endpoint and no registered Clover webhook receiver anywhere** (verified by
  repo-wide search). Standing one up is an infrastructure/deployment decision
  outside a code change, so Live Sync implements the explicitly-allowed
  fallback: lightweight incremental polling. It is structured so a future
  webhook handler could call the exact same `import_clover_period(mode=
  MODE_LIVE_SYNC)` per affected Order/Payment with no change to the acquisition
  logic — only the trigger would differ.
- **Latency**: short interval + narrow checkpoint-advancing window means a
  settled Payment/Order is typically visible within one poll interval —
  seconds, not the old button-click-driven latency.
- **Concurrency**: one restaurant-scoped guard, `IngestionRun.lock_key =
  "CLOVER_ACQUISITION:{restaurant_id}"`, shared by *every* mode (renamed from
  the Tips-specific `TIPS_CLOVER_IMPORT:{restaurant_id}`) — a Live Sync cycle
  and a Historical Backfill can never write concurrently. A cycle that loses
  the race is not an error: it logs and retries next tick.

## 4. Backfill behavior

Historical Backfill is now explicitly framed (UI text, docstrings) as
**manual re-import/recovery only** — not the normal operational path. Its
underlying mechanics are byte-for-byte the same idempotent logic Live Sync
uses: date-range selection (From/Through in the Tips UI), safe re-import
(re-running a period upserts from Clover's current values, never duplicates —
unique-constraint-keyed upsert, unchanged), and it shares the same concurrency
guard as Live Sync, so the two can never corrupt each other's writes.

## 5. Interruption / recovery behavior

- **Verification** (task §9): confirmed via direct, read-only inspection of the
  real operational database — no partial/corrupt data, no duplicate records,
  `PRAGMA integrity_check` clean; the *only* real defect was the orphaned
  RUNNING row (locked status) itself.
- **Automatic self-heal** (task §10): `_reap_if_stale()` inside the lock-acquire
  path — if the run currently holding a restaurant's acquisition lock has been
  RUNNING longer than `_STALE_RUN_THRESHOLD` (30 minutes — generous enough for
  a large paginated Backfill, short enough to self-heal within a session), the
  next acquisition attempt (Backfill or Live Sync) automatically marks it
  FAILED with an explicit "AUTO-RECOVERED" note, releases its lock, and
  proceeds — never disturbs a run that is merely old-ish but still genuinely
  in progress.
- **Explicit status/recovery mechanism** (task §10): `get_latest_acquisition_status()`
  (read-only) and `reap_stale_acquisition_run()` (mutating, operator-triggered),
  exposed via `clover_acquisition_status.py --restaurant-id N [--reap]`.
- **Real-world fix applied**: the live incident (run id=5) was recovered using
  this exact mechanism. One wrinkle: its `lock_key` used the *pre-rename*
  `TIPS_CLOVER_IMPORT:1` format, so the new guard's own lock-key lookup
  couldn't find it automatically (harmless going forward — the old and new
  prefixes never collide, so it was no longer actually blocking anything
  either way) — it was recovered via one targeted, explicit update (same
  FAILED-status/cleared-lock/audit-note shape the automatic path produces),
  documented in its own `notes`. Confirmed after: zero RUNNING rows remain in
  `ingestion_runs`, and the stray `-journal` file is gone (SQLite's own
  cleanup, triggered by a subsequent connection).

## 6. Test result

| Suite | Result |
|---|---|
| `test_clover_acquisition.py` (renamed from `test_tips_clover_import.py`) | 38/38 |
| `test_clover_live_sync.py` (new) | 7/7 |
| `test_tips_import_concurrency_guard.py` (+11 new staleness/status checks) | 26/26 |
| `test_tips_distribution_rules.py` | 24/24 |
| `test_tips_distribution_engine.py` | 29/29 |
| `test_organization_validation.py` | 14/14 |
| `test_restaurant_profile_bootstrap.py` | 14/14 |
| `test_purchasing_engine.py` (shared-schema sanity check) | 24/24 |

Plus a Flask end-to-end smoke test (test client, disposable DB, no real
browser available in this environment): `/` shows "Historical Backfill" (no
more "Import from Clover"), `POST /historical-backfill` runs successfully,
the old `/import` route returns 404. And a `clover_acquisition_status.py`
CLI smoke test against a disposable DB reproducing a stale RUNNING row,
confirming detect → `--reap` → recovered end-to-end — before applying the
same flow to the real database.

All suites provision their own disposable database and never contact Clover
production. No test suite touched `data/rfone.db`; only the two explicit,
documented one-off operational fixes above did (reading the incident, then
recovering it).

## Confirmation

Only one Clover data acquisition implementation now exists, owned by
`rfone_data_store/ingestion/clover/` (outside Tips), used identically by
Historical Backfill (Tips UI trigger) and Live Sync (`clover_live_sync.py`).
The real orphaned RUNNING import has been recovered; zero RUNNING rows remain.
