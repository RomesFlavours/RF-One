# Data Dictionary

## Purpose

This document defines the business attributes of every Entity belonging to the Purchasing Module.

It specifies the meaning of each attribute independently from database implementation.

Entity behavior is documented elsewhere.

This document explicitly separates **persisted source facts** (canonical, stored) from **derived measures** (recalculable, never canonical stored truth) — see "Persist Facts — Derive Calculations" at the end of this document.

---

# Supplier

| Attribute | Description |
|------------|-------------|
| SupplierId | Unique internal identifier |
| Name | Supplier business name |
| Status | Active / Inactive |
| AcquisitionMethods | Supported acquisition methods |
| Notes | Optional business notes |

---

# Purchase Order

| Attribute | Description |
|------------|-------------|
| PurchaseOrderId | Unique internal identifier |
| SupplierId | Referenced Supplier |
| OrderDate | Purchase order date |
| Status | Current business status |
| Notes | Optional notes |

---

# Purchase Order Line

| Attribute | Description |
|------------|-------------|
| PurchaseOrderLineId | Unique internal identifier |
| PurchaseOrderId | Parent Purchase Order |
| SupplierProductId | Requested Supplier Product, when resolved |
| ItemDescription | Recognizable item identity/description, when Supplier Product is not yet resolved |
| Quantity | Requested quantity |

This is the minimum information Purchase Recording needs from an Order for reconciliation (`EntityDefinitions.md`, "Purchase Order Line"). The Order/Purchase Support capability that creates and manages Purchase Order Lines is not designed here.

---

# Purchase Document

| Attribute | Description |
|------------|-------------|
| PurchaseDocumentId | Unique internal identifier |
| SupplierId | Referenced Supplier |
| PurchaseOrderId | Related Purchase Order (optional) |
| DocumentNumber | Supplier document/invoice number |
| DocumentType | Invoice, Receipt, Credit Note, API purchase record, other |
| IssueDate | Supplier issue/invoice date |
| DeliveryDate | Delivery date, when disclosed by the source |
| DestinationLocation | Ship-to / delivery location, when disclosed by the source |
| CustomerAccountReference | Supplier's identifier for this customer/account, when disclosed |
| AcquisitionMethod | OCR, PDF, API, XML, EDI, Manual |
| Currency | Original document currency |
| TotalAmount | Total document amount |
| PaymentTerms | Payment terms, when disclosed by the source |
| Status | Business processing status |

**Every header field above is present only when the source document discloses it.** A field's absence is Unknown for that document, never zero, never inferred, never treated as "not applicable" — see `EntityDefinitions.md`, "Purchase Document," and the Core Epistemic Boundary (`00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md`).

---

# Purchase Line

Common attributes, present regardless of `LineType`:

| Attribute | Description |
|------------|-------------|
| PurchaseLineId | Unique internal identifier |
| PurchaseDocumentId | Parent Purchase Document |
| LineType | `PRODUCT`, `SURCHARGE`, or `DISCOUNT` |
| SourceLineNumber | Supplier's own line number, when disclosed |
| RawDescription | Original supplier description, preserved exactly as received |
| SourceAmount | Original line amount as printed on the source document (the sign/semantics of a `DISCOUNT` line are preserved as disclosed) |

Attributes applicable only to `LineType = PRODUCT`:

| Attribute | Description |
|------------|-------------|
| SupplierProductId | Referenced Supplier Product, when supplier product identity is available (nullable — see `EntityDefinitions.md`, "Supplier Product Relationship") |
| SupplierItemCode | Supplier's own item code, when disclosed |
| SupplierCategoryCode | Supplier's own category/section label, when disclosed — a source fact, never automatically an RF-One classification (see `EntityDefinitions.md`, "Merchandise / Economic Classification") |
| SourceSection | Physical section/grouping the line appeared under on the source document, when disclosed |
| ManufacturerCode | Manufacturer/product code, when disclosed |
| Brand | Brand, when disclosed |
| Quantity | Original purchased quantity |
| PurchaseUnit | Original purchasing unit |
| PackCount | Number of packs/units per commercial configuration, when disclosed (e.g. the `20` in `20 × 500 g`) |
| PackSize | Pack size, when disclosed (e.g. the `500 g` in `20 × 500 g`) |
| ProductVariant | Supplier's disclosed product variant, when applicable |
| Grade | Supplier's disclosed product grade, when applicable |
| UnitPrice | Supplier unit price |
| EconomicClassification | Merchandise/economic classification (`FOOD`, `DRINK`, `SUPPLIES`, `OTHER`), once known and human-confirmed — a persisted fact, not a derived value (see "Persist Facts — Derive Calculations" below) |

