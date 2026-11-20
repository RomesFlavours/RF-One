# TASK_PURCHASING_001 — Reconcile and Canonicalize Purchasing Model

**Type:** Documentation only. No database or software implementation.
**Input:** `07 Tasks/Reports/PURCHASING_CURRENT_STATE_AUDIT.md` and the canonical decisions approved by the Product Owner below.

---

## PURPOSE

Reconcile and simplify all Purchasing documentation in light of the audit
(`07 Tasks/Reports/PURCHASING_CURRENT_STATE_AUDIT.md`) and the canonical decisions approved by the Product Owner.

This task is DOCUMENTATION ONLY. Do NOT implement database or software.

---

## 1. Domain placement — canonical

Purchasing belongs to the Restaurant Domain. Canonical placement: `01 Domains/Restaurant/Purchasing/`.

Purchasing is NOT a Domain peer of Restaurant. Correct documents that currently use "Purchasing" as an example of a Domain peer of Restaurant. Use consistent phrasing such as "Restaurant Domain └── Purchasing module" or "Restaurant/Purchasing". Do not modify Core beyond what is strictly necessary to remove this terminological inconsistency.

## 2. Remove duplicate Administration invoice model

`01 Domains/Administration/Invoice Intake.md` duplicates the same reality already modeled as Purchase Document / Purchase Line in Restaurant/Purchasing. Canonical decision: no two parallel models of the same invoice may exist.

- Migrate into canonical Purchasing all valid ideas not already present.
- Delete `01 Domains/Administration/Invoice Intake.md` as a duplicate canonical document.
- Remove references from `01 Domains/Administration/README.md`, `01 Domains/README.md`, `01 Domains/Restaurant/Purchasing/README.md`, `01 Domains/Restaurant/Purchasing/EntityDefinitions.md`, and every other current reference.
- Do not delete historical task reports; they remain history, not canonical documentation.
- Invoice Intake becomes a CAPABILITY / source acquisition path of the Purchasing module, not an Administration Domain module.

## 3. Purchase Document

Keep as canonical concept: Purchase Document — the source commercial document of the purchase. May derive from Invoice, Receipt, Credit Note, API purchase record, or other real documents. Preserve all header facts genuinely present in the source useful to other Restaurant modules (Supplier, document/invoice number, issue/invoice date, delivery date, destination/ship-to/delivery location, customer/account reference, currency, total, payment terms, acquisition method, source/provenance, other real header facts). Do not make supplier-specific fields universally mandatory. Principle: extract what the source knows; do not invent what the source does not know.

## 4. Purchase Line — unified model

One canonical concept: Purchase Line. Add `line_type`: `PRODUCT`, `SURCHARGE`, `DISCOUNT`. Every real line of the document is preserved as a Purchase Line source fact. Do NOT create separate canonical entities `InvoiceLine`/`InvoiceCharge`/`InvoiceDiscount`/`SupplierInvoice`.

## 5. Product Purchase Line

A Purchase Line with `line_type = PRODUCT` represents a product actually purchased. May contain source facts: supplier item code, supplier category code, manufacturer/product code, brand, supplier raw description, quantity, purchase unit, pack size, unit price, base line amount, source section/grouping, other real source fields. Supplier source data must be preserved separately from RF-One semantics (e.g. Supplier Section = "Cooler" is a source fact, it does not automatically mean Food).

## 6. Supplier Product relationship

Correct the old rule ("Every Purchase Line must reference exactly one Supplier Product"). New rule: PRODUCT lines may/reference a Supplier Product when supplier product identity is available; SURCHARGE and DISCOUNT lines have Supplier Product = NULL/not applicable. A surcharge or discount is not a product.

## 7. Supplier Product memory

Maintain and consolidate: Supplier + Supplier Item Code → Supplier Product identity. If known, reuse the existing Supplier Product and confirmed mappings/classifications. If new, create/recognize a candidate; AI may propose, human validates; approved knowledge becomes reusable. Do not re-interpret a known Supplier Product from zero each time. Historical source facts must never be rewritten by later mapping/classification changes.

## 8. Merchandise / economic classification

More general rule than the old Supplier Product → Ingredient focus: every PRODUCT Purchase Line may have a merchandise/economic classification when known (Food, Drink, Supplies, Other/future categories). This determines the economic nature of the purchase. Ingredient mapping is a further, downstream semantics applicable when relevant (e.g. classification = FOOD may map to Ingredient; classification = SUPPLIES does not require Ingredient mapping). Ingredient mapping is not a universal requirement for every purchased product.

## 9. Unknown product / learning

If RF-One does not know a PRODUCT's classification, do not invent it. Use the existing canonical Validation Log / unresolved workflow. Principle: known product → reuse confirmed knowledge; unknown product → validation/review, AI proposal, human confirmation, reusable learned mapping/classification. Consolidate this behavior in existing documents rather than creating a duplicate "Unclassified Item Log" if the Validation Log already suffices.

## 10. Surcharge Purchase Line

