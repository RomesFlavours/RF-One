# Bank Reconciliation — one transaction row

**Task:** BANK_RECONCILIATION_001
**Status:** Implemented on `feature/bank-new-reconciliation` — service, page, tests. No schema change. Not deployed.
**Module:** Domain / Shared Domains / Administration / Bank Reconciliation
**UI specification:** the approved disposable prototype (BANK_RECONCILIATION_PROTOTYPE_001), reviewed by the Product Owner and deliberately not part of the product or the repository; the real page is `/bank/reconciliation`
**Builds on:** `BANK_CONFIGURATION_001.md`, `BANK_ECONOMIC_ALLOCATION_FOUNDATION_001.md` (this folder)

---

## The unit of work is one transaction row

`/bank/reconciliation?year=YYYY&month=MM` (default: the previous calendar
month in the Location's time zone) shows, per bank transaction:

Account / Card · Date · Description · Amount · WHO (WHY underneath) · WHO
action · For Whom · Confirm · Status. **No WHAT.**

## Where every fact lives — no new model

| Row fact | Authoritative storage | Written by |
|---|---|---|
| Transactions of the month | `FinancialTransaction`, scope `export.in_scope_transactions` (posting date; confirmed duplicates and accounting-suppressed rows excluded; NULL duplicate status kept) | import |
| Account / Card | `PaymentInstrument.display_name` + last four | Configuration |
| WHO, WHY | the CURRENT `BankTransactionExplanation` | `recognition.record_human_decision` (the one human-decision service) |
| For Whom | `BankTransactionAllocation.reporting_entity_id` | `economic_allocation.set_allocations` |
| Row confirmed | exactly one allocation, `COMPLETE`, `decision_source = HUMAN`, whole amount, same WHY as the current decision | `economic_allocation.set_allocations` |
| New WHO | `BankOccurrence` + associations | `configuration.save_who` (same as Bank Configuration) |

`COMPLETE` already means "who it is for, a WHY, and a resolved account"
(`ck_bta_complete_requires_resolution`); the WHO is taken from the decision.
The WHAT and the intercompany consequence (Due From / Due To when For Whom
differs from the payer) are derived by the allocation service, never chosen.

## Rules

* **WHO modal.** One modal for the page. WHO list = active WHOs (plus an
  inactive one already assigned), searchable, drawn 80 at a time. WHY list =
  the WHO's active possible WHY; its default WHY is only proposed. A WHY
  that is not one of the WHO's possible WHY is refused. WHY may stay open.
  No recognition rule is learned from this modal.
* **Add new WHO** creates the WHO through the Configuration service (name,
  possible WHY chosen from existing WHY, default WHY, entities served) and
  records it on the transaction in the same database transaction.
* **Confirm WHO never confirms the row.** Changing WHO or WHY on a confirmed
  row removes its allocation: the row must be confirmed again.
* **For Whom default** — Bank Account: its owning entity. Credit Card: the
  entity of its settlement account on the transaction date (never the card's
  own value). Every active entity stays selectable; the WHO's served
  entities are marked ✓, not filtered. A changed For Whom is saved only by
  Confirm.
* **Confirm** requires WHO, WHY (resolved decision) and an active For Whom.
  **Reopen** removes the confirmation; the WHO/WHY decision stays.

> **Superseded in part by `BANK_RECONCILIATION_STANDARDS_001.md`:** statuses are now exactly Needs review / Automatic / Confirmed, and the Monthly Export follows them.

## Status — derived, never stored (original version)

| Label | Persisted condition |
|---|---|
| Confirmed | the row-confirmed condition above |
| Ready | current decision has WHO and WHY in a resolved status (`RESOLVED_DECISION_STATUSES`) and a For Whom exists (stored, or the account default) |
| Needs review | anything else |

## Known boundary

The Monthly Export still reads its own resolution rule (a resolved WHO/WHY
decision); it does not require the row confirmation above. Aligning the two
is a Product Owner decision, not made here.
