# BANK_AWS_DATA_MIGRATION_DRY_RUN_001 — Report

**Date:** 2026-09-25  ·  **Scope:** dry run only. The migration was applied only to a disposable `rfone_pgval_*` database, since dropped. The live `rfone` database was only read.

## Source and target

| | Local SQLite `data/rfone.db` | AWS RDS `rfone-dev` / `rfone` |
|---|---|---|
| Alembic | `e7b2c94d0f18` | `e7b2c94d0f18` |
| SHA-256 | `05acfe71c605843690115b932a6fd64f2dea2175a18e5d68025c6efd74d240ae` (unchanged by the run) | fingerprint of all 247 tables identical before and after the run |
| Bank operational rows | 45,214 in the migrated tables | 0 |

## Table classification

- **A — migrate** (18 tables): `reporting_groups`, `reporting_entities`, `reporting_entity_destination_aliases`, `bank_occurrence_types`, `payment_instruments`, `bank_card_settlement_accounts`, `bank_instrument_identity_audits`, `bank_import_batches`, `financial_transactions`, `raw_bank_transactions`, `bank_occurrences`, `bank_occurrence_aliases`, `bank_who_recognitions`, `bank_transaction_explanations`, `bank_monthly_source_periods`, `bank_monthly_instrument_coverages`, `bank_historical_instrument_candidates`, `bank_historical_instrument_candidate_evidence`.
- **B — already seeded, not duplicated:**
  - `bank_accounting_classifications` (136) and `bank_reason_groups` (14): identical id for id;
  - `bank_transaction_reasons` (77): same codes, ids +5 on AWS;
  - `bank_reconciliation_control_configs`: the same 2026-01 / 2026-08 is already set.
- **C — shared, mapped:** `legal_entities`, by the Product Owner's decision of 2026-09-25:

  | Local Legal Entity | AWS target |
  |---|---|
  | 1 Angeli E Demoni, LLC | 1 RF-Winter Park |
  | 3 RF Mount Dora, LLC | 2 RF-Mount Dora |
  | 2 RF Gelati, LLC | NEW |

  AWS names are not changed.
- **D — not migrated:** Orders / Tips / Clover / Purchased and supplier data (other domains), `rfone_accounts` (local 0; accounts hold secrets), and 11 Bank tables that are empty locally. The tool requires those 11 to be empty on the target too.
- **E — generated:** none. Accounting dedup keys and coverage rows are stored decisions and are migrated as they are.

## Keys

- The target tables are empty, so every Bank id is preserved; sequences are advanced past the copied ids.
- FK remaps: the WHY re-pointed by code, the three Legal Entity columns through the approved map, and `financial_transactions.explanation_id` (the one FK cycle) set in a second pass.

## Tool

`03 Software/RF-One Data Store/migrate_bank_to_postgres.py`:

- **Default behaviour:** preview; `--apply` is required to write, and is refused against `live` in this version.
- **Guards:** AWS account, database name and Alembic revision; empty target tables; identical catalogues; an explicit and complete Legal Entity map.
- **Safety:** one transaction, and a per-table logical manifest checked before commit. A mismatch rolls everything back, with the first differing row and columns reported. This check caught the `updated_at` onupdate side effect of the second pass, which was then fixed.
- **Second run:** a safe refusal.

## Dry-run result

67 of 67 checks passed:

- counts for every table;
- every transaction's amount, posting date, description, instrument, batch, fingerprint and dedup key;
- no duplicates and no omissions;
- raw-row lineage;
- WHO decisions, aliases and recognitions, and WHY by code;
- current-decision pointers;
- instruments with lifecycle, start and end dates and mapped owners;
- card settlements;
- monthly periods, coverage and human resolutions;
- Control Start and Validated Through;
- all 13 monthly blockers identical;
- 215 non-Bank tables unaltered.

RF-One Web against the migrated PostgreSQL database: every Bank page returns 200, with no FK, ORM or template error.

## Risk to watch

The Bank pages issue many queries per request:

| Page | Queries | Estimated time on AWS (about 1.5 ms per query) |
|---|---|---|
| `/bank` | 12,796 | about 26 s |
| `/bank/classification` | 13,448 | about 38 s |
| `/bank/review` | 3,542 | about 14 s |

These estimates are under the 60 s gunicorn timeout, with limited headroom. This is not a data-integrity issue. It should be measured right after the live migration.

## Live preview (read-only)

The live migration would insert 45,214 rows into the 18 tables above, plus one new Legal Entity (RF Gelati, LLC). There are no conflicts. The control configuration is kept (identical).
