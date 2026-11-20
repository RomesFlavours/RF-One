# TASK_INVOICE_001 — REPORT

**Task:** Formalize the first canonical Invoice Intake / Invoice Cost Semantics model, derived from real mixed-type supplier invoice analysis (Ben E. Keith, Gordon Food, Cheney Brothers).
**Scope:** Documentation only. No database schema, ORM model, parser, OCR pipeline, IMAP/API integration, bank-matching engine, PDF report, or classification engine was created.
**Origin:** Specified directly by the Product Owner in this working session (not via a separately filed `07 Tasks/TASK_INVOICE_001_*.md` spec — see Section N).
**Date:** 2026-08-29

---

## A. Summary

Created the first canonical Administration-level model for supplier invoice ingestion and cost composition: `01 Domains/Administration/Invoice Intake.md`. It defines `SupplierInvoice`, `InvoiceLine`, the separation between supplier source semantics and RF-One's own economic classification, Supplier Item recognition memory, `Effective Item Cost` and its surcharge/discount allocation formulas, the Tax Treatment open question, the `FinancialTransaction` ≠ `SupplierInvoice` boundary, and the future `TransactionAttribution` relationship. Registered the new module in `01 Domains/Administration/README.md` and `01 Domains/README.md`, added a new open question to `OpenQuestions.md`, and added minimal, non-redesigning cross-reference notes to the pre-existing Restaurant Purchasing documents where a real conceptual adjacency exists (Section D). No code, schema, or Software-layer file was touched.

---

## B. Canonical SupplierInvoice

`SupplierInvoice` is the canonical, source-faithful representation of one supplier invoice, independent of acquisition source (today: PDF upload; future: IMAP mailbox, supplier API/token, other structured sources — all converge on the same model).

Fields recorded when available: supplier, invoice number, invoice date, delivery date, customer/account reference, bill-to, ship-to/delivery location, payment terms, invoice total, source document reference, source/provenance. Fields are explicitly **not** assumed uniform across suppliers — a missing field is an epistemic Unknown, never treated as zero or inferred. The original document is always preserved unmodified. See `Invoice Intake.md`, §1–§2.

---

## C. Canonical InvoiceLine

`InvoiceLine` is the atomic fact for one line item: supplier line number, supplier item code, supplier category code, brand, manufacturer/product code, raw description (preserved verbatim), quantity, unit, pack size, unit price, line amount, source section/supplier grouping. See `Invoice Intake.md`, §3.

---

## D. Supplier source semantics vs. RF-One classification

Supplier section/category labels (e.g. "Cooler," "Dry," "Dry Goods") are preserved as source facts and are explicitly barred from being treated automatically as RF-One's economic classification. `InvoiceLineClassification` (Food/Drink/Supplies/other) is a distinct, separately recorded fact, derived only through the Supplier Item Memory process (Section E) — never inferred directly from the supplier's own label. See `Invoice Intake.md`, §4.

**Consistency check performed:** this is the same non-inference discipline already used for tax/legal interpretation in Core (`05_Epistemic_Boundary_and_Subject_Sovereignty.md`) and is stated explicitly to prevent a supplier's warehouse-organization convention from silently becoming RF-One's cost-reporting category.

---

## E. Supplier Item recognition memory

`(Supplier, Supplier Item Code)` is the recognition key. A new pair triggers an AI proposal → human confirmation → reusable classification memory cycle; a recurring pair applies the confirmed classification directly without re-interpreting the raw description each time. An override updates memory going forward and never rewrites already-recorded historical `InvoiceLine`s. This reuses, rather than duplicates, the "AI proposes / human confirms / AI never validates autonomously" principle already established for Ingredient Mapping in `01 Domains/Restaurant/Purchasing/README.md`. See `Invoice Intake.md`, §5.

---

## F. Effective Item Cost

```text
Effective Item Cost
=
Base Line Amount
+ allocated applicable surcharges
- allocated applicable discounts
+ applicable tax, only when the applicable fiscal rule establishes that
  the tax is economically borne by the business
```

Never persisted as canonical truth when recalculable — see Section L. See `Invoice Intake.md`, §6.

---

## G. Surcharge allocation

`InvoiceCharge` (invoice, source description, charge type/source label, amount, applicable scope/eligible lines). Canonical rule: a surcharge that economically increases real product cost must be distributed proportionally across eligible lines, never left outside cost analysis as a separate invoice-level amount.

```text
allocation share    = line base amount / total eligible base amount
allocated surcharge = allocation share × surcharge amount
```

`line base amount` is the default proportional basis; eligible lines default to all merchandise lines unless a narrower scope is a recorded fact on the `InvoiceCharge` (e.g. a cold-chain surcharge applying only to refrigerated items — flagged as a default assumption, not yet evidenced by a real narrow-scope surcharge in the three analyzed suppliers). Real example: Cheney Brothers' Fuel Surcharge is distributed proportionally across eligible items and increases their Effective Item Cost — it must not remain outside Food Cost. See `Invoice Intake.md`, §7.

---

## H. Discount allocation

