# PURCHASING_CURRENT_STATE_AUDIT

**Type:** Read-only documentary audit. No file was created, modified, or deleted other than this report. No `git add`, `git commit`, or `git push` was executed.
**Scope:** Everything currently documented in the repository about Purchasing/acquisti — canonical, supporting, legacy/archived, and Runtime/Software.
**Method:** Repository-wide keyword search (Purchase, Purchasing, Purchase Document, Purchase Line, Supplier, Supplier Product, Supplier Item, Invoice, Receipt, Credit Note, Surcharge, Discount, Bonus, Ingredient Cost, Food Cost, Invoice Intake, Validation Log, AI classification, supplier code, delivery, ship-to, destination, tax, accounting, bank reconciliation) followed by full or targeted reading of every file returning substantive matches.
**Date:** 2026-08-29
**Note on this audit's own inputs:** this report describes only what is currently written in the repository. It does not use external knowledge and does not use anything said in chat that is not already recorded in a repository file (this includes `01 Domains/Administration/Invoice Intake.md` and `07 Tasks/Reports/TASK_INVOICE_001_REPORT.md`, both created in a prior session turn and now present on disk, which are therefore in scope).

---

## A. Executive Summary

Purchasing-related knowledge exists in the repository in three separate, currently unreconciled layers:

1. **`01 Domains/Restaurant/Purchasing/`** — 16 files. This is the oldest, most complete, and most internally cross-referenced Purchasing documentation in the repository. It defines `Purchase Document`, `Purchase Line`, `Supplier`, `Supplier Product`, `Purchase Order`, `Product`, `Specification`, `Ingredient`, and `Validation Log`, plus business rules, validation levels, AI responsibilities, error handling, acceptance criteria, testing strategy, permissions, configuration, a development roadmap, and integration/data-acquisition semantics. It is explicitly scoped to the Restaurant Domain and to Ingredient/Food-Cost normalization (grams, cost-per-gram). Authoritative for: Purchase Document, Purchase Line, Supplier, Supplier Product, Purchase Order, Ingredient-mapping workflow, within the Restaurant Domain.

2. **`01 Domains/Administration/Invoice Intake.md`** — one file, created most recently (TASK_INVOICE_001). It defines `SupplierInvoice`, `InvoiceLine`, `InvoiceLineClassification`, Supplier Item Memory, `Effective Item Cost`, `InvoiceCharge`, `InvoiceDiscount`, a Tax Treatment open question, `FinancialTransaction` ≠ `SupplierInvoice`, and a future `TransactionAttribution` relationship. It explicitly states (§13) that its relationship to `Purchase Document`/`Purchase Line` is an open, unresolved architectural question. Authoritative for: `SupplierInvoice`, `InvoiceLine`, and the terms listed above, at Administration (transversal) level — but not integrated with the Restaurant-level model in (1).

3. **`01 Domains/Taxation/`** — 9 files (README + 8 concept files), Status "Draft (initial canonical foundation)." Defines transversal tax reasoning concepts (`Taxation`, `TaxJurisdiction`, `TaxObligation`, `TaxPosition`, `TaxTreatment`, `TaxScenario`, `TaxImpact`, `TaxStrategy`, `TaxEvidence`). Contains no purchase-specific, resale-certificate, or sales-tax-on-purchases content. Authoritative for: general tax reasoning vocabulary only.

Beyond these three, `90 Archive/Legacy Repository/X00 Knowledge Repository/06 Business Model/` contains three empty stub files (`Purchase Invoice.md`, `Purchase Line.md`, `Supplier.md` — each is a single title line with no body) that were never developed past being "planned entities" in the legacy Business Model README. They carry no canonical content and are superseded by (1).

`00 Core/` does not define any Purchasing-specific concept; it references "Purchasing" only as an illustrative Domain-example name (see Section B, N.1) and, once, as an example of legitimate Domain-level AI-authority configuration (`00 Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md`).

`03 Software/` contains one working prototype, `03 Software/InvoiceIntake/` (Flask app + OCR/PDF-text extraction + Excel persistence), that implements a reduced subset of (1)'s `Purchase Document`/`Purchase Line` fields. `03 Software/RF-One Data Store/` (the more recent, database-backed Runtime) contains **no** Purchasing/Supplier/Invoice table, model, or migration at all — confirmed by direct search of `DATABASE_SCHEMA.md` and `rfone_data_store/models.py` (zero matches for Purchas/Supplier/Invoice).

No `07 Tasks/TASK_PURCHASING_*` spec or report exists anywhere (active or archived) for the Restaurant/Purchasing module — it predates the current task-spec/report convention (its content was introduced in commit `4cd9856`, "Restaurant domain revision," before `07 Tasks/`/`TASK_CORE_001` existed).

---

## B. Domain Placement

