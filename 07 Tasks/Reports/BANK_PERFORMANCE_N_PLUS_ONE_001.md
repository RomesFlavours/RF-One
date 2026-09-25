# BANK_PERFORMANCE_N_PLUS_ONE_001 — Report

**Date:** 2026-09-25  ·  **Scope:** read-only query patterns of the Bank pages. There is no semantic, schema or data change, and the gunicorn timeout is unchanged.

## Cause (profiled on the migrated dataset, not guessed)

| Page | Before | Root cause |
|---|---|---|
| `/bank` | 12,796 statements | `service.compute_batch_review_state`: one `financial_transaction_matches` query per transaction (12,678) |
| `/bank/classification` | 13,448 statements | `receiver_candidates._rule_suggestion`: one `bank_recognition_rules` query per receiver group (6,477), and the whole candidate build ran twice (page + `summary`); `accounting_classification_usage`: 3 counts per What (408) |
| `/bank/review` | 3,542 statements | `why_catalog.reasons_for_occurrence` called per Who, twice (2,458); one copy count per canonical row (500) |

## Fix

- **`compute_batch_review_state`:** one query for all matches touching the batch, plus one for the counterparts' instruments. It counts exactly what the per-transaction loop counted.
- **`_exact_rules_by_pattern`:** the ACTIVE exact rules are read once. `summary(session, candidates)` reuses the candidates the page has already built.
- **`classification.accounting_classification_usages`:** three grouped counts; same keys and values as the per-What function.
- **`why_catalog.reasons_by_occurrence`:** one query for every Who, in the same order.
- **Review copy counts:** one grouped count.

## Result

On the migrated dataset (local SQLite copy), the three pages render HTML identical to the pre-change rendering once CSRF tokens are normalized.

| Page | Statements | PostgreSQL time from the operator PC (about 45 ms per query to RDS) |
|---|---|---|
| `/bank` | 12,796 → 149 | 570 s → 9.4 s |
| `/bank/classification` | 13,448 → 55 | 602 s → 8.4 s |
| `/bank/review` | 3,542 → 583 | 155 s → 27.6 s |

Test `RF-One Web/tests/test_bank_query_bounds_http.py`:

- builds 3,000 and then 6,000 transactions, 300 and then 600 Whos, aliases, rules, decisions and matches;
- checks that each optimized result equals the former per-row algorithm;
- checks that the pages render with their business content;
- checks that statement counts stay under flat ceilings and do not grow with the data.

## Remaining (not changed here)

- `/bank/review` still issues one `matching.find_cross_ledger_candidates` query per displayed row (500). This is bounded by page size, not by the dataset.
- `/bank/classification` renders a page of about 17 MB.
- `/bank` still issues three queries per batch.
