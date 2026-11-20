# BANK_HISTORICAL_DETERMINISTIC_WHY_EXPERTIZATION_001 — Report

**Status:** COMPLETED (first iteration)  ·  **Recognizer version:** `why-v1`
**Module:** `rfone_data_store/bank_reconciliation/structural_why.py`  ·  **Runner:** `apply_structural_why.py`
**Scope:** local golden database only. No AWS, no deploy. No schema change.

Safe, aggregate content only.

---

## 1. Principle applied

WHY is decided only from the transaction's own text read together with RF-One's instrument
registry — never from who the counterparty is and never from history. Three outcomes:
DETERMINISTIC, STRONG_STRUCTURAL (purpose determined; a separate ownership question stays with
Economic Allocation), UNRESOLVED. WHAT / Balance Sheet destination is derived from the WHY by
the existing decision function; no allocation is created.

Rules are versioned code, not `bank_recognition_rules` rows: a recognition rule always names a
WHO, and `ck_bank_recognition_rule_purpose_scope` forbids a description rule from deciding
purpose. Each decision is a `bank_transaction_explanations` row, `decision_source = RULE`,
`decision_status = AUTO_APPLIED`, confidence HIGH (deterministic) / MEDIUM (strong structural),
notes tagged `[why-v1:<RULE>]` with the evidence.

## 2. Rules and corpus QA (all 12,678 canonical transactions)

| Rule | Tier | WHY | Matches | Known contradictions |
|---|---|---|---:|---:|
| CARD_PAYMENT_RECEIVED (issuer "…THANK YOU", credit, card layouts) | DET | CREDIT_CARD_SETTLEMENT | 255 | 0 |
| ONLINE_TRANSFER_RELATED_ENTITY (both accounts registered, different LLCs) | STRONG | RELATED_PARTY_TRANSFER_OUT / _IN | 69 / 102 | 0 |
| ISSUER_ACH_CARD_PAYMENT (Amex ACH PMT, Chase Credit Crd AUTOPAY/AUTOPAYBUS, Amazon store card) | STRONG | CREDIT_CARD_SETTLEMENT | 160 | 0 |
| FOREIGN_TRANSACTION_FEE (debit) | DET | FOREIGN_TRANSACTION_FEE | 116 | 0 |
| BANK_SERVICE_CHARGE (named bank fees, bank-account layouts, debit) | DET | BANK_SERVICE_CHARGE | 100 | 0 |
| MERCHANT_SERVICE_FEE (merchant-services FEE / INTERCHNG / DISCOUNT) | DET | MERCHANT_PROCESSING_FEE | 54 | 0 |
| INTEREST_INCOME (exact "INTEREST PAYMENT", credit, bank account) | DET | INTEREST_INCOME | 31 | 0 |
| LOAN_ADVANCE (bank credit memorandum "ADVANCE ON LOAN") | DET | LOAN_ADVANCE | 12 | 0 |
| CARD_PAYMENT_OWN_CARD (registered card, paid by its own settlement owner) | DET | CREDIT_CARD_SETTLEMENT | 11 | 0 |
| ONLINE_TRANSFER_SAME_ENTITY (both accounts, same LLC) | DET | INTERNAL_BANK_TRANSFER | 6 | 0 |
| LOAN_INTEREST_PAID (bank debit memorandum "INTEREST PAYMENT ON LOAN") | DET | INTEREST_EXPENSE | 3 | 0 |
| BANK_SERVICE_CHARGE_REFUND (refund naming the service/overdraft fee) | DET | BANK_SERVICE_CHARGE | 2 | 0 |

Corrections made during QA before persisting:

* "INTEREST PAYMENT ON LOAN" is a **debit** — excluded from INTEREST_INCOME by exact text and
  direction; it is INTEREST_EXPENSE.
* Almost every online transfer connects **two different legal entities**. INTERNAL_BANK_TRANSFER
  ("between the company's own accounts") would be wrong for them; the canonical related-party
  WHYs are used instead, and transfers involving a personal instrument are left unresolved.
* The Chase `AUTOPAYBUS` entry fills its 10-character field and runs into `SEC:`; the pattern
  was widened for that (coverage, not a false positive).

## 3. Results

| Measure | Count | Share |
|---|---:|---:|
| Canonical transactions | 12,678 | |
| WHY DETERMINISTIC | 590 | 4.7% |
| WHY STRONG STRUCTURAL | 331 | 2.6% |
| **WHY resolved total** | **921** | **7.3%** |
| WHY from invoice evidence | 0 | — (0 WHO↔Supplier links, 0 invoice matches) |
| WHY unresolved | 11,757 | 92.7% |
| Money-movement / Balance Sheet WHY | 615 | |
| P&L WHY | 306 | |
| Zelle payments without WHY | 960 | (the 41 Zelle lines with a WHY are the bank's own fee) |
| Rule count | 12 | |

Second run: 0 created, 921 unchanged, 0 conflicts. Post-persistence QA: 100 random
assignments, every rule under 10 matches and every money-movement rule inspected against the
raw text; destination, direction and status checked on all 921 — 0 problems. Allocations: 0.

## 4. Deliberately unresolved (missing business rule or insufficient evidence)

| Family | Rows | Why not decided |
|---|---:|---|
| No structural purpose (card/POS purchases, ACH suppliers) | 8,323 | Identity is not purpose; needs invoice evidence or later expertise |
| Cheque / cash / deposit | 1,294 | Source names neither party nor purpose |
| Zelle | 960 | No payment note in the structured line |
| Merchant settlement deposits | 638 | No clearing / undeposited-funds WHY; revenue would double-count POS sales |
| Transfers to unregistered accounts / wallets / wires | 230 | Other side not guessed |
| ADP Tax | 73 | Impound includes employee withholdings, not purely employer tax (6500) |
| Tax authority (FL DOR C01, IRS) | 64 | Code does not prove tax type |
| Transfers involving a personal instrument | 64 | Contribution vs loan vs draw not defined |
| ADP wage pay | 54 | Payroll detail required (Payroll not touched) |
| Payment to unregistered card (the 4 candidates) | 19 | Candidate owners unresolved |
| Card payment across owners | 14 | Settlement vs draw vs related-party funding |
| Merchant chargeback/adjustment, FDMS | 14 | Fee vs equipment vs reversal not stated |
| Unspecified fees (fee reversal, card late/annual fee) | 10 | Kind or canonical account not established |

## 5. Invariants

Raw rows 15,816 · canonical transactions 12,678 · canonical manifest
`eb64a5f30414d222084cabc28cd5a393f7b2cf398d3247688766f09f1a4d8c8a` · per-instrument counts,
debits and credits · 4 unresolved candidates · payment instruments — all unchanged. The only
column written on `financial_transactions` is the current-decision pointer `explanation_id`
(approved decision model); every other column is hash-verified unchanged.
