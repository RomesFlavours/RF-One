# TASK_PURCHASING_001 — REPORT

**Task:** Reconcile and canonicalize the Purchasing model across Restaurant/Purchasing and Administration, per `07 Tasks/TASK_PURCHASING_001_Reconcile_and_Canonicalize_Purchasing_Model.md` and the Product Owner decisions it records.
**Scope:** Documentation only. No database schema, ORM model, parser, OCR pipeline, or integration code was created or modified.
**Input:** `07 Tasks/Reports/PURCHASING_CURRENT_STATE_AUDIT.md` (2026-08-29).
**Date:** 2026-08-30

---

## A. Summary

Reconciled the three previously unreconciled layers of Purchasing knowledge identified by the audit (Restaurant/Purchasing, Administration/Invoice Intake, and the peer-Domain terminology inconsistency) into a single canonical model under `01 Domains/Restaurant/Purchasing/`. Deleted the duplicate `01 Domains/Administration/Invoice Intake.md`, migrating every valid idea it introduced (mixed-supplier source facts, merchandise/economic classification, Supplier Item memory with override semantics, surcharge/discount allocation formulas, the persistence invariant, and the Bank/Payment boundary) into the canonical Restaurant/Purchasing documents. Introduced `line_type` (`PRODUCT`/`SURCHARGE`/`DISCOUNT`) on Purchase Line, corrected the "every Purchase Line references a Supplier Product" rule, added Merchandise/Economic Classification as a first-class concept distinct from Ingredient mapping, formalized Effective Product Cost as a derived (never persisted) measure, rewrote `Workflow.md` as a complete 8-step process, corrected every active document that used "Purchasing" as a Domain peer of Restaurant, and updated `OpenQuestions.md` so "Invoice Tax Treatment — OPEN" references the surviving canonical model.

---

## B. Domain placement

Purchasing is confirmed as a module of the Restaurant Domain (`Restaurant Domain └── Purchasing module`, canonically `01 Domains/Restaurant/Purchasing/`), not a peer Domain. Corrected active documents that listed "Purchasing" alongside "Restaurant" as if both were Domain-level examples:

