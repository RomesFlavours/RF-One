# BANK_EXPLICIT_STILL_ACTIVE_DECISION_001 — Report

**Date:** 2026-09-24  ·  **Scope:** local golden database only (no AWS, no deploy)

## Implemented

| Item | Where |
|---|---|
| New resolution `STILL_ACTIVE` in the existing vocabulary | `models.RESOLUTION_STILL_ACTIVE`, `COVERAGE_RESOLUTIONS` |
| DB CHECK widened by one value (downgrade refuses while a STILL_ACTIVE row exists) | migration `e7b2c94d0f18` |
| Eligibility (server-authoritative, also used by the UI) | `monthly_source.still_active_refusal` |
| Effect: month resolved, instrument status → ACTIVE, no dates written | `monthly_source.resolve_coverage` |
| UI: option shown only for eligible instruments | `RF-One Web/bank_routes.py` (monthly view), `templates/bank_monthly.html` |
| Test | `test_bank_still_active_decision.py` (17 checks) |

Refused when: the instrument is already ACTIVE (use `NO_ACTIVITY`, unchanged); it has an end date
or lifecycle reason; or any month records CLOSED / LOST / REPLACED / OTHER for it.

## Golden database

Only the schema migration was applied. No resolution was recorded. Chase-2915 unchanged
(INACTIVE, no start, no end, no reason) and the only instrument currently eligible for
STILL ACTIVE. Blockers remain 13. Batches, raw rows, transactions, instruments, coverage and
configuration hashes identical before and after.
