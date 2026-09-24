# Bank Reconciliation

**Version:** 1.0
**Status:** Foundation — TASK_BANK_RECONCILIATION_PAYPAL_001
**Module:** Domain / Administration / Bank Reconciliation

*Preserved from an earlier design (TASK_BANK_RECONCILIATION_PAYPAL_001); the Financial Model Convergence work may supersede parts of this foundation. Retained here for its unique conceptual history — see `01 Domains/Domain Architecture.md` §9 item 6 and the Purchased Domain README for related, still-open boundaries.*

**The current implementation specifications are `BANK_RECONCILIATION_MANUAL_IMPORT_NORMALIZATION_001.md`, `BANK_ECONOMIC_ALLOCATION_FOUNDATION_001.md`, `BANK_INVOICE_EVIDENCE_COLLABORATION_001.md` and `BANK_REPORTING_CONFIGURATION_001.md` (this folder)** — it supersedes this README's `PaymentInstrumentTransaction`-based schema description below with the canonical `FinancialTransaction`/Bank Recognition Expert System model now on `main`. This README remains for historical/conceptual context only.

---

## Purpose

**Bank Reconciliation** is the Administration module responsible for recognizing that a financial movement can originate from more than one financial/payment instrument — a Bank Account, a Credit Card, or a PayPal account — and for matching movements that represent the two sides of the same internal transfer of funds across those instruments (e.g. a PayPal payout landing in a bank account, or a bank payment settling a credit card bill).

Before this task, no Bank Account, Credit Card, or generic Reconciliation/Classification concept existed anywhere in RF-One's canonical schema — this document, and the `PaymentInstrument`/`PaymentInstrumentTransaction`/`PaymentInstrumentTransactionMatch` schema it defines (`03 Software/RF-One Data Store/rfone_data_store/models.py`), are the foundation, not an extension of a pre-existing model.

Bank Reconciliation does not decide WHAT was purchased, does not own supplier-side facts, and does not maintain a general ledger. It observes normalized transaction ledgers per Payment Instrument and decides, per transaction, whether it is an **Internal Transfer** between two of the business's own instruments — the one classification this module's own matching logic ever assigns automatically. Any other classification (Revenue, Expense, Fee) is available on the schema but is never inferred by this module — assigning those is out of this foundation's scope.

---

## Scope

This foundation covers exactly three things:

