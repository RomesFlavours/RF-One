# Reconciliation Standards and the inline exception editor

**Task:** BANK_RECONCILIATION_STANDARDS_001
**Status:** Implemented on `feature/bank-new-reconciliation` — schema, services, page, Export alignment, tests. Not deployed.
**Module:** Domain / Shared Domains / Administration / Bank Reconciliation
**Migration:** `b9e4c2a7d5f3` (revises `f6c2e8a4b1d7`)
**Builds on:** `BANK_RECONCILIATION_001.md`, `BANK_ECONOMIC_ALLOCATION_FOUNDATION_001.md`

---

## Three statuses, one definition

`rfone_data_store/bank_reconciliation/reconciliation_status.py` is the only
definition, read by the Reconciliation page and by the Monthly Export.

| Status | Mark | Persisted condition | Exportable |
|---|---|---|---|
| NEEDS REVIEW | red ✗ | anything below does not hold (including an automatic suggestion) | no |
| AUTOMATIC | orange ✓ | one allocation, COMPLETE, decision source RULE, destination source STANDARD, and the current decision names the same Standard, WHY and destination | yes |
| CONFIRMED | green ✓ | COMPLETE HUMAN allocation(s), balanced, no Standard lineage, matching the current decision's WHY and destination | yes |

Marks carry text and an accessible label; colour is never the only signal.

## Reconciliation Standard

`bank_reconciliation_standards`: human-approved knowledge

    recognition signature -> WHO -> WHY -> accounting destination -> For Whom

* **Separate from `BankRecognitionRule`,** which stays WHO-only; its
  purpose-scope CHECK (BANK_WHO_WHY_INVARIANT_001) is unchanged. A Standard
  may carry the WHY only because a person approved the complete result.
* **Signature:** if one identifiable recognition rule produced the
  recognition (the decision's rule, or the single matching active rule),
  its match type, pattern and field are reused; otherwise EXACT on the
  normalized description. Always scoped to the transaction's Account / Card
  and direction. Matched by `recognition._rule_matches` — one recognition
  semantics.
* **At most one ACTIVE Standard per signature** (`ux_brs_active_signature`).
  Same signature and same result: reused. Same signature, different result:
  refused ("no distinct recognition pattern"); the transaction can still be
  saved individually.
* **Applied only at import** (`reconciliation_standards.apply_to_transaction`
  after `recognition.deduce_for_transaction`), and only when the matching
  ACTIVE Standards agree on one still-valid result; otherwise the row stays
  NEEDS REVIEW. Nothing already imported is re-processed.
* **Lineage:** `reconciliation_standard_id` on both the decision and the
  allocation it produced. A later change of the WHY's master mapping does not
  change what a Standard produces (it stores its own destination).

## Accounting destination provenance

`accounting_destination_source` on `bank_transaction_explanations` and
`bank_transaction_allocations`:

| Value | Meaning |
|---|---|
| WHY | derived from the WHY's mapping (every row that existed before this task) |
| TRANSACTION | a person chose this destination for this transaction only |
| STANDARD | supplied by the Standard named in `reconciliation_standard_id` |

Decided by the services from authoritative values (chosen destination vs the
WHY's own), never from a browser flag. A CHECK on each table makes STANDARD
exactly equivalent to "a Standard is named". The WHY master mapping,
Configuration and Standards are never changed by a transaction exception.

**Reclassify** re-derives only WHY-source destinations; it refuses
TRANSACTION and STANDARD ones and leaves them unchanged.

## The page

* **Compact row:** Confirm (this transaction only) and Standard (confirm, then
  create/reuse a Standard); Reopen on a Confirmed or Automatic row. A changed
  For Whom shows "Changed — not saved" (NEEDS REVIEW) until saved.
* **Inline editor** (every row, directly below it, one shared editor): WHO
  (every active WHO), WHY (every active WHY — this editor handles
  exceptions), WHAT (every P&L WHAT, plus the destination the transaction
  already has and the chosen WHY's own, shown truthfully), For Whom (every
  active entity). An Automatic row shows the Standard that produced it.
  **Save — keep Standard unchanged** or **Save as New Standard**; both leave
  the current transaction CONFIRMED.

## Export

`export._resolution_facts` now counts a transaction as resolved only when it
is AUTOMATIC or CONFIRMED (confirmed internal transfers keep their existing
exemption). Blocker text: "Needs review: …". The Kermali workbook is
unchanged.