- **Where Purchasing lives today:** `01 Domains/Restaurant/Purchasing/`, listed under `01 Domains/Restaurant/README.md`, "Current Modules" (line: `- Purchasing`) as one of the Restaurant Domain's modules.
- **Declared relationship with Restaurant:** `01 Domains/Restaurant/Purchasing/README.md`, "Purpose" — "The Purchasing Module transforms heterogeneous purchasing information into a single standardized knowledge model for **the Restaurant Domain**." `01 Domains/Restaurant/Model/PurchasingModel.md`, "Domain Overview" — "The Purchasing Module transforms supplier purchasing information into canonical **Restaurant** knowledge."
- **Declared relationship with Administration:** stated only from the Administration side. `01 Domains/Administration/Invoice Intake.md`, §13, "Relationship to Restaurant Purchasing" — states the two models are related but distinct, and that how they reconcile operationally is "an open architectural question, not resolved here." No file inside `01 Domains/Restaurant/Purchasing/` itself states a relationship to Administration, **except** two short cross-reference notes added by TASK_INVOICE_001 to `EntityDefinitions.md` ("Purchase Document," Note (TASK_INVOICE_001)) and `README.md` ("Fundamental Principle," Note (TASK_INVOICE_001)), which point to `Invoice Intake.md` without altering Purchase Document/Purchase Line's own definitions.
- **Declared relationship with Taxation:** none exists inside `01 Domains/Restaurant/Purchasing/`. `01 Domains/Taxation/Taxation.md`, "Cross-Domain examples," names "Restaurant equipment purchase" as an illustrative example of a fact Taxation evaluates tax consequences for, but this is an equipment-purchase example, not a reference to the Purchasing Module or to Purchase Document/Purchase Line. No Taxation file references `Purchasing/`, `Purchase Document`, `Purchase Line`, `Supplier`, or `Supplier Product` by name.
- **Explicit boundaries already stated (Purchasing's own):** `01 Domains/Restaurant/Purchasing/README.md`, "Out of Scope" — "The module does not manage: Inventory, Production, Recipes, Accounting, Payments, Warehouse, Menu Engineering." `BusinessRules.md`, Rule 15 — "No downstream module may alter purchasing history. Recipes, Inventory, Food Cost and Forecasting consume purchasing knowledge but never modify it."
- **Naming ambiguity found while placing Purchasing:** see Section N.1 — some documents outside `01 Domains/Restaurant/` refer to Purchasing as if it were its own Domain rather than a Restaurant module.

---

## C. Purchase Document

**Definition** (`01 Domains/Restaurant/Purchasing/EntityDefinitions.md`, "Purchase Document," "Purpose"): "Represents the official legal and commercial representation of a completed purchase. The Purchase Document is the central business entity of the Purchasing Module." "Identity": "A Purchase Document preserves the commercial information extracted from the supplier's original document. The original supplier document is always preserved and never modified."

**Types/documents supported** (`DataDictionary.md`, "Purchase Document" table, `DocumentType` attribute): "Invoice, Receipt, Credit Note, etc." No document elsewhere defines distinct behavior/semantics for Receipt or Credit Note beyond this enum-style mention (see Section O).

**Header fields already previsti** (`DataDictionary.md`, "Purchase Document"): `PurchaseDocumentId`, `SupplierId`, `PurchaseOrderId` (optional), `DocumentNumber`, `DocumentType`, `IssueDate`, `AcquisitionMethod`, `Currency`, `TotalAmount`, `Status`.

**Source/provenance:** `AcquisitionMethod` field, values per `DataDictionary.md`: "OCR, PDF, API, XML, EDI, Manual" (as a Purchase Document attribute description, not a closed enum list). `01 Domains/Restaurant/Purchasing/README.md`, "Fundamental Principle": "Supported acquisition sources include: Paper invoices, PDF invoices, Electronic invoices, APIs, XML, EDI, Manual data entry. All acquisition sources generate the same logical Purchase Document." `DataAcquisition.md` (file whose own H1 heading is "# API Integration" — see Section N.3), "Supported Sources": "Supplier APIs, XML, EDI, Electronic Invoices, PDF Invoices, Paper Invoices (OCR), Manual Data Entry."

**Delivery / destination semantics:** No dedicated field or entity for delivery/ship-to/destination exists in `EntityDefinitions.md` or `DataDictionary.md` for Purchase Document. "Delivery" appears only as: (a) an example of a document-level charge to be allocated (`BusinessRules.md`, Rule 9 — "Delivery" listed alongside "Fuel Surcharge, Service Fees, Environmental Fees"); (b) "Delivery information" as optional integration output (`DataAcquisition.md`, "Optional Information"); (c) a "Delivery Fee" line item in the worked example (`Examples.md`, Example 5). No document defines a `DeliveryDate`, `ShipTo`, or destination field on Purchase Document itself.

**Invoice/receipt/credit note/API semantics:** Not separately defined beyond the `DocumentType` enum values and the acquisition-source list above. `TestingStrategy.md`, "Business Scenario Tests," lists "Credit note processing" as a named test scenario, but no business rule or workflow document defines what processing a Credit Note actually entails (see Section O).

**Invariants:**
- `BusinessRules.md`, Rule 1 — "Every purchasing event must generate exactly one Purchase Document... The acquisition method is irrelevant."
- `BusinessRules.md`, Rule 2 — "The original supplier document is never modified. Corrections, interpretations and validations are stored separately."
- `BusinessRules.md`, Rule 15 — "Every purchasing calculation originates from the Purchase Document... The Purchase Document Is the Single Source of Truth."
- `AcceptanceCriteria.md`, "Purchase Document" — "Every purchase generates exactly one Purchase Document. Every Purchase Document contains one or more Purchase Lines. Original supplier information is preserved."

---

## D. Purchase Line

**Definition** (`EntityDefinitions.md`, "Purchase Line," "Purpose"): "Represents one purchased item contained within a Purchase Document." "Identity": "Each Purchase Line references exactly one Supplier Product. The supplier description is preserved exactly as received."

**Fields** (`DataDictionary.md`, "Purchase Line"): `PurchaseLineId`, `PurchaseDocumentId`, `SupplierProductId`, `SupplierDescription`, `Quantity`, `PurchaseUnit`, `UnitPrice`, `LineAmount`, `NormalizedQuantity`, `CostPerGram`, `RealIngredientCost` ("Cost after allocation of document-level charges"), `EffectiveCost` ("Cost after temporary discounts").

**Quantity/unit/price semantics:** `DataDictionary.md`, "Attribute Principles" — "Quantities are normalized into grams." `BusinessRules.md`, Rule 7 — "Every purchasable Ingredient is internally represented using grams. Commercial purchasing units are preserved only as supplier information." Original `Quantity`/`PurchaseUnit`/`UnitPrice`/`LineAmount` are supplier-verbatim; `NormalizedQuantity` is the derived gram value.

**Item/product/ingredient relationship:** `BusinessRules.md`, Rule 3 — "Each Purchase Line must reference exactly one Supplier Product. Supplier terminology is always preserved." Rule 4 — "Every Supplier Product must eventually be mapped to exactly one Ingredient. A newly acquired Supplier Product may temporarily remain unmapped until validation is completed." Rule 6 — "An Ingredient is uniquely identified by: one Product; zero or more Specifications."

**SupplierProduct relationship:** One Purchase Line → exactly one Supplier Product (`EntityDefinitions.md`, "Purchase Line," "Identity"; `BusinessRules.md`, Rule 3). One Supplier Product → exactly one Supplier, optionally one Ingredient (`EntityDefinitions.md`, "Supplier Product": "A Supplier Product may exist before being associated with an Ingredient"). Many Supplier Products may reference the same Ingredient (`BusinessRules.md`, Rule 4 — "Many Supplier Products may reference the same Ingredient").

**Surcharge/discount/service/freight/fuel semantics:** Not modeled as Purchase Line attributes. They are modeled only as **document-level** costs, per `BusinessRules.md`, Rule 9 — "Document-Level Costs Are Allocated. Costs that do not belong to individual Purchase Lines are proportionally allocated across all purchased products. Examples include: Delivery, Fuel Surcharge, Service Fees, Environmental Fees. The allocation becomes part of the Real Ingredient Cost." Rule 10 — "Temporary Discounts Remain Independent. Temporary commercial discounts affect Food Cost. They do not modify historical purchasing knowledge." No dedicated entity (e.g. a "Purchase Charge" or "Purchase Discount" entity analogous to Administration's `InvoiceCharge`/`InvoiceDiscount`) exists in `EntityDefinitions.md` or `DataDictionary.md`; the allocation is described as a rule/behavior, not as a modeled entity with its own fields.

**Nullable/non-nullable assumptions:** `DataDictionary.md` marks `SupplierProduct.IngredientId` explicitly as "Referenced Ingredient (**optional until validated**)." `EntityDefinitions.md`, "Purchase Order," "Identity" — "One Purchase Order may generate: one Purchase Document; multiple Purchase Documents; partial deliveries" (implying `PurchaseLine.PurchaseOrderId`-type traceability is not 1:1, though no such field is listed in `DataDictionary.md`'s Purchase Line table at all — `PurchaseOrderId` appears only on Purchase Document, marked "optional"). No other field is explicitly marked nullable/non-nullable in `DataDictionary.md`; all other attributes are listed without a nullability annotation.

**Contradictions found between documents:** see Section N.2 (surcharge allocation scope: "all purchased products" vs. "eligible lines") and N.4 (cost-terminology divergence: `RealIngredientCost`/`EffectiveCost` vs. `Effective Item Cost`).

---

## E. Supplier

**Definition** (`EntityDefinitions.md`, "Supplier," "Purpose"): "Represents a commercial organization that supplies products to the restaurant." "Identity": "A Supplier maintains its identity independently of: products sold; Purchase Documents issued; acquisition methods."

**Supplier identity fields** (`DataDictionary.md`, "Supplier"): `SupplierId`, `Name`, `Status` (Active/Inactive), `AcquisitionMethods` (supported acquisition methods for that Supplier), `Notes`.

**Supplier code / item code:** Modeled at the Supplier Product level, not directly on Supplier. `DataDictionary.md`, "Supplier Product": `SupplierCode` ("Supplier product code"), `SupplierName` ("Original supplier description"). No standalone "Supplier Item Code" field name is used in the Restaurant/Purchasing documents (Administration's `Invoice Intake.md` uses "supplier item code" terminology instead — see Section J).

**Supplier Product:** `EntityDefinitions.md`, "Supplier Product," "Purpose" — "Represents the commercial product defined by one specific Supplier." "Identity" — "Supplier Products belong exclusively to one Supplier. Different Suppliers may define different Supplier Products that represent the same Ingredient. A Supplier Product may exist before being associated with an Ingredient."

**Relationship Supplier + Product/Ingredient:** `BusinessRules.md`, Rule 5 — "Ingredients Are Supplier Independent. Ingredients belong to the Restaurant Domain. Suppliers never define Ingredients. Supplier Products only reference existing Ingredients."

**Historical memory / mapping rules already present:** `Workflow.md` (whose entire content is "Step 5 – Ingredient Mapping" — see Section N.5/O) — "Every Supplier Product must eventually reference one Ingredient. If a mapping already exists, it is reused. Otherwise: AI may suggest one or more Ingredients. A human validates the final mapping. Approved mappings become part of the Restaurant Knowledge Base." `AcceptanceCriteria.md`, "Supplier Product" — "Unknown Supplier Products are created automatically. Existing Supplier Products are reused." This is a reuse-by-key mechanism (implicitly keyed on `SupplierId` + `SupplierCode`) but is stated more briefly than the equivalent mechanism in `01 Domains/Administration/Invoice Intake.md`, §5 ("Supplier Item Memory"), which explicitly names the `(Supplier, Supplier Item Code)` recognition key and describes an AI-propose/human-confirm/override cycle with memory versioning. No Restaurant/Purchasing document uses the phrase "Supplier Item Memory."

---

## F. Product / Ingredient Classification

**How a purchased product is classified today (Restaurant/Purchasing):** through the chain `Supplier Product → (manual mapping) → Ingredient`, where `Ingredient = Product + zero or more Specifications` (`BusinessRules.md`, Rule 6; `EntityDefinitions.md`, "Ingredient," "Identity"). `Model/Product.md`, "Business Meaning" — a Product is "the generic food concept" (e.g. Tomato, Olive Oil); `Model/Specification.md` — a Specification "transforms a generic Product into a specific Ingredient" (e.g. "PDO," "24 Months," "San Marzano").

**Relationship with Ingredient:** `Model/Product.md`, "Relationships" — "Product ↓ Specifications ↓ Ingredient ↓ Supplier Product" (a Product may generate many Ingredients; a Supplier Product references an Ingredient, not a Product directly). `Model/PurchasingModel.md`, "Business Flow" — "Supplier → Purchase Order → Purchase Document → Purchase Line → Supplier Product → Ingredient → Recipe / Inventory / Food Cost."

**Relationship with food/drink/supplies or equivalent:** No such economic-category classification exists anywhere in `01 Domains/Restaurant/Purchasing/` or `01 Domains/Restaurant/Model/`. The Product/Specification/Ingredient chain classifies by **culinary identity** only (what the ingredient *is*, e.g. "Tomato/San Marzano/Italian"), not by an economic category such as Food/Drink/Supplies. The only place a Food/Drink/Supplies-style classification exists is `01 Domains/Administration/Invoice Intake.md`, §4 ("Supplier Source Semantics vs. RF-One Classification") under the name `InvoiceLineClassification`. No document states how, or whether, `InvoiceLineClassification` and the Restaurant Product/Ingredient classification relate to or depend on each other (see Section O).

**What happens if the product is not known:**
- `BusinessRules.md`, Rule 4 — "A newly acquired Supplier Product may temporarily remain unmapped until validation is completed."
- `ValidationRules.md`, "Warning" level — "Unknown Supplier Product," "Missing mapping" are Warning-level anomalies ("The Purchase Document can be processed but requires attention").
- `ErrorHandling.md`, "Mapping Errors" — examples "Unknown Supplier Product," "Multiple possible Ingredients," "No matching Ingredient"; behavior: "Create a new Supplier Product if necessary. Request manual Ingredient mapping. Preserve purchasing workflow."
- `AcceptanceCriteria.md`, "Supplier Product" — "Unknown Supplier Products are created automatically. Existing Supplier Products are reused. Manual Ingredient mapping is required before business use."
- No document states what happens to Ingredient-dependent downstream calculations (Food Cost, Recipe costing) while a Supplier Product remains unmapped, beyond "Manual Ingredient mapping is required before business use" (i.e., unmapped items are implicitly excluded from those calculations, but this is not stated as an explicit rule).

---

## G. AI / Validation / Learning

**What is documented about AI use (Restaurant/Purchasing):**
- `AIResponsibilities.md`, "AI Responsibilities" — "AI may: Read purchasing documents. Extract structured data. Recognize Supplier Products. Suggest Ingredient mappings. Normalize quantities. Calculate normalized costs. Detect anomalies. Estimate confidence levels. Prioritize validations. Learn from approved human decisions."
- Same file, "AI Limitations" — "AI must never: Modify the original supplier document. Create or approve a new Ingredient autonomously. Validate a new Supplier Product mapping. Rewrite purchasing history. Delete business information. Close Validation Log entries. Perform irreversible business decisions."
- Same file, "Decision Authority" — AI may decide automatically only when "The confidence level satisfies the configured threshold... No business knowledge is required... The decision is reversible" (examples: OCR extraction, unit conversion, cost normalization). Human validation is always required for "New Ingredient creation, New Supplier Product mapping, Business exceptions, Data conflicts, Ambiguous interpretations."

**When AI proposes vs. when human confirmation is required:**
- `Purchasing/README.md`, "Ingredient Mapping" — "Supplier Products are manually associated with Ingredients by an authorized user. AI may propose mappings but never validates them autonomously."
- `ValidationRules.md`, "AI Validation" / "Human Validation" — AI "may Detect anomalies, Estimate confidence, Suggest corrections, Propose Ingredient mappings" but "never: Modify supplier documents, Confirm a correction, Validate an Ingredient mapping, Close a Validation Log entry." A human "may Accept AI suggestions, Reject AI suggestions, Correct extracted values, Create new Ingredient mappings, Close Validation Log entries."

**Validation Log / unresolved mappings:**
- `EntityDefinitions.md`, "Validation Log," "Purpose" — "Represents every anomaly detected during acquisition, normalization or validation." "Responsibilities" — "Preserve traceability. Record anomalies. Support human validation."
- `DataDictionary.md`, "Validation Log" fields: `ValidationId`, `PurchaseDocumentId`, `PurchaseLineId` (optional), `Severity`, `Message`, `SuggestedAction`, `HumanDecision`, `Status` (Open, Approved, Rejected, Closed), `Timestamp`.
- `ValidationRules.md`, "Validation Levels" — Informational / Warning / Error, each with examples; "Errors never invalidate the original supplier document. They only stop automatic processing until validated."
- `ValidationRules.md`, "Validation Workflow" — "1. Acquire Purchase Document. 2. Detect anomalies. 3. Create Validation Log entries. 4. Continue automatic processing whenever possible. 5. Request human validation when required. 6. Record every decision." "Validation history is never deleted."

**What is learned/persisted:**
- `AIResponsibilities.md`, "Continuous Learning" — "AI improves by observing validated human decisions. Learning may include: OCR improvements, Product recognition, Ingredient mapping suggestions, Packaging recognition. Learning never changes historical business data."
- `AIResponsibilities.md`, "Explainability" — "Every AI suggestion should be explainable... Confidence score, Supporting evidence, Reason for the suggestion, Alternative candidates."
- Administration-level equivalent, not phrased identically: `01 Domains/Administration/Invoice Intake.md`, §5 ("Supplier Item Memory") — describes a `(Supplier, Supplier Item Code)`-keyed classification memory with explicit "AI proposes → human confirms → becomes reusable classification memory" and override semantics ("a human may still override; the override updates memory going forward and never rewrites the historical InvoiceLines already recorded under the prior classification"). This override/versioning detail is not present in the Restaurant/Purchasing AI-learning documents.

---

## H. Charges / Surcharges / Discounts / Bonuses

**How represented today (Restaurant/Purchasing):**
- `BusinessRules.md`, Rule 9 ("Document-Level Costs Are Allocated") — Delivery, Fuel Surcharge, Service Fees, Environmental Fees are **document-level costs**, not Purchase Lines, "proportionally allocated across all purchased products." "The allocation becomes part of the Real Ingredient Cost."
- `BusinessRules.md`, Rule 10 ("Temporary Discounts Remain Independent") — "Temporary commercial discounts affect Food Cost. They do not modify historical purchasing knowledge. Supplier evaluation is based on Real Ingredient Cost rather than temporary promotions."
- `DataAcquisition.md`, "Optional Information" — lists "Discounts," "Surcharges," "Credit Notes" as optional integration-provided information, alongside "Taxes" and "Delivery information," stating they "enrich the Purchase Document but never change its structure."
- `Examples.md`, Example 5 — a worked example with a "Delivery Fee: €10.00" that is "proportionally allocated," feeding into "Real Ingredient Cost."
- `TestingStrategy.md`, "Business Scenario Tests" — names "Fuel surcharge allocation" and "Credit note processing" as test scenarios (no corresponding business-rule detail beyond Rule 9's general allocation formula-in-words).
- **No "Bonus" concept appears anywhere in `01 Domains/Restaurant/Purchasing/`.** The keyword "Bonus" was not found in any file under that path.

**Are they modeled as a Purchase Line?** No. They are explicitly document-level (Rule 9), not Purchase Line attributes — no `PurchaseChargeId`/`PurchaseDiscountId`-type entity exists in `EntityDefinitions.md` or `DataDictionary.md`.

**Do they require a Supplier Product?** No — they are described as affecting the allocation across existing Purchase Lines/Supplier Products, not as themselves referencing a Supplier Product.

**Do they have or lack classification?** No classification (e.g. into Food/Drink/Supplies, or into a charge-type taxonomy) is documented for these document-level costs anywhere in Restaurant/Purchasing. `Administration/Invoice Intake.md`, §7 introduces a `charge type / source label` field on `InvoiceCharge`, which does not exist in the Restaurant/Purchasing documents.

**How they influence cost:** Rule 9 — surcharges become part of "Real Ingredient Cost." Rule 10 — discounts affect "Food Cost" but not "historical purchasing knowledge," and are explicitly excluded from Supplier evaluation ("Supplier evaluation is based on Real Ingredient Cost rather than temporary promotions").

**Existing allocation rule:** Rule 9's stated rule is a proportional allocation "across all purchased products," described only in words — no formula is written in any Restaurant/Purchasing file (contrast with `Administration/Invoice Intake.md`, §7, which states an explicit `allocation share = line base amount / total eligible base amount` formula).

**Textual incoherences found across files (see also Section N for full citations):**
- Rule 9's "across all purchased products" (unconditional) vs. `Invoice Intake.md` §7's "eligible lines" (a possibly narrower, recorded subset) — Section N.2.
- `DataDictionary.md`'s two-stage cost fields `RealIngredientCost` (post-surcharge) / `EffectiveCost` (post-discount) vs. `Invoice Intake.md`'s single-formula `Effective Item Cost` (surcharge + discount + conditional tax computed together) — Section N.4.
- Rule 10 states discounts "affect Food Cost" (a downstream, Restaurant-specific concept) while Rule 9 states surcharges become part of "Real Ingredient Cost" (a Purchase Line field) — the two rules describe the discount and surcharge effects landing on two different named cost concepts (Food Cost vs. Real Ingredient Cost) rather than symmetrically on the same one; no document reconciles whether this asymmetry is intentional.

---

## I. Cost Semantics

**Base cost:** Restaurant/Purchasing — `UnitPrice` / `LineAmount` (`DataDictionary.md`, "Purchase Line"), described as "Supplier unit price" / "Original line amount." Administration — `Base Line Amount` (`Invoice Intake.md`, §6, referencing `InvoiceLine.line_amount`).

**Effective cost:** Restaurant/Purchasing — `EffectiveCost`, "Cost after temporary discounts" (`DataDictionary.md`). Administration — `Effective Item Cost = Base Line Amount + allocated surcharges − allocated discounts + applicable tax (conditionally)` (`Invoice Intake.md`, §6).

**Ingredient cost:** `RealIngredientCost`, "Cost after allocation of document-level charges" (`DataDictionary.md`, "Purchase Line"); also referenced as a named cost measure in `BusinessRules.md`, Rule 8 ("Ingredient Cost Is Standardized... The Purchasing Module calculates: Supplier Price, Real Ingredient Cost, Effective Cost. The standardized cost is always expressed as cost per gram") and Rule 9.

**Food cost:** Referenced as a downstream concept affected by discounts (`BusinessRules.md`, Rule 10) and appears in the Restaurant Domain scope list (`Restaurant/README.md`, "Scope" — "Food Cost") and Roadmap (`Restaurant/Roadmap.md`, "Not yet modeled" — "Food Cost, Forecasting... listed in README.md scope as future capabilities; no canonical content yet"). No dedicated `Food Cost.md` file exists; Food Cost is referenced but not itself canonically defined anywhere found in this audit.

**Landed cost:** The term "landed cost" was not found anywhere in the repository under any of the paths searched. The closest documented equivalent concepts are `Real Ingredient Cost` (Restaurant/Purchasing) and `Effective Item Cost` (Administration/Invoice Intake).

**Surcharge/discount treatment:** See Section H.

**What is persisted vs. derived:**
- Restaurant/Purchasing does not state a general "persist facts, derive calculations" principle in those words. It states related but narrower principles: `DataDictionary.md`, "Attribute Principles" — "Historical values are never overwritten. Temporary commercial events never modify historical purchasing data." `BusinessRules.md`, Rule 11 — "Purchasing History Is Permanent... Historical purchasing information is never overwritten." However, `DataDictionary.md` lists `RealIngredientCost`, `EffectiveCost`, `NormalizedQuantity`, and `CostPerGram` directly as **Purchase Line attributes** (i.e., as if stored/persisted fields on the entity), without stating whether they are computed-on-write, computed-on-read, or literally persisted columns.
- Administration/Invoice Intake explicitly states the principle in those words: `Invoice Intake.md`, §12 ("Persistence Invariant") — "Persist source facts, events, confirmed decisions, and evidence. Derive calculations," and explicitly lists `Effective Item Cost`, allocated surcharge/discount shares, and category totals as "Never persisted as canonical truth when recalculable." This mirrors the same invariant already stated in `01 Domains/Administration/Personnel Cost.md`, §8.
- **This is a difference in explicitness, not a stated contradiction**: Restaurant/Purchasing's `DataDictionary.md` does not say whether `RealIngredientCost`/`EffectiveCost` are canonical stored values or derived-on-demand values, whereas Administration/Invoice Intake explicitly says its analogous field (`Effective Item Cost`) is never canonical stored truth. No document reconciles the two.

---

## J. Invoice Intake

**What is already documented:** `01 Domains/Administration/Invoice Intake.md` (single file, Version 1.0, Status "Approved (initial foundation — TASK_INVOICE_001)"). Also `03 Software/InvoiceIntake/` (a working prototype) and `03 Software/InvoiceIntake/README.md` (Italian-language description of the prototype).

**Is it a Domain, capability, source adapter, or other?** `Invoice Intake.md` states its own placement explicitly: "**Module:** Administration Domain / Invoice Intake" and "Invoice Intake is documented at Administration level... a foundation module for what `01 Domains/Administration/README.md` already anticipates as a possible future **Accounts Payable** sibling module." `01 Domains/Administration/README.md`'s module map lists it as a sibling module to Payroll: `Administration ├── Personnel Cost ├── Payroll └── Invoice Intake`. It is documented as a Domain module, not as a Product, Software capability, or source adapter — though it also functions conceptually as the description of a source-ingestion process (§1, "Invoice Intake Sources").

**PDF / OCR / IMAP / API / XML / EDI citation status:**
- `Invoice Intake.md`, §1 — "Today: PDF upload (see `03 Software/InvoiceIntake/`, current prototype). Future: IMAP mailbox... Supplier API/token-based integration... other structured sources (EDI, XML, portal export)." XML and EDI are named only inside the parenthetical "other structured sources," not individually elaborated.
- `03 Software/InvoiceIntake/README.md` — describes only PDF/photo upload with OCR (Tesseract) or direct PDF-text extraction; no IMAP/API/XML/EDI code exists (confirmed by reading `app.py`, `parser.py`, `ocr_engine.py`, `excel_store.py` — none reference IMAP, an external API, XML, or EDI).
- By contrast, `01 Domains/Restaurant/Purchasing/DataAcquisition.md`, "Supported Sources," already names all of "Supplier APIs, XML, EDI, Electronic Invoices, PDF Invoices, Paper Invoices (OCR), Manual Data Entry" as sources the Purchasing Module (conceptually) supports — with none of them implemented in `03 Software/` either, per the same code inspection above.

**Relation with Purchase Document/Purchase Line:** Stated only from the Administration side, as an explicitly open question — `Invoice Intake.md`, §13: "This document does not redefine, restructure or replace Purchase Document/Purchase Line... **Open architectural question, not resolved here:** how the two ingestion paths relate operationally... is not decided by this document." No Restaurant/Purchasing document states a reciprocal position beyond the two short cross-reference notes described in Section B.

**Current conceptual overlap:** Both models represent "a supplier's commercial document and its line items," both state the original document is preserved unmodified, both describe an AI-propose/human-confirm mapping-or-classification cycle, and both describe a document-level-charge proportional-allocation mechanism — using different entity names (`Purchase Document`/`Purchase Line` vs. `SupplierInvoice`/`InvoiceLine`) and, in places, different field names and allocation-scope wording (Section N.2, N.4). No document declares one as authoritative over the other, as a specialization of the other, or as scheduled for merger/deprecation.

---

## K. Taxation / Accounting Boundary

**What Purchasing already knows about tax:** Very little. `DataDictionary.md` does not list a tax field on Purchase Document or Purchase Line at all. `DataAcquisition.md`, "Optional Information," lists "Taxes" as one of several optional integration outputs, with no further elaboration. No Restaurant/Purchasing file mentions "resale," "exemption," "sales tax," "deductible," or "recoverable."

**What Administration/Invoice Intake adds:** `Invoice Intake.md`, §9 ("Tax Treatment — Open Question") states atomic tax facts to preserve (tax amount, source label/type, jurisdiction, source evidence, invoice/line level) and explicitly declines to assume tax is always/never part of `Effective Item Cost` or always/never recoverable — see the mirrored entry in `OpenQuestions.md`, "Invoice Tax Treatment — OPEN."

**What is demanded to Taxation:** `Invoice Intake.md`, §9 — "This question is expected to be resolved once the Taxation Domain... or a jurisdiction rule pack establishes the applicable treatment for these suppliers/purchase categories." However, **the Taxation Domain, as currently documented, contains no purchase-specific, resale-certificate, or sales-tax-on-purchase-transactions content.** A targeted search of all 9 Taxation files for "purchas," "resale," "sales tax," and "Florida" returned only two incidental hits: `TaxScenario.md` line 25 (an illustrative aside, "make the purchase this fiscal period" versus "make it next period") and `Taxation.md`/`README.md`'s "Restaurant equipment purchase" cross-domain example. Neither addresses purchase-side sales/use tax, resale exemption, or deductibility of a supplier invoice.

**What is demanded to Accounting:** `01 Domains/Restaurant/Purchasing/README.md`, "Out of Scope," lists "Accounting" as excluded from the Purchasing Module. `01 Domains/Administration/README.md` states "Administration ≠ Accounting" ("Accounting records, classifies and reports financial transactions in a ledger. Administration produces the economic facts... that Accounting, where it exists, would post — it does not maintain a ledger or produce financial statements itself"). `01 Domains/Taxation/README.md` states "Taxation ≠ Accounting" in near-identical terms. **No Accounting Domain, module, or file exists anywhere in the repository** — it is referenced only as an exclusion/boundary by three different documents (Restaurant/Purchasing, Administration, Taxation), never as something itself documented.

**Deductible/tax/resale semantics if already present:** None beyond the provisional, explicitly-unresolved rule already quoted in Section I/J: "Tax enters Effective Item Cost only when the applicable rule layer establishes that it is economically borne by the business" (`Invoice Intake.md`, §9; `OpenQuestions.md`).

**What is NOT defined (flagged, not solved):** purchase-side sales/use tax treatment for any of the three named suppliers or for Florida specifically; resale/exemption certificate semantics; whether/how a Purchasing-side tax field would map onto `Taxation`'s `TaxObligation`/`TaxTreatment`/`TaxPosition` concepts; any Accounting Domain content at all.

---

## L. Bank / Payment / Reconciliation Boundary

**`FinancialTransaction`:** Exists only as a named concept in `01 Domains/Administration/Invoice Intake.md`, §10 ("Bank / Invoice Boundary") — "`FinancialTransaction ≠ SupplierInvoice`... A bank debit is a settlement/reconciliation fact, never the source of line-level economic detail." No schema, field list, or entity definition for `FinancialTransaction` exists anywhere (§10 itself states "No bank-matching engine is designed or implemented by this document").

**Payment:** Not modeled as an entity in Restaurant/Purchasing (`Purchasing/README.md`, "Out of Scope," explicitly excludes "Payments"). Referenced only as a future field in `Invoice Intake.md`, §2 ("payment terms" as a `SupplierInvoice` attribute, when disclosed).

**Settlement:** Mentioned only in `01 Domains/Administration/Payroll/Payroll Provider Result.md` (payroll context, not purchasing): "the bank transaction is a settlement/reconciliation source, never the source of employee-level payroll detail. A deep bank reconciliation engine is not implemented by this task; this is documented as the next integration point." `Invoice Intake.md`, §10, explicitly cites and reuses this same sentence/boundary for the purchasing/invoice case.

**Bank matching / invoice-payment matching:** No implementation, schema, or detailed conceptual model exists. `Invoice Intake.md`, §11 ("Future Transaction Attribution") describes only a future conceptual flow (`SupplierInvoice → InvoiceLines → RF-One classifications → category totals derived → TransactionAttribution`) with one worked numeric example, explicitly stating "No `TransactionAttribution` schema, matching algorithm, or persistence model is defined by this document."

**Explicit confirmation that this does not exist:** Confirmed — no `FinancialTransaction`, payment, settlement, or bank-matching table/model exists in `03 Software/RF-One Data Store/` (search of `DATABASE_SCHEMA.md` and `models.py` for these terms and for Purchas/Supplier/Invoice returned no matches). The only Runtime code that touches a bank-adjacent concept is Payroll's direct-deposit discussion in `Payroll Provider Result.md`, which is documentation, not a bank-integration implementation either.

---

## M. Runtime / Software Status

**`03 Software/InvoiceIntake/` (prototype, implemented):**
- `app.py` — Flask app with two routes (`/upload`, `/save`). Accepts `.jpg/.jpeg/.png/.pdf/.webp/.bmp/.tiff`.
- `ocr_engine.py` — for PDFs, tries `pdfplumber` text-layer extraction first (`method = "PDF-Text"`), falls back to rendering pages and running Tesseract OCR (`method = "OCR"`) if no usable text layer or `pdfplumber` unavailable; for images, always Tesseract OCR (`method = "OCR"`).
- `parser.py` — regex/heuristic extraction of header fields (`supplier_name`, `document_number`, `issue_date`, `currency`, `total_amount`) and candidate line items (`description`, `quantity`, `unit_price`, `line_amount`). Docstring: "This is intentionally simple (regex-based, no ML)... Every field it produces is shown in an editable review form before anything is saved."
- `excel_store.py` — persists to `data/PurchaseDocuments.xlsx`, two sheets. Implemented columns:
  - `PurchaseDocuments` sheet: `PurchaseDocumentId, SupplierName, DocumentNumber, DocumentType, IssueDate, AcquisitionMethod, Currency, TotalAmount, Status, SourceFile, CreatedAt`.
  - `PurchaseLines` sheet: `PurchaseLineId, PurchaseDocumentId, SupplierDescription, Quantity, PurchaseUnit, UnitPrice, LineAmount, NormalizedQuantity, CostPerGram`.
  - Module docstring states explicitly: "Cost-normalization columns (NormalizedQuantity, CostPerGram, etc.) are left as empty headers, ready for a later step" — confirmed by `save_purchase_document()`'s line-append code, which always writes `""` for both columns.
- Fields defined in `DataDictionary.md` but **not present** in the implemented Excel schema: `SupplierId` (only `SupplierName`, a string, is stored — no Supplier entity/table exists), `PurchaseOrderId`, `SupplierProductId` (only free-text `SupplierDescription` is stored — no Supplier Product entity/table exists), `RealIngredientCost`, `EffectiveCost`. No `Validation Log` is implemented (no anomaly/severity/status records are written anywhere in this codebase).
- `AcquisitionMethod` values actually produced by the code (`"PDF-Text"`, `"OCR"`) do not exactly match the value name `"PDF"` used in `DataDictionary.md`'s description of the same field ("OCR, PDF, API, XML, EDI, Manual").
- `03 Software/InvoiceIntake/README.md`, "Limiti noti di questo prototipo" (Italian) — states explicitly: "Non fa ancora normalizzazione in grammi/costo per grammo né mapping automatico verso gli Ingredienti... Un solo utente alla volta (nessuna gestione concorrenza sul file Excel)."

**`03 Software/RF-One Data Store/` (the current database-backed Runtime):**
- Direct search of `DATABASE_SCHEMA.md` and `rfone_data_store/models.py` for "Purchas," "Supplier," and "Invoice" returned **zero matches**. This Runtime implements Restaurant Profile, Organization (Operational Area/Physical Area/Restaurant Role/Employee Assignment), Tips, Payroll, and Clover ingestion — no Purchasing/Supplier/Invoice table, ORM model, or migration exists there.

**`03 Software/Clover Data Explorer/`:** POS/sales-side data (orders, payments, employees, tips, categories, modifiers). Not a purchasing/supplier-invoice data source; incidental keyword matches found during the repository-wide search (e.g. "tax" as Clover's sales tax rate on orders, "discount" as a Clover order-level discount) are sell-side concepts unrelated to supplier purchasing and were not reviewed further as out of this audit's scope.

**Summary — documented vs. implemented:**
- Documented only, not implemented anywhere: `Purchase Order`, `Validation Log` (as a stored/queryable entity), `Supplier` and `Supplier Product` as first-class stored entities, `RealIngredientCost`/`EffectiveCost` as computed values, any tax field, any IMAP/API/XML/EDI acquisition path, `FinancialTransaction`, bank matching, `TransactionAttribution`, `InvoiceCharge`/`InvoiceDiscount` as modeled entities.
- Documented and partially implemented: `Purchase Document`/`Purchase Line` (reduced field set, Excel-backed, single-user, no concurrency handling).
- Implemented but not yet fed into the documented Ingredient-costing chain: OCR/PDF-text extraction and header/line heuristic parsing.

---

## N. Contradictions / Ambiguities

**N.1 — Whether Purchasing is a Domain or a Module.**
- File A: `CLAUDE.md` (both copies, `C:\Users\servi\OneDrive\AI-RF-ONE\CLAUDE.md` and this repository's own `CLAUDE.md`), section "What RF-One Is" — "Application Domains use only the Core concepts they require. Examples: ... Restaurant, Purchasing, Sales, Workforce, Selection, Training, Personal Decision." Also `00 Core/ConceptualArchitecture/00_RF-One_Core_Vision.md`, §1 — "**Domain** applies and, where necessary, specializes Core concepts for a specific field (e.g. Restaurant, Purchasing, Sales, Workforce)." Also `00 Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md` — "the human-approval requirements retained in **the Restaurant Purchasing Domain**."
- File B: `01 Domains/Restaurant/README.md`, "Current Modules" — lists "Purchasing" as one of the Restaurant Domain's modules, not as a sibling Domain. `01 Domains/Restaurant/Purchasing/README.md`'s own title and body consistently say "Purchasing Module."
- Conflict: three documents (CLAUDE.md ×2, and two Core documents) use Purchasing as an example on the same list as "Restaurant" itself (implying peer status as a Domain), while the actual canonical Domain-layer documents place Purchasing inside the Restaurant Domain as a module. Not resolved anywhere.

**N.2 — Surcharge/discount allocation scope: "all purchased products" vs. "eligible lines."**
- File A: `01 Domains/Restaurant/Purchasing/BusinessRules.md`, "Rule 9 – Document-Level Costs Are Allocated" — "Costs that do not belong to individual Purchase Lines are proportionally allocated **across all purchased products**."
- File B: `01 Domains/Administration/Invoice Intake.md`, §7 ("Invoice-level Surcharges") — defines `InvoiceCharge.applicable scope / eligible lines` and states "Eligible lines default to all merchandise lines on the invoice **unless** the source or a confirmed rule establishes a narrower scope."
- Conflict: Rule 9 states the allocation base is unconditionally "all purchased products"; `Invoice Intake.md` §7 allows for a recorded, narrower-than-all eligible subset. Not resolved between the two documents.

**N.3 — `DataAcquisition.md` filename does not match its own document title.**
- File: `01 Domains/Restaurant/Purchasing/DataAcquisition.md` — its content begins with the heading `# API Integration`, not "Data Acquisition." The filename on disk and the document's own declared title differ.

**N.4 — Two different, non-identical cost-terminology sets describe an overlapping idea.**
- File A: `01 Domains/Restaurant/Purchasing/DataDictionary.md`, "Purchase Line" — `RealIngredientCost` ("Cost after allocation of document-level charges"), `EffectiveCost` ("Cost after temporary discounts"), two sequential named fields. Also `BusinessRules.md`, Rule 8 ("Supplier Price, Real Ingredient Cost, Effective Cost").
- File B: `01 Domains/Administration/Invoice Intake.md`, §6 — a single `Effective Item Cost = Base Line Amount + allocated surcharges − allocated discounts + applicable tax (conditionally)` formula.
- Conflict/ambiguity: neither document states whether `RealIngredientCost`/`EffectiveCost` (Restaurant/Purchasing) and `Effective Item Cost` (Administration) are meant to be the same value, sequential stages of the same value, or genuinely different values. Not resolved.

**N.5 — `Workflow.md` is titled as a general workflow document but contains only one step.**
- File: `01 Domains/Restaurant/Purchasing/Workflow.md` — entire content is a single section, "# Step 5 – Ingredient Mapping." No Steps 1–4 exist in this file or, under those step numbers, in any other Purchasing file. (Related process content exists narratively elsewhere — e.g. `ValidationRules.md`, "Validation Workflow," a differently-numbered 6-step list — but nothing in the repository presents "Steps 1–4" that `Workflow.md`'s own "Step 5" heading implies should exist.)

**N.6 — `01 Domains/Taxation/README.md` cites a task file that does not exist in the repository.**
- File A: `01 Domains/Taxation/README.md`, "Related documents" — "`../../07 Tasks/TASK_TAXATION_001_Create_RF_One_Taxation_Domain.md` — task that created this Domain."
- File B: repository-wide search (this audit) confirms no file matching `TASK_TAXATION*` exists anywhere in `07 Tasks/`, `90 Archive/`, or git history. This restates, without resolving, the same gap already recorded in `07 Tasks/Reports/PRE_COMMIT_AUDIT.md`, Section D.3 ("Taxation Domain: no task provenance found"). Included here because the Taxation Domain is the domain Invoice Intake's Tax Treatment open question names as its expected resolver (Section K).

**N.7 — Rule 9 and Rule 10 route surcharges and discounts to two differently-named cost concepts.**
- File: `01 Domains/Restaurant/Purchasing/BusinessRules.md` — Rule 9: surcharges become part of "**Real Ingredient Cost**." Rule 10: discounts "affect **Food Cost**." No document states whether this is an intentional asymmetry (i.e., discounts genuinely act on a different, later-stage cost concept than surcharges) or an inconsistency in terminology.

---

## O. Missing / Undefined

Only what current documents do not clearly define — no proposed resolutions.

- No standalone `Supplier.md` file exists in the current canonical Restaurant/Purchasing documentation; `Supplier` is defined only inline inside `EntityDefinitions.md` and `DataDictionary.md` (already noted in `09 Strategy/04_Business_Capability_Coverage.md`, row KD-010).
- `Workflow.md` documents only "Step 5 – Ingredient Mapping"; Steps 1–4 of whatever numbered workflow this belongs to are not defined under that numbering anywhere in the repository (Section N.5).
- No business rule, workflow, or field-level semantics define what distinguishes a "Receipt" or "Credit Note" from an "Invoice" beyond `DataDictionary.md`'s `DocumentType` enum-style mention and one named test scenario ("Credit note processing" in `TestingStrategy.md`). Sign handling, matching to an originating document, and any special validation for a Credit Note are undefined.
- No document defines the long-lived consequence of a Supplier Product that remains permanently unmapped to an Ingredient (only the transitional "temporarily remain unmapped until validation is completed" state is defined — `BusinessRules.md`, Rule 4).
- No document defines the relationship (if any) between the Restaurant/Purchasing Product→Specification→Ingredient culinary-identity classification and the Administration/Invoice-Intake `InvoiceLineClassification` (Food/Drink/Supplies) economic classification — whether one depends on the other, whether they are assigned independently, or whether they must ever agree.
- No document defines delivery/ship-to/destination as a modeled concept with its own fields (header-level vs. line-level, single vs. multiple per document) — it is mentioned only as an example charge (Rule 9), an optional integration output (`DataAcquisition.md`), a line item in a worked example (`Examples.md`), and, in `Invoice Intake.md` §2, as two unelaborated `SupplierInvoice` fields (`delivery date`, `ship-to / delivery location`).
- No business rule or data-dictionary field documents how a Purchase Order's "partial deliveries" (asserted possible in `EntityDefinitions.md`, "Purchase Order," "Identity") are tracked or reconciled against the originating Order once multiple Purchase Documents result from it.
- No Accounting Domain, module, or file exists anywhere in the repository, despite being named as an exclusion boundary by three separate documents (Restaurant/Purchasing's "Out of Scope," Administration's "Administration ≠ Accounting," Taxation's "Taxation ≠ Accounting").
- No schema, field list, or matching algorithm exists for `FinancialTransaction`, bank reconciliation, or invoice-payment matching — only the boundary statement that they are distinct from `SupplierInvoice`/`Payroll` (Section L).
- The Taxation Domain, as currently documented, defines no purchase-side sales/use tax, resale, or exemption content — the specific Florida resale/exemption question `Invoice Intake.md` §9 and `OpenQuestions.md` pose to it has no corresponding content anywhere in `01 Domains/Taxation/` yet (Section K).
- No document states whether `RealIngredientCost`/`EffectiveCost` (Restaurant/Purchasing) are persisted/stored fields or values computed on demand (Section I).

---

## P. Source Map

| Concept | Authoritative file(s) | Supporting files | Status |
|---|---|---|---|
| Purchase Document | `Restaurant/Purchasing/EntityDefinitions.md`, `BusinessRules.md` (Rules 1, 2, 15), `DataDictionary.md` | `README.md`, `Workflow.md`, `Examples.md`, `AcceptanceCriteria.md`, `ValidationRules.md`, `ErrorHandling.md`, `Model/PurchasingModel.md` | Canonical (Restaurant Domain) |
| Purchase Line | `Restaurant/Purchasing/EntityDefinitions.md`, `BusinessRules.md` (Rules 3, 6–8), `DataDictionary.md` | same as above | Canonical (Restaurant Domain) |
| Purchase Order | `Restaurant/Purchasing/EntityDefinitions.md`, `DataDictionary.md` | `Model/PurchasingModel.md` | Canonical but thin — no dedicated workflow/business-rule detail beyond the entity definition |
| Supplier | `Restaurant/Purchasing/EntityDefinitions.md`, `DataDictionary.md` | `Model/PurchasingModel.md` | Canonical (Restaurant Domain); superseded legacy stub at `90 Archive/.../Supplier.md` (empty) |
| Supplier Product | `Restaurant/Purchasing/EntityDefinitions.md`, `BusinessRules.md` (Rules 3–5), `DataDictionary.md` | `Model/PurchasingModel.md`, `Model/Product.md` | Canonical (Restaurant Domain) |
| Product / Specification / Ingredient | `Restaurant/Model/Product.md`, `Restaurant/Model/Specification.md`, `Restaurant/Purchasing/EntityDefinitions.md` (Ingredient), `DataDictionary.md` | `Model/PurchasingModel.md`, `BusinessRules.md` (Rules 5–7) | Canonical (Restaurant Domain) |
| Validation Log | `Restaurant/Purchasing/EntityDefinitions.md`, `ValidationRules.md`, `DataDictionary.md` | `BusinessPermissions.md`, `Non-FunctionalRequirements.md` | Canonical (Restaurant Domain); not implemented in any Software layer found (Section M) |
| Document-level charge/discount allocation | `Restaurant/Purchasing/BusinessRules.md` (Rules 9–10) | `DataAcquisition.md`, `Examples.md`, `TestingStrategy.md` | Canonical (Restaurant Domain), stated as a rule-in-words, not a modeled entity |
| `SupplierInvoice` / `InvoiceLine` | `Administration/Invoice Intake.md` | `07 Tasks/Reports/TASK_INVOICE_001_REPORT.md` | Canonical (Administration Domain), new (TASK_INVOICE_001); relationship to Purchase Document/Purchase Line explicitly unresolved (§13) |
| `InvoiceLineClassification` | `Administration/Invoice Intake.md`, §4 | — | Canonical (Administration Domain), new; relationship to Restaurant's Product/Ingredient classification undefined (Section O) |
| Supplier Item Memory | `Administration/Invoice Intake.md`, §5 | `Restaurant/Purchasing/Workflow.md`, `AcceptanceCriteria.md` (Restaurant's own, less detailed mapping-reuse statement) | Canonical (Administration Domain), new |
| `InvoiceCharge` / `InvoiceDiscount` | `Administration/Invoice Intake.md`, §7–8 | `Restaurant/Purchasing/BusinessRules.md` (Rules 9–10, the pre-existing, differently-worded Restaurant-side rule) | Canonical (Administration Domain), new; scope wording differs from Restaurant's Rule 9 (Section N.2) |
| Tax Treatment (purchase-side) | `OpenQuestions.md`, "Invoice Tax Treatment — OPEN"; `Administration/Invoice Intake.md`, §9 | `Taxation/TaxTreatment.md`, `TaxObligation.md`, `TaxPosition.md` (generic transversal concepts only) | **Open / unresolved** |
| `FinancialTransaction` / bank boundary | `Administration/Invoice Intake.md`, §10 | `Administration/Payroll/Payroll Provider Result.md` (the pre-existing settlement-boundary sentence this reuses) | Concept named only; no schema anywhere |
| Tax Category (sell-side) | `Restaurant/Commercial Catalog/TaxCategory.md` | — | Canonical (Restaurant Domain, Commercial Catalog); distinct scope from purchase-side tax (sells to customer, not purchases from supplier) |
| Discount (sell-side) | `Restaurant/Sales/Restaurant Sales Model.md`, §18 | — | Canonical (Restaurant Domain, Sales); distinct scope from purchase-side discounts (Order/OrderItem level, not Purchase Line/Invoice level) |
| Accounting | *(none)* | Referenced only as an exclusion boundary in `Restaurant/Purchasing/README.md`, `Administration/README.md`, `Taxation/README.md` | Not documented anywhere as its own Domain/module |
| Legacy `Purchase Invoice` / `Purchase Line` / `Supplier` | `90 Archive/Legacy Repository/X00 Knowledge Repository/06 Business Model/Purchase Invoice.md`, `Purchase Line.md`, `Supplier.md` | same folder's `README.md` (lists them as "planned entities") | **Legacy — empty stub files, no content beyond a title; superseded by current canonical Restaurant/Purchasing content** |

---

## Q. Exact files reviewed

Repository-wide keyword search matched 185 files. Of these, the following were opened and read in full or targeted detail because they contain substantive Purchasing/Supplier/Invoice/purchase-side-tax content:

**Restaurant/Purchasing (16/16 files, full read):**
`01 Domains/Restaurant/Purchasing/README.md`, `EntityDefinitions.md`, `DataDictionary.md`, `BusinessRules.md`, `ValidationRules.md`, `Workflow.md`, `AIResponsibilities.md`, `ErrorHandling.md`, `Examples.md`, `AcceptanceCriteria.md`, `TestingStrategy.md`, `BusinessPermissions.md`, `Configuration.md`, `DevelopmentRoadmap.md`, `DataAcquisition.md`, `Non-FunctionalRequirements.md`.

**Restaurant Domain (other):**
`01 Domains/Restaurant/README.md`, `Roadmap.md`, `Model/PurchasingModel.md`, `Model/Product.md`, `Model/Specification.md`; targeted sections of `Sales/Restaurant Sales Model.md` (§18 Discounts) and `Commercial Catalog/TaxCategory.md`.

**Administration Domain:**
`01 Domains/Administration/README.md`, `Invoice Intake.md`, `Personnel Cost.md`; `Payroll/README.md`, `Payroll/Payroll Provider Result.md` (bank/settlement boundary passage).

**Taxation Domain (9/9 files present; 5 read in full, 4 grep-verified for purchase/resale/Florida relevance):**
Full read: `README.md`, `Taxation.md`, `TaxTreatment.md`, `TaxObligation.md`, `TaxPosition.md`. Grep-checked only (no substantive purchase-side content found): `TaxJurisdiction.md`, `TaxScenario.md`, `TaxImpact.md`, `TaxStrategy.md`, `TaxEvidence.md`.

**Core:**
`00 Core/ConceptualArchitecture/00_RF-One_Core_Vision.md`; targeted passages of `06_Business_Autopilot_and_Intelligence_Engine.md`, `01_Subject_and_Reality.md`, `Core Evolution.md`; `05_Epistemic_Boundary_and_Subject_Sovereignty.md` (full, for the epistemic-boundary citations already made by Invoice Intake.md/Taxation).

**Domain-level cross-cutting:**
`01 Domains/README.md`, `01 Domains/Domain Architecture.md`.

**Software:**
`03 Software/InvoiceIntake/README.md`, `app.py`, `parser.py`, `ocr_engine.py`, `excel_store.py` (full read of all code files). `03 Software/RF-One Data Store/DATABASE_SCHEMA.md` and `rfone_data_store/models.py` (targeted keyword search, zero Purchasing-relevant matches — confirmed absence, not reviewed line-by-line beyond that search).

**Strategy:**
`09 Strategy/04_Business_Capability_Coverage.md` (targeted rows KD-006 through KD-010).

**Tasks/Reports:**
`07 Tasks/Reports/PRE_COMMIT_AUDIT.md` (targeted, Section D.3, for the Taxation task-provenance finding reused in N.6); `07 Tasks/Reports/TASK_INVOICE_001_REPORT.md` (own prior output, now in repository).

**Legacy/Archive:**
`90 Archive/Legacy Repository/X00 Knowledge Repository/06 Business Model/README.md`, `Purchase Invoice.md`, `Purchase Line.md`, `Supplier.md` (all four full read — the three concept files are empty stubs beyond their title line).

**Matched but not reviewed in depth (out of scope for a Purchasing/acquisti audit):** the remaining files among the 185 keyword matches — chiefly `03 Software/Clover Data Explorer/**` (sell-side POS data), `01 Domains/Personnel Management/**` and `01 Domains/Administration/Payroll/*` files beyond those cited above (matched on unrelated uses of "delivery," "tax," or "bonus" in a payroll/performance context), `01 Domains/Restaurant/Commercial Catalog/*` files beyond `TaxCategory.md` (sell-side catalog/pricing concepts), and `90 Archive/Task History/**` task specs/reports for unrelated Core tasks (matched incidentally on the word "Purchasing" inside illustrative Domain-example lists, the same wording already captured in N.1).
