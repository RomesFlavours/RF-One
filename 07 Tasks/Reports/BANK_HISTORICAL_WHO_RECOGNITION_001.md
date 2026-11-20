# BANK_HISTORICAL_WHO_RECOGNITION_001 — Report

**Status:** COMPLETED AND VALIDATED (resumed by BANK_RECOVER_STATE_AND_CONTINUE_EXPERTIZATION_001, 2026-09-24)
**Recognizer version:** `who-v1`  ·  **Migration:** `c6a2e8f41d93` (additive)
**Scope:** local golden database only. No AWS, no deploy.

Safe, aggregate content only: no raw description, no personal counterparty
name and no full account number appears here.

---

## 1. Recovered state (before resumption)

| Evidence | Observed |
|---|---|
| Golden DB SHA-256 | `85677e67…4927`, byte-identical to `rfone.db.pre-who-recognition-20260923T212704Z` |
| DB Alembic revision | `b31e7c0d9a54` (repository head was `c6a2e8f41d93`: WHO migration written, never applied) |
| WHO tables | absent; `bank_occurrences` 0, aliases 0 |
| Code | `who_recognition.py`, migration, model classes written (uncommitted); no test, no runner, no report |

Classification: **WHO_TASK_PARTIAL_RESUMABLE** — code partially complete, nothing
persisted, financial data untouched. Resumed without discarding any work.

## 2. What was completed on resumption

| Item | Change |
|---|---|
| Zelle (First Citizens "Zelle NAME phone") | Was DETERMINISTIC; now PROPOSED. The name slot is fixed-width and visibly truncated, and deterministic Zelle recipient extraction is limited to the structured Chase line. An exact match on an RF-One legal entity stays STRUCTURAL. |
| `test_bank_who_recognition.py` | New — 38 checks (parsers, refusals, persistence, supplier linking, idempotency, financial immutability). |
| `apply_who_recognition.py` | New — preview/apply runner; rolls back if the canonical manifest or raw/canonical counts move. |

## 3. Results on the golden database

| Tier | Transactions | Share |
|---|---:|---:|
| DETERMINISTIC | 9,599 | 75.7% |
| STRUCTURAL (counterparty is RF-One itself) | 567 | 4.5% |
| PROPOSED (operator decides) | 992 | 7.8% |
| UNRESOLVED | 1,520 | 12.0% |
| **Total** | **12,678** | |

WHO occurrences created: **1,229** · aliases: **1,644** · recognition rows: **12,678** ·
WHO↔Supplier links: **0** (exact-name only; the Supplier catalog holds 7 rows, several
of them OCR noise, and none equals a recognised WHO) · recognition rules: **0** (a rule
carries a WHY; recognition never does).

Largest families: POS fixed-width DBA 2,505 · card-network descriptor 2,217 · card
merchant 2,012 · counterparty not named (cheques, cash, deposits) 1,388 · ACH originator
929 · Chase Zelle recipient 913 · ACH masked-reference (corroborated/invariant) 632 ·
internal transfer to a registered instrument 266 (structural) / to an unregistered
account 110 (unresolved, never guessed) · card settlement received 255 (structural).

## 4. Requirement checks

| Requirement | Outcome |
|---|---|
| WHO does not determine WHY / FOR WHOM | PASS — no WHY column, no decision row, no allocation, no default WHY written |
| Deterministic only from source structure | PASS — every DETERMINISTIC row names its parser and evidence |
| No fuzzy merges | PASS — identical normalized key only; store numbers kept |
| Internal transfers / own entities create no WHO or supplier | PASS — STRUCTURAL, `occurrence_id` NULL (CHECK-enforced) |
| Zelle recipient only from structured Chase description | PASS (after the correction in §2) |
| Zelle Payment Activity PDF not used | PASS — not read |
| Second run idempotent | PASS — 0 created / 0 updated / 12,678 unchanged (run 3 times) |
| Canonical financial data unchanged | PASS — full `financial_transactions` table hash identical before/after WHO |

## 5. Open observations

* Seven card purchases name the business's own restaurant brand as merchant. RF-One has no
  registry of its own trade names linked to legal entities, so they stay an external WHO;
  not guessed.
* Supplier catalog quality (OCR-noise supplier names) prevents useful exact linking.
* First Citizens transfers to accounts ··8326 / ··8190 and Chase external transfers name
  accounts RF-One has not registered; they are not among the four historical instrument
  candidates.
