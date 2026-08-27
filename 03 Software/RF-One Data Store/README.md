# RF-One Data Store

The physical RF-One Restaurant **operational database** — the canonical, vendor-independent relational schema (TASK_DATABASE_001), now populated with the first real Clover ingestion (TASK_DATABASE_002).

```text
Clover / future POS
        ↓
Source ingestion            ← rfone_data_store/ingestion/ (TASK_DATABASE_002, Clover only so far)
        ↓
RF-One canonical operational database   ← this module (TASK_DATABASE_001 schema)
        ↓
Analytics / KPI / Performance / Training / Decisions   (NOT built yet)
```

This module is **vendor-independent**. Clover is one source adapter (`03 Software/Clover Data Explorer/` for raw evidence collection, `rfone_data_store/ingestion/clover/` for canonical mapping) — the canonical schema does not copy Clover's tables mechanically. See `DATABASE_SCHEMA.md` for the full table-by-table documentation and the modeling principles behind it, `CLOVER_INGESTION.md` / `CLOVER_INGESTION_RECONCILIATION.md` for the ingestion architecture and this run's results, `RESTAURANT_PROFILE.md` for the Restaurant Profile / Organization layer (Restaurant, Operational Area, Physical Area, Restaurant Role, temporal Employee Assignment — TASK_RESTAURANT_001), and `PAYROLL.md` for the Administration/Payroll implementation (Payroll Schedule/Period/Workweek, Compensation Terms, ADP `Payroll Detail` Excel import, Payroll Employer Cost — TASK_PAYROLL_001).

**Still not built:** KPI computation, Performance/Training logic, Table Service reconstruction, payroll tax calculation, a jurisdiction/labor-rule engine, a web UI, a REST API — see `DATABASE_SCHEMA.md`, `CLOVER_INGESTION.md` and `PAYROLL.md` for the full explicit non-goals.

---

## Technology

- **Python + SQLAlchemy 2.x** (typed `Mapped`/`mapped_column` declarative style).
- **SQLite** for local development (default), with a schema designed to avoid SQLite-specific constructs so it can target **PostgreSQL** later by changing only the database URL.

## Configuration

The database URL is read from the `RFONE_DATABASE_URL` environment variable, falling back to a local `.env` file at the repository root (same convention as `03 Software/Clover Data Explorer/clover_explorer/config.py`), falling back to a local SQLite file:

```text
03 Software/RF-One Data Store/data/rfone.db
```

Example, to target PostgreSQL later:

```text
RFONE_DATABASE_URL=postgresql+psycopg://user:password@host:5432/rfone
```

No credentials are ever printed — `create_database.py`/`inspect_database.py` redact any password in the URL before printing it.

## Usage

```text
pip install -r requirements.txt
python create_database.py      # creates all tables + runs synthetic-fixture validation
python inspect_database.py     # table name / column count / row count
python ingest_clover.py [--dry-run] [--skip-enrichment] [--max-enrichment N]
                                # Clover → canonical ingestion (TASK_DATABASE_002) — see CLOVER_INGESTION.md
python enrich_clover_cache.py [--max N]
                                # standalone resumable dedicated-line-item cache enrichment
python validate_ingestion.py   # post-promotion validation: non-zero rows where expected, empty where deferred
python test_tips_engine.py     # Tips engine synthetic-fixture tests (TASK_TIPS_001) — run against a fresh/staging DB
python validate_tips_readiness.py       # read-only Tips readiness report against the configured (real) DB
python calculate_tips.py --restaurant-id N --period-start ... --period-end ... [--persist]
                                # post-hoc Tip calculation entry point — dry-run by default
python bootstrap_restaurant_profile.py --restaurant-id N [--use-snapshot] [--persist]
                                # Restaurant Profile bootstrap/sync from Clover source configuration
                                # (TASK_RESTAURANT_003) — dry-run by default
python test_restaurant_profile_bootstrap.py     # bootstrap engine synthetic-fixture tests — run against a fresh/staging DB
python import_payroll_results.py --file <PayrollDetail.xlsx> --restaurant-id N \
        --period-start ... --period-end ... --run-type REGULAR [--persist]
                                # ADP Payroll Detail Excel import (TASK_PAYROLL_001) — see PAYROLL.md
                                # dry-run by default
python test_payroll_engine.py   # Payroll synthetic-fixture tests — run against a fresh/staging DB
```

