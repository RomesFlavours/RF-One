# Purchased

**Version:** 1.2 (closes, for the legacy `03 Software/InvoiceIntake/` path specifically, the "Relationship to Restaurant's existing Purchasing module" open question v1.1 recorded below — see "Invoice Intake alignment (closed)" — while leaving v1.1's conceptual content otherwise unchanged; v1.1 expanded v1.0's initial definition with non-goods cost allocation, date policy, Supplier identity resolution, source/format validation and training, the NORMALIZED/HUMAN functional-state model, duplicate handling, supplier-side correction mechanics, and the single-object invoice scope rule)
**Status:** APPROVED DOMAIN DEFINITION
**Module:** Shared Domains / Purchased

---

## Related documents

- [../../Domain Architecture.md](../../Domain%20Architecture.md) §4 (Shared Domains / Business Domain taxonomy, where Purchased is introduced as a Shared Domain) and §9, Open Question 6 (Purchased vs. Restaurant/Purchasing — partially closed for the `03 Software/InvoiceIntake/` path, see below; still open more broadly)
- [../../README.md](../../README.md) (`01 Domains/` purpose, the Shared Domains / Business Domain taxonomy, and the distinction between `Shared Domains/` and `_Shared/`)
- [../Administration/README.md](../Administration/README.md) and [../Administration/Invoice Intake/README.md](../Administration/Invoice%20Intake/README.md) — Administration is a possible consumer of Purchased's output (economic category/document totals); Administration's own Invoice Intake module is a distinct, pre-existing capability under Administration, not the same thing as Purchased and not renamed or merged by this document
- [../../Business Domain/Restaurant/Purchasing/README.md](../../Business%20Domain/Restaurant/Purchasing/README.md) — Restaurant's existing, Business-Domain-specific Purchasing module, which normalizes supplier invoices into a Purchase Document/Purchase Line/Effective Product Cost model now consuming, rather than owning, the Purchase Fact for the `03 Software/InvoiceIntake/` path; see "Relationship to Restaurant's existing Purchasing module" below
- `CLAUDE.md` — Core/Domain/Product/Runtime distinction; this document is Domain-level definition, not Product or Runtime design

---

## Purpose

Purchased is a **Shared Domain** consumed by Business Domains (**BD** — an accepted textual abbreviation for "Business Domain" in RF-One documents; it is never used as a folder/path name, which stays spelled out as `Business Domain/`).

Purchased transforms supplier-side evidence of what was invoiced/purchased into normalized Purchased Lines.

> **Purchased represents the factual picture of what the business was invoiced for, and therefore what it purchased/spent, subject only to supplier-side corrections.**

Purchased is, and must remain, exactly three things:

> **capture + normalize + publish factual purchased data.**

Nothing more (see "Stress test" under Open implementation points, and "What Purchased does NOT own" below).

**Purchased does not determine whether the document was paid.**

---

## Scope

Purchased owns the **purchase fact**: turning heterogeneous supplier-side source evidence (an invoice, receipt, credit memo, or equivalent) into a normalized, canonical representation of what was purchased.

Purchased does not own:

- inventory;
- production/recipes;
- accounting/general ledger posting;
- tax treatment;
- payments or bank reconciliation;
- vendor selection/purchasing decisions (what, how much, from whom to buy);
- management/business decisions of any kind.

Purchased is explicitly **not**, and must never become:

- Procurement (deciding what/how much/from whom to buy);
- Accounts Payable (deciding what/when to pay);
- Accounting (posting to a ledger, tax treatment);
- Bank Reconciliation (matching bank movements to invoices);
- Inventory (stock levels, usage, valuation);
- POS/sales history (that is sales-side, not purchase-side, evidence);
- a generic document archive (Purchased always produces normalized, structured Purchased Lines — it is not a passive file store).

---

## Inputs

Purchased may acquire evidence from, illustratively and non-exhaustively:

- supplier invoices;
- supplier PDF;
- scanned invoices;
- handwritten invoices;
- receipts;
- email attachments;
- supplier portals;
- supplier APIs;
- EDI / structured source;
- manual upload;
- other authorized supplier-side source systems.

**Invoice Intake is a process that feeds Purchased — it is not the name of this Domain.** No email intake, OCR, invoice parser, or supplier API integration is designed, authorized, or implied by this document.

