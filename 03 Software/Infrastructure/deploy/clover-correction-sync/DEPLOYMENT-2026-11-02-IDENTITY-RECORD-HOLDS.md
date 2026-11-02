# Clover — identity record holds release (2026-11-02)

Product Owner decision 2026-11-02 (EMPLOYEE_DIRECTORY_RECORD_HOLD_001): an unconfirmed Clover
employee holds only the records that depend on that person, never the Location's acquisition.
Spec: `01 Domains/Shared Domains/Employee Directory/README.md`. No migration, no schema change.

## Released

| Component | Before | After |
|---|---|---|
| Source | `628996a` | `59246b0` (branch `release/tips-shared-migrations`) |
| Worker image (`rfone-tips`) | `sha256:d351090c…5e005a` | `sha256:62b68db53ec3e50f3148254396516e96f358501f761eef9293868b408b8dd2d8`, tag `identity-record-holds-20261102t123252z`, build `rfone-tips-build:3345080c-2233-4fef-ac4d-ce8bfc99994e` |
| `rfone-clover-correction-sync` | task definition 7 | 8 (rollout COMPLETED, task `d0ccf585698243a49a27c283dd9befd9`) |
| `rfone-clover-acquisition-job` | 8 | 9 (pre-check task `68e5625f0074425f954a48dfea7e967c`: `CLOVER_RELEASE_VERIFIED`, 16 tests, no writes) |
| `rfone-tips` App Runner (Tips finalization guard) | `rfone-tips:person-20261029t134240z-lf` | same image as the worker, tag `identity-record-holds-20261102t123252z`; operation `70c4f0a7353647668696619d94dcd3c3` |
| `rfone-web` App Runner (re-attribution on confirmation) | `rfone-web:interviews-test-20261101t202720z` | `rfone-web:identity-record-holds-20261102t123252z` (`sha256:d7cad631…d3220a`); operation `e94f7cd1473a4e64b183b4f3f3c41e04` |

The Tips/worker source equals the running Tips source (`a195e4c`, 656/656 files) plus the approved
shared-migrations fix and this change. The web package equals the running web package
(`releases/interviews-test-20261101t202720z/source.zip`, 838 files) plus exactly
`employee_directory.py` and the new `identity_holds.py`.

## Data recovery (Winter Park, location 1)

| | Before | After |
|---|---|---|
| Orders/Payments/Refunds checkpoints | 2026-10-31 19:06:29 UTC | advancing every minute (13:03:33 UTC at verification) |
| Sync Now point | 2026-10-29 03:17:07 UTC | 2026-11-02 12:44:39 UTC |
| Orders / Payments / Shifts at the Location | 13,282 / 14,264 / 15 | 13,353 / 14,344 / 71 |
| Duplicates (orders, payments, refunds, shifts) | 0 | 0 |

Sync Now job `188229` (2026-10-29 03:17 → 2026-11-02 12:44 UTC) COMPLETE: 201 orders, 212 payments,
56 shifts processed. Held: 7 shifts of the three pending identities (link ids 65–67), kept in the
Provider Mirror; no order, payment or refund was held. Tips finalization is refused only for Business
Dates 2026-10-31 (5 shifts) and 2026-11-01 (2 shifts). No identity was confirmed automatically.

## Rollback references

- Images: `rfone-tips:pre-identity-holds-worker-20261102t123252z` (worker, `d351090c…`),
  `rfone-tips:pre-identity-holds-tipsapp-20261102t123252z` (Tips app, `1d13878c…`),
  `rfone-web:pre-identity-holds-web-20261102t123252z` (`999c3b22…`).
- Task definitions: `previous/rfone-clover-correction-sync-7.json`, `previous/rfone-clover-acquisition-job-8.json`.
  Revision 7/8 run the whole-Location stop again; use them only with a Product Owner decision.
- Source backups: `s3://rfone-tips-deploy-418674484214/backups/rfone-tips-source-pre-identity-holds-20261102t123252z.zip`,
  `…/backups/rfone-web-source-pre-identity-holds-20261102t123252z.zip`.
- RDS snapshot `rfone-dev-pre-clover-identity-holds-20261102t123252z` (taken before the Sync Now writes).
