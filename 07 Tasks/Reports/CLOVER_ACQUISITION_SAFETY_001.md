# CLOVER_ACQUISITION_SAFETY_001 — a failed Clover read is never an empty answer

**Status: completed and deployed on AWS (2026-09-26).** Commit `4661aa7`
(+ this report). Follows the incident in
[CLOVER_ACQUISITION_JOBS_001](CLOVER_ACQUISITION_JOBS_001.md) §3.

## 1. Problem

A Clover read that failed (401/403, wrong merchant, 404, 429, 5xx, network,
incomplete pagination) reached the acquisition engine as an **empty list**,
and the engine applied it: Employees/Tenders/Devices → no links, Shifts → 0,
catalog/roles/line items → nothing, a per-item tax lookup → 0 %, an
unreadable Order → skipped (PARTIAL), a failed Refunds scan → FAILED but with
the run's writes kept.

## 2. Change

- `technical/connectors/clover/source_guard.py`:
  - `verify_clover_access()` — run by `import_clover_period()` right after the
    Location lock, **before any fetch or write**: the configured merchant must
    be the Location's `source_location_id`; `GET /v3/merchants/{id}` must
    succeed and return that id; every collection the job reads must answer.
  - `require_complete()` / `require_ok()` — every Clover read in
    `acquisition.py` and `historical_backfill_detail.py` goes through them. A
    successful answer (possibly a real empty list) is returned; anything
    else raises `CloverAcquisitionError` with a plain message.
- Raising rolls back everything the run wrote (one transaction), ends it
  FAILED with that message in `error_summary`; the last successful sync
  does not move. Refunds are now read with Payments, before any write.
- **Mandatory sources = every source the job reads** (the project defines
  none as optional). Every mode: Orders, Payments, Refunds, Employees,
  Shifts. Full scope (Backfill, Sync Now) also: Tenders, Devices,
  Categories, Modifier Groups, Discounts, Tax Rates, Order Types, Items,
  Roles, Order line items, per-item tax rates. Live Sync does not read
  Tenders/Devices from Clover (resolved from RF-One), so they are not its
  precondition.
- Kept: a real empty line-items answer still falls back to the Order's
  nested `lineItems` (existing project rule). Mapping, upsert, Business Date,
  Tips logic unchanged.

## 3. Tests

`test_clover_acquisition_safety.py` — 40 checks: invalid token, wrong
merchant, Clover answering for another merchant, Employees / Tenders /
Shifts denied, Clover error mid-job after writes began, truncated
pagination, valid empty answer. Each failure: FAILED, every table except
the job history identical, no link cleared, sync point unchanged, message
names the real cause. Mutation check: with the old "failure = empty list"
behaviour the same suite fails 26 of 40 checks. All Clover, Tips and HTTP
suites green.

## 4. Production

| Run | Test | Result |
|---|---|---|
| 23 | Sync Now through a temporary task definition with merchant `WRONGMERCH01` (shared secret untouched; definition deregistered after) | FAILED before any write: "Wrong Clover merchant for location 'Rome's Flavours - WP' (id 1): it expects Clover merchant PYQYB7SKB6V31, but the configured Clover merchant is WRONGMERCH01 …"; all 245 tables identical; sync point unchanged |
| 24 | Normal Sync Now from the page | COMPLETE (0 orders/payments — valid empty window, 2 shifts); sync point advanced |

Tips tables fingerprint identical throughout; 0 Orders/Payments without
their Employee link. Image `sha256:fa531fb5…`.

## 5. Not changed / open

- Correction/Reconciliation Poller (not active): its own Orders/Payments/
  Refunds cursor fetches keep their existing per-resource failure handling;
  the line-items and catalog reads it shares are now guarded.
- Live Sync runs the pre-flight on every cycle (6 small GETs) — acceptable
  while inactive; to revisit when it is enabled.
