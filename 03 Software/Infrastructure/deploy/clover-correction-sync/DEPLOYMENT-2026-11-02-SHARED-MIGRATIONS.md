# Clover workers — shared migrations release (2026-11-02)

Status: `rfone-clover-correction-sync` RUNNING on task definition 7, rollout COMPLETED.
`rfone-clover-acquisition-job:8` ACTIVE (7 deregistered: CRLF package, see below).
No other service, no migration, no data change.

## Diagnosis before the release (read-only)

The poller was not hung. Since 2026-10-31 19:07 UTC every one-minute cycle ended FAILED in about one
second: "N Clover employee identities require confirmation in Employee Directory. Work corrections will
resume after identity confirmation." (1, then 2, now 3 unlinked `employee_clover_links`, ids 65-67).
Failed cycles write no log line, so CloudWatch looked silent. Checkpoints of orders/payments/refunds
stay at 2026-10-31 19:06:29 UTC, so nothing is skipped: the backlog is re-read once the identities are
confirmed. No lock waits, no open transaction, no RDS event at that time.

## Release

- Branch `release/tips-shared-migrations` = deployed worker source `a195e4c` + `ffed7c4` (e0a1 file) +
  `6134f5a` (shared-migrations fix). The source ZIP differs from the deployed one only by those files.
- Image `rfone-tips@sha256:d351090c9ddbb7a04e2533d868d40a5c2b41a97ca131e2c184a953a219e5005a`
  (tag `tips-shared-migrations-20261102t051746z-lf`, build `rfone-tips-build:86041c2c-f15e-422b-9cbd-b72799213857`,
  `MIGRATION CHAIN OK head=e0a120261101`). `rfone-tips:latest` and the `rfone-tips` App Runner service unchanged.
- Package rule: build the ZIP with `git -c core.autocrlf=false archive`. A CRLF package
  (digest `664340e5…`, task definition 7) fails `Runtime artifact mismatch` and was never used by the poller.
- Read-only pre-check task `89f8c34477ef4d7190c56d3105b0a31b`: `CLOVER_RELEASE_VERIFIED`, schema
  `e0a120261101` known, `database_writes: false`, `orphan_shifts: 0`.

## Previous definitions (reference, not a rollback target)

`previous/rfone-clover-*-6.json`, image `rfone-tips@sha256:1d13878c…a2a5a` (also tagged
`pre-clover-shared-migrations-20261102t051313z`). Revision 6 asserts revision `d9e220261029`
exactly and cannot start against the current schema.

## Verified after restart

New task `e38e9a4608c24c75bb320143e574d615`: release check passed, loop started 05:22:25 UTC, one
cycle per minute, no duplicate cycle, no open run. Data resume after the three identities are
confirmed in Employee Directory (a Person Foundation decision, not changed here).
