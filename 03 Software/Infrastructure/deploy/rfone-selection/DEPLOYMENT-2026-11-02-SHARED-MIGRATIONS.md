# Selection — shared migrations release (2026-11-02)

Status: App Runner operation `48a902f1ea8c4aecaeaa530b57e41a25` SUCCEEDED; service RUNNING.

## What changed

Only the shared-migrations fix (`1fc0f38`, see `RF-One Data Store/MIGRATIONS.md`) on top of the
image that was running (`sel-94eda7c51cfa`, commit `94eda7c`: five-tab Job process, CV Selection SP,
Interviews evidence). Selection no longer runs `alembic upgrade head` at start; it checks its 112
required tables read-only. No migration was applied; no data was changed.

## Release identity

- Branch `release/selection-shared-migrations`, commit `fa35e6131032065e68f22dd1d03e849bb3ae4dd1`.
- Image `418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-selection:sel-fa35e6131032`.
- Build `rfone-selection-build:9a245fd3-07f8-4814-b6b5-de64a2478d30`: `MIGRATION CHAIN OK head=e0a120261101`, `GUARD OK rmaed-selection-bridge-3`.

## Before the release (read-only)

- Running image `sel-94eda7c51cfa` (digest `sha256:c44c1c32…4b0d0`); RDS `alembic_version` = `e0a120261101`.
- RDS schema read in a read-only transaction (ECS task `0c95d7cb5b0a4329b5eb4711100b5a3d`, 297 tables):
  all 112 Selection tables and their columns present.

## Rollback

- Image `rfone-selection:pre-shared-migrations-001-20261102t042135z` (= `sel-94eda7c51cfa`).
- Source backup `s3://rfone-tips-deploy-418674484214/backups/rfone-selection-source-pre-shared-migrations-001-20261102t042135z.zip`.
- RDS snapshot `rfone-dev-pre-selection-shared-migrations-001-20261102t042135z` (not needed: no schema or data change).

## Verified

Health 200 (`rmaed-selection-bridge-3`); 13 public/protected URLs return the same status and
redirect target as before the release; application log shows a clean gunicorn start with no schema
warning or error. Release-tree tests: 13/13 Selection test files passed (including five-tab process,
SP engine, SP integration, schema start-up scenarios).
