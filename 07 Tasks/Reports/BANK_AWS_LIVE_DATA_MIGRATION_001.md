# BANK_AWS_LIVE_DATA_MIGRATION_001 — Report

**Date:** 2026-09-25  ·  **Target:** RDS `rfone-dev`, database `rfone` (account 418674484214)  ·  **Tool:** `migrate_bank_to_postgres.py` (commit `00638db`)

## Result

The certified local Bank dataset (SQLite sha256 `05acfe71…d240ae`, Alembic `e7b2c94d0f18`) was copied to the live database:

- 45,214 rows across 18 tables, plus one new Legal Entity (**RF Gelati, LLC**, id 3), per the Product Owner's map.
- One transaction; every table's logical manifest was verified before commit. The apply ran 03:41:56Z–03:43:02Z.
- Recovery point: snapshot `rfone-dev-pre-bank-data-migration-20260925t033756z`.

## Verification (71 of 71)

- **Counts:** equal for all 18 tables. The 11 other Bank tables stay empty.
- **Transactions:** every FinancialTransaction is identical in id, amount, posting date, descriptions, instrument, batch, fingerprint, dedup key and statuses. None omitted, none duplicated, same total.
- **Lineage:** batch lineage and raw-row lineage are identical.
- **Decisions:** all 921 current-decision pointers and decision rows are identical, and the WHY is preserved by canonical code.
- **WHO:** occurrences, aliases and recognitions are identical; Legal Entity references are re-pointed through the approved map.
- **Instruments:** instruments, their lifecycle and the settlement mappings are identical.
- **Monthly control:**
  - monthly periods and coverage are identical, with no resolution invented;
  - the 13 enforced blockers are identical month by month;
  - Control Start is 2026-01 and Validated Through is 2026-08; September is provisional.
- **Shared data:** a fingerprint of all 247 live tables was taken before and after. Only the 18 Bank tables and `legal_entities` (+1 row) changed. Tips, Orders, Payroll, Employees, accounts and the catalogues are unchanged.
- **Re-run:** a second invocation refuses, because the target Bank tables already hold rows.

## Deployed application

Measured twice on the deployed `rfone-web` service:

| Page | Result |
|---|---|
| `/bank` | 200 in 29–39 s |
| `/bank/monthly` | 200 in ≤ 4 s |
| `/bank/review` | 200 in about 10 s |
| `/bank/export` | 200 in under 1 s |
| **`/bank/classification`** | **500 after about 61 s on both attempts** |

For `/bank/classification`, the App Runner log shows `WORKER TIMEOUT`: gunicorn's `--timeout 60` kills the worker. This is not a data or ORM error. The page issues about 13,400 queries per request (N+1).

**Classification: RELEASE PERFORMANCE ISSUE.** This is the next technical task. The data was not touched.

## Operational note

The temporary technical account `release-smoke-20260925` was reactivated for the authenticated smoke test. It is back to INACTIVE, with BANK access disabled and its password rotated.
