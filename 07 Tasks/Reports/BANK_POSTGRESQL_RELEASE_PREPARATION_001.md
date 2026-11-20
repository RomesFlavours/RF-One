# BANK_POSTGRESQL_RELEASE_PREPARATION_001 — Report

**Date:** 2026-09-24  ·  **Scope:** local only — no AWS, no deploy, golden database untouched.

## Migration changes

| Revision | Problem on PostgreSQL | Change | SQLite | Business semantics |
|---|---|---|---|---|
| `00e6783b630f` | 5 Boolean defaults written as `sa.text('0'/'1')` — rejected for a `boolean` column | `sa.text('false'/'true')` (AWS_RDS_ALEMBIC_RECONCILIATION_001, previously uncommitted) | same stored value | none |
| `4afdc598f407` | `backup_required` default `sa.text('0')` | `sa.text('false')` (idem) | same stored value | none |
| `8ddfe6f314be` | 3 upgrade + 4 downgrade Boolean defaults | `sa.text('false'/'true')` (idem) | same stored value | none |
| `e5b28d413f7a` | `is_override` default `sa.text("0")` | `sa.false()` (repository convention since 92cb7ce); renders `0` on SQLite, `false` on PostgreSQL | identical DDL | none |
| `a9e6d3c71f24` | row-count fence ran on every dialect, so a populated `bank_import_batches` stopped the upgrade although PostgreSQL rebuilds nothing | fence moved inside the SQLite rebuild path; PostgreSQL drops/re-adds the widened CHECK in place | path byte-identical | none — widening admits every existing row; narrowing is refused by PostgreSQL itself if an Amex row exists |

## Local validation (SQLite)

* Single head `e7b2c94d0f18`; fresh database base → head.
* Four older database copies (`a5e1c93f7b20`, `b7d4e92a1c58`, `d3a7c9f15b28`, `b31e7c0d9a54`) → head; data unchanged.
* Downgrade from head through every revision changed here (62 revisions, stopping at a pre-existing, unrelated Tips downgrade error) and re-upgrade: schema semantically identical except a cosmetic foreign-key order in `ingestion_runs`.
* Alembic offline mode rendered all 11 pending Bank revisions as PostgreSQL SQL (the only interruption is `e5b28d413f7a`'s row count, which offline mode cannot evaluate).

## Still required on PostgreSQL

Run `alembic upgrade head` on a disposable PostgreSQL database on the RDS instance, and read the
RDS revision and `bank_import_batches` row count before upgrading `rfone-dev`.
