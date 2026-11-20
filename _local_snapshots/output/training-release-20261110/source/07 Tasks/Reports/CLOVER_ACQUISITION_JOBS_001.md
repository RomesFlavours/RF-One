# CLOVER_ACQUISITION_JOBS_001 — Clover acquisition as jobs (Live Sync, Sync Now, Historical Backfill)

**Status: completed and deployed on AWS (2026-09-26).** Commits `9f51b06`, `2c9982a`
and this report. Live Sync prepared, **not active**.

## 1. What changed

How a Clover acquisition is *started, windowed and tracked* — never how Clover
data is acquired. `acquisition.import_clover_period()` fetches, maps and
upserts exactly as before.

| Mode | Window | Trigger |
|---|---|---|
| Live Sync | now − 2 h → now (configurable, `RFONE_CLOVER_LIVE_SYNC_WINDOW_MINUTES`); from the last successful sync if that is older | a loop — **not active** until `RFONE_CLOVER_LIVE_SYNC_ENABLED` is set |
| Sync Now | last successful synchronization → now, no dates | a person, from any RF-One area (central service) |
| Historical Backfill | the chosen From/Through dates | a person, for recovery |

- Central service `rfone_data_store/technical/connectors/clover/acquisition_jobs.py`:
  accepts a job (status **QUEUED**, holding the existing Location lock), hands it
  to a launcher and returns; a separate process runs it (**RUNNING**, heartbeat)
  and it ends **COMPLETE / PARTIAL / FAILED** as the engine decides.
- One history: `ingestion_runs` gains `acquisition_mode`, `queued_at`,
  `heartbeat_at`, `orders_processed`, `payments_processed`, `shifts_processed`,
  `error_summary` (migration `b8d4e2f7a1c9`, additive; old rows' mode filled from `notes`).
- Last successful sync = latest window end of a COMPLETE/PARTIAL Sync Now or Live
  Sync run (bootstrap: latest successful Backfill). FAILED never moves it;
  a later Backfill of an old period never rewinds it.
- Sync Now uses Backfill's full scope (catalog, Order Item Tax, Order Discounts).
- Existing stale-run recovery extended: QUEUED > 15 min, or RUNNING without
  heartbeat for 5 min → FAILED; long runs that heartbeat are never reaped.
- Tips page "Clover Acquisition": Sync Now, Historical Backfill, Live Sync
  state, job history; polls and refreshes itself while a job runs.
- Unchanged: Tips rules, distribution, certified results, Run Tips,
  validation, finalization, Payroll, Mercury, correction poller.

## 2. AWS

| Item | State |
|---|---|
| Runner | ECS Fargate, cluster `rfone-jobs`, task def `rfone-clover-acquisition-job:1` (rfone-tips image) |
| Why | App Runner throttles CPU between requests; `rfone-tips` has no Internet egress (VPC without NAT) |
| ECS API endpoint | `vpce-03dc68cffc4932f8b`, SG `sg-0503f48dd3ae94599` |
| `rfone-tips` | image `sha256:ad6f5aef…`, `RFONE_CLOVER_JOB_LAUNCHER=ecs` + ECS variables |
| DB | snapshot `rfone-dev-pre-clover-acquisition-jobs-20260926t131546z`, then `b8d4e2f7a1c9` |
| S3 backup | `backups/source-pre-clover-acquisition-jobs-<ts>.zip` |

## 3. Stuck run and findings

- Run **17** (Backfill 2026-09-20→26, started 12:20:48 UTC): the gunicorn
  worker hung on the first TCP connect to Clover and was killed at 60 s
  (`WORKER TIMEOUT`, SIGKILL). No open DB transaction. Closed FAILED with
  `clover_acquisition_status.py --reap` (committed version). Root cause: no
  Internet egress from `rfone-tips`.
- First production launch (run 19) hung 60 s on the ECS API for the same
  reason → 500; fixed by bounded boto3 timeouts (`2c9982a`) and the ECS
  endpoint. Run 19 was auto-recovered FAILED by the new mechanism.
- **Incident:** secret `rfone-tips/clover-merchant-id` held a wrong 12-character
  value. Payments/Orders use the Location's merchant id and worked; Employees,
  Tenders, Devices, Shifts and catalog use the configured one and got 401,
  which the engine treats as an empty list. Test runs 20 and 21 therefore set
  `employee_id`/`tender_id` to NULL on 203 Orders / 217 Payments (source ids
  intact). Secret corrected (new version `94788d25…`, previous kept as
  AWSPREVIOUS); run 22 (Backfill 2026-09-20→26) restored every row: 0 Orders
  or Payments without their Employee, 0 without Tender. Tips tables
  fingerprint identical before, during and after.

## 4. Production verification

| Run | Mode | Window (UTC) | Result |
|---|---|---|---|
| 20 | Backfill | 2026-09-25 | COMPLETE, 48 orders / 51 payments (0 shifts — see §3) |
| 21 | Sync Now | 2026-09-20 00:22 → 09-26 14:01 | COMPLETE, 203 / 217; sync point → 14:01 |
| 22 | Backfill | 2026-09-20 → 09-26 | COMPLETE, 207 / 221 / 65 shifts |

POST answered in 1–7 s (redirect); concurrent Sync Now refused; no duplicates;
every touched Order has its Business Date.

## 5. Open decisions

1. The engine silently treats a failed Employees/Tenders/Devices/Shifts scan
   as an empty list and clears resolved links (§3). Recommended: make such a
   failure end the run FAILED (small change in `acquisition.py`).
2. Sync Now reads Payments by `createdTime` from the last sync point; a card
   tip adjusted later on a Payment created before that point is only picked up
   by a Backfill (or Live Sync's 2 h window). Pre-existing behaviour.
3. `rfone-tips` has no authentication; anyone with the URL can start Sync Now
   or a Backfill (pre-existing for Backfill).
4. `RFONE_WEB_BASE_URL` is still not set on `rfone-tips`
   (TIPS_AWS_FINALIZATION_WORKFLOW_001 §12).
