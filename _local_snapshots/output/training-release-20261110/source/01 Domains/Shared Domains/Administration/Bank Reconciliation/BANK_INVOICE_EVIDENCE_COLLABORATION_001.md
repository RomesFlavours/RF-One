# Invoice Evidence for Bank Assessment

**Task:** BANK_INVOICE_EVIDENCE_COLLABORATION_001
**Status:** Implemented — schema, services, tests. No historical Bank import, no export change.
**Module:** Domain / Shared Domains / Administration / Bank Reconciliation
**Migration:** `e5b28d413f7a`
**Builds on:** `BANK_ECONOMIC_ALLOCATION_FOUNDATION_001.md` (this folder)

---

## The principle

**Bank Assessment is the accounting and reporting control point. Invoices
are evidence it consumes.**

There is no second accounting assessment at invoice level, and no parallel
reporting ledger built from invoices. Purchasing classifies and prepares;
Bank Assessment decides. Reporting reads `BankTransactionAllocation` and
nothing else, exactly as before.

```text
BANK TRANSACTION            the movement of money
      ↓  BankInvoiceMatch   many-to-many, with amounts
PURCHASE DOCUMENT           the evidence
      ↓  PurchaseLineClassification
INVOICE LINES               what each item is, and who it was for
      ↓  aggregate by (economic owner, WHY)
BANK TRANSACTION ALLOCATION(S)
      ↓
P&L
```

---

## The operator is never asked an accounting question

> "Should this be 5100 or 7830?"

is a question RF-One must answer for itself, from the invoice item.

> "Who were these items for — Winter Park, Mount Dora, or Corporate?"

is an operational question only a person can answer, and it is the only
kind the system asks.

Accordingly there is **no way anywhere in this module to choose an
account**. An operator picks a WHY; the canonical destination follows from
it through `BankTransactionReason`, exactly as it already does for bank
decisions. The WHY → WHAT chain is untouched.

---

## WHO category capability

A counterparty (`BankOccurrence`) now carries what it is *capable* of
supplying:

| Value | Meaning |
|---|---|
| `SINGLE_CATEGORY` | Normally one accounting category. No invoice decomposition needed. |
| `MULTI_CATEGORY_CAPABLE` | **When a matching invoice exists, its lines MUST be examined.** |
| `UNKNOWN` | Not yet known. Never treated as `SINGLE_CATEGORY`. |

`MULTI_CATEGORY_CAPABLE` does **not** mean a given payment contains
several categories. Most Cheney invoices are food and nothing else. It
means exactly one thing: *WHO alone may never decide WHY for this
counterparty while a document exists to be read.*

So `WHO = Cheney` does **not** imply `WHY = FOOD_PURCHASES`. The invoice
decides.

This is deliberately a separate column from
`BankOccurrence.default_transaction_reason_id`, which is a suggestion
about *meaning*. Capability is about *evidence*.

### How a capability is established

* an operator configures it, or
* **a real invoice establishes it by itself** — a document whose confirmed
  line classifications resolve to two or more different canonical accounts
  is direct proof. No prior configuration is required before RF-One can
  discover the fact.

### It is never downgraded automatically

Once a supplier has been shown to issue several categories, the next ten
single-category invoices do not unlearn it. A supplier that *can*
decompose still can. Only an explicit operator decision
(`allow_downgrade=True`) may move it back, and that decision records its
own evidence.

---

## Missing invoice: financially reconciled, accounting pending

This is the rule the task exists to enforce.

When a `MULTI_CATEGORY_CAPABLE` counterparty's invoice is **absent**:

* the bank movement may be **financially reconciled** and perfectly
  canonical;
* its accounting allocation stays **`PENDING_EVIDENCE`** — one allocation
  for the full amount, with **no WHY, no account, no beneficiary**;
* RF-One does **not** fall back on what that supplier usually meant;
* the reporting period **cannot become accounting-complete** while it
  remains unresolved.

The existing canonical `PENDING_EVIDENCE` status is reused. No new
vocabulary was invented for this case.

---

## Explicit human bypass

An operator may authorize classification without the missing invoice. This
is **never a silent fallback**: nothing calls it on RF-One's behalf, and a
reason is mandatory.

`BankEvidenceBypassAuthorization` records the operator, the timestamp, the
reason, the counterparty and its capability at that moment, and the fact
that the document was unavailable. Every allocation produced under it
carries `evidence_kind = OPERATOR_BYPASS` and a reference to the
authorization.