RF-One already has a pre-existing **Invoice Intake** capability (`../Administration/Invoice Intake/README.md`), documented as "a Shared Domains capability... document acquisition, OCR/parsing, normalization, review, and routing." As of "Align legacy Invoice Intake with Purchased" (see "Relationship to Restaurant's existing Purchasing module" below, "Invoice Intake alignment (closed)"), its legacy runtime prototype (`03 Software/InvoiceIntake/`) feeds Purchased's persistence directly — Restaurant/Purchasing consumes that output rather than owning it.

---

## Purchased Line

The canonical unit of Purchased's output is **not** "one invoice = one row."

It is:

> **One normalized Purchased Line per single economic item read from the source evidence.**

Example — an invoice containing:

- 3 cases tomatoes
- 2 mozzarella
- delivery fee

produces normalized Purchased Lines for the goods purchased (tomatoes, mozzarella), each linked back to the same source invoice/document, with the delivery fee **allocated** into those goods lines' normalized effective cost rather than becoming its own free-standing Purchased Line — see "Non-goods cost allocation" immediately below.

### Purchased Line — minimum conceptual data

Without fixing a database schema, a Purchased Line may conceptually carry at least:

- Supplier (canonical identity — see "Supplier identity" below)
- Legal Entity
- Business Unit / Restaurant / destination scope (see "Scope" further below)
- Source document
- Invoice number
- Invoice date, delivery date, service date, purchase date, received date — all preserved (see "Dates" below)
- Original supplier description, original supplier item code, original Unit of Measure, original values (see "Item normalization" below)
- Normalized item/service, when resolved
- Quantity
- Unit of Measure (normalized)
- Unit price
- Discount
- Tax
- Allocated non-goods cost (fees/surcharges apportioned in per "Non-goods cost allocation")
- Line amount (normalized effective cost, goods value + allocated non-goods cost)
- Document total reference
- Currency
- Source provenance (original text/code, acquisition method/document format — see "Source/format validation")
- NORMALIZED / HUMAN functional state (see below)

No technical field, type, or storage decision is fixed here — this is a conceptual minimum, not a schema.

---

## Non-goods cost allocation

**Product Owner decision:** any invoiced amount that does **not** directly represent a purchased good must be apportioned proportionally across the goods lines, in proportion to each line's own value.

Examples of non-goods amounts to allocate:

- freight;
- delivery fee;
- fuel surcharge;
- tax not directly attributable to a specific good;
- service/handling charge;
- other equivalent charges.

Example:

```text
Goods A = 100
Goods B = 300
Delivery = 40

Total goods value = 400

Allocation:
A receives 25% of Delivery = 10
B receives 75% of Delivery = 30

Normalized effective cost:
A = 110
B = 330
```

**Purchased does not automatically create a standalone Purchased Line for such a charge when it can instead be allocated proportionally across the goods lines.** The allocation mechanism itself (rounding rules, what counts as "directly attributable," how to handle an invoice with no goods lines at all) is an open implementation point, not fixed here.

---

## Dates

Purchased preserves **every** date available from the source, illustratively and non-exhaustively:

- invoice date;
- delivery date;
- service date;
- purchase date;
- received date;
- other relevant dates.

> **Which date is used as the canonical "Purchase Date" for a given process is not universal.** It must be configurable by business/system configuration.

Purchased's role is to **preserve** the data; configuration decides which date a given consumer process actually uses. This document does not fix a default or a resolution algorithm.

---

## Supplier identity

Purchased must resolve supplier aliases, codes, and descriptions to the **same canonical Supplier identity** whenever possible.

Example — these may all refer to the same Supplier:

```text
US Foods
US Foods Inc.
USF #123
```

> **Purchased must not duplicate a Supplier merely because of a naming/source difference.**

The original text/code as it appeared in the source must always remain available as source provenance, even after resolution to a canonical Supplier. No specific matching/resolution algorithm is designed by this document — this is a conceptual requirement, not an implementation.

---

## Item normalization

Purchased always preserves:

- the original supplier description;
- the original supplier item code, when available;
- the original Unit of Measure;
- the original values.

When possible, Purchased links these to a canonical RF-One item/service.

Example: `"TOM ROMA 25LB CS"` may be normalized toward a canonical Tomato/Roma item, without ever losing the original description.