A surcharge on the document is a Purchase Line with `line_type = SURCHARGE` (e.g. Fuel Surcharge, Delivery Surcharge, Service Fee, Environmental Fee). Preserves raw description and source amount. Has no Supplier Product and no merchandise classification. Its cost is distributed across eligible PRODUCT lines when computing effective product cost.

## 11. Discount / bonus Purchase Line

A discount or commercial bonus on the invoice is a Purchase Line with `line_type = DISCOUNT`. Preserves source description, source amount, source sign/semantics. No Supplier Product, no merchandise classification. Its effect proportionally reduces the effective cost of eligible PRODUCT lines.

## 12. Effective Product Cost

Single coherent rule, for each PRODUCT:

```
Effective Product Cost
=
Base Product Line Amount
+ proportional share of applicable SURCHARGE lines
- proportional share of applicable DISCOUNT lines
+ tax only when a future applicable fiscal rule establishes that tax is
  economically borne by the business
```

Current proportional basis: `product base line amount / sum of eligible PRODUCT base line amounts`. Surcharge/Discount may have a narrower eligible scope only if the source invoice establishes it, or a confirmed rule exists. Default: all eligible PRODUCT lines.

## 13. Persist facts — derive calculations

Correct all Purchasing documentation that treats derivable values as canonical stored attributes. Strong RF-One invariant: persist facts, derive calculations.

Canonical persisted/source facts: Purchase Document; Purchase Lines; quantity; unit; supplier product identity; base line amount; surcharge lines; discount lines; classifications; mappings; source/provenance; validation decisions.

NOT canonical stored truth: Effective Product Cost; Real Ingredient Cost; Effective Cost; surcharge allocation share; discount allocation share; category totals; Food Cost totals; normalized quantity when fully recalculable from atomic source facts/configuration; CostPerGram when recalculable. These may be defined derived measures/functions, never canonical facts. Revise `DataDictionary.md` and `BusinessRules.md` to make this distinction explicit.

## 14. Ingredient / Recipe costing

Do not eliminate existing work on Product, Specification, Ingredient, grams, cost per gram, Recipe costing — but reposition it correctly as a DOWNSTREAM SEMANTICS applicable to PRODUCT lines that belong to the Food/Ingredient context.

Canonical flow: Purchase Document → PRODUCT Purchase Line → Supplier Product → merchandise/economic classification → Ingredient mapping when applicable → derived normalized quantity / ingredient cost / recipe cost. Do not force Ingredient semantics onto Drink/Supplies/other purchased products when not applicable.

## 15. Purchases precede Administration and Taxation

Formalize this boundary: Restaurant/Purchasing understands WHAT was purchased. Administration does not reinterpret item-level semantics. Taxation does not reinterpret item-level semantics. Restaurant/Purchasing produces facts and derivable economic results (Purchase Document → Purchase Lines → classifications → derived category totals). Example: Olive Oil, Beef Tenderloin, Tomatoes → all classified FOOD; Administration does not need item identity, it consumes the derived economic allocation (Food = $X, Drink = $Y, Supplies = $Z). Canonical dependency: Restaurant/Purchasing → Economic Classification → derived category allocation → Administration → Taxation/Accounting treatment. Purchasing comes BEFORE fiscal treatment.

## 16. Administration boundary

Administration receives the economic result of Purchasing. It does NOT own: Purchase Document, Purchase Line, Supplier Product, Ingredient mapping, product recognition, invoice parsing semantics. Administration may consume: category totals, document totals, payment/reconciliation status, other derived economic facts required for the administration/accounting handoff. Do not create a second invoice ontology under Administration.

## 17. Bank / payment boundary

Preserve: FinancialTransaction ≠ Purchase Document. FinancialTransaction = movement of money. Purchase Document = economic composition of the purchase. Future relationship: FinancialTransaction ↔ Payment/Invoice Matching ↔ Purchase Document. Example: Purchase Document total = 1,000; derived classification Food = 700, Drink = 200, Supplies = 100; matched FinancialTransaction = -1,000; Administration can later produce Transaction Attribution (700 → Food, 200 → Drink, 100 → Supplies). Do NOT implement FinancialTransaction or matching in this task.

## 18. Tax — keep open

Preserve and consistently relocate the open question "Invoice Tax Treatment — OPEN". Tax source facts must be preserved. Do NOT assume yet that invoice tax always enters Effective Product Cost, never enters it, is always deductible, is always recoverable, or is always economically borne by the company. Tax treatment belongs to the Taxation/jurisdiction rule layer. Update `OpenQuestions.md` so the question references Restaurant/Purchasing canonical concepts, not the deleted Administration Invoice Intake model.

## 19. Invoice / Purchase Document acquisition

Invoice Intake is a CAPABILITY of Restaurant/Purchasing. Canonical input adapters may include, today: PDF upload; future: IMAP mailbox, Supplier API/token, XML, EDI, structured exports, OCR/paper, manual entry if necessary. All sources converge on Purchase Document → Purchase Lines. Do not create a source-specific ontology. Update `01 Domains/Restaurant/Purchasing/DataAcquisition.md` and fix its current title mismatch (`# API Integration`) so filename and document title are coherent.

