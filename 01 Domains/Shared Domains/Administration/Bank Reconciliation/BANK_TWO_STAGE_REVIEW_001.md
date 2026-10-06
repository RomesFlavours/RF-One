# Review in two queues: To Reconcile and Reconciled

**Task:** BANK_TWO_STAGE_REVIEW_001
**Status:** Implemented on `feature/bank-simple-who-rules` — service, page, tests. Not committed, not deployed.
**Module:** Domain / Shared Domains / Administration / Bank Reconciliation
**Schema:** no migration, no new status column.

---

## What it is

`/bank/review` is split into two tabs, each a VIEW over facts already persisted
(`rfone_data_store/bank_reconciliation/review_queues.py`):

| Tab | A transaction is here when | Work done here |
|---|---|---|
| **To Reconcile** (default, `view=to_reconcile`) | its current decision names **no** WHO — no decision, no matching rule, contradicting rules, or only a raw recognizer proposal — or its duplicate question is still open | Select Who, **Rule** (shared modal), Distinct / Duplicate |
| **Reconciled** (`view=reconciled`) | the WHO question is answered: its current decision (`FinancialTransaction.explanation_id` -> `BankTransactionExplanation.occurrence_id`) names a WHO — from a rule, a person, a Standard or an earlier decision — **or** it is an own-account movement, which has no WHO by design (see below) | WHY, WHAT, For Whom, Confirm, Standard, Reopen — the Reconciliation rows |

### Own-account movements are resolved without a WHO

To Reconcile means *the business meaning is still unresolved*, not *the WHO field is empty*.
A transfer between RF-One's own accounts has no external counterparty, and the model records
it deliberately **without** a WHO. It is resolved for queue purposes — and listed under
Reconciled — when either authoritative fact already in the model holds
(`review_queues.own_account_movement`):

* its current WHO recognition (`BankWhoRecognition`, `who-v1`) is **STRUCTURAL** — the
  recognizer proved from registered RF-One data that the counterparty is RF-One itself: a
  registered instrument (`INTERNAL_TRANSFER`), one of its own legal entities
  (`OWN_LEGAL_ENTITY`), or a card settlement paid from its own funds
  (`CARD_SETTLEMENT_RECEIVED`); or
* it is one side of a confirmed `FinancialTransactionMatch` of type `INTERNAL_TRANSFER` (the
  cross-ledger link the Monthly Export trusts).

No WHO is invented for it. On Reconciled the WHO cell reads *Internal transfer · <other
account>* (or *Own legal entity*, *Card payment from own funds*, *Internal transfer (matched)*)
instead of *No WHO yet*; WHY and WHAT are the existing decision's, unchanged. Its status stays
the truthful one from `reconciliation_status` (*Needs review* — see Open points). A Rule Apply
counts these rows as *Own-account transfers resolved without WHO* and says they are under
Reconciled; they are not failures.

A raw `BankWhoRecognition` is the recognizer's proposal, not an authoritative WHO: a
transaction recognised only as `SAMUELS AND SON SEAF` stays To Reconcile until a Rule or a
person gives it a WHO. The moment its decision names a WHO — even with WHY or For Whom still
open, even if no person confirmed it — it moves to Reconciled. Nothing ever sends it back for an
incomplete WHY.

Scope is the Monthly Export's (`_not_confirmed_duplicate`, `not_suppressed_filter`). A copy
suppressed as an accounting duplicate is never counted; it stays visible at the end of To
Reconcile, marked *Excluded from accounting*, because the Review remains the audit view of the
deduplication (BANK_CARDHOLDER_AND_ACCOUNTING_DEDUPLICATION_001).

> **Since BANK_MANUAL_WHO_WHY_001** *Select WHO* is the "Select WHO / WHY" popup (WHO **and** WHY for
> one transaction, a HUMAN decision; never a rule), and Reconciled shows WHO, WHY and WHAT on the row with
> WHY editable there. See `BANK_MANUAL_WHO_WHY_001.md`.

## Reconciled reuses the Reconciliation rows

The tab renders `bank_reconciliation.html` in review mode from `row_reconciliation.rows_view`
(the function `month_view` now calls), so status, editor and actions have one definition:

* statuses from `reconciliation_status`: **Automatic** (orange check — completed by an approved
  Standard, exportable with no click), **Confirmed** (green check — accepted by a person),
  **Needs review** (WHO known, something still open);
* rows still to accept come first (no COMPLETE allocation yet), then the accepted ones;
* every row action (WHO, Confirm, Standard, Save, Reopen) returns to the same tab, filters and
  row (`return_to`, accepted only for a `/bank/review` address).

## Navigation and filters

* Tabs show **To Reconcile (N)** and **Reconciled (M)** for the same month / instrument / batch,
  counted by one grouped query; the tab links carry those filters.
* The former *Status* filter (candidate duplicates / requires review) is removed: the two tabs
  are the status split. The Import page's batch link opens the batch in Review without it.
* After a Rule Apply on To Reconcile the page reloads without the rows that now have their WHO,
  and the result says *WHO assigned to N transactions: they are now under Reconciled* with a
  **View reconciled transactions** link.

## Performance (production-shaped disposable copy, August 2026)

| | Before | After |
|---|---|---|
| To Reconcile (396 rows) | 4.6–5.3 s, 491 SQL statements | 0.5–0.7 s, 97 statements |
| Reconciled (28 rows) | — | 0.07–0.23 s, 28 statements |

The gain is `matching.find_cross_ledger_candidates_for_many`: the internal-transfer candidates of
every row in two queries instead of two per row, by the same criteria (tested equal to the
per-row function).

## Open points

* An undecided candidate duplicate stays To Reconcile even with a WHO, because the duplicate
  decision lives there — own-account movements included.
* **Own-account movements cannot yet be Confirmed or exported.** `reconciliation_status` makes
  Confirmed / Automatic (the exportable statuses) require a WHO, and Confirm refuses a row without
  one. An own-account movement is therefore listed under Reconciled as *Needs review* with Confirm
  disabled. Letting it be accepted without a WHO is a change to the status and export rule, left
  to a Product Owner decision; it is not part of the queue correction.
* The Reconciled editor replaces the old Review's *Reclassify* button (the route remains); a WHY
  change is saved through the editor.
* To Reconcile still renders each row's instrument-reassignment form; its HTML (≈2.7 MB for a full
  month) is the next size reduction.
