# CLOVER_ACQUISITION_ENGINE_001 — shared Clover acquisition engine

Product Owner instruction, 2026-11-22 (verbatim, Italian):

> RF-One — Parti dal motore di scarico dati Clover. Sostituisci il comando precedente. Lavora sul motore di
> acquisizione Clover condiviso. La ripartizione Tips e Mercury vengono dopo.
> Verifica il comportamento attuale su AWS in sola lettura. Identifica lo scheduler, la configurazione dei
> merchant e l'ultimo scarico riuscito per Winter Park e Mount Dora. Poi completa in una worktree locale
> isolata ciò che manca per ottenere questo comportamento:
> 1. Scarico ordinario. Un orario comune modificabile dall'utente nelle impostazioni RF-One. Valore iniziale:
>    mezzanotte, America/New_York. A ogni esecuzione, acquisisci dati nuovi e aggiornamenti da tutte le sedi
>    Clover attive e configurate, usando il merchant di ciascuna sede.
> 2. Registra separatamente per sede l'esito, l'ultimo scarico riuscito e la copertura dei dati. Se una sede
>    fallisce, completa l'altra. Un tentativo fallito non deve risultare come copertura completata.
> 3. Scarico Live. Spento in condizioni ordinarie. Parte solo su richiesta di una funzione autorizzata e usa
>    lo stesso motore, limitato alle sedi e ai dati richiesti.
> 4. Prova in isolamento due merchant, il cambio dell'orario, il fallimento di una sola sede e uno scarico
>    Live richiesto per una sola sede. Ripeti uno scarico e verifica che non duplichi i dati.
> Non avviare scarichi su AWS, non cambiare Tips, non fare push o deploy.

## AWS today (read-only, 2026-11-22/23 UTC)

One-off ECS task of `rfone-clover-correction-sync:12` with a read-only session
(`default_transaction_read_only=on`), task `a466f9b7f5d8485b8c29dbba964cff8d`. RDS revision `a1c220261121`.

| | Winter Park (location 1) | Mount Dora (location 2) |
|---|---|---|
| Merchant | `PYQYB7SKB6V31`, active | `WP3NHX517C0M1`, location and merchant **inactive** |
| Scheduler | ECS service `rfone-clover-correction-sync` (task def :12): `correction_sync --location-id 1 --interval-seconds 60`, always on; no EventBridge/Scheduler rule for Clover | none |
| Credentials given to the worker | `CLOVER_MERCHANT_ID` / `CLOVER_API_TOKEN` (WP) | MD secrets exist in Secrets Manager (`rfone-tips/clover-md-*`) but are given to no worker |
| What is downloaded | every 60 s: Orders and Payments modified since their own checkpoint, Refunds of the last 48 h; shifts not read by this worker | nothing ever |
| Last successful download | correction cycle 2026-11-23 04:10 UTC (2026-11-22 23:10 ET); last full Sync Now 2026-11-16 23:47 UTC; last Live Sync 2026-11-02 | never (0 orders, 0 runs) |
| Data held | 14,339 orders 2026-01-02 → 2026-11-23 01:53 UTC | none |

## What was implemented (local, `feature/clover-acquisition-engine`)

- `rfone_data_store/operational_acquisition.py` — the engine: common schedule (`get_schedule`/`set_schedule`),
  one worker per active site, ordinary download once per day per site, per-site request rows with outcome and
  (only when COMPLETE) covered period, `describe_site_status`, Live requests (`request_live`/`end_live`).
- `technical/connectors/clover/shared_cycle.py` — one download for one site with its own merchant: ordinary =
  new records (`import_clover_period`, Sync Now scope) + updates (`run_correction_cycle`); Live = updates only,
  limited to the requested resources. PARTIAL counts as failed.
- `correction_sync.run_correction_cycle(resources=...)` — optional subset of orders/payments/refunds.
- Migration `d2a120261122` (after `c7d820261122`): `operational_acquisition_schedules` (seeded 00:00
  America/New_York) and `operational_acquisition_requests`.
- RF-One Web Settings > Clover download (`/admin/clover-download`, administrators): time, next download,
  status by site; How Works `help/clover_download.html`, registered.

Implementation interpretations (to confirm): Live "data requested" = orders / payments / refunds; "authorized
function" = a named RF-One function acting for an account with the CLOVER_ACQUISITION access to those sites; a
site never downloaded (MD) has no starting point and fails with "run a Historical Backfill first"; a download
missed while the engine was stopped runs as soon as it restarts the same day.

## Product Owner decisions, 2026-11-23

Verbatim: «Il motore a 60 secondi non serve a nulla va comunque eliminato. Punto. Le tip vengono calcolate e
pagate il giorno dopo delle operazioni, quindi necessariamente dopo lo scarico notturno di TUTTI i dati di Clover
per entrambe le sedi. Quindi i dati saranno sempre aggiornati. Per lo scarico live ne parleremo quando ci sarà
una applicazione che lo necessita.»

- The 60-second correction service (`rfone-clover-correction-sync`) is to be removed.
- Tips are calculated and paid the day after operations, after the nightly download of both sites.
- Live download: deferred until an application needs it (the interpretations above stay unconfirmed).

