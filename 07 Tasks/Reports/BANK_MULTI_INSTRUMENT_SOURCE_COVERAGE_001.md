# BANK_MULTI_INSTRUMENT_SOURCE_COVERAGE_001 — Report

**Date:** 2026-09-24  ·  **Scope:** local golden database only (no AWS, no deploy)

## Rule implemented

Source received for (instrument, month) =
1. a batch assigned to the instrument covers the month (existing `batches_covering`, unchanged); or,
   only when there is none,
2. a batch with no single `payment_instrument_id` has a `RawBankTransaction` linked to a
   `FinancialTransaction` of that instrument with `posting_date` in the month.

Raw-row lineage (`RawBankTransaction.import_batch_id` + `normalized_transaction_id`), not
`FinancialTransaction.import_batch_id`. Duplicate/suppressed transactions still count as source
evidence. NULL posting date proves nothing. Representative batch = lowest id. No schema change.

Code: `monthly_source.multi_instrument_batches_evidencing`, fallback in `refresh_coverage`.
Test: `test_bank_multi_instrument_coverage.py` (15 checks).

## Effect on the golden database

| | Before | After |
|---|---:|---:|
| Missing-source blockers (2026-01..09) | 37 | 36 |
| Coverage rows changed | — | 1 |

Only change: **Business Anthony — 2026-09**, now credited to batch 31
(`Historic Data/Chase3144_Activity_20260922.csv`, no single instrument; 11 Business Anthony rows).
Verified in a rolled-back preview before writing; identical after the write; second refresh changed
nothing. Batches 36, raw rows 15,816, transactions 12,678 and the canonical manifest are unchanged;
no lifecycle, control start, resolution or period status changed.
