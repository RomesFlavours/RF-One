# Economic Allocation Foundation

**Task:** BANK_ECONOMIC_ALLOCATION_FOUNDATION_001
**Status:** Implemented — foundation (schema, services, tests). No historical data imported, no export changed.
**Module:** Domain / Shared Domains / Administration / Bank Reconciliation
**Migration:** `d3a7c9f15b28` (additive; single head)

---

## The five principles this foundation establishes

### 1. BANK TRANSACTION ≠ ECONOMIC ALLOCATION

A **Bank Transaction** (`FinancialTransaction`) is the movement of money:
who paid, who was paid, when, how much, on which instrument.

An **Economic Allocation** (`BankTransactionAllocation`) is what that
movement *means*: for whom the cost was borne or the revenue earned, and
which canonical account it belongs to.

These are two different facts about the same event, and RF-One no longer
stores them as one. A bank movement can be perfectly understood
financially — canonical, deduplicated, reconciled — while nobody has yet
decided who bore its cost. That is a normal, readable state, not an error.

### 2. ONE BANK TRANSACTION → 1..N ALLOCATIONS

```text
Bank Transaction   CHENEY   $2,000
    ├── Allocation   Food Purchases                 $1,500   →  5100
    ├── Allocation   To-Go Packaging                  $300   →  5300
    └── Allocation   Restaurant Operating Supplies    $200   →  7830
```

There is still exactly **one** bank transaction. No fictitious child
transactions are created: reconciliation, deduplication and source
provenance all stay anchored to the movement that really happened.

A transaction with a single economic category is represented the same way —
as **one** allocation, not as a special "unsplit" shape:

```text
Bank Transaction   GORDON FOOD   $1,000
    └── Allocation   RF Winter Park   Food Purchases   $1,000   →  5100
```

One model, so no consumer ever has to handle a split case and an unsplit
case differently.

**The amounts must sum exactly.** `SUM(allocation.amount_minor)` equals the
parent's `amount_minor`, in the parent's own sign convention (money out
negative, money in positive — the convention `parsers.py` already
produces). Both sides are integer minor units, so nothing rounds. A set
that does not balance is **refused**; no tolerance exists, hidden or
otherwise, and no remainder is quietly absorbed into the last line. A
caller splitting by percentage must decide where an odd cent goes and say
so.

### 3. PAYER ≠ ECONOMIC OWNER

`PaymentInstrument` identifies the financial **payer**. It does not
identify who bore the cost.

> RF Gelati's credit card pays $500 of material destined for RF Mount Dora.

| Question | Answer |
|---|---|
| Whose cash moved? | RF Gelati, LLC |
| Whose cost is it? | RF Mount Dora, LLC |
| Whose P&L carries it? | RF Mount Dora |
| What does RF Gelati's P&L carry? | Nothing, for that transaction |

The payer is resolved through the **settlement account**, using the
existing `card_configuration.accounting_account_for` /`legal_entity_for` —
never from the card's own `legal_entity_id` and never from whoever holds
the card. The economic owner comes from the allocation's
`ReportingEntity`. They are allowed to disagree, and that disagreement is
the point.

### 4. P&L IS GENERATED FROM ALLOCATIONS, NOT FROM BANK PARENT ROWS

Every query in `bank_reconciliation/economic_reporting.py` reads
`bank_transaction_allocations`. Not one of them reads
`FinancialTransaction.classification` or a parent's
`BankTransactionExplanation` accounting snapshot.

Double counting is therefore **absent from the model**, not prevented by a
filter somebody has to remember:

* a $2,000 payment split three ways contributes $2,000, across three lines;
* the parent contributes nothing, because nothing reads it;
* when RF Gelati pays a vendor for RF Mount Dora, the external cost appears
  **once**, on RF Mount Dora — in that entity's P&L and in the consolidated
  P&L alike.

The parent bank row remains essential for visibility, bank reconciliation,
source provenance and the total. It is simply never an accounting source.

### 5. VIRTUAL REPORTING ENTITY IS NOT A LEGAL ENTITY

A `ReportingEntity` answers *for whom* a result is reported. It comes in
two kinds:

| Kind | Means | `legal_entity_id` |
|---|---|---|
| `LEGAL` | Exactly one real `LegalEntity`. Its P&L **is** that LLC's P&L. | NOT NULL, and unique |
| `VIRTUAL` | A management/reporting entity that is **not** a legal organization — a brand line, a project, a location run inside somebody else's LLC. It gets a real management P&L. | Always NULL |

