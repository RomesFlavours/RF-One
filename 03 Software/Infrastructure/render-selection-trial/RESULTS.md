# Selection Render trial: execution record

Date: 2026-11-04 (America/New_York). Production AWS was not queried or modified.

## Completed

- Existing `Selection/test_selection_workspace_http.py`: exit 0, ALL PASSED.
  Synthetic temporary SQLite DB, isolated AI client, mock SMTP/SMS transport.
  Covers permissions, positions, five workspace tabs, candidate verification,
  CV intake, interviews, evaluations, decisions, per-position settings and email outbox.
- Packaged `test_trial_wsgi.py`: PASS. Fresh SQLite DB, real RF-One login, mounted
  Selection, HTTPS cookie flow, noindex/banner, Aruba bridge disabled. This does
  not establish PostgreSQL compatibility or measure live Render performance.
- `render.yaml`: passes JSON Schema validation using the official current schema
  at https://render.com/schema/render.yaml.json . Render CLI/platform validation
  has not been run; CLI is not installed.
- Render workspace explicitly confirmed by user: RF One, tea-dblj5nu1egvs73fenf00.
- Render PostgreSQL 18 created on Free in Virginia, status Available:
  dpg-dblj7rmc6qcc73biu6b0-a, rfone-selection-free-trial.
  Database name: rfone_selection_free_trial. Public IP allow list empty.
  Expires 2026-12-04 at 08:32 America/New_York. No production data copied.

## Source package

`tmp/render-selection-free-trial-v2` is a standalone source snapshot with its own
local Git metadata, not a worktree switch or modification to the main repository.
Local branch: codex/render-selection-free-trial. No remote push succeeded.
Source folders: Selection, RF-One Data Store, RF-One Web, Training, Shared UI,
and Clover Data Explorer. The latter modules are imported by the RF-One shell;
an initial narrower package failed with missing clover_explorer. No Clover
connector was called by the integration smoke test.

The allowlist includes source/templates/assets and canonical migration CSVs,
not databases, CV uploads, .env files, local credentials or DPAPI configuration.
The one existing migration constraint over 63 characters is renamed only in
the disposable snapshot. Actual PostgreSQL migration remains untested.
The manifest hashes original packaged file bytes; Git newline normalization
may differ. The builder now normalizes text to LF for subsequent packages.
Dependencies retain upstream version ranges, so source identity is captured
but Python dependencies are not yet fully locked.

## Blocked / not executed

The automatic approval review rejected the push of the 836-file source snapshot
to the existing GitHub RF-One repository. It identified broad internal source,
including Clover/shared components, beyond explicitly approved isolated Selection
egress. No alternate upload or indirect push was attempted. Explicit authorization
for the reviewable package is required before retrying publication.

The Render connector can create resources but cannot apply a Blueprint or retrieve
the database password through its exposed tools. Blueprint application must wire
the database and platform-generated secrets in Render; no credential is requested
in chat. Git provider connection may require the user's Dashboard interaction.

Pending: live web deployment, PostgreSQL migrations, five tabs over the public URL,
CV upload/read/delete, concurrency, cold/warm latency, restart persistence,
database export and restore, live IMAP, and AWS comparison.
No conclusion about migration readiness or performance can yet be drawn.

## Cost of restrictions (USD, monthly estimates)

| Capability | Additional resource / cost |
| --- | --- |
| SMTP 465/587 | Paid web instance from $7; existing Aruba mailbox unchanged |
| Persistent CV files | Paid web instance plus disk $0.25/GB/month |
| DB past 30 days and managed recovery | Paid PostgreSQL compute from $6; storage per quote |
| Starter app + DB + 1 GB document disk | $13.25 baseline, before tax/overages/storage adjustments |
| 2 GB RAM app + same DB and document disk | $31.25 baseline, before tax/overages/storage adjustments |
| Independent background worker | Separate paid compute, from $7 if needed; not provisioned |
| IMAP 993 | Not identified as a Free-tier restriction; implementation/connectivity untested |
| OpenAI | Separate metered API cost; no provider calls or API spend authorized |
| Manual DB export/restore | Can be tested without managed backup subscription, subject to available tools and an isolated target |

Free infrastructure remains $0 within included build/bandwidth quotas; no paid
upgrade has been made. Free compute may sleep, restart and lose local CV files.
Paid disk still limits horizontal scaling and causes redeploy downtime.
Paid Hobby DB recovery covers three days; disk snapshots seven days. Restoring
PITR can create another billable instance. Confirm the Dashboard quote before spend.

Sources checked: https://render.com/pricing , https://render.com/docs/free ,
https://render.com/docs/disks , https://render.com/docs/postgresql-backups .

## Conditional migration approach

Use one authoritative production DB, not bidirectional automatic writes. Inventory
active AWS workloads and schema revisions; lock and test the release; automate
initial copy, verified deltas, migrations and restore checks; cut over with a
controlled write boundary and documented rollback. Sharing the authoritative DB
temporarily across providers needs explicit networking/TLS, latency measurement
and compatible migration policy. No such connection has been enabled.