`InvoiceDiscount` mirrors `InvoiceCharge`'s allocation logic in reverse — same proportional formula, reducing rather than increasing Effective Item Cost. See `Invoice Intake.md`, §8.

---

## I. Tax open question

A new open question, "Invoice Tax Treatment — OPEN," was added to `OpenQuestions.md` (inserted immediately after the intro, before the existing "Resolved" section). It records the atomic tax facts to preserve, the four assumptions RF-One does **not** yet make, the provisional rule (tax enters Effective Item Cost only when established as economically borne by the business), and the Florida resale/exemption verification requirement. It cross-references the Core Epistemic Boundary (legal/tax interpretation is Belief/Inference, never silently Fact) and names the Taxation Domain as the expected future resolver. See `Invoice Intake.md`, §9, and `OpenQuestions.md`.

---

## J. Bank/Invoice boundary

`FinancialTransaction ≠ SupplierInvoice`: a bank/card movement is a settlement/reconciliation fact, never the source of line-level economic detail — the same boundary already stated for payroll direct-deposit debits in `Payroll Provider Result.md`, cited here rather than restated as a new rule. Future connection: `FinancialTransaction ↔ Invoice/Payment Matching ↔ SupplierInvoice`. For a mono-type supplier, attribution can often derive directly from the supplier/profile; for a mixed-type supplier, the invoice is the necessary source for the correct economic split. No bank-matching engine is designed. See `Invoice Intake.md`, §10.

---

## K. Future TransactionAttribution relationship

Documented conceptual flow only: `SupplierInvoice → InvoiceLines → RF-One classifications → category totals derived → TransactionAttribution`, illustrated with the worked example (Invoice 1,000 = Food 700 + Drink 200 + Supplies 100, matched to a -1,000 `FinancialTransaction`). Category totals are explicitly derived, not persisted as canonical truth. No schema or matching algorithm is defined. See `Invoice Intake.md`, §11.

---

## L. Persistence invariant

Persisted as canonical fact: `SupplierInvoice` and `InvoiceLine` source-verbatim fields, `InvoiceCharge`/`InvoiceDiscount` atomic facts, tax atomic facts, a human-confirmed Supplier Item classification, and `FinancialTransaction`. Never persisted as canonical truth when recalculable: `Effective Item Cost`, allocated surcharge/discount shares, and category totals/`TransactionAttribution`. This is the same invariant already established for Employee cost in `Personnel Cost.md`, §8, applied here rather than restated as a new principle. See `Invoice Intake.md`, §12.

---

## M. Exact documentation changed

**Created:**

- `01 Domains/Administration/Invoice Intake.md`
- `07 Tasks/Reports/TASK_INVOICE_001_REPORT.md` (this file)

**Modified:**

- `01 Domains/Administration/README.md` — added Invoice Intake to the module map, module table, and Related documents.
- `01 Domains/README.md` — extended the Administration row to mention the Invoice Intake module.
- `01 Domains/Restaurant/Purchasing/EntityDefinitions.md` — added a short cross-reference note under "Purchase Document" pointing to `Invoice Intake.md` (no redefinition of Purchase Document).
- `01 Domains/Restaurant/Purchasing/README.md` — added a short cross-reference note under "Fundamental Principle" pointing to `Invoice Intake.md` (no redefinition of the module's scope or entities).
- `OpenQuestions.md` — added "Invoice Tax Treatment — OPEN."

**Not touched:** any file under `03 Software/`, `00 Core/`, `02 Products/`, or `09 Strategy/`; the existing `Purchase Document`/`Purchase Line` definitions themselves (only a note was added alongside them).

---

## Unresolved issues / questions for the Product Owner

1. **Conceptual overlap with Purchase Document/Purchase Line (flagged, not resolved).** `SupplierInvoice`/`InvoiceLine` (transversal, Administration) and `Purchase Document`/`Purchase Line` (Restaurant-specific, Ingredient-costing) both canonically represent "a supplier's commercial document and its lines." This task documents a plausible boundary — Invoice Intake as the transversal source-fidelity/cost-composition layer, Purchase Document as the Restaurant-specific Ingredient-costing consumption of the Food-relevant subset — but does **not** decide how the two ingestion paths reconcile operationally (which is upstream, whether one is derived from the other, or whether both are independently populated with a reconciliation step). This should be resolved before any Software/Runtime work ingests real invoices into both models. See `Invoice Intake.md`, §13.
2. **Surcharge eligibility default is provisional.** "Eligible lines default to all merchandise lines unless a narrower scope is recorded" is a documentation-time default, not yet evidenced against a real narrow-scope surcharge from any of the three analyzed suppliers. Worth revisiting once a concrete counter-example appears (e.g. a surcharge that only applies to refrigerated items).
3. **Tax Treatment remains genuinely open**, as instructed — not a defect, tracked in `OpenQuestions.md`.

---

## N. Git scope confirmation

No `git add`, `git commit`, or `git push` was run. The working tree contains only the file creations/modifications listed in Section M; nothing has been staged or committed.