- `CLAUDE.md` — removed "Purchasing" from the Domain examples list; added an explicit note that Purchasing is a Restaurant module.
- `00 Core/ConceptualArchitecture/00_RF-One_Core_Vision.md` §1 — removed "Purchasing" from the Domain examples list; added a one-line clarification that a Domain may have modules, and a module is not a peer Domain.
- `00 Core/ConceptualArchitecture/01_Subject_and_Reality.md` §4 — removed "Purchasing" from the Domain examples list.
- `00 Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md` — "the Restaurant Purchasing Domain" → "the Restaurant Domain's Purchasing module."
- `01 Domains/Personnel Management/README.md`, `Selection/README.md`, `Performance/Performance.md` — "a Purchasing account manager" / "Purchasing (selecting...)" / "a Purchasing role" → "Restaurant/Purchasing" throughout, so Purchasing is no longer implied to be a Domain of the same standing as Sales or a future professional-services Domain.
- `01 Domains/Restaurant/Commercial Catalog/Item.md` — "Purchasing (Purchasing Domain)" in the consumption-flow diagram → "Purchasing (Restaurant Domain, Purchasing module)"; the adjacent "Inventory (Inventory Domain)" / "Sales (Sales Domain)" labels in the same diagram were also corrected to "(Restaurant Domain)" for internal consistency of that one diagram (these were not separately in this task's scope but were directly adjacent to, and equally wrong for, the same reason).
- `01 Domains/Restaurant/Model/PurchasingModel.md` — title "Purchasing Domain Map" → "Purchasing Module Map (Restaurant Domain)".
- `01 Domains/Restaurant/Purchasing/DataAcquisition.md` — "never modify the Purchasing Domain" → "never modify the Purchasing Module."

Not changed (already correct or out of scope): `01 Domains/Restaurant/README.md` ("Current Modules" already lists Purchasing correctly as a module), `01 Domains/Restaurant/Roadmap.md` (table already classifies Purchasing under "Restaurant Domain"), `09 Strategy/04_Business_Capability_Coverage.md` (KD-007 already classifies Purchasing as "Restaurant Domain"), `PROJECT_STATE.md` (already correct), `01 Domains/Restaurant/Commercial Catalog/README.md` and `UnitOfMeasure.md` (list Purchasing alongside Sales/Inventory as consuming modules, without asserting Domain status), `90 Archive/**` and historical task reports (left untouched as history, per instruction).

**Duplicate CLAUDE.md note:** an identical copy of `CLAUDE.md` exists one level up, at `C:\Users\servi\OneDrive\AI-RF-ONE\CLAUDE.md`, outside this git repository. Only the in-repository copy (`RF One/CLAUDE.md`) was edited, since only it is under version control here; the outer copy is now out of sync and may need the Product Owner's attention separately.

---

## C. Duplicate Administration Invoice model removed

Deleted `01 Domains/Administration/Invoice Intake.md` in its entirety. Before deletion, every valid idea it introduced that was not already present in Restaurant/Purchasing was migrated:

- Mixed-supplier source facts (supplier item code, supplier category code, brand, manufacturer/product code, pack size, source section) → `EntityDefinitions.md`/`DataDictionary.md`, "Purchase Line," `PRODUCT`-only attributes.
- Header facts (delivery date, ship-to/destination, customer/account reference, payment terms) → `DataDictionary.md`, "Purchase Document."
- Supplier source semantics vs. RF-One classification (e.g. "Cooler" ≠ Food) → `EntityDefinitions.md`, "Supplier Product" and "Merchandise / Economic Classification."
- Supplier Item Memory with override semantics (a correction updates memory going forward, never rewrites historical lines) → `EntityDefinitions.md`, "Supplier Product"; `ValidationRules.md`.
- Effective Item Cost formula (surcharge + discount + conditional tax) → renamed `Effective Product Cost`, `BusinessRules.md`, Rule 12.
- Surcharge/discount allocation formula (`allocation share = line base amount / total eligible base amount`) → `BusinessRules.md`, Rules 9–10.
- Persistence Invariant → `DataDictionary.md`, "Persist Facts — Derive Calculations."
- Bank/Invoice boundary (`FinancialTransaction ≠ SupplierInvoice`) → `BusinessRules.md`, Rule 18, renamed `FinancialTransaction ≠ Purchase Document`.
- Acquisition sources (IMAP, Supplier API/token) → `DataAcquisition.md`, "Supported Sources."
- Priority suppliers (Ben E. Keith, Cheney Brothers, Gordon Food) → `DevelopmentRoadmap.md`.

References removed from `01 Domains/Administration/README.md` (module map, module table, Related documents — replaced with a short note explaining the removal and pointing to Restaurant/Purchasing and this report), `01 Domains/README.md` (Administration row description), `01 Domains/Restaurant/Purchasing/README.md` and `EntityDefinitions.md` (the TASK_INVOICE_001 cross-reference notes, replaced with the migrated content itself rather than a pointer to a separate document). Historical files (`07 Tasks/Reports/PURCHASING_CURRENT_STATE_AUDIT.md`, `07 Tasks/Reports/TASK_INVOICE_001_REPORT.md`) were left untouched, as instructed.

---

## D. Canonical Purchase Document

`Purchase Document` remains the single canonical representation of a purchase's source commercial document (Invoice, Receipt, Credit Note, API purchase record, or other real document). `DataDictionary.md` now lists `DeliveryDate`, `DestinationLocation`, `CustomerAccountReference` and `PaymentTerms` alongside the existing header fields, all explicitly documented as present only when the source discloses them ("extract what the source knows; do not invent what the source does not know" — `EntityDefinitions.md`). No field is universally mandatory.

---

## E. Canonical Purchase Line and line_type

`Purchase Line` gained `line_type` ∈ {`PRODUCT`, `SURCHARGE`, `DISCOUNT`}. Every real line of a Purchase Document is preserved as one Purchase Line regardless of economic nature. No separate `InvoiceLine`/`InvoiceCharge`/`InvoiceDiscount`/`SupplierInvoice` entities were created — `EntityDefinitions.md`, `DataDictionary.md`, `BusinessRules.md` Rule 3, `Model/PurchasingModel.md`.

---

## F. Supplier Product semantics

Corrected the old universal rule ("every Purchase Line references exactly one Supplier Product") to depend on `line_type`: `PRODUCT` lines may/reference a Supplier Product when identity is available; `SURCHARGE`/`DISCOUNT` lines never do (`BusinessRules.md`, Rule 3; `EntityDefinitions.md`, "Supplier Product Relationship").

---

## G. Merchandise/economic classification

Added as a first-class concept (`EntityDefinitions.md`, new "Merchandise / Economic Classification" section; `DataDictionary.md`, `Purchase Line.EconomicClassification` and `Supplier Product.EconomicClassification`). Values: `FOOD`, `DRINK`, `SUPPLIES`, `OTHER`. Applies to every `PRODUCT` Purchase Line when known; never applies to `SURCHARGE`/`DISCOUNT` lines. This is the general replacement for the old Supplier-Product-only-focused-on-Ingredient model.

---

## H. Ingredient mapping boundary

Ingredient mapping is now explicitly a downstream semantics conditioned on merchandise classification placing a product in the Food/Ingredient context (typically `FOOD`) — not a universal requirement (`BusinessRules.md`, Rule 4; `EntityDefinitions.md`, "Ingredient"). A `SUPPLIES` or `DRINK` classification does not require Ingredient mapping.

---

## I. Supplier product learning/validation

Consolidated the "known → reuse, unknown → AI proposes/human confirms/never rewrite history" behavior into `EntityDefinitions.md` ("Supplier Product," Supplier Product memory) and `ValidationRules.md` (Human Validation section). No second "Unclassified Item Log" was created — the existing Validation Log already covers unknown classifications and mappings, as instructed.

---

## J. Surcharge semantics

A `SURCHARGE` Purchase Line preserves raw description and source amount, has no Supplier Product and no merchandise classification, and is proportionally allocated across eligible `PRODUCT` lines (`allocation share = product base line amount / sum of eligible PRODUCT base line amounts`) when deriving Effective Product Cost (`BusinessRules.md`, Rule 9). Eligible lines default to all `PRODUCT` lines unless a narrower scope is a recorded source fact.

---

## K. Discount semantics

A `DISCOUNT` Purchase Line mirrors the surcharge allocation logic in reverse, reducing rather than increasing Effective Product Cost (`BusinessRules.md`, Rule 10). This also resolves the audit's Contradiction N.7 (surcharges previously routed to "Real Ingredient Cost," discounts to "Food Cost") — both now symmetrically affect the same single derived measure, Effective Product Cost.

---

## L. Effective Product Cost derivation

Formalized as a single rule (`BusinessRules.md`, Rule 12):

```text
Effective Product Cost
=
Base Product Line Amount
+ proportional share of applicable SURCHARGE lines
- proportional share of applicable DISCOUNT lines
+ tax, only when a future applicable fiscal rule establishes that tax
  is economically borne by the business
```

This replaces the previous two-stage, ambiguous `RealIngredientCost`/`EffectiveCost` fields (resolving audit Contradiction N.4). Effective Product Cost is explicitly derived, never persisted as canonical stored truth.

---

## M. Persistence invariant

Added an explicit "Persist Facts — Derive Calculations" section to `DataDictionary.md`, listing canonical persisted facts (Purchase Document/Purchase Line source-verbatim fields, Supplier Product identity, EconomicClassification and Ingredient mapping once confirmed, source/provenance, Validation Log decisions) versus derived measures never stored as canonical truth (Effective Product Cost, surcharge/discount allocation shares, category totals, NormalizedQuantity/CostPerGram when recalculable). `BusinessRules.md` Rules 7, 8, 9, 10 and 12 cross-reference this distinction, and it is added to the Design Principles list ("Persist facts. Derive calculations.").

---

## N. Administration boundary

`01 Domains/Administration/README.md` and `01 Domains/README.md` were updated to state that Administration does not own Purchase Document, Purchase Line, Supplier Product, Ingredient mapping, product recognition, or invoice parsing semantics — it consumes the derived economic category allocation Purchasing produces. `BusinessRules.md`, new Rule 17 ("Purchasing Precedes Administration and Taxation"), and a new "Administration Boundary" section in `README.md` formalize this on the Purchasing side.

---

## O. Taxation boundary

Unchanged in substance: Taxation reasons about the tax treatment of a derived category/purchase, it does not reinterpret item-level Purchasing semantics. This is now stated explicitly in `BusinessRules.md`, Rule 17, and reflected in the updated `OpenQuestions.md` entry (Section T below).

---

## P. Bank/payment boundary

Added `BusinessRules.md`, Rule 18: `FinancialTransaction ≠ Purchase Document` — a bank/card movement is a settlement fact, distinct from the economic composition of the purchase. No `FinancialTransaction` schema, matching engine, or `TransactionAttribution` was implemented, as instructed.

---

## Q. Acquisition capability

`DataAcquisition.md` renamed in substance (its H1 heading changed from the mismatched `# API Integration` to `# Data Acquisition`, matching the filename — resolving audit Contradiction N.3) and repositioned as the Invoice Intake capability of the Purchasing module. "Supported Sources" now separates Today (PDF upload, OCR, manual entry) from Future (IMAP mailbox, Supplier API/token, XML, EDI, structured portal exports). All sources converge on Purchase Document/Purchase Line; no source-specific ontology was created.

---

## R. Workflow correction

`Workflow.md` — previously only "Step 5 – Ingredient Mapping" with no Steps 1–4 (audit Contradiction N.5) — was rewritten as the full 8-step canonical workflow: Acquire Purchase Document; Extract Header and Purchase Lines; Resolve Supplier/Supplier Products; Classify PRODUCT Lines; Validate Unknown/Ambiguous Items; Derive Surcharge/Discount-Adjusted Costs; Produce Downstream Restaurant Economic Knowledge; Expose Derived Category Allocation to Administration.

---

## S. Priority suppliers

`DevelopmentRoadmap.md` now records Ben E. Keith, Cheney Brothers and Gordon Food as the first operational priority suppliers for implementation/testing, with the rationale (mixed economic classifications on the same invoice) — recorded as roadmap/implementation context, not as ontology. BBC Wine is explicitly noted as not Priority 1.

---

## T. OpenQuestions status

`OpenQuestions.md`, "Invoice Tax Treatment — OPEN," was updated to reference the surviving canonical Restaurant/Purchasing terminology (Purchase Document/Purchase Line, Effective Product Cost) instead of the deleted Administration `SupplierInvoice`/`InvoiceLine`/`Effective Item Cost` model, and now cross-references `BusinessRules.md`, "Purchasing Precedes Administration and Taxation." **The question remains OPEN** — no tax-treatment assumption was introduced by this task. The file's intro line was also updated ("Administration / Payroll and Labor Cost" → "Administration, Restaurant/Purchasing and Labor Cost") since it now tracks a Purchasing-originated question too.

---

## U. Contradictions resolved

From `PURCHASING_CURRENT_STATE_AUDIT.md`, Section N:

- **N.1** (Purchasing shown as Domain peer of Restaurant) — resolved, see Section B above.
- **N.2** (surcharge allocation scope: "all purchased products" vs. "eligible lines") — resolved: `BusinessRules.md` Rule 9 now states the same "eligible PRODUCT lines, default all, narrower only if recorded" rule the deleted Administration document used, applied to the single surviving model.
- **N.3** (`DataAcquisition.md` title/filename mismatch) — resolved, see Section Q above.
- **N.4** (two divergent cost-terminology sets, `RealIngredientCost`/`EffectiveCost` vs. `Effective Item Cost`) — resolved into the single `Effective Product Cost` (Section L above).
- **N.5** (`Workflow.md` only "Step 5") — resolved, see Section R above.
- **N.7** (surcharges routed to "Real Ingredient Cost," discounts to "Food Cost" — asymmetric terminology) — resolved: both now symmetrically affect Effective Product Cost (Section K above).
- **N.6** (Taxation README cites a non-existent `TASK_TAXATION_001` file) — **not addressed by this task**; it concerns the Taxation Domain's own provenance, not Purchasing, and is out of this task's scope. Recorded here for visibility, not silently dropped.

---

## V. Remaining unresolved issues

1. **Duplicate `CLAUDE.md` outside the repository** (Section B) is now out of sync with the corrected in-repository copy. Not fixed by this task, since it lives outside the git repository this task operates on — flagged for the Product Owner's decision on whether/how to keep the two in sync.
2. **`03 Software/InvoiceIntake/` prototype schema** does not yet implement `line_type` or Merchandise/Economic Classification — its README now states this explicitly as a known gap against the canonical model, but the Excel schema itself was not touched, per the "no software changes" instruction.
3. **Audit item N.6** (Taxation task provenance) remains unresolved, as noted in Section U — genuinely out of this task's scope, not a Purchasing contradiction.
4. **Invoice Tax Treatment** remains genuinely OPEN, as instructed — not a defect.

No other contradiction requiring a Product Owner decision was found during the validation pass (Section below).

---

## W. Exact files created/modified/deleted

**Created:**

- `07 Tasks/TASK_PURCHASING_001_Reconcile_and_Canonicalize_Purchasing_Model.md`
- `07 Tasks/Reports/TASK_PURCHASING_001_REPORT.md` (this file)

**Deleted:**

- `01 Domains/Administration/Invoice Intake.md`

**Modified (27 files):**

- `CLAUDE.md`
- `OpenQuestions.md`
- `00 Core/ConceptualArchitecture/00_RF-One_Core_Vision.md`
- `00 Core/ConceptualArchitecture/01_Subject_and_Reality.md`
- `00 Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md`
- `01 Domains/README.md`
- `01 Domains/Administration/README.md`
- `01 Domains/Personnel Management/README.md`
- `01 Domains/Personnel Management/Selection/README.md`
- `01 Domains/Personnel Management/Performance/Performance.md`
- `01 Domains/Restaurant/Commercial Catalog/Item.md`
- `01 Domains/Restaurant/Model/PurchasingModel.md`
- `01 Domains/Restaurant/Purchasing/README.md`
- `01 Domains/Restaurant/Purchasing/EntityDefinitions.md`
- `01 Domains/Restaurant/Purchasing/DataDictionary.md`
- `01 Domains/Restaurant/Purchasing/BusinessRules.md`
- `01 Domains/Restaurant/Purchasing/ValidationRules.md`
- `01 Domains/Restaurant/Purchasing/Workflow.md`
- `01 Domains/Restaurant/Purchasing/AIResponsibilities.md`
- `01 Domains/Restaurant/Purchasing/ErrorHandling.md`
- `01 Domains/Restaurant/Purchasing/Examples.md`
- `01 Domains/Restaurant/Purchasing/AcceptanceCriteria.md`
- `01 Domains/Restaurant/Purchasing/TestingStrategy.md`
- `01 Domains/Restaurant/Purchasing/BusinessPermissions.md`
- `01 Domains/Restaurant/Purchasing/DataAcquisition.md`
- `01 Domains/Restaurant/Purchasing/DevelopmentRoadmap.md`
- `03 Software/InvoiceIntake/README.md`

**Not touched:** `Configuration.md`, `Non-FunctionalRequirements.md` (reviewed, found already consistent with the canonical decisions — no change needed); any file under `03 Software/` other than the one README note; any `00 Core/` file beyond the three terminology fixes above; `02 Products/`, `09 Strategy/` (reviewed, already correctly classify Purchasing under Restaurant Domain); `90 Archive/**` and historical `07 Tasks/Reports/*` (left as history, per instruction).

---

## X. Git scope confirmation

No `git add`, `git commit`, or `git push` was run. The working tree contains only the file creations, modifications and the one deletion listed in Section W; nothing has been staged or committed.

---

## Validation pass (Section 27 of the task)

- No active canonical document treats Purchasing as a peer Domain to Restaurant (checked repository-wide; only historical/archived files retain the old wording, as expected).
- No active canonical Administration document defines `SupplierInvoice`/`InvoiceLine` as a second invoice model (the file defining them was deleted; the only remaining occurrences are in `01 Domains/Administration/README.md`'s explanatory historical note and in historical task reports/archive).
- `PRODUCT`/`SURCHARGE`/`DISCOUNT` semantics are consistent across `EntityDefinitions.md`, `DataDictionary.md`, `BusinessRules.md`, `Workflow.md`, `Examples.md`, `AcceptanceCriteria.md`, and `Model/PurchasingModel.md`.
- No active canonical rule states that every Purchase Line requires a Supplier Product (Rule 3 corrected; `Model/PurchasingModel.md` corrected).
- Derived costs (Effective Product Cost, allocation shares, category totals, NormalizedQuantity/CostPerGram) are explicitly documented as non-canonical/derived in `DataDictionary.md` and cross-referenced from `BusinessRules.md`.
- "Invoice Tax Treatment" remains OPEN in `OpenQuestions.md`.
- Administration is documented as downstream of Restaurant/Purchasing for purchase semantics in both `01 Domains/Administration/README.md` and `01 Domains/Restaurant/Purchasing/BusinessRules.md`/`README.md`.
- All active references checked resolve to existing files; no dangling link to the deleted `Invoice Intake.md` remains outside historical/backtick-only mentions in `OpenQuestions.md`, `Administration/README.md`, and historical reports.