It lives in its own append-only table, **not** on the allocation row,
because allocations are restated as a whole set whenever a split is
corrected — an authorization recorded there would vanish the first time
somebody fixed a number. It is never deleted, including after the missing
invoice turns up. That the classification was once made without the
document remains true.

---

## Supplier item learning — two confirmations, not ten

Supplier product substance is stable. After **two consistent
human-confirmed classifications** of the same (supplier item, WHY), the
mapping is `LEARNED` and is proposed automatically on later invoices.

* **One confirmation teaches nothing.** It stays `OBSERVED` and proposes
  nothing.
* **A machine proposal never teaches itself.** Only `HUMAN` + `CONFIRMED`
  decisions record a confirmation.
* **Per-line override is always available**, and the overridden proposal
  is preserved as history rather than erased.
* **An override does not automatically rewrite the rule.** One
  disagreement against two confirmations is *recorded on the learned
  mapping* — visible, not hidden — but does not overturn it.
* **A genuine contradiction suspends learning.** When a second WHY also
  reaches two confirmations for the same item, both mappings become
  `CONTRADICTED` and automatic proposal stops until a person decides.
  Neither side is deleted or overwritten.

### Item identity, strongest evidence first

1. the canonical `SupplierProduct` — the `(Supplier, Supplier Item Code)`
   pair Purchasing already treats as supplier product memory;
2. the supplier's own item code as printed;
3. a normalized description, **only** when the source offers nothing
   better.

`supplier_id` is part of every key, so the same description from two
different suppliers is two different things and learning never leaks
between them.

Not to be confused with InvoiceIntake's `supplier_format_training`, which
trains how to *parse* a supplier's document layout. Different question,
different application, different database.

---

## Ancillary costs — reused, not reinvented

Tax, freight, shipping, service fees and other invoice-level non-goods
costs are apportioned across item lines **in proportion to item value** by
Purchasing's existing, tested
`repository.get_purchased_lines_with_allocation`. This task **calls** it.

```text
Items:      Food 700   Packaging 300
Ancillary:  100

Result:     Food 770   Packaging 330      Total 1100
```

The only proportional arithmetic written here is at a *different* level —
distributing a payment across category totals when a payment covers part
of an invoice — and it follows the same deterministic rule: proportional
shares with the last share absorbing the odd cent, so parts always sum to
the whole. Exact-money integer arithmetic throughout; nothing rounds away.

---

## Bank ↔ Invoice matching

Genuinely many-to-many, with amounts, because that is how suppliers are
actually paid:

| Case | Supported |
|---|---|
| one payment → one invoice | yes |
| one payment → several invoices | yes |
| several payments → one invoice | yes |
| explainable amount difference | yes, recorded as a stated kind |

`BankInvoiceMatch.matched_amount_minor` is what makes this checkable.
Without a per-link amount, "this payment covers those three invoices" is
an assertion nobody can verify.

Matching evidence considered: supplier/WHO (through the new WHO ↔ Supplier
link), amount, dates, document number appearing in the bank reference,
payment instrument, combinations of invoices, and amounts already matched.

### Two hard amount controls

* a transaction may never have more matched to it than it is worth;
* an invoice may never have more matched to it than it is payable for.

Neither difference is absorbed. What is left over is reported by
`unmatched_difference`, in figures and in words.

### Ambiguity is reported, never resolved by guessing

Two different combinations of invoices that both sum to the payment are
ambiguous by definition. RF-One writes **nothing** — not an auto-match and
not even a proposal. Auto-confirmation happens only when exactly one
candidate is high-confidence, unambiguous and exactly balancing.

---

## FOR WHOM is never guessed

Invoice/delivery evidence establishes the beneficiary when it can.
Since `BANK_REPORTING_CONFIGURATION_001`, `PurchaseDocument.
destination_location` is resolved through the destination mapping catalog
(supplier scope first, then global), with an exact match against a
reporting entity's own name kept only as a secondary fallback.

When it does not, **only the operator may choose**, and the question is
asked at the smallest useful level, with bulk selection when several lines
share an answer.

The beneficiary is **never** inferred from:

* the payer;
* a historical majority;
* the supplier's identity;
* the product category;
* previous purchases from the same supplier.

Amazon is the canonical example: one order of toner, pans and shelving can
legitimately belong to three different entities.