1. **Payment Instrument** — the common way RF-One identifies a source instrument (`instrument_type` ∈ `BANK_ACCOUNT`, `CREDIT_CARD`, `PAYPAL`), its provider, its external/account identifier, its owning Legal Entity, its linked settlement/funding instrument, and its connector/import source. Deliberately only these three instrument types — this is not a speculative plugin architecture for arbitrary future providers (a fourth payment instrument type is a future task, not implied by this one).
2. **PayPal Connector** — a Technical Connector (`03 Software/RF-One Data Store/rfone_data_store/technical/connectors/paypal/`) that retrieves transactions from PayPal's own Transaction Search API and loads them, idempotently, into the same normalized transaction ledger every instrument type shares. PayPal is a payment instrument with its own connector, ledger, and native transaction identifiers/types — never modeled as "just another bank account."
3. **Cross-Ledger Reconciliation** — the one matching engine (`03 Software/RF-One Data Store/rfone_data_store/bank_reconciliation/matching.py`) that links two transactions on different instruments representing the same internal transfer, deterministically (never a probabilistic/fuzzy match — same convention Restaurant/Purchasing's own Three-Way Reconciliation already establishes), and only when sufficient evidence exists; otherwise the transaction is left for human review.

## Explicitly out of scope (this foundation)

- Other payment providers (Stripe, Square, Venmo, wire transfer feeds, etc.) — not implemented, not anticipated by this schema beyond the three named instrument types.
- A general Revenue/Expense/Fee classification engine on `PaymentInstrumentTransaction.classification` — this module's automated *matching* logic assigns exactly one value there (`INTERNAL_TRANSFER`). (The separate, human-driven Who → Why → What accounting classification described below was added later and is not what this bullet excludes.), on a confirmed cross-ledger match; every other value there exists on the schema for human/manual use but is never assigned automatically here.
- A general ledger, chart of accounts, or financial statement production (see "Bank Reconciliation ≠ Accounting" below).
- A redesign of RF-One's reconciliation/classification learning mechanism (see "Relationship to auto-expertising/learning" below) — this foundation only ensures its own confirmed matches are structured so a future learning mechanism can read them.

---

## Payment Instrument

| Field | Meaning |
|---|---|
| `instrument_type` | `BANK_ACCOUNT` \| `CREDIT_CARD` \| `PAYPAL` |
| `provider` | Free text business-level provider name (e.g. "Chase", "American Express", "PayPal") |
| `legal_entity_id` | Which `LegalEntity` (`00 Core`/`03 Software` canonical identity) owns this instrument |
| `linked_instrument_id` | Another `PaymentInstrument` this one settles to/funds from (e.g. a PayPal account's linked bank account, or a Credit Card's linked payment bank account) — self-referential, many-to-one |
| `source_system_id` | The connector (`SourceSystem`) this instrument is synchronized from, if any |

`linked_instrument_id` is the PRIMARY signal Cross-Ledger Reconciliation requires before ever proposing an automatic match — two instruments whose transactions merely happen to have equal-and-opposite amounts are never auto-matched without this configured relationship (see "Cross-Ledger Reconciliation" below).

## Normalized transaction ledger

Every instrument type writes into the same table, `PaymentInstrumentTransaction` — there is no PayPal-only or Bank-only ledger. The pipeline is:

```text
Connector (e.g. PayPal API)
    -> raw source transactions
    -> RF-One normalized transaction representation (PaymentInstrumentTransaction)
    -> classification (bank_reconciliation/matching.py)
    -> reconciliation (cross-ledger match)
```

**Money sign convention** (this task defines it — none existed before): `amount_minor` is the transaction's NET effect on its OWN instrument's balance — positive = inflow, negative = outflow — in integer minor units (this schema's existing money convention). `gross_amount_minor`/`fee_amount_minor`/`net_amount_minor` are optional enrichment populated when the source reports them (PayPal always does); a fee is preserved as its own column on the transaction that carried it and is never merged away or dropped by a later match.

A connector's own source type/event code (e.g. PayPal's T-code) is preserved verbatim as `native_transaction_type` — it is evidence of WHAT happened at the source, never RF-One's own business classification of WHY the transaction exists (`classification`).

## PayPal Connector

`03 Software/RF-One Data Store/rfone_data_store/technical/connectors/paypal/` — a Technical Connector in the same sense as the existing Clover connector (`technical/connectors/clover/`): owns only PayPal integration concerns (OAuth2 client-credentials authentication, the Transaction Search API client, mapping PayPal's own status vocabulary to RF-One's small canonical set, idempotent upsert). Retrieves data from PayPal's API rather than requiring CSV/manual upload as its primary source. Deduplicates on `(payment_instrument_id, external_transaction_id)` — PayPal's own transaction ID — so repeated synchronization never creates duplicate transactions, reusing the same `SourceSystem`/`IngestionRun`/`SourceRecord` provenance mechanism every other connector in this codebase already uses.

## Cross-Ledger Reconciliation

`03 Software/RF-One Data Store/rfone_data_store/bank_reconciliation/matching.py` — the one reconciliation/matching engine this module owns. A match is only ever created automatically when ALL of the following hold: exact opposite amount, same currency, an explicitly configured `linked_instrument_id` relationship between the two instruments, and the counterpart transaction date within a configurable tolerance window (default 3 days) — and only when exactly one such candidate exists. Zero or multiple candidates leave the transaction unresolved rather than guessing; a human can still resolve an ambiguous or unlinked case explicitly (`confirm_match`).

A confirmed match:

- sets **both** transactions' `classification` to `INTERNAL_TRANSFER` — never Revenue or Expense (a transfer between a business's own instruments is neither);
- never deletes or merges either source transaction — both remain independently auditable;
- is idempotent per ordered pair of transactions — re-matching the same pair returns the existing match.

---

## Classification: Who → Why → What

Recognizing that a movement happened is not the same as saying what it is. Bank Reconciliation classifies a movement as a chain of three levels, each answering one question:

- **Who** (`BankOccurrence`) — which subject/receiver the movement concerns.
- **Why** (`BankTransactionReason`) — the economic reason it exists.
- **What** (`BankAccountingClassification`) — the final accounting classification: one line of a **Profit & Loss** statement or of a **Balance Sheet**.

Each Why resolves to exactly one What, configured once (Bank › Classification) and stored on the vocabulary itself, so **the What always derives from the Why** and is never picked per transaction.