Not done (out of scope): no AWS change, no deploy, the 60 s correction service is untouched, no Tips change.

## Codex audit 2026-11-23 (NO-GO) — fixes on `feature/clover-engine-rfone` (RF One/tmp/clover-engine)

PO decisions the same day (also in `RF One/Decisioni RF1.md`): Tips waits for EVERY active Clover site (people
work at several restaurants; tips are summed per person); Registry stops using Clover data now.

1. PARTIAL never a starting point; Tips gates on `operational_acquisition.describe_data_coverage` (COMPLETE
   ordinary downloads of every active site up to the period end) in `tips/readiness.py` and
   `tips/payment_readiness.py`. No active Clover site at all = nothing to wait for (previous rule).
2. Every active site required; inactive sites ignored.
3. Lease on ordinary downloads (`claimed_by`, `lease_until`, renewed every minute, 10 min); only expired leases
   are recovered; only the claim holder records the outcome.
4. Start-check manifest regenerated from LF content (`generate_clover_connector_manifest.py`), engine files and
   `test_operational_acquisition` added; verified on an LF copy (CLOVER_RELEASE_VERIFIED, 25 tests). Must be
   regenerated again on the final committed release tree.
5. Escalation deadline: `Schedule.first_run_at_or_after` (a download due exactly at the period end counts).
6. Registry: department classification and overview from Registry assignments only (OQ-7 functions from
   409ce8f); Sync Now and Clover sync status removed from the Registry page (route removed).
7. Missed download of the previous day caught up at restart; DST convention in the help.
8. Home link, help button and modal close label follow `RFONE_UI_LANGUAGE`.

## Independent audit 2026-11-23 — four blockers

1. Coverage and restart point: unchanged logic (only COMPLETE ordinary downloads carry coverage; the start is the
   last COMPLETE ordinary download, else the last COMPLETE Sync Now/Live Sync/Backfill run). `payment_readiness`
   now always requires the whole period being paid (`required_until = period_end`). New regression tests: first
   ordinary download after a COMPLETE Backfill and a later PARTIAL Sync Now starts from the Backfill; a PARTIAL
   and a BUSY ordinary download advance neither coverage nor the start point.
2. Every active site: new test with Winter Park covered and Mount Dora active but failed, two distinct
   restaurants — calculation and payment readiness not ready; Mount Dora inactive — ready.
3. Concurrency: the lease test now uses two independent engines (two instances) on the same test database, and
   checks a single ordinary request per site and date.
4. Release artifact: `generate_clover_connector_manifest.py` now hashes the bytes of a `git -c
   core.autocrlf=false archive` of the working tree (temporary index, no commit) — the same bytes the
   `rfone-tips` image copies (`COPY "RF-One Data Store"`, `COPY "Clover Data Explorer"`); `--extract` writes that
   artifact so `clover_connector_release_check.py` runs on it. The image itself was not built.
5. How Works: `admin_clover_download.html` registered also for the Registry, Training and Kitchen entries (they
   read the same RF-One Web templates); error set identical to acd44b2.

## Second audit (Codex) 2026-11-23 and PO decision

PO decision: once the nightly download is done, Tips are ready ("Scarico notturno e le tip sono pronte per la
lavorazione. Punto"). The period-coverage checks were removed:
- `operational_acquisition.describe_nightly_download(now)`: the latest nightly download already due is COMPLETE for
  every active Clover site (inactive sites ignored). It replaces `describe_data_coverage`; `tips/readiness.py` and
  `tips/payment_readiness.py` use it (no period end, no cycle preparation time).
- Payment: persistently failing once that nightly download is more than the threshold past its due time.
- Restart point (engine correctness, not a Tips constraint): a Sync Now counts as a first starting point only if it
  began before the site's first ordinary download; a Backfill always counts; Live Sync never. A download that
  imported new records and then failed on updates never moves the start (`_starting_acquisitions`).

## AWS release 2026-11-23 (PO: "Fai il deploy")

Layered on the code live that day (Codex registry hotfix included), only the engine, the settings page and the
Tips nightly-download gate:
- RDS snapshot `rfone-dev-pre-clover-engine-20261123t164758z`; migration `a1c220261121 -> d2a120261122`
  (task `rfone-clover-engine-migration:1`). In the shared chain d2a1 is parented on a1c2 and b2c3 re-parented on d2a1.
- Worker: ECS service `rfone-clover-correction-sync` -> task def `:14`, image `rfone-tips:clover-engine-20261123-jobs`
  (branch `release/clover-engine-jobs-20261123`), runs `rfone_data_store.operational_acquisition`; the 60 s poller is
  gone. Rollback: task def `:13`.
- Tips: App Runner `rfone-tips` image `rfone-tips:clover-engine-20261123-tips` (branch
  `release/clover-engine-tips-20261123`); rollback `rfone-tips:tip-role-history-20261118c-tips`.
- Web: App Runner `rfone-web` image `rfone-web:clover-engine-20261123-web` (branch
  `release/clover-engine-web-20261123`); rollback `rfone-web:registry-hotfix-20261123-c0f7c5b`.
- First Winter Park ordinary download (2026-11-23): COMPLETE, 2026-11-16T23:41Z -> 2026-11-23T16:56Z.