This is enforced by a database CHECK constraint
(`ck_reporting_entity_type_legal_entity`), not by convention. A VIRTUAL
entity **cannot** point at an LLC and a LEGAL entity **cannot** exist
without one. Creating a virtual entity creates one row, in
`reporting_entities`, and no `LegalEntity` anywhere.

`LegalEntity` keeps its single, narrow meaning: a genuine juridical entity.

A `ReportingGroup` is the consolidation perimeter that N reporting entities
add up into. It is deliberately **not** called `Corporate` — see "Naming"
below.

---

## Intercompany is derived, never chosen

When the payer's Legal Entity differs from the economic owner's, the
Balance Sheet consequence follows deterministically:

```text
payer          RF Gelati, LLC
economic owner RF Mount Dora, LLC
amount         $500

RF Gelati      →  1610  Due From Related Parties
RF Mount Dora  →  2710  Due To Related Parties
                  +  the expense, per its WHY → WHAT
```

The operator is never asked to pick a direction. `derive_intercompany` is a
pure function of (payer, economic owner) and is the single place the rule
lives.

Both accounts already exist in the canonical catalog; neither is invented
here. Both are **Balance Sheet** positions, which is exactly why a future
reimbursement from RF Mount Dora to RF Gelati settles the position and
**does not create a second P&L expense**. In a consolidated P&L the
external cost therefore appears once — a property of the model, not a
correction applied to a report.

### The four derived outcomes

| Outcome | When | Result |
|---|---|---|
| `NONE` | Payer LLC is the economic owner, or the owner is a VIRTUAL entity | No position. A virtual entity is a management view, not a juridical person: it cannot owe anybody anything. |
| `CROSS_ENTITY` | Payer LLC ≠ economic owner LLC | 1610 on the payer, 2710 on the owner |
| `PERSONAL_PAYER_DUE_TO` | A personal instrument bore a business cost | No LLC-to-LLC position is invented; the business records `2710 Due To Related Parties`. *(Superseded name — was `PERSONAL_PAYER_UNDEFINED`; decided by BANK_INVOICE_EVIDENCE_COLLABORATION_001 §19.)* |
| `PERSONAL_PAYER_CONTRIBUTION` | Same, and an operator explicitly classified the funding as non-reimbursable | `3300 Member Contributions` instead of 2710 |
| `NOT_DERIVABLE` | The card has no settlement account configured for that date | Reported, never guessed |

---

## Personal payment instruments