> ~~**Known gap:** RF-One has no configured mapping from a supplier's
> ship-to text to a reporting entity, so only a destination that already
> reads like the entity's own name resolves automatically.~~
> **CLOSED by `BANK_REPORTING_CONFIGURATION_001.md` §5.**
> `ReportingEntityDestinationAlias` is that catalog: a destination text
> maps to a reporting entity, scoped per supplier where the evidence is
> supplier-specific and global only where the text carries that claim.
> Exact equality with the entity's name is no longer required, and remains
> only as a secondary fallback.

---

## Personal payer — Product Owner decision

When a **personal** payment instrument pays a legitimate business expense
for a Legal reporting entity, the business side is:

**`2710 Due To Related Parties`, by default.** The business owes the
individual back.

It is **not** automatically `3300 Member Contributions` — treating a
reimbursable payment as permanent equity would assert something nobody
said. `3300` applies **only** when an operator explicitly classifies the
funding as a non-reimbursable Member Contribution
(`personal_funding_treatment = MEMBER_CONTRIBUTION`).

No fake `LegalEntity` is created for the individual, and no LLC-to-LLC
intercompany position arises — there is no second LLC.

When a **company** pays a **personal** expense, the existing Owner/Personal
WHY model is untouched: depending on the WHY selected, the canonical
destination remains `1610 Due From Related Parties` or `3400 Member
Distributions / Draws`. No new universal rule overrides those semantics.

This closes the gap `BANK_ECONOMIC_ALLOCATION_FOUNDATION_001` recorded as
open.

---

## Bank / accounting boundary — clarified

**Bank Reconciliation is not the General Ledger.** It does not post
journal entries and it is not the external accounting ledger.

**But Bank Assessment determines the economic allocations required for
reporting and accounting export.** It is responsible for:

* the financial movement;
* the evidence match;
* the economic allocation, and whether it is complete.

No separate Accounting domain is created to move this functionality. The
open question raised by the previous task is hereby answered: the
capability stays in Bank Assessment, and the boundary statement is
restated rather than the code relocated.

---

## Period completeness — two states, never one

| Question | Owner |
|---|---|
| Did every instrument's source file arrive? | `BankMonthlySourcePeriod.status` — untouched |
| Is every movement a resolved financial fact? | `PeriodCompleteness.financially_reconciled` |
| Has somebody decided what every movement *means*? | `PeriodCompleteness.accounting_complete` |

A month can be **fully reconciled financially and still accounting
incomplete**, because a multi-category supplier's invoice has not arrived.
Collapsing the two would let that month be signed off as finished while
its P&L is still missing a split nobody has made. `PeriodCompleteness`
reports them separately and always.

P&L continues to use only `COMPLETE` allocations.

---

## QBO / CSV — documented, not implemented

**No export code is changed by this task.** The model is compatible with
the already-approved future behaviour:

| Transaction | QBO | CSV |
|---|---|---|
| Single category | one debit line with its category | the canonical allocation |
| Multi-category | **one total debit line marked SPLIT REQUIRED** | N canonical allocation detail lines |

Kermali performs the QuickBooks split manually. A QuickBooks API is
future work and out of scope.

---

## What this task deliberately does not do

* No AWS access, no deploy.
* **No historical Bank import.** `Bank/Historic Data`, `Bank/Download`,
  Zelle, Kermali and WP Control are untouched; operational Bank rows
  remain zero.
* No QBO or CSV export change.
* No `reconciliation_control_start` change.
* No supplier, WHO capability, learned mapping, reporting entity,
  reporting group, invoice or transaction seeded into the authoritative
  database.
* No change to Tips, Payroll or Compensation.

---

## Where the code lives

| Concern | File |
|---|---|
| Models | `03 Software/RF-One Data Store/rfone_data_store/models.py` (`BankOccurrenceSupplier`, `BankInvoiceMatch`, `PurchaseLineClassification`, `SupplierItemCategoryLearning`, `BankEvidenceBypassAuthorization`, plus capability columns on `BankOccurrence`) |
| WHO capability, item identity, learning, line classification | `.../bank_reconciliation/invoice_evidence.py` |
| Bank ↔ Invoice matching, amount control, candidates | `.../bank_reconciliation/invoice_matching.py` |
| Evidence → allocations, pending, bypass | `.../bank_reconciliation/invoice_allocation_bridge.py` |
| Period completeness | `.../bank_reconciliation/economic_reporting.py` |
| Ancillary apportionment (reused) | `.../purchasing/repository.py::get_purchased_lines_with_allocation` |
| Migration | `.../migrations/versions/e5b28d413f7a_add_invoice_evidence_collaboration.py` |
| Tests | `.../test_bank_invoice_evidence_collaboration.py` |