**Purchased does not invent a mapping when it is not sufficiently reliable.** An item that cannot be reliably mapped is left in the **HUMAN** functional state (see below), never silently guessed.

No AI normalization engine, OCR pipeline, or mapping algorithm is designed or implemented by this document.

---

## Source/format validation and training

Purchased distinguishes between two different kinds of reliability, and must not conflate them:

1. **SOURCE FORMAT reliability** — how trustworthy the acquisition method/document format is at producing correct raw data.
2. **ITEM MAPPING reliability** — how trustworthy the link from a raw supplier item to a canonical RF-One item is.

**Purchased does not validate "the Supplier" in the abstract.** It validates the combination:

> **Supplier + acquisition method / document format / structured source.**

Illustrative, non-exhaustive examples:

- **A. API / EDI / structured integration** — the source format is trusted/validated by default (a structured feed is inherently low-ambiguity at the format level). This does **not** mean item mapping is automatically trusted too: a given supplier item code → RF-One item mapping can still start, and remain, **unresolved/HUMAN** even when the source format itself is fully trusted.
- **B. Standard supplier PDF** — subject to a training/validation period: for the first N invoices, an AI reads the document and a human verifies the result; once observed accuracy is sufficient, the format may become internally "validated" for that Supplier/format combination.
- **C. Small supplier / handwritten invoice / receipt** — may require routing to **HUMAN** more frequently, indefinitely, not only during an initial training period.

**No universal value for N, an accuracy threshold, or a training-period length is fixed here — these must be configurable**, not hard-coded constants.

An internal "this Supplier+format combination is currently trusted" marker is a technical/operational concept that may exist to drive routing decisions; it is not itself one of Purchased Line's two functional states (see immediately below) and must not be confused with them.

---

## NORMALIZED / HUMAN

A Purchased Line has **only two functional states**:

- **NORMALIZED** — read and normalized with sufficient reliability; equivalent to "confirmed."
- **HUMAN** — not sufficiently reliable; requires human intervention.

Flow:

```text
Source
  → Read / Extract
  → Normalize
      reliable enough  → NORMALIZED
      doubtful         → HUMAN
                              ↓ (after human verification)
                          NORMALIZED
```

**No other functional state is introduced at the Domain-model level** — specifically, **CAPTURED**, **PARSED**, **CONFIRMED**, and **VALIDATED** are explicitly rejected as Domain-model functional states. Such labels may exist as internal technical/implementation states (e.g. a processing-pipeline stage, or the internal "format currently trusted" marker from "Source/format validation" above), but they do not belong to, and must not leak into, Purchased's own functional Domain model, which recognizes only NORMALIZED and HUMAN.

---

## Duplicate handling

The same source document can arrive through more than one channel — illustratively: email, manual upload, scan, supplier portal, API.

> **Purchased must produce exactly one purchase fact/document identity per actual source document**, regardless of how many channels delivered it.

Before deduplicating, Purchased must verify that the documents are genuinely equivalent — arrival through multiple channels is not, by itself, proof of equivalence.

**If the same invoice identity arrives with different content, Purchased must not choose automatically.** This case goes to **HUMAN**, because it may represent:

- a corrected invoice;
- a changed invoice;
- a supplier-side revision;
- another anomalous case not yet understood.

No deduplication/equivalence-check algorithm is designed by this document.

---

## Supplier-side corrections

A supplier-side correction belongs to **Purchased**, because it changes the economic snapshot of a purchase. Illustrative, non-exhaustive examples:

- credit memo;
- corrected invoice;
- return credit;
- supplier adjustment.

**Purchased must not retroactively delete the prior fact.** A correction is represented as a compensating economic fact, or an appropriate corrective relationship to the original — preserving the full economic history of the source evidence, never overwriting it.

Example:

```text
Invoice:      +500
Credit Memo:   -50

Net purchased effect: 450
```

A bank payment mismatch is **not** a supplier-side correction (see "Bank Reconciliation boundary" below) — this distinction must remain sharp: Purchased reacts to supplier-side documents, never to settlement/payment evidence.

---

## Scope — one invoice, one economic object

**Product Owner decision:** an invoice belongs, by definition, to exactly **one** economic/corporate/operational object (Legal Entity / Business Unit / Restaurant / equivalent destination scope) — normally the same object that is the actual recipient of the goods/services and the addressee of the accompanying documentation.