**A Who never decides a Why** (BANK_FINAL_RELEASE_BLOCKERS_001). A Who may carry a *usual* Why, shown to the reviewer as a suggestion, but no live path applies it: choosing a Who records the Who and leaves the Why open. The Why of a transaction comes from exactly two places — the **one automatic WHY engine** (`structural_why.recognize_transaction`: the bank's own structure first, e.g. a same-entity transfer is `INTERNAL_BANK_TRANSFER`, a transfer between two RF-One legal entities is `RELATED_PARTY_TRANSFER_IN/OUT`, a transfer to an unregistered account stays unresolved; then an explicit purpose in the source memo), used identically at import, on reprocess and on instrument reassignment — or **a person** choosing it. Reprocessing never touches a human decision and appends nothing when the engine's answer is unchanged.

Two rules keep this honest:

- **A confirmed decision is an immutable snapshot.** Editing an association changes future classifications only; a transaction already confirmed never changes silently. Applying a changed chain to a historical transaction is the explicit, auditable `Reclassify` action, which appends a new decision rather than rewriting the old one.
- **The invoice still owns invoice-level classification.** A supplier paid by invoice may classify to an Accounts Payable settlement What — a Balance Sheet line — because settling a liability is all a bank movement tells us. The Food / Operating composition of that invoice's lines comes from the invoice (Invoice Intake / Purchased), never from the bank movement. This is the same boundary the next section states, applied to the classification level.

The full specification is §12 of `BANK_RECONCILIATION_MANUAL_IMPORT_NORMALIZATION_001.md`.

---

## The card, its account and its holder

A Credit Card raises two separate questions, and Bank Reconciliation keeps them strictly apart because they have entirely different consequences.

**Which bank account the card settles to** is an accounting fact:

```text
Credit Card → Settlement Bank Account → Company / Legal Entity
```

The Company of a card transaction comes from the settlement account — never from the card's own Legal Entity, and never from whoever holds the card. The assignment is historized, so a transaction posted in 2025 is attributed to the configuration that was true in 2025, and a card with no assignment stays visibly unconfigured rather than being quietly attributed to something.

**Who physically held the card** is a responsibility fact, historized the same way, used for accountability, analysis and possible personal benefits. It is inert for accounting: the holder never determines the Company, never determines the settlement account, and never takes part in deciding whether two transactions are the same accounting fact.

## Accounting deduplication

The same operation can reach the books twice: from a mother card and its linked card, from two overlapping Chase downloads, twice inside one file, from files saved under different names, or from imports run weeks apart. **A different last-four does not make a row a different accounting fact.**

Rows that share a **settlement account, posting date, signed amount and normalized payee** are one accounting fact. One canonical occurrence — the earliest acquired — feeds accounting, the monthly export, P&L and Balance Sheet; the others are kept, linked to it, marked, and excluded.

Three rules make this safe:

- **Nothing is destroyed.** No raw row and no transaction is ever deleted. A suppressed copy stays fully visible in the import and audit screens, showing its file and its canonical.
- **Nothing is invented.** A transaction whose settlement account is unknown is reported, never merged — and two cards whose accounts are both unknown are not thereby the same account.
- **A human decision wins.** Where a person already judged two rows distinct, automatic deduplication does not overrule them.

The detail — the exact key, the payee normalization, the canonical choice, the recalculation behavior and the open points — is §13 of `BANK_RECONCILIATION_MANUAL_IMPORT_NORMALIZATION_001.md`.

---

## From import to classified books

Importing a bank file is not the same as knowing what its movements are. Classification is made practical in three steps rather than one long review:

1. **The What catalog is loaded from the accountant's own chart of accounts**, not typed in. Upload, parse, preview, confirm — structure only, never amounts, and totals and headings are reported rather than turned into accounts. A plan with no codes of its own gets stable technical codes, so re-importing it changes nothing.
2. **Receivers are proposed, not invented.** The canonical transactions are grouped by the receiver they actually name, so one decision covers every row naming the same one. Accounting duplicates and confirmed internal transfers are excluded — classifying them would be work that never reaches the books. Descriptions that merely look alike are shown as suggestions with the reason and are never merged automatically.
3. **One approval names the Who of the whole group**, writes an append-only snapshot per transaction, and records an exact-match rule so the same receiver is recognised on the next import. It never applies the Who's usual Why: each transaction keeps its own Why question, answered by the automatic engine or a person (BANK_FINAL_RELEASE_BLOCKERS_001). A human decision is never overwritten, and a receiver already classified under two different Who values is reported as ambiguous rather than resolved by guesswork.

Full detail, including the boundary with invoices, is §15 of `BANK_RECONCILIATION_MANUAL_IMPORT_NORMALIZATION_001.md`.

## RF-One's own chart of accounts

RF-One does not wait for the accountant's chart and does not treat it as the source of truth. It defines its **own canonical restaurant accounting structure** — 134 accounts, 91 Profit & Loss and 43 Balance Sheet, on a fixed 1000–8000 numbering — which arrives in every environment through the ordinary deployment, with no manual SQL and no spreadsheet upload. QuickBooks/Kermali may later be mapped onto it; mapping is not owning the meaning.

Four rules the chart encodes, because getting them wrong is expensive:

- **Sales tax and guest tips are liabilities, not revenue.** Collecting or paying either has no profit-and-loss effect at all.
- **Employees and vendors are WHO, never accounts.** There is no person account and no Costco account.
- **Derived totals are calculations.** Net Revenue, Gross Profit, Prime Cost and Net Income are computed from the hierarchy — none of them is a posting account, so none can be posted to.
- **Unknown is review, never Miscellaneous.** Residual accounts exist for genuine residual cases and are never an automatic fallback.

Detail is §16 of the same specification.

---

## Bank Reconciliation ≠ Purchased

Bank Reconciliation is the Business-Domain/Administration-side reconciliation Purchased's own README (`01 Domains/Shared Domains/Purchased/README.md`, "Bank Reconciliation boundary") already anticipates and explicitly excludes from its own scope:

- Purchased: Supplier X invoiced $1,000 (a supplier-side fact).
- Bank Reconciliation: a bank movement of $950 (a settlement-side fact).

A discrepancy between the two does not automatically modify Purchased, originates here, and may require human intervention here — Purchased remains the supplier-side snapshot until an actual supplier-side correction exists there. Bank Reconciliation, as implemented by this task, reconciles movements ACROSS a business's own Payment Instruments (PayPal ↔ Bank, Bank ↔ Credit Card) — matching a Purchased fact to a specific settlement transaction is a related but separate capability, not built by this foundation.

**Open documentation tension (flagged, not resolved here):** Purchased's own README (line 333) states "Bank Reconciliation belongs to the consuming Business Domain, not to Purchased" — written when Bank Reconciliation was expected to be owned per-Business-Domain (e.g. inside Restaurant). This task instead places Bank Reconciliation under `01 Domains/Shared Domains/Administration/` (a transversal/Shared Domain module), matching the already-existing, already-reserved empty folder this README now fills, and architecturally consistent with `linked_instrument_id`/cross-ledger matching being industry-independent logic (equally applicable to Restaurant or any future Business Domain). Purchased's own wording was not edited by this task (out of this task's strict scope) — a Product Owner decision is needed on whether to update it to match.

## Bank Reconciliation ≠ Accounting

> **Restated — decided (BANK_INVOICE_EVIDENCE_COLLABORATION_001 §20).** Bank Reconciliation is **not the General Ledger**: it posts no journal entries and is not the external accounting ledger. **But Bank Assessment determines the economic allocations required for reporting and accounting export** — the financial movement, the evidence match, and whether the economic allocation is complete. The canonical chart of accounts (`bank_accounting_classifications`) and P&L production from Economic Allocations therefore live here by decision, not by accident. No separate Accounting domain is created to move this functionality. The original statement below stands for journal entries and for the external ledger; read it with this scope.

Consistent with Administration's own existing "Administration ≠ Accounting" boundary (`01 Domains/Shared Domains/Administration/README.md`): Bank Reconciliation records that two transactions are the same internal movement and assigns Internal Transfer classification — it does not post journal entries, does not maintain a chart of accounts, and does not produce financial statements.

## Relationship to auto-expertising/learning

RF-One's reconciliation/classification learning mechanism (the Purchased Domain's Supplier + Source Format Training, `03 Software/InvoiceIntake/supplier_format_training.py`) is not redesigned or extended by this task. `PaymentInstrumentTransactionMatch.match_method` (`AUTO` vs `HUMAN`) and `confirmed_by` provide the same kind of structured, auditable record of a confirmed human decision that mechanism's own "observation" pattern relies on — usable by a future Bank Reconciliation learning mechanism without this task building one.

---

## Relationship to Core 2.0

Bank Reconciliation is built on the RF-One Core Conceptual Architecture and reuses its concepts without redefining them — a Payment Instrument Transaction is a Reality fact recorded after the fact (not a Decision), and a confirmed cross-ledger match is Learning-eligible evidence, consistent with Temporal Coherence and the Decision/Action/Outcome/Learning chain (`00 Core/ConceptualArchitecture/`).
