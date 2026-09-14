# Purchased

**Version:** 1.0
**Status:** APPROVED DOMAIN DEFINITION
**Module:** Shared Domains / Purchased

---

## Related documents

- [../../Domain Architecture.md](../../Domain%20Architecture.md) §4 (Shared Domains / Business Domain taxonomy, where Purchased is introduced as a Shared Domain) and §9, Open Question 6 (Purchased vs. Restaurant/Purchasing, recorded but not decided by this document)
- [../../README.md](../../README.md) (`01 Domains/` purpose, the Shared Domains / Business Domain taxonomy, and the distinction between `Shared Domains/` and `_Shared/`)
- [../Administration/README.md](../Administration/README.md) and [../Administration/Invoice Intake/README.md](../Administration/Invoice%20Intake/README.md) — Administration is a possible consumer of Purchased's output (economic category/document totals); Administration's own Invoice Intake module is a distinct, pre-existing capability under Administration, not the same thing as Purchased and not renamed or merged by this document
- [../../Business Domain/Restaurant/Purchasing/README.md](../../Business%20Domain/Restaurant/Purchasing/README.md) — Restaurant's existing, Business-Domain-specific Purchasing module, which already normalizes supplier invoices into its own Purchase Document/Purchase Line/Effective Product Cost model; see "Relationship to Restaurant's existing Purchasing module" below for the explicitly open question this document does not resolve
- `CLAUDE.md` — Core/Domain/Product/Runtime distinction; this document is Domain-level definition, not Product or Runtime design

---

## Purpose

Purchased is a **Shared Domain** consumed by Business Domains. It transforms what the business was invoiced for into normalized purchase facts.

> **Purchased represents what the business was invoiced for, and therefore what it purchased/spent, subject to later supplier-side corrections such as credit memos.**

**Purchased does not determine whether the document was paid.**

---

## Scope

Purchased owns the **purchase fact**: turning a heterogeneous source document (an invoice, receipt, credit memo, or equivalent) into a normalized, canonical representation of what was purchased.

Purchased does not own:

- inventory;
- production/recipes;
- accounting/general ledger posting;
- tax treatment;
- payments or bank reconciliation;
- vendor selection/purchasing decisions (what, how much, from whom to buy).

---

## Canonical output

The canonical unit of Purchased's output is **not** "one invoice = one row."

It is:

> **One normalized Purchased Line per economic item/service/charge represented in the source document.**

Example — an invoice containing:

- 3 cases tomatoes
- 2 mozzarella
- delivery fee

produces three Purchased Lines (tomatoes, mozzarella, delivery fee), each linked back to the same source invoice/document.

### Purchased Line — minimum conceptual data

Without fixing a database schema, a Purchased Line may conceptually carry at least:

- Supplier
- Legal Entity
- Business Unit / Restaurant / destination scope
- Source document
- Invoice number
- Invoice date
- Purchase / service date, when available
- Original supplier description
- Normalized item/service
- Quantity
- Unit of Measure
- Unit price
- Discount
- Tax
- Fee / surcharge
- Line amount
- Document total reference
- Currency
- Source provenance
- Confidence / unresolved status, where necessary

No technical field, type, or storage decision is fixed here — this is a conceptual minimum, not a schema.

---

## Input sources

Purchased may acquire evidence from, illustratively and non-exhaustively:

- supplier invoices;
- scanned invoices;
- email attachments;
- supplier portals;
- supplier APIs;
- EDI / structured files;
- manual document upload;
- other authorized source systems.

**Invoice Intake is a process that feeds Purchased — it is not the name of this Domain.** No email intake, OCR, invoice parser, or supplier API integration is designed, authorized, or implied by this document.

RF-One already has a pre-existing **Invoice Intake** capability (`../Administration/Invoice Intake/README.md`), documented as "a Shared Domains capability... document acquisition, OCR/parsing, normalization, review, and routing," which today feeds Restaurant/Purchasing's canonical model rather than this document. Whether that existing process should also (or instead) feed Purchased as defined here is part of the same open question recorded below — this document does not redirect Invoice Intake's existing output.

