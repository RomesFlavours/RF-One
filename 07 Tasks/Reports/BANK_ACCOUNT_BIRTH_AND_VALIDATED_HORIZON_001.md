# BANK_ACCOUNT_BIRTH_AND_VALIDATED_HORIZON_001 — Report

**Date:** 2026-09-24  ·  **Scope:** local golden database only (no AWS, no deploy)
**Product Owner rules:** birth = first eligible posting date; the last transaction never ends a
life; data validated through 2026-08, September 2026 provisional.

## Implementation

| Item | Where |
|---|---|
| Birth derivation (MIN eligible posting date, same population as the MAX closure rule) | `monthly_source.first_posting_date`, `derive_birth_dates` |
| Validated-through horizon (additive nullable column) | `BankReconciliationControlConfig.validated_through_month`, migration `d3f8a61c2e47` |
| Provisional months: not opened/refreshed, gaps shown not enforced, not certifiable | `bring_months_under_control`, `evaluate`, `complete_period` |
| Setting the horizon (advance → apply to existing batches; move back → setting only) | `set_validated_through`, `activate_validated_through`; route `POST /bank/monthly/validated-through` |
| Neutral blocker wording inside the validated horizon | `evaluate` |
| Runner option `--validated-through`; guard allows only the birth date on instruments | `activate_reconciliation_control_start.py` |
| Test | `test_bank_account_birth_and_validated_horizon.py` (20 checks) |

`evaluate_expectation` is unchanged. STILL ACTIVE reuses the existing `NO_ACTIVITY` resolution
("existed, stayed active, nothing happened"), which writes no end date.

## Effect on the golden database

| | Before | After |
|---|---:|---:|
| Enforced blockers (2026-01..08 + 09) | 36 | 13 |
| Removed: pre-birth months | — | 20 |
| Removed: September provisional | — | 3 |
| Removed for any other reason / added | — | 0 / 0 |
| Birth dates derived | 0 | 14 (Chase-2915: none — no transactions) |
| End dates / lifecycle reasons / status changes | — | 0 |

Remaining (human decisions): Chase-2915 2026-01..08 (8), Amex 2026-04..08 (5).
Financial data (36 batches, 15,816 raw rows, 12,678 transactions, canonical manifest) unchanged.