> **RESOLVED by `BANK_INVOICE_EVIDENCE_COLLABORATION_001.md` §19.** The
> business side of a personal payer's business expense is **`2710 Due To
> Related Parties` by default** — the business owes the individual back —
> and `3300 Member Contributions` **only** when an operator explicitly
> classifies the funding as non-reimbursable. The allocation outcomes are
> now `PERSONAL_PAYER_DUE_TO` and `PERSONAL_PAYER_CONTRIBUTION`;
> `PERSONAL_PAYER_UNDEFINED` no longer exists. The section below records
> why the question was originally left open.

Some `PaymentInstrument` rows have no Legal Entity: they are personal. When
one pays a cost belonging to an LLC, the economic allocation is recorded
correctly — the right entity, the right account, the right amount — and
**no fictitious LLC-to-LLC intercompany is created**, because there is no
second Legal Entity.

What was *not* decided anywhere in this repository, at the time this
foundation was built, was which canonical account the company's side of
that payment lands on. The catalog offers `2710 Due To Related Parties`,
`3300 Member Contributions` and `3400 Member Distributions / Draws`, and
the existing WHY vocabulary carries `MEMBER_CONTRIBUTION`, `MEMBER_DRAW`
and the `OWNER_PERSONAL_*` family. Choosing between them was an
accounting decision for the Product Owner, so RF-One stated the gap on
the allocation (`intercompany_outcome = PERSONAL_PAYER_UNDEFINED`, with
the reason in `intercompany_notes`) instead of guessing.

The Product Owner has since chosen `2710` as the default and `3300` only
on an explicit operator statement, so that outcome value no longer
exists — see the note at the top of this section.

~~**This requires a Product Owner decision before personal-instrument transactions can be fully closed.**~~ — decided, see the note at the top of this section.

---

## Allocation status vs transaction status

Two different questions, deliberately kept apart:

| | Question | Values |
|---|---|---|
| `FinancialTransaction.accounting_status` | Is this movement the one true occurrence of this bank event? | `CANONICAL`, `DUPLICATE_SUPPRESSED`, `UNRESOLVED_NO_SETTLEMENT_ACCOUNT` |
| Allocation status | Has anybody decided what this movement means economically? | `UNALLOCATED`, `PENDING_EVIDENCE`, `NEEDS_OPERATOR`, `COMPLETE` |

A transaction may be `CANONICAL` and `UNALLOCATED` at the same time
indefinitely. Only `COMPLETE` allocations enter a P&L; anything else is a
stated unknown, reported by `economic_reporting.allocation_exceptions`
rather than silently missing from a total.

`COMPLETE` is a promise, enforced by CHECK constraint: an entity it belongs
to, a WHY, and a resolved canonical account. Anything less cannot claim it.

---

## WHY → accounting destination, unchanged

The accounting destination is **derived from the WHY**, exactly as
`BankTransactionReason` already defines it. There is no per-allocation
accounting override: an operator picks the WHY, never the account.

* a P&L WHY yields a **WHAT**;
* a non-P&L WHY yields a **Balance Sheet destination**, and the allocation
  legitimately has no WHAT at all.

The `*_snapshot` columns capture that resolution once, at completion,
following the convention `BankTransactionExplanation` already establishes:
editing a WHY's mapping later changes future work, never this history.

---

## Naming: why `ReportingGroup` and not `Corporate`

`00 Core/Corporate.md` defines **Corporate** as the highest organizational
Entity — governance, ownership, Brands, strategy. `LegalEntity`'s own
docstring records the standing decision that no Corporate table is
persisted in this schema.

What this foundation needs is much narrower: the set of entities whose
economic results are added together, including virtual ones that are not
legal organizations at all. Persisting that under the name `Corporate`
would quietly redefine an approved Core concept, so it does not.
`ReportingGroup` is the reporting perimeter and says so.

If the Product Owner would rather the perimeter carry the Corporate name,
that is a rename plus a Core reconciliation, not a schema change.

---

## Boundary note — answered

> **RESOLVED by `BANK_INVOICE_EVIDENCE_COLLABORATION_001.md` §20.** Bank
> Reconciliation is not the General Ledger, but Bank Assessment does
> determine the economic allocations required for reporting and accounting
> export. The capability stays here; no separate Accounting domain is
> created. The section below records the original observation.

This folder's `README.md` states, under *Bank Reconciliation ≠ Accounting*,
that Bank Reconciliation "does not post journal entries, does not maintain
a chart of accounts, and does not produce financial statements."

Two of those three are still true. The third is now partly overtaken: the
canonical chart of accounts already lives here
(`bank_accounting_classifications`, seeded by migration `b8d3f1a72c64`),
and this task adds P&L production from allocations.

This is recorded rather than silently resolved. The boundary statement was
approved and is not rewritten here. The smallest reasonable correction is
either to restate that boundary, or to lift Economic Allocation and
economic reporting into their own Administration module that *consumes*
reconciled bank movements. **The Product Owner chose the first: the
boundary is restated and the code stays where it is.**

---

## What this foundation deliberately does not do

* No invoice matching, no invoice line reading, no supplier-item learning,
  no ancillary cost allocation — the next task owns those. The two
  `evidence_kind` / `evidence_reference` columns are left open on purpose
  rather than pre-filled with a vocabulary that task must decide.
* No historical Bank import. The operational Bank tables stay empty.
* No change to QBO or CSV export. The model is compatible with the decision
  already taken: single category exports as one category; multi-category
  exports as one total row marked SPLIT REQUIRED, with the canonical
  allocation detail in CSV.
* No WHO created, no learned WHY rules, no `reconciliation_control_start`.
* No real reporting group and no real reporting entity is configured. All
  three new tables ship empty; the real perimeter is a Product Owner
  configuration decision.

---

## Where the code lives

| Concern | File |
|---|---|
| Models | `03 Software/RF-One Data Store/rfone_data_store/models.py` (`ReportingGroup`, `ReportingEntity`, `BankTransactionAllocation`) |
| Allocation writing, payer resolution, intercompany derivation | `.../bank_reconciliation/economic_allocation.py` |
| Reporting entities and perimeters | `.../bank_reconciliation/reporting_entity.py` |
| P&L and intercompany reporting | `.../bank_reconciliation/economic_reporting.py` |
| Migration | `.../migrations/versions/d3a7c9f15b28_add_economic_allocation_foundation.py` |
| Tests | `.../test_bank_economic_allocation_foundation.py` |