---

## Normalization

Purchased transforms supplier-specific data into canonical form.

Example: a supplier description such as `"TOM ROMA 25LB CS"` may be normalized toward a canonical item, while the original supplier description/source evidence is always preserved alongside the normalized value — normalization must never discard the source description.

When a mapping is not sufficiently reliable:

- Purchased does not invent a normalized value;
- the line is left **unresolved**;
- human Attention/intervention may be required.

No AI normalization engine, OCR pipeline, or mapping algorithm is designed or implemented by this document.

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

Purchased remains the snapshot of the source invoice until an actual supplier-side correction exists.

---

## Corrections / credit memos

A supplier credit memo, corrected invoice, return credit, or other supplier-side document belongs to **Purchased**, because it changes the economic snapshot of the purchase.

A bank payment mismatch is **not** a supplier-side correction. This distinction must remain sharp: Purchased reacts to supplier-side documents; it does not react to settlement/payment evidence.

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

Purchased **publishes** the purchase fact; consuming Domains are not automatically assigned ownership of it, and Purchased does not automatically own their processes.

---

## What Purchased does NOT own

- Whether an invoice was paid, or how (Bank Reconciliation — owned by the consuming Business Domain).
- Inventory, production, recipes.
- Accounting/tax treatment of the purchase.
- Vendor selection or purchasing decisions (what/how much/from whom to buy).
- Any consuming Domain's own processes (Inventory, Cost Analysis, Forecasting, etc.) beyond publishing the purchase fact they consume.
- Email intake, OCR, invoice parsing, supplier API integration, banking, payment matching, or an AI normalization engine — none of these is designed or implemented by this document.

---

## Relationship to Restaurant's existing Purchasing module

Restaurant already has its own, pre-existing, Business-Domain-specific **Purchasing** module (`Business Domain/Restaurant/Purchasing/README.md`), which normalizes supplier invoices of any origin into a Purchase Document / Purchase Line / Effective Product Cost model, including its own Invoice Intake capability, Merchandise/Economic Classification, and Order/Invoice/Physical-Receiving reconciliation.

This document does **not** merge, redefine, rename, or take over Restaurant/Purchasing's existing approved content — Restaurant/Purchasing's entities and business rules remain exactly as previously approved, unmodified by this task.

Whether — and how — Purchased (this Shared Domain) and Restaurant/Purchasing (that Business Domain module) should relate is an **explicitly open question**, not decided here: for example, whether Restaurant/Purchasing should eventually be re-expressed as Restaurant's own consumer/specialization of Purchased (the same kind of relationship already recognized between Ambient Operational Context and the Restaurant Domain's Service Copilot module), or whether the two are deliberately kept separate because Restaurant/Purchasing's scope (Physical Receiving, Configured Expectations/Alerts, Ingredient Mapping) genuinely exceeds what a cross-industry Purchased fact needs to model. This question is sharpened, not created, by this document: `Administration/Invoice Intake/README.md` already records that an earlier, Administration-local invoice model was previously reconciled *into* Restaurant/Purchasing's canonical model (`07 Tasks/Reports/TASK_PURCHASING_001_REPORT.md`) — the same kind of consolidation this open question may eventually require in the other direction, or may not. This is recorded as an open implementation point (see also [../../Domain Architecture.md](../../Domain%20Architecture.md) §9, Open Question 6) for a future, dedicated Product Owner decision — it is not resolved by formalizing Purchased.

---

## Open implementation points

- The relationship between Purchased and Restaurant's existing Purchasing module (see above) — not decided by this document.
- No database schema, table, or field is fixed by this document — the "minimum conceptual data" list above is illustrative, not final.
- No Invoice Intake process (email, OCR, parser, supplier API) is designed or implemented here.
- No Bank Reconciliation process is designed here — only the boundary that it does not belong to Purchased.
- How "unresolved" Purchased Lines surface to a human (Attention routing, review queue, etc.) is not designed here.
- Which Business Domain(s)/capabilities actually consume Purchased's output, and how, is left to future Domain/Product/Runtime work.
