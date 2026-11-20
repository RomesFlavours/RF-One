# TECHNICAL_CONNECTORS_STRUCTURE_001 — Implementation Report

## 1. Previous Clover location

`rfone_data_store/ingestion/clover/` (mapping, ingest/upsert, enrichment,
parser, reader, reconciliation, plus the acquisition/live-sync orchestration
added by CLOVER_DATA_ACQUISITION_ARCHITECTURE_001). Framed at the time as
"Restaurant-level shared acquisition" and keyed everywhere by `restaurant_id`
— a Domain-specific business concept the connector should never have needed.

## 2. New Technical/Connectors/Clover structure

```
rfone_data_store/
├── technical/                      NEW — shared technical infrastructure
│   ├── __init__.py
│   └── connectors/                 NEW — external system integrations
│       ├── __init__.py
│       └── clover/                 the Clover connector (moved, whole package)
│           ├── __init__.py
│           ├── acquisition.py      Historical Backfill + Live Sync entry point, guard, recovery
│           ├── live_sync.py        near-real-time polling loop
│           ├── mapping.py          raw Clover dict -> canonical column-kwargs
│           ├── ingest.py           idempotent upsert-by-source-identity
│           ├── enrichment.py       dedicated-endpoint catch-up enrichment
│           ├── parser.py, reader.py, reconciliation.py  (full bulk-pipeline support)
├── ingestion/
│   └── common.py                   unchanged — generic, non-Clover-specific (payload_hash, utc_now)
```

`03 Software/RF-One Data Store/rfone_data_store/` is where all shared
library code in this repository already lives (Tips, Payroll, Purchasing,
Sales-validation, etc. are all its subpackages) — no existing precedent
puts shared library code as a sibling of that package, so `technical/` was
created inside it rather than as a new top-level folder next to
`00 Core/`/`01 Domains/` in the documentation tree. This is the "closest
equivalent appropriate to the existing repository layout" the task allows
for. Only `Technical/Connectors/Clover` was created — no empty placeholder
folders for Messaging/Scheduler/EventBus/Storage/Observability.

