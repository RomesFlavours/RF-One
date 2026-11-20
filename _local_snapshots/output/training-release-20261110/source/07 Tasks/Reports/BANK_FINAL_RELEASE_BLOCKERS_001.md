# BANK_FINAL_RELEASE_BLOCKERS_001 — Report (Bank + Tips)

**Date:** 2026-09-24  ·  **Scope:** local code and tests, plus PostgreSQL validation on disposable `rfone_pgval_*` databases only (no deploy, no push, live database never written)

This task fixed the seven release blockers found by the Final Under-the-Rug Audit.

## Fixes

| # | Blocker | Fix | Where |
|---|---|---|---|
| B1 | A Who's default Why was applied as the transaction's Why | No live path applies `default_transaction_reason_id`. Confirming a Who records only the Who and leaves the Why open. The usual Why is shown only as a labelled suggestion. Reclassify keeps the decision's own Why. An INACTIVE Who is refused. | `recognition.record_human_decision`, `recognition.reclassify_transaction`, `service.record_recognition_decision`, `receiver_candidates.approve_candidates`, `bank_routes.py` Who picker |
| B2 | Two competing automatic WHY engines | One engine, `structural_why.recognize_transaction`: structural rules first, then the source memo. Import, reprocess, instrument reassignment and receivers review all use it. `deterministic_rules` decides no Why at runtime. `apply_deterministic_bank_classification.py` is retired. | `structural_why.py`, `recognition._propose` |
| B3 | Reprocess could replace decisions | `recognition.redecide_for_transaction` never touches a HUMAN decision. It appends a new decision only when the engine's Why (or the recognised Who) changes, so repeated reprocess changes nothing. | `recognition.py`, `service._reprocess_transaction` |
| B4 | The instrument edit form could change the lifecycle `status` | The service refuses any `status` change. The route drops the field and the form shows the state read-only. Lifecycle changes only through Monthly Sources (CLOSED / LOST / REPLACED / OTHER, STILL_ACTIVE). | `service.update_payment_instrument`, `bank_routes.py`, `bank_instrument_edit.html` |
| T1 | Two persisted Tips calculations; one used UTC midnight | "Run Calculation Now" and the scheduler persist through `calculation_run_service.save_calculation_run`, the same service "Calculate and save this period" uses. It works over the Location's Business Day (timezone + 04:00 cutoff, Order Open Time). Readiness uses the same window. The preview stays stateless. | `payout_process.py`, `readiness.py` |
| T2 | Every unpaid entitlement was payable | Only entitlements of a FINAL run are payable. A Business Date can be in only one FINAL run: finalizing a run whose range overlaps a FINAL run is refused, so no day is paid twice. No new status was added. | `payment_cycle_service.get_unpaid_entitlements`, `calculation_run_service._blocking_final_run` |
| T3 | Clover fee `percentage` overflowed PostgreSQL `Numeric(7,4)` | The raw value is divided by 10000 (180000 → 18). | `technical/connectors/clover/mapping.py` |

## Tests

- New: `test_bank_final_release_blockers.py` (21 checks: Bank cases 1–13 and the B3 disagreement case) and `test_tips_final_release_blockers.py` (14 checks: Tips cases 1–11). Tips case 12 (Host eligibility, Order Open Time, VOLUNTARY + GRATUITY) is covered by the existing, unchanged suites: host audit, distribution engine, order service owner and stateless calculation. The engine code was not modified.
- Existing tests that asserted the old behaviour (Why derived from the Who; entitlements payable without validation; UTC window; a second FINAL run for an overlapping range) now assert the new rules, or have the person choose the Why explicitly.
- `tips_payment_execution_validation.py`: its `SourceSystem.code` exceeded `String(32)`. PostgreSQL rejects that and SQLite did not, so the code is now cut to the column length (test fixture only).

## Deliberately not changed

- `default_transaction_reason_id` and every other schema field. There are no migrations; the Alembic head stays `e7b2c94d0f18`.
- `deterministic_rules` is kept as seed vocabulary for migrations and seeding, and for analysis scripts.
- `distribution_engine.run_tip_distribution_calculation` is kept, but no runtime caller is left. It persists no entitlements.
- `ai_client.py`, `.env.example`, `CLAUDE.md` and the other unrelated working-tree files.
