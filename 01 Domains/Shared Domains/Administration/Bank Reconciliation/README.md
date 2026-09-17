# Bank Reconciliation

**Version:** 1.0
**Status:** Foundation — TASK_BANK_RECONCILIATION_PAYPAL_001
**Module:** Domain / Administration / Bank Reconciliation

*Preserved from an earlier design (TASK_BANK_RECONCILIATION_PAYPAL_001); the Financial Model Convergence work may supersede parts of this foundation. Retained here for its unique conceptual history — see `01 Domains/Domain Architecture.md` §9 item 6 and the Purchased Domain README for related, still-open boundaries.*

**The current implementation specification is `BANK_RECONCILIATION_MANUAL_IMPORT_NORMALIZATION_001.md` (this folder)** — it supersedes this README's `PaymentInstrumentTransaction`-based schema description below with the canonical `FinancialTransaction`/Bank Recognition Expert System model now on `main`. This README remains for historical/conceptual context only.

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
- A general Revenue/Expense/Fee classification engine — this module's automated logic assigns exactly one classification value (`INTERNAL_TRANSFER`), on a confirmed cross-ledger match; every other classification value on `PaymentInstrumentTransaction.classification` exists on the schema for human/manual use but is never assigned automatically here.
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

## Bank Reconciliation ≠ Purchased

Bank Reconciliation is the Business-Domain/Administration-side reconciliation Purchased's own README (`01 Domains/Shared Domains/Purchased/README.md`, "Bank Reconciliation boundary") already anticipates and explicitly excludes from its own scope:

- Purchased: Supplier X invoiced $1,000 (a supplier-side fact).
- Bank Reconciliation: a bank movement of $950 (a settlement-side fact).

A discrepancy between the two does not automatically modify Purchased, originates here, and may require human intervention here — Purchased remains the supplier-side snapshot until an actual supplier-side correction exists there. Bank Reconciliation, as implemented by this task, reconciles movements ACROSS a business's own Payment Instruments (PayPal ↔ Bank, Bank ↔ Credit Card) — matching a Purchased fact to a specific settlement transaction is a related but separate capability, not built by this foundation.

**Open documentation tension (flagged, not resolved here):** Purchased's own README (line 333) states "Bank Reconciliation belongs to the consuming Business Domain, not to Purchased" — written when Bank Reconciliation was expected to be owned per-Business-Domain (e.g. inside Restaurant). This task instead places Bank Reconciliation under `01 Domains/Shared Domains/Administration/` (a transversal/Shared Domain module), matching the already-existing, already-reserved empty folder this README now fills, and architecturally consistent with `linked_instrument_id`/cross-ledger matching being industry-independent logic (equally applicable to Restaurant or any future Business Domain). Purchased's own wording was not edited by this task (out of this task's strict scope) — a Product Owner decision is needed on whether to update it to match.

## Bank Reconciliation ≠ Accounting

Consistent with Administration's own existing "Administration ≠ Accounting" boundary (`01 Domains/Shared Domains/Administration/README.md`): Bank Reconciliation records that two transactions are the same internal movement and assigns Internal Transfer classification — it does not post journal entries, does not maintain a chart of accounts, and does not produce financial statements.

## Relationship to auto-expertising/learning

RF-One's reconciliation/classification learning mechanism (the Purchased Domain's Supplier + Source Format Training, `03 Software/InvoiceIntake/supplier_format_training.py`) is not redesigned or extended by this task. `PaymentInstrumentTransactionMatch.match_method` (`AUTO` vs `HUMAN`) and `confirmed_by` provide the same kind of structured, auditable record of a confirmed human decision that mechanism's own "observation" pattern relies on — usable by a future Bank Reconciliation learning mechanism without this task building one.

---

## Relationship to Core 2.0

Bank Reconciliation is built on the RF-One Core Conceptual Architecture and reuses its concepts without redefining them — a Payment Instrument Transaction is a Reality fact recorded after the fact (not a Decision), and a confirmed cross-ledger match is Learning-eligible evidence, consistent with Temporal Coherence and the Decision/Action/Outcome/Learning chain (`00 Core/ConceptualArchitecture/`).
