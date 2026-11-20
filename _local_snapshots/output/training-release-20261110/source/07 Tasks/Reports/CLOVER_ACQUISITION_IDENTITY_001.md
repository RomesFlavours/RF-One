# CLOVER_ACQUISITION_IDENTITY_001 — manual Clover actions protected by the RF-One identity

**Status: completed and deployed on AWS (2026-09-26).** Commit `97c7236`
(+ this report). Closed: manual Clover actions protected by the RF-One identity.

## 1. Decision

RF-One had no definition of who may start a Clover acquisition. Product
Owner decision (2026-09-26): a **dedicated access entry, `CLOVER_ACQUISITION`**,
in the existing access list (`RF-One Web/domain_registry.py`), granted
account by account through the existing Admin → account access screen. No
new role, no hierarchy.

## 2. What changed

| Where | Change |
|---|---|
| RF-One Web `clover_acquisition_routes.py` | `/clover-acquisition` page, `POST /clover-acquisition/sync-now`, `POST /clover-acquisition/backfill`, `GET /clover-acquisition/status.json` |
| Gates (server side, before the acquisition service is called) | 1. live RF-One session, else → normal login with a plain message and `next` back to the page; 2. `account_may_enter_domain(..., "CLOVER_ACQUISITION")`, else 403; 3. CSRF on the POSTs. A refused request creates no job row and launches no Fargate task. |
| Login | honours `next`, local paths only (`//host`, `http://…` refused) |
| Home | "Clover Acquisition" under Administration, only for accounts holding the access |
| `ingestion_runs.requested_by_account_id` | FK to `rfone_accounts` (migration `c9e5a3b7d2f1`, additive); set by `acquisition_jobs` before launch; page shows **Requested by** (the account's display name). NULL = no person: older runs, and automatic acquisition (Live Sync → "System (automatic)") |
| Standalone Tips app | no acquisition action, no job history; links to `RFONE_WEB_BASE_URL/clover-acquisition`. The former action URLs no longer exist (404/405). |
| AWS | `rfone-web`: launcher variables + `RunTask` policy `rfone-web-run-clover-acquisition-job`. `rfone-tips`: launcher variables removed, `RFONE_WEB_BASE_URL` set (the missing configuration reported by TIPS_AWS_FINALIZATION_WORKFLOW_001 §12). |

Unchanged: the acquisition engine and its safety checks, modes, Sync Now
window, Backfill date logic, Live Sync (NOT ACTIVE), Tips, Payroll, Mercury,
Compensation.

## 3. Why RF-One Web

On AWS `rfone-web` and `rfone-tips` are two hostnames; the RF-One session
cookie reaches only the first. Protected actions therefore live where the
login lives — the same resolution already used for Tips validation. No
routing or domain change.

## 4. Tests (local)

- RF-One Web `tests/test_clover_acquisition_http.py` — 27 checks: A
  unauthenticated (page → login with message and way back; Sync Now and
  Backfill refused; no job; no launch), B direct POST without session (even
  with a made-up CSRF token) refused, C signed in without the access → 403,
  no job; with the access but no CSRF → 400, D authorized Backfill and Sync
  Now accepted with requester recorded and shown, E page and status poll
  never create a job, F concurrent acquisition refused, G return to the page
  after login and no off-host `next`, H Home link only with the access.
- Tips `test_clover_acquisition_moved_http.py` — 8 checks.
- All 24 RF-One Web suites, Tips suites and Clover suites green.

## 5. Production verification

| Check | Observed |
|---|---|
| Anonymous `GET /clover-acquisition` (rfone-web) | 302 → `/login?next=/clover-acquisition`, message "Please sign in to RF-One to use Clover Acquisition…" |
| Anonymous POST Sync Now / Backfill (rfone-web, made-up CSRF) | 302 → login; `status.json` 401 |
| Former action URLs on rfone-tips | 404 |
| Effect of anonymous requests | job history unchanged (20 rows, last #24); no ECS task started |
| rfone-tips page | links to `https://vhmsm9mgh8.us-east-1.awsapprunner.com/clover-acquisition` |
| Authorized click (Product Owner, account "Pino Miraglia", access granted by him in Admin) | Sync Now #25 accepted, requested by **Pino Miraglia**, ran as a separate Fargate task, COMPLETE (2026-09-26 15:08 → 18:05 UTC, 19 orders, 19 payments, 6 shifts) |
| Tips tables | fingerprint identical |

AWS: `rfone-web` image `sha256:d78a229e…`, `rfone-tips` image `sha256:e389356c…`;
RDS snapshot `rfone-dev-pre-clover-acquisition-identity-20260926t173030z`;
`RunTask` removed from `rfone-tips-apprunner-instance-role`.