> **Purchased does not design a standard model for allocating a single invoice across multiple scopes.**

If an exceptional source genuinely spans more than one scope, it is routed to **HUMAN / anomaly** — the exception is not promoted to become the standard model, and no multi-scope allocation mechanism is designed by this document.

---

## Purchased owns the purchase fact

> **Purchased owns the purchase fact. Purchased does not own the financial settlement of that fact.**

Purchased answers:

> "What was invoiced / purchased?"

Purchased does **not** answer:

> "Was it paid correctly?"

---

## Bank Reconciliation boundary

Bank Reconciliation belongs to the consuming Business Domain, **not to Purchased**.

Example:

- Purchased: Supplier X invoiced $1,000.
- Bank Reconciliation (owned by the Business Domain): a bank movement of $950.

This discrepancy:

- does **not** automatically modify Purchased;
- originates in the Business Domain responsible for reconciliation;
- may generate Attention in that Business Domain;
- may require human intervention there.

Purchased remains the supplier-side snapshot until an actual supplier-side correction exists.

---

## Output to BD

Purchased exposes to Business Domains **literally what it has read and normalized**, illustratively and non-exhaustively:

- normalized Purchased Lines;
- source provenance;
- Supplier (canonical identity);
- scope (the single economic/corporate/operational object the invoice belongs to);
- dates (all preserved dates, not a single pre-chosen "the" date);
- quantities;
- Unit of Measure;
- prices;
- allocated non-goods costs;
- taxes/charges already normalized;
- original source values, where needed;
- NORMALIZED / HUMAN state, where relevant.

Nothing more.

Purchased does **not**:

- interpret the data economically;
- decide whether it is convenient;
- decide whether/when to pay;
- perform reconciliation;
- decide inventory policy;
- decide accounting treatment;
- decide vendor action;
- make decisions on behalf of a Business Domain.

> **Principle: Shared Domains provide normalized shared facts. Business Domains make business decisions.**

---

## Consumers

Purchased may be consumed by multiple Business Domains/capabilities, illustratively and non-exhaustively:

- Inventory
- Cost Analysis
- Forecasting
- Accounting / Administration
- Vendor Analysis
- Cognito
- other future Business Domains

Purchased **publishes** the purchase fact; consuming Domains are not automatically assigned ownership of it, and Purchased does not automatically own their processes — ownership of a consumer process (Inventory policy, Cost Analysis method, and so on) always remains with the consuming Domain.

---

## What Purchased does NOT own

- Whether an invoice was paid, or how (Bank Reconciliation — owned by the consuming Business Domain).
- Inventory, production, recipes.
- Accounting/tax treatment of the purchase.
- Vendor selection or purchasing decisions (what/how much/from whom to buy) — Procurement.
- Accounts Payable decisions (what/when to pay).
- Any economic interpretation, convenience judgment, reconciliation, inventory policy, accounting treatment, or vendor-action decision (see "Output to BD" above).
- Any consuming Domain's own processes (Inventory, Cost Analysis, Forecasting, etc.) beyond publishing the purchase fact they consume.
- Email intake, OCR, invoice parsing, supplier API integration, banking, payment matching, or an AI normalization engine — none of these is designed or implemented by this document.
- A generic document archive role — Purchased always produces normalized, structured Purchased Lines, never merely stores files.

---

## Relationship to Restaurant's existing Purchasing module

Restaurant already has its own, pre-existing, Business-Domain-specific **Purchasing** module (`Business Domain/Restaurant/Purchasing/README.md`), which normalizes supplier invoices of any origin into a Purchase Document / Purchase Line / Effective Product Cost model, including its own Invoice Intake capability, Merchandise/Economic Classification, and Order/Invoice/Physical-Receiving reconciliation.

This document does **not** merge, redefine, rename, or take over Restaurant/Purchasing's existing approved content — Restaurant/Purchasing's entities and business rules remain exactly as previously approved, unmodified by this task.

Whether — and how — Purchased (this Shared Domain) and Restaurant/Purchasing (that Business Domain module) should relate *more broadly* is still an **open question** for a future, dedicated Product Owner decision — e.g. whether Restaurant/Purchasing should eventually be re-expressed wholesale as Restaurant's own consumer/specialization of Purchased (the same kind of relationship already recognized between Ambient Operational Context and the Restaurant Domain's Service Copilot module), or whether the two are deliberately kept separate because Restaurant/Purchasing's remaining scope (Physical Receiving, Configured Expectations/Alerts, Ingredient Mapping) genuinely exceeds what a cross-industry Purchased fact needs to model (see also [../../Domain Architecture.md](../../Domain%20Architecture.md) §9, Open Question 6).