`create_database.py` creates the schema and then validates it against a small **synthetic fixture that is always rolled back** — the database is left with tables only, no leftover test rows, ready for a future ingestion task. It prints only the (redacted) database URL, the number of tables created, and the validation outcome — never raw data.

## Schema migrations (Alembic)

Introduced by TASK_DATABASE_002, before any real data was loaded. Alembic is now the **only** supported way to create or evolve the schema — `create_database.py` itself runs `alembic upgrade head` internally, so a fresh database and an existing one on an older revision both end up correctly at the latest schema without ever deleting a populated database.

```text
python -m alembic upgrade head        # create/upgrade the configured database to the latest schema
python -m alembic revision --autogenerate -m "describe the change"   # after editing models.py
python -m alembic current              # show the current revision
python -m alembic history              # show the revision history
```

The migration scripts live in `migrations/versions/`. `migrations/env.py` resolves the target database the same way `rfone_data_store.database.get_database_url()` does (`RFONE_DATABASE_URL` / `.env` / local SQLite default), or via the `ALEMBIC_DATABASE_URL_OVERRIDE` environment variable — used internally by the ingestion pipeline to run migrations against its isolated staging database (see `CLOVER_INGESTION.md`).

**Baseline revision** (`migrations/versions/9516f3bd1495_baseline_canonical_restaurant_schema.py`) represents the exact 32-table schema (including the `device_id` FKs added by TASK_DATABASE_002's pre-ingestion review — see `DATABASE_SCHEMA.md`) used for the first real ingestion. Any future schema change must be a new revision on top of it, generated with `alembic revision --autogenerate` after editing `models.py` and reviewed before applying. Four further revisions have since been applied on the populated database without data loss: `7afe7c953207` (TASK_CLOVER_004/TASK_DATABASE_003 — `source_roles`/`employee_source_roles`), `e6df7aa7d83b` (TASK_RESTAURANT_001 — `restaurants`, `restaurant_locations`, `operational_areas`, `physical_areas`, `restaurant_roles`, `operational_area_roles`, `employee_assignments`, plus a nullable `physical_tables.physical_area_id`, applied via Alembic batch mode since SQLite cannot `ALTER TABLE ADD CONSTRAINT` directly), `dc31a1741fd8` (TASK_TIPS_001 — `tip_policies`, `tip_policy_components`, `tip_calculation_runs`, `tip_allocations`, `tip_calculation_issues`; a pure additive migration, no `ALTER` on any existing table), `2ae7e5a3d715` (TASK_RESTAURANT_003 — `restaurant_profile_source_controls`, `source_role_mappings`, `profile_bootstrap_runs`, `restaurant_profile_reconciliation_issues`; also pure additive, no `ALTER` on any existing table), and `47b3d9bb8108` (TASK_PAYROLL_001 — `payroll_schedules`, `workweek_definitions`, `employee_compensation_terms`, `payroll_runs`, `payroll_provider_employee_identities`, `employee_payroll_results`, `payroll_earning_facts`, `payroll_employer_liability_facts`, `payroll_payment_facts`, `payroll_import_runs`, `payroll_import_issues`; pure additive, no `ALTER` on any existing table, upgrade/downgrade tested on a disposable copy of the populated database).

## Module structure

| File | Responsibility |
|---|---|
| `rfone_data_store/database.py` | Database URL resolution (`RFONE_DATABASE_URL` / `.env` / local SQLite default), engine/session creation, SQLite foreign-key enforcement. |
| `rfone_data_store/models.py` | The full SQLAlchemy ORM schema — see `DATABASE_SCHEMA.md`. |
| `rfone_data_store/schema_validation.py` | Builds a synthetic (non-Clover) fixture and asserts the required relationships/edge cases, per TASK_DATABASE_001 §40. Always rolled back. |
| `create_database.py` | Entry point: create schema + validate. |
| `inspect_database.py` | Entry point: read-only schema/row-count inventory. |
| `rfone_data_store/ingestion/` | The Clover source adapter (TASK_DATABASE_002) — see `CLOVER_INGESTION.md`. |
| `rfone_data_store/tips/` | Post-hoc Tip calculation engine — `engine.py` (calculation), `resolvers.py` (service-attribution boundary), `rounding.py` (deterministic largest-remainder apportionment). TASK_TIPS_001 — see `RESTAURANT_PROFILE.md` §3 and `01 Domains/Restaurant/Tips/`. |
| `rfone_data_store/tips_validation.py` | Synthetic-fixture Tips engine tests, same pattern as `schema_validation.py`. Always rolled back. |
| `calculate_tips.py` | Entry point: post-hoc Tip calculation for a Restaurant/period, dry-run by default. |
| `validate_tips_readiness.py` | Entry point: read-only Tips readiness report against the configured database. |
| `test_tips_engine.py` | Entry point: run the Tips engine synthetic-fixture tests. |
| `rfone_data_store/profile/` | Restaurant Profile bootstrap/sync engine — `bootstrap.py` (T0, SourceRole→RestaurantRole mapping, root Operational Area, prospective EmployeeAssignments, reconciliation issues), `source_snapshot.py` (loads the optional fresh, read-only Clover snapshot from disk). TASK_RESTAURANT_003 — see `RESTAURANT_PROFILE.md` §6. |
| `rfone_data_store/profile_validation.py` | Synthetic-fixture bootstrap engine tests, same pattern as `schema_validation.py`. Always rolled back. |
| `bootstrap_restaurant_profile.py` | Entry point: Restaurant Profile bootstrap/sync from Clover source configuration, dry-run by default. |
| `test_restaurant_profile_bootstrap.py` | Entry point: run the bootstrap engine synthetic-fixture tests. |
| `rfone_data_store/payroll/` | Administration/Payroll — `schedule.py` (PayrollSchedule/Workweek helpers, no overtime logic), `compensation.py` (Compensation Terms temporal/conflict helpers), `adp_importer.py` (ADP Payroll Detail Excel parsing, Employee mapping, idempotent import), `labor_cost.py` (Payroll Employer Cost query). TASK_PAYROLL_001 — see `PAYROLL.md` and `01 Domains/Administration/Payroll/`. |
| `rfone_data_store/payroll_validation.py` | Synthetic-fixture Payroll tests, same pattern as `schema_validation.py`. Always rolled back. |
| `import_payroll_results.py` | Entry point: ADP Payroll Detail Excel import, dry-run by default. |
| `test_payroll_engine.py` | Entry point: run the Payroll synthetic-fixture tests. |
| `alembic.ini`, `migrations/` | Schema migrations — see "Schema migrations (Alembic)" above. |
| `data/` | Local SQLite database file lives here (Git-ignored) — not the raw Clover exports, which remain under `03 Software/Clover Data Explorer/data/`. |

## Numeric conventions

- **Money** is stored as **integer minor units** (cents) — never floating point. Chosen because Clover already supplies cents, and it avoids rounding ambiguity (TASK_DATABASE_001 §38).
- **Quantity** (`OrderItem.quantity`) is stored as `Numeric(12, 4)`, independent of money — TASK_CLOVER_003 found Clover Order Item quantity is not guaranteed to be exactly one physical unit (it can be fractional, e.g. a half portion).
- **Rates/percentages** (`TaxRate.rate`, `Discount*.percentage`, `OrderItemTax.rate_applied`) are stored as canonical decimal `Numeric` values (e.g. `0.065000` = 6.5%), not in Clover's own internal encoding (`rate / 10,000,000`) — the canonical model does not inherit a source system's arbitrary scaling.

## Timestamp conventions

All timestamps are `DateTime(timezone=True)`. The application/ingestion boundary is responsible for normalizing to UTC before persisting — this module does not hard-code Eastern time, and does not invent a Location timezone the source never confirmed (TASK_CLOVER_003 found no `timezone` field anywhere on the current Clover Merchant object).

## Explicit non-goals (this task)

Clover ingestion, incremental synchronization, Table Service reconstruction logic, the KPI engine, Performance scoring, Training recommendations, bank reconciliation, Taxation, a web UI, a REST API. Payroll (TASK_PAYROLL_001) is now implemented — see `PAYROLL.md` — but its own non-goals remain: ADP API/OAuth submission, payroll tax calculation, a jurisdiction/labor-rule engine, direct deposit execution, contractor/1099 payables. Those are later tasks, layered on top of this schema.