The ENTIRE `ingestion/clover/` package moved, not just `acquisition.py`/
`live_sync.py`: `mapping.py`/`ingest.py`/`enrichment.py`/`parser.py`/
`reader.py`/`reconciliation.py` are equally Clover-connector responsibilities
(provider-specific mapping, idempotent upsert, API client reuse) — leaving
them behind would have fractured the connector across two locations.
`ingestion/common.py` (a generic `utc_now`/`payload_hash` helper, also used
by Tips' distribution engine) is genuinely source-independent and stayed
put.

## 3. Files moved/changed

**Moved (whole directory, contents unchanged except import paths):**
`rfone_data_store/ingestion/clover/*.py` → `rfone_data_store/technical/connectors/clover/*.py`.

**New:** `rfone_data_store/technical/__init__.py`, `rfone_data_store/technical/connectors/__init__.py`.

**Rewritten (restaurant_id → location_id API correction, see §4):**
`acquisition.py`, `live_sync.py`.

**Modified (import path fixes, +one relative-dot-depth from the move):**
`mapping.py`, `ingest.py`, `enrichment.py`, `reader.py`, `reconciliation.py`
(sys.path `parents[4]`→`parents[5]` where used).

**Modified (consumers — import path + API call-site updates):**
- `03 Software/Tips/app.py` — new import path; added `_resolve_clover_location_id()`
  (Restaurant → Location join, kept in Tips since it's a Restaurant-Domain
  concern); Historical Backfill route now resolves and passes `location_id`.
- `rfone_data_store/tips/distribution_engine.py` — new import path for
  `get_order_settlement_time` (function itself unchanged).
- `ingest_clover.py`, `enrich_clover_cache.py` — new import paths only (the
  full historical bulk pipeline; untouched otherwise).
- `clover_live_sync.py`, `clover_acquisition_status.py` (top-level CLI
  scripts) — new import paths; `--restaurant-id` → `--location-id`.
- `rfone_data_store/clover_acquisition_validation.py`,
  `rfone_data_store/clover_live_sync_validation.py`,
  `rfone_data_store/tips_import_concurrency_guard_validation.py` — new
  import paths; all `restaurant_id=` call-site kwargs → `location_id=`.

**Documentation:** `PROJECT_STATE.md` (new Technical-layer status bullet,
rewritten Clover-connector bullet); `07 Tasks/Reports/
CLOVER_DATA_ACQUISITION_ARCHITECTURE_001.md` (a short "superseded structural
note" added at the top, pointing here — its own historical body left
unchanged, per this repository's convention of not rewriting historical
task reports).

## 4. Restaurant-specific assumptions removed

- `import_clover_period(session, *, restaurant_id, ...)` → `(session, *,
  location_id, ...)`. The connector no longer performs any Restaurant
  resolution at all.
- `_resolve_clover_location(session, restaurant_id)` (joined through
  `RestaurantLocation`) → `_resolve_clover_merchant(session, location_id)`
  (a direct `Location` + `SourceSystem` lookup — no Restaurant join).
- Lock key: `CLOVER_ACQUISITION:{restaurant_id}` → `CLOVER_ACQUISITION:{location_id}`.
- `ImportSummary.restaurant_id` field → `ImportSummary.location_id`.
- `get_latest_acquisition_status`/`reap_stale_acquisition_run`/
  `compute_next_sync_window`/`run_live_sync_cycle` — all `restaurant_id` →
  `location_id`; `get_latest_acquisition_status` no longer needs to resolve
  a merchant at all (queries `IngestionRun.location_id` directly).
- CLI flags: `--restaurant-id` → `--location-id` in both
  `clover_live_sync.py` and `clover_acquisition_status.py`.
- No new framework was invented: `Location`/`Merchant`/`SourceSystem`
  already existed in `models.py` as RF-One's own organizational/integration
  model (a Location already carries `source_location_id`, the external
  identifier; `Merchant` and `SourceSystem` already express "external
  account"). The connector now uses exactly these, nothing new.
- Restaurant-scoped parameters that legitimately remain elsewhere
  (`distribution_engine.py`'s Tip calculation, `seed_tip_distribution_rules.py`,
  `bootstrap_restaurant_profile.py`, Payroll scripts) were left untouched —
  those are genuine Restaurant-Domain concerns, not connector code.

## 5. How consumers now access Clover

- **Tips (Historical Backfill)**: `Tips/app.py` resolves its Restaurant's
  Clover `location_id` via a new, small `_resolve_clover_location_id()`
  helper (a `RestaurantLocation` join — a Restaurant-Domain concern, kept in
  Tips, never inside the connector), then calls
  `technical.connectors.clover.acquisition.import_clover_period(location_id=...)`.
- **Live Sync**: `clover_live_sync.py --location-id N` (was `--restaurant-id`)
  runs independently, calling the same connector directly with a known
  `location_id` — an operator or a future scheduler supplies it (found via
  the same Restaurant → Location join if starting from a Restaurant).
- **Tip Distribution Engine**: imports `get_order_settlement_time` from the
  connector's new path (`technical.connectors.clover.acquisition`) — this
  function takes an `order_id`, never a `restaurant_id`/`location_id`, so it
  was otherwise unaffected.
- **Full historical bulk pipeline** (`ingest_clover.py`): unchanged
  behavior, new import paths only.
- **Status/recovery**: `clover_acquisition_status.py --location-id N [--reap]`.

## 6. Documentation updated

- `PROJECT_STATE.md`: new bullet stating the Core/Domains/Technical
  distinction (Core = universal logic; Domains = functional/business logic;
  Technical = shared technical infrastructure; Technical/Connectors =
  external integrations usable by Core and/or Domains); rewrote the Clover
  bullet to describe it as the Clover Technical Connector, Location-scoped.
- `07 Tasks/Reports/CLOVER_DATA_ACQUISITION_ARCHITECTURE_001.md`: added a
  short superseded-note pointing to this report; historical body unchanged
  (this repository's convention: never rewrite a historical task report's
  own account of what was built and why — correct the live reading
  experience with a pointer instead).
- Every relocated/rewritten module's own docstring (`acquisition.py`,
  `live_sync.py`, both `__init__.py`s, `Tips/app.py`) now states the Clover
  connector explicitly as a Technical cross-domain connector — not "outside
  Tips" and not "Restaurant-level."
- **Not changed** (judged out of this task's scope — a bigger, separate
  decision): CLAUDE.md's own canonical top-level structure list. The
  Technical layer was realized as a code package
  (`rfone_data_store/technical/`) inside the existing Software layer, not as
  a new top-level numbered documentation folder alongside `00 Core/`/
  `01 Domains/` — introducing the latter is a foundational, repo-wide
  structural decision (CLAUDE.md itself gates that kind of change behind an
  explicit `TASK_CORE_*`-style process), not something this connector-
  relocation task should do unilaterally.
- Two stray comment-only mentions of the old `ingestion/clover/` path in
  unrelated files (`profile/source_snapshot.py`, `sales_validation.py`)
  were left as-is — cosmetic, in files outside this task's scope
  ("do not refactor unrelated code").

## 7. Validation / test result

| Suite | Result |
|---|---|
| `test_clover_acquisition.py` | 38/38 |
| `test_clover_live_sync.py` (+1 new non-Clover-Location check) | 8/8 |
| `test_tips_import_concurrency_guard.py` | 26/26 |
| `test_tips_distribution_rules.py` | 24/24 |
| `test_tips_distribution_engine.py` | 29/29 |
| `test_organization_validation.py` | 14/14 |
| `test_restaurant_profile_bootstrap.py` | 14/14 |
| `test_purchasing_engine.py` (shared-schema sanity check) | 24/24 |

Plus two Flask/CLI end-to-end smoke tests (disposable database, no real
browser available in this environment): (a) `/historical-backfill` runs
successfully through the new connector path, producing an `IngestionRun`
scoped by `location_id` with the new `CLOVER_ACQUISITION:{location_id}` lock
key and `location_id=...` notes format; (b) `clover_acquisition_status.py
--location-id N` correctly reports it. All suites/smoke tests run against
disposable databases only; none contact Clover production.

Explicit validation checklist:
1. Clover code now lives under `technical/connectors/clover/` — confirmed.
2. No Clover acquisition implementation remains under `tips/` — confirmed
   (only `distribution_engine.py`'s import path, pointing at the connector).
3. No Clover acquisition implementation remains keyed by `restaurant_id` —
   confirmed (§4); Restaurant resolution lives only in the Domain-layer
   caller (`Tips/app.py`).
4. Existing consumers still work — confirmed (regression suite + smoke
   tests above).
5. Current Clover acquisition tests still pass — confirmed (38/38, 8/8,
   26/26).
6. Historical Backfill still works — confirmed (smoke test).
7. Live Sync still works — confirmed (`test_clover_live_sync.py`, including
   checkpoint continuity between Backfill and Live Sync).
8. Imports/references updated correctly — confirmed by full-repo grep sweep
   for the old `ingestion.clover`/`ingestion/clover` path and for
   `--restaurant-id` in connector-related CLI scripts; zero remaining
   functional references (only the two cosmetic comment mentions in §6).

## 8. Blockers

None. `reconciliation.py` (part of the moved package, used only by
`ingest_clover.py`'s full bulk pipeline, never by the automated test suites)
has a pre-existing, unrelated environment gap on this Windows Python
install — `ModuleNotFoundError: No module named 'tzdata'` when it evaluates
`ZoneInfo("America/New_York")` at import time. Confirmed pre-existing (not
introduced by this move: the only change to that file was its import-path
fix; `tzdata` is simply not installed in this environment) and outside this
task's scope to fix.