**Invoice Intake alignment (closed) — "Align legacy Invoice Intake with Purchased":** for the one concrete path this open question originally named — `03 Software/InvoiceIntake/` (the legacy prototype: OCR/parse → human review → save) — the Product Owner has closed it. As of this task:

- **Purchased owns the Purchase Fact** that path produces: capture (Invoice Intake) + normalize (OCR/parser + human review) + publish. Persistence continues to use the existing `PurchaseDocument`/`PurchaseLine` schema under `03 Software/RF-One Data Store/rfone_data_store/purchasing/` — evolved (ownership documentation, a duplicate/correction check, and derived NORMALIZED/HUMAN and non-goods-allocation read functions), never duplicated into a second schema. See `03 Software/RF-One Data Store/PURCHASING.md` §1 and §10.
- **Restaurant/Purchasing consumes** this Purchase Fact for its own remaining, still Purchasing-owned scope (Purchase Order, Configured Expectation, Physical Receiving, Reconciliation, Alert, Expected Supplier Credit) — it is never a prerequisite for creating one; `03 Software/InvoiceIntake/purchased_bridge.py` (renamed from `purchasing_bridge.py`) calls none of Purchasing's decision/receiving functions.
- This closes Open Question 6 **for this one software path only** — the broader question in the paragraph above (e.g. whether Restaurant/Purchasing's remaining scope should itself eventually be re-expressed as a Purchased consumer/specialization) stays open.

---

## Open implementation points

- The relationship between Purchased and Restaurant's existing Purchasing module (see above) — closed for the `03 Software/InvoiceIntake/` path ("Invoice Intake alignment (closed)"); still open more broadly.
- No database schema, table, or field is fixed by this document — the "minimum conceptual data" list above is illustrative, not final.
- No Invoice Intake process (email, OCR, parser, supplier API) is designed or implemented here.
- No Bank Reconciliation process is designed here — only the boundary that it does not belong to Purchased.
- The non-goods cost allocation mechanism's edge cases (rounding, what counts as "directly attributable," an invoice with no goods lines) are not fully specified here.
- Which date a given consumer process should treat as "the" Purchase Date is left to business/system configuration, not fixed here.
- The Supplier identity resolution algorithm (alias/code matching) is not designed here (a concrete canonical-Supplier-plus-alias mechanism now exists for the `03 Software/InvoiceIntake/` path specifically — "Purchased Supplier Training — Phase 2" — but no general algorithm is fixed by this document).
- The training-period length (N), accuracy threshold, and per-Supplier/format "trusted" criteria in "Source/format validation and training" are left configurable, not fixed here (a concrete, overridable default — N=5 consecutive correct documents — now exists for `03 Software/InvoiceIntake/` specifically; still a configuration value, not a rule fixed by this document).
- Whether one physical source document always corresponds to exactly one Purchase Fact is not addressed here (a real acquired document can bundle more than one invoice — `03 Software/InvoiceIntake/invoice_splitter.py`, "Purchased Supplier Training — Phase 2," handles this for that one concrete path; no general multi-document-source model is designed by this document).
- The document-equivalence check used before deduplication is not designed here.
- How HUMAN-state Purchased Lines and duplicate/anomaly cases surface to a person (Attention routing, review queue, etc.) is not designed here (a concrete review queue + correction/confirmation UI now exists for the `03 Software/InvoiceIntake/` path specifically — "Purchased Human Review + Supplier Format Training UI" — but it is not reached through Attention, which remains undesigned/unintegrated everywhere in RF-One; no general HUMAN-state routing model is fixed by this document).
- Which Business Domain(s)/capabilities actually consume Purchased's output, and how, is left to future Domain/Product/Runtime work.

**Stress test (self-check against scope creep):** this definition has been checked to ensure Purchased is not, and does not become, Procurement, Accounts Payable, Accounting, Bank Reconciliation, Inventory, POS/sales history, or a generic document archive (see "Scope" above) — it remains capture + normalize + publish factual purchased data only.