## 20. First operational priority suppliers

Update the Purchasing roadmap/development documentation to record the first real mixed-product suppliers selected for implementation/testing: Ben E. Keith, Cheney Brothers, Gordon Food. Reason: their invoices can contain multiple economic product classifications, so FinancialTransaction/Supplier recognition alone is insufficient to determine the correct expense allocation. BBC Wine is not Priority 1. Keep this as implementation/roadmap context, not ontology.

## 21. Clean current Purchasing documentation

Review all files in `01 Domains/Restaurant/Purchasing/` and reconcile them with the decisions above, at minimum: README.md, EntityDefinitions.md, DataDictionary.md, BusinessRules.md, ValidationRules.md, Workflow.md, AIResponsibilities.md, ErrorHandling.md, Examples.md, AcceptanceCriteria.md, TestingStrategy.md, Configuration.md, DevelopmentRoadmap.md, DataAcquisition.md, Non-FunctionalRequirements.md, Model/PurchasingModel.md, Restaurant README/Roadmap, Domain README references, Core/CLAUDE references where Purchasing is incorrectly shown as peer Domain. Do not rewrite files unnecessarily; make the smallest coherent changes needed.

## 22. Workflow.md

The audit found `Workflow.md` contains only "Step 5 – Ingredient Mapping" with no Steps 1–4. Fix this defect: rewrite it as a coherent Purchasing workflow based on the now-canonical process. Preferred coherent workflow:

1. Acquire Purchase Document
2. Extract Header and Purchase Lines
3. Resolve Supplier / Supplier Products
4. Classify PRODUCT lines
5. Validate unknown/ambiguous items
6. Derive surcharge/discount-adjusted costs
7. Produce downstream Restaurant economic knowledge
8. Expose derived category allocation to Administration

Do not implement software.

## 23. Delete / remove duplicate canonical content

After migrating any unique useful content into Restaurant/Purchasing, delete `01 Domains/Administration/Invoice Intake.md`. Remove all active canonical references to `SupplierInvoice`, `InvoiceLine`, `InvoiceCharge`, `InvoiceDiscount`, `InvoiceLineClassification` when they represent the now-rejected duplicate Administration model. Historical task/report files may still mention them as historical facts; do not rewrite historical reports merely to hide that history.

## 24. Open questions

Update `OpenQuestions.md`. Keep active "Invoice Tax Treatment — OPEN" using the new canonical Purchasing terminology. Do NOT invent additional open questions unless a genuine contradiction remains impossible to resolve from the Product Owner decisions in this task; if such a contradiction remains, document it explicitly in the final report rather than deciding silently.

## 25. Software

Do NOT modify implementation. Do NOT create SQLAlchemy models, database tables, Alembic migrations, invoice parser, OCR pipeline, IMAP integration, supplier API integration, bank reconciliation, FinancialTransaction, TransactionAttribution, or QuickBooks integration. May update `03 Software/InvoiceIntake/README.md` only if needed to state that the existing software is a legacy/current prototype whose canonical target is now Restaurant/Purchasing Purchase Document/Purchase Line. Do not modify its code.

## 26. Report

Create `07 Tasks/Reports/TASK_PURCHASING_001_REPORT.md` including: A. Summary; B. Domain placement; C. Duplicate Administration Invoice model removed; D. Canonical Purchase Document; E. Canonical Purchase Line and line_type; F. Supplier Product semantics; G. Merchandise/economic classification; H. Ingredient mapping boundary; I. Supplier product learning/validation; J. Surcharge semantics; K. Discount semantics; L. Effective Product Cost derivation; M. Persistence invariant; N. Administration boundary; O. Taxation boundary; P. Bank/payment boundary; Q. Acquisition capability; R. Workflow correction; S. Priority suppliers; T. OpenQuestions status; U. Contradictions resolved; V. Remaining unresolved issues, if any; W. Exact files created/modified/deleted; X. Git scope confirmation.

## 27. Validation

Before finishing, perform a repository-wide read-only search and verify: no active canonical document still treats Purchasing as a peer Domain to Restaurant; no active canonical Administration document still defines SupplierInvoice/InvoiceLine as a second invoice model; Purchase Line PRODUCT/SURCHARGE/DISCOUNT semantics are consistent; no active canonical rule says every Purchase Line requires Supplier Product; derived costs are explicitly non-canonical/persisted; Tax Treatment remains OPEN; Administration is downstream of Restaurant/Purchasing for purchase semantics; all active references resolve to existing files. Report any remaining inconsistency.

## 28. Git

Do NOT run `git add`, `git commit`, or `git push`. At the end, print only: task file created; report created; number of files modified; number of files deleted; any unresolved inconsistencies; confirmation that Invoice Tax Treatment is still OPEN; confirmation that no git add/commit/push was performed.
