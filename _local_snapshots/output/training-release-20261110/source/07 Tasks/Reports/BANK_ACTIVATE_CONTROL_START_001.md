# BANK_ACTIVATE_CONTROL_START_001 — Report

**Date:** 2026-09-24  ·  **Scope:** local golden database only (no AWS, no deploy)
**Product Owner decisions:** control start = 2026-01-01; apply the boundary to batches
already imported when the start is first set or moved earlier.

Aggregate content only.

## 1. What changed in code

| File | Change |
|---|---|
| `rfone_data_store/bank_reconciliation/monthly_source.py` | `months_spanned`, `bring_months_under_control`, `apply_control_to_existing_batches`, `activate_control_start` — orchestration over the EXISTING `get_or_create_period` / `refresh_coverage` / `evaluate` |
| `RF-One Web/bank_routes.py` | import hook and control-start route use the shared service; the route applies the boundary to existing batches on first set / earlier move |
| `RF-One Web/templates/bank_monthly.html` | explanatory text |
| `activate_reconciliation_control_start.py` | new guarded runner (preview / `--apply`) |
| `test_bank_control_start_activation.py` | new — 28 checks |
| `tests/test_bank_reconciliation_control_start_http.py` | check 12d0: backward move opens months before any re-upload |

No schema change, no migration.

## 2. Result on the golden database

| Measure | Value |
|---|---:|
| Batches examined (non-rejected, dated) | 36 |
| Historical months spanned, not opened | 85 (2018-12 .. 2025-12) |
| Controlled months created | 9 (2026-01 .. 2026-09) |
| Coverage rows created | 135 (9 × 15 instruments) |
| Months COMPLETE | 0 |
| Resolutions written | 0 |
| Second run | 0 created, 9 reused, 135 rows unchanged |

All 135 coverage rows are NEEDS_HUMAN_CONFIRMATION: no instrument has an effective start
date, so the existing expectation rule cannot say whether it was active. Instruments credited
with a source file are not blockers; the rest are:

| Instrument | Months without a credited source (2026) |
|---|---|
| Chase-2915 (registered, no source) | 01–09 |
| Ceo Checking | 01–07 |
| Amex | 04–09 |
| Ink Unlimited | 01–04 |
| Business Anthony | 01–04, 09 |
| Ink Giovanna | 01–03 |
| RFMD Checking | 01–02 |
| RF Saving | 09 |

Blockers per month: 6, 6, 5, 5, 3, 3, 3, 2, 4 (Jan..Sep) = 37.

## 3. Invariants

Batches 36 · raw rows 15,816 · transactions 12,678 · canonical manifest
`eb64a5f30414d222084cabc28cd5a393f7b2cf398d3247688766f09f1a4d8c8a` · full hashes of
`financial_transactions`, `payment_instruments`, `bank_import_batches` · WHO/WHY/allocation
counts — all unchanged (guarded; the run rolls back otherwise). Every instrument keeps its
status and lifecycle fields.

## 4. Observations for the operator

* Business Anthony 2026-09 has transactions, but only through the multi-card Chase ··3144
  download (batch without a single instrument). Existing file-to-instrument identity credits a
  month only to a batch's own instrument, so the month shows a blocker. Not changed.
* Ceo Checking, RFMD Checking, Ink Unlimited, Ink Giovanna and Business Anthony have no data
  before a given 2026 month; whether they were open then is an operator decision (lifecycle not
  inferred).
* Amex data ends 2026-03-31; April–September sources are missing or the card changed.