`SURCHARGE` and `DISCOUNT` lines never carry `SupplierProductId`, `EconomicClassification`, or any other `PRODUCT`-only attribute above — they are not products (see `EntityDefinitions.md`).

These `PRODUCT`-only attributes are collectively the commercial configuration facts a Configured Expectation may reference and against which a variation is detected (`EntityDefinitions.md`, "Product Identity vs Commercial Configuration," "Configured Expectation"; `BusinessRules.md`, Rules 19–20). A packaging/configuration change alone (e.g. `PackCount`/`PackSize` differing from a prior purchase) never changes `SupplierProductId`, `EconomicClassification` or Ingredient mapping.

---

# Supplier Product

| Attribute | Description |
|------------|-------------|
| SupplierProductId | Unique internal identifier |
| SupplierId | Referenced Supplier |
| SupplierCode | Supplier product code |
| SupplierName | Original supplier description |
| Packaging | Commercial packaging |
| EconomicClassification | Confirmed merchandise/economic classification (optional until validated) — reused across every Purchase Line referencing this Supplier Product |
| IngredientId | Referenced Ingredient (optional; applicable only when EconomicClassification places this Supplier Product in the Food/Ingredient context) |

---

# Product

| Attribute | Description |
|------------|-------------|
| ProductId | Unique internal identifier |
| Name | Canonical product name |
| Category | Business category |

---

# Specification

| Attribute | Description |
|------------|-------------|
| SpecificationId | Unique internal identifier |
| Name | Specification name |
| Type | Specification type |
| Value | Specification value |

---

# Ingredient

| Attribute | Description |
|------------|-------------|
| IngredientId | Unique internal identifier |
| ProductId | Referenced Product |
| Specifications | Set of associated Specifications |
| Density | Used for liquid normalization |
| EdibleYield | Percentage of usable product |
| CookingYield | Percentage after cooking |

---

# Configured Expectation

| Attribute | Description |
|------------|-------------|
| ConfiguredExpectationId | Unique internal identifier |
| SupplierProductId | Referenced Supplier Product |
| AcceptableConfigurations | One or more accepted commercial configurations (e.g. PackCount/PackSize/Unit/Brand/Variant/Grade combinations — see `EntityDefinitions.md`, "Configured Expectation") |
| Status | Active / Superseded |
| ApprovedBy | Authorized user who approved the current configuration(s) |
| LastUpdated | Date and time of the last approved change |

A Configured Expectation is created or changed only through a Human Decision (`BusinessRules.md`, Rule 23) — it is never inferred automatically from a single observed purchase.

---

# Receiving Record

| Attribute | Description |
|------------|-------------|
| ReceivingRecordId | Unique internal identifier |
| SupplierId | Referenced Supplier |
| PurchaseOrderId | Related Purchase Order, when known |
| PurchaseDocumentId | Related Purchase Document/Invoice, when known |
| Location | Receiving destination |
| ReceivingTimestamp | Date and time of receiving |
| ReceivingUserId | User who performed the Receiving |
| CaptureMethod | `LABEL_BASED`, `ORDER_BASED`, or `MANUAL` — the capture mode actually used, fallback-capable (`BusinessRules.md`, "Receiving Method Is Fallback-Capable") |
| SourceProvenance | Reference to captured source evidence (scanned Invoice, labels, photos) |
| Status | `IN_PROGRESS` or `COMPLETED` — independent of whether related Alerts are still Open (`BusinessRules.md`, "Receiving Completion Is Independent of Alert Resolution") |

---

# Receiving Line

| Attribute | Description |
|------------|-------------|
| ReceivingLineId | Unique internal identifier |
| ReceivingRecordId | Parent Receiving Record |
| PurchaseOrderLineId | Related Purchase Order Line, when known (absent for an Extra/Unexpected Item) |
| PurchaseLineId | Related `PRODUCT` Purchase Line, when known |
| SupplierProductId | Recognized Supplier Product, when known |
| RawDescription | Free-text description, principally used for an Extra/Unexpected Item |
| ObservedQuantity | Quantity actually observed |
| ObservedPackaging / PackCount / PackSize / Unit / Brand / Variant / Grade | Observed commercial configuration facts, when recognizable — same source facts as a `PRODUCT` Purchase Line (see above) |
| DamagedQuantity | Portion of ObservedQuantity recorded as damaged, when applicable |
| PhotoEvidence | Photographic evidence — mandatory when this line is an Extra/Unexpected Item or carries a DamagedQuantity (`BusinessRules.md`, "Extra/Unexpected Item Always Generates an Alert," "Damaged Item Is a Factual Receiving Observation") |
| CaptureMethod | `LABEL_SCAN`, `ORDER_CONFIRMATION`, or `MANUAL` |

A Receiving Line with no `PurchaseOrderLineId` is, by definition, an Extra/Unexpected Item (`EntityDefinitions.md`, "Receiving Line").

---

# Alert

| Attribute | Description |
|------------|-------------|
| AlertId | Unique internal identifier |
| Trigger | `CONFIGURATION_DEVIATION` or `RECEIVING_DISCREPANCY` — which case raised the Alert (`EntityDefinitions.md`, "Alert Trigger") |
| PurchaseDocumentId | Related Purchase Document |
| PurchaseLineId | Related `PRODUCT` Purchase Line, when the Trigger references one |
| SupplierProductId | Related Supplier Product, when known |
| PurchaseOrderLineId | Related Purchase Order Line — applicable when Trigger = `RECEIVING_DISCREPANCY` |
| ReceivingRecordId | Related Receiving Record — applicable when Trigger = `RECEIVING_DISCREPANCY` |
| ReceivingLineId | Related Receiving Line that revealed the discrepancy — applicable when Trigger = `RECEIVING_DISCREPANCY` |
| ComparisonBasis | `CONFIGURED_EXPECTATION` or `PREVIOUS_PURCHASE` — which reference level detected the deviation; applicable when Trigger = `CONFIGURATION_DEVIATION` (`BusinessRules.md`, Rule 20) |
| ExpectedConfiguration | The configuration that was expected, as observed at comparison time — applicable when Trigger = `CONFIGURATION_DEVIATION` |
| ObservedConfiguration | The configuration actually observed on this Purchase Line — applicable when Trigger = `CONFIGURATION_DEVIATION` |
| ReconciliationOutcome | One or more atomic differences derived by reconciliation (e.g. `SHORT`, `EXTRA`, `SUBSTITUTED`, `DAMAGED`, `INVOICE_MISMATCH`, `ORDER_MISMATCH`) — applicable when Trigger = `RECEIVING_DISCREPANCY`, derived, not persisted as canonical truth (`BusinessRules.md`, "Reconciliation Produces Atomic Differences, Not a Boolean Result") |
| ResponsibleUser | User/role responsible for acknowledging and deciding |
| Status | Open, Acknowledged, Decided, Closed |
| HumanDecision | When Trigger = `CONFIGURATION_DEVIATION`: `ACCEPT_THIS_PURCHASE_ONLY`, `ACCEPT_AS_ALTERNATIVE`, `CHANGE_EXPECTATION`, or a recorded Module Capability Gap escalation (`BusinessRules.md`, Rules 23–24). When Trigger = `RECEIVING_DISCREPANCY`: `ACCEPT` or `REJECT_RETURN` (`BusinessRules.md`, "Purchasing Decision on a Receiving Discrepancy") |
| DecidedBy | User who made the Human Decision |
| DecidedAt | Date and time of the Human Decision |
| CreatedAt | Date and time the Alert was raised |

An Alert is a distinct concept from a Validation Log entry and is never recorded as one (`ValidationRules.md`, "Alert vs Validation"). Raising an Alert never blocks Purchase Recording, or Receiving completion, when the underlying facts are certain (`BusinessRules.md`, Rule 21, "Receiving Completion Is Independent of Alert Resolution").

---

# Expected Supplier Credit

| Attribute | Description |
|------------|-------------|
| ExpectedSupplierCreditId | Unique internal identifier |
| AlertId | Related Alert whose `REJECT_RETURN` Human Decision created this expectation |
| PurchaseDocumentId | Original Purchase Document that invoiced the rejected/returned quantity |
| PurchaseLineId | Original `PRODUCT` Purchase Line that invoiced the rejected/returned quantity |
| RejectedQuantity | Quantity rejected/returned |
| ExpectedAmount | Economic amount the Restaurant expects the Supplier to credit |
| LinkedCreditReferences | One or more later Purchase Documents (typically Credit Note) or credit-adjustment Purchase Lines, each with its applied amount, recognized as satisfying this expectation in whole or in part |
| RecognizedAmount | Sum of applied amounts across LinkedCreditReferences — derived, not persisted as canonical truth |
| OutstandingAmount | ExpectedAmount minus RecognizedAmount — derived, not persisted as canonical truth |
| Status | Open, Partially Resolved, Resolved |
| CreatedAt | Date and time the expectation was created |
| ResolvedAt | Date and time the expectation was resolved, when applicable |

An Expected Supplier Credit has no arbitrary expiration (`BusinessRules.md`, "No Arbitrary Expiration for Long-Lived Open Supplier Issues").

---

# Validation Log

| Attribute | Description |
|------------|-------------|
| ValidationId | Unique internal identifier |
| PurchaseDocumentId | Related Purchase Document |
| PurchaseLineId | Related Purchase Line (optional) |
| Severity | Information, Warning or Error |
| Message | Validation message |
| SuggestedAction | AI proposed action |
| HumanDecision | Approved business decision |
| Status | Open, Approved, Rejected, Closed |
| Timestamp | Date and time of creation |

---

# Persist Facts — Derive Calculations

RF-One persists source facts, confirmed decisions and evidence. It derives calculations on demand. A value that can be recomputed from persisted facts is never itself the canonical stored truth, regardless of whether it is convenient to cache it at runtime.

**Canonical persisted/source facts** (stored):

- Purchase Document and its disclosed header facts
- Purchase Lines (`PRODUCT`, `SURCHARGE`, `DISCOUNT`) and their source-verbatim attributes above
- Quantity, PurchaseUnit, UnitPrice, SourceAmount
- Supplier Product identity
- EconomicClassification, once human-confirmed
- Ingredient mapping, once human-confirmed
- Source/provenance (acquisition method, source document reference)
- Validation Log decisions
- Configured Expectation (current accepted configuration(s) per Supplier Product), once human-approved
- Alert records and their Human Decisions
- Purchase Order Line (Supplier, item, requested quantity)
- Receiving Record and Receiving Line (observed items, quantities, configuration, damaged quantity, photographic evidence, capture method, source/provenance)
- Expected Supplier Credit (expected amount, rejected quantity, linked satisfying credit references, status)

**Not canonical stored truth** (derived measures — recalculable from the facts above and current configuration):

- Effective Product Cost
- Surcharge allocation share
- Discount allocation share
- Category totals (e.g. Food = $X, Drink = $Y, Supplies = $Z)
- NormalizedQuantity, when fully recalculable from Quantity/PurchaseUnit and configuration
- CostPerGram, when recalculable
- Reconciliation Outcome (the atomic differences — MATCH, SHORT, EXTRA, SUBSTITUTED, DAMAGED, INVOICE MISMATCH, ORDER MISMATCH, PACKAGING DEVIATION, QUANTITY DEVIATION — derived by comparing Order, Invoice and Receiving facts; see `BusinessRules.md`, "Reconciliation Produces Atomic Differences, Not a Boolean Result")
- Expected Supplier Credit's RecognizedAmount and OutstandingAmount

These derived measures may be defined as functions or views and may be cached for performance, but they are never the canonical source of truth — a discrepancy is always resolved in favor of the persisted source facts, never the cached derived value. See `BusinessRules.md`, "Effective Product Cost," for the derivation formula.

---

# Attribute Principles

- Every Entity has one unique internal identifier.
- Original supplier information is always preserved.
- Internal business identifiers never depend on supplier identifiers.
- Quantities are normalized into grams as a derived measure (see "Persist Facts — Derive Calculations" above); the original commercial quantity/unit is always preserved as source fact.
- Historical values are never overwritten.
- Temporary commercial events (surcharges, discounts) never modify historical purchasing data — they are preserved as their own Purchase Lines and enter only derived calculations.
- A later correction to a classification or mapping updates memory going forward; it never rewrites the historical Purchase Lines already recorded under the prior classification.
- A Human Decision on an Alert updates the Configured Expectation prospectively, when it does; it never rewrites the historical Purchase Line, the Alert, or the decision context recorded at that time (`BusinessRules.md`, Rule 23).
- A REJECT/RETURN decision never rewrites a Receiving Line as if the merchandise had never been received; it records the rejection as a further fact alongside the original observation (`BusinessRules.md`, "Rejection Preserves Historical Reality," "Return Is Not 'Never Received'").
