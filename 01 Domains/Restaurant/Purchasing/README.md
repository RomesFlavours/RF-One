# Purchasing Module

## Purpose

The Purchasing Module transforms heterogeneous purchasing information into a single standardized knowledge model for the Restaurant Domain.

Its purpose is to create a reliable and supplier-independent representation of every purchase performed by the restaurant.

The module is designed around the Purchase Document, regardless of how the information is acquired.

---

## Objectives

The Purchasing Module enables RF-One to:

- Acquire purchasing information from any supplier.
- Normalize heterogeneous purchasing data.
- Calculate the real cost of Ingredients.
- Maintain the purchasing history.
- Compare suppliers objectively.
- Provide reliable purchasing knowledge to the rest of the Restaurant Domain.

---

## Scope

The module manages:

- Suppliers
- Supplier Products
- Purchase Orders (Purchase Order Lines, at the minimum needed for reconciliation)
- Purchase Documents
- Purchase Lines (PRODUCT, SURCHARGE, DISCOUNT)
- Merchandise / Economic Classification
- Ingredient Mapping (downstream, Food/Ingredient context only)
- Unit Normalization
- Cost Allocation
- Purchase History
- Configured Expectation and Alert (Purchase Recording — see below)
- Physical Receiving (Receiving Record, Receiving Line) and Order vs Invoice vs Receiving reconciliation (Purchase Recording — see below)
- Expected Supplier Credit and credit reconciliation (Purchase Recording — see below)

---

## Purchase Recording vs Purchase Support

The behavior currently documented in this module — observing Reality, comparing an incoming purchase against a Configured Expectation or the previous purchase, raising Alerts, and recording human decisions — belongs to **Purchase Recording**: understanding what actually happened.

**Purchase Support** — deciding what, how much and from whom to purchase — is a distinct, future capability and is not designed by the current documentation.

---

## Out of Scope

The module does not manage:

- Inventory
- Production
- Recipes
- Accounting
- Payments
- Warehouse
- Menu Engineering

---

## Fundamental Principle

The Purchase Document is the central entity of the Purchasing Module.

Every purchasing event must be representable as a Purchase Document regardless of its origin.

Supported acquisition sources include:

- Paper invoices
- PDF invoices
- Electronic invoices
- APIs
- XML
- EDI
- Manual data entry

All acquisition sources generate the same logical Purchase Document.

Invoice Intake — reading a supplier's invoice, receipt, credit note or API purchase record and turning it into a Purchase Document — is a capability of this module, not a separate Domain module. This applies equally to mixed-type suppliers (e.g. broadline foodservice distributors selling Food, Drink and Supplies on the same invoice, such as Ben E. Keith, Cheney Brothers and Gordon Food): every purchased line is preserved as a Purchase Line, classified via Merchandise/Economic Classification, and costed via Effective Product Cost — see `EntityDefinitions.md` and `BusinessRules.md`. See `DataAcquisition.md` for the supported acquisition channels.

---

## Domain Philosophy

The module is designed around the minimum information that every supplier can provide.

Additional information enriches the model but never changes its structure.

---

## Internal Standard

Every purchasable Ingredient is normalized into:

- grams
- cost per gram

All economic calculations are based on these values.

---

## Merchandise / Economic Classification and Ingredient Mapping

Every purchased product (`PRODUCT` Purchase Line) may be assigned a merchandise/economic classification (Food, Drink, Supplies, Other) when known. This determines the economic nature of the purchase and is required for derived category allocation — it is not conditioned on the product having a culinary identity.

Ingredient mapping is a further, downstream semantics: Supplier Products classified in the Food/Ingredient context are manually associated with Ingredients by an authorized user. A Supplies or Drink classification does not require Ingredient mapping.

AI may propose classifications and mappings but never validates them autonomously.

## Administration Boundary

Restaurant/Purchasing understands what was purchased. Administration consumes the derived economic result (category totals, document totals, reconciliation status) but does not own Purchase Document, Purchase Line, Supplier Product, or Ingredient mapping, and does not reinterpret item-level semantics — see `BusinessRules.md`, "Purchasing Precedes Administration and Taxation."

---

## Validation

RF-One never modifies supplier documents.

Detected inconsistencies are recorded in a Validation Log.

The Purchase Document always remains the legal representation of the purchase.

---

## Alerts and Configured Expectations

A `PRODUCT` Purchase Line's commercial configuration (e.g. packaging) may deviate from a Configured Expectation or, failing that, from the previous purchase of the same Supplier Product. When Product identity is certain, this deviation raises an Alert without blocking Purchase Recording — the Alert stays open until a responsible User acknowledges it and, when required, records a decision.

An Alert is not a Notification (it requires a traceable human response) and is not a Validation Log entry (it does not signal identity/interpretation uncertainty). See `EntityDefinitions.md`, "Alert" and "Configured Expectation"; `BusinessRules.md`, Rules 19–24; `ValidationRules.md`, "Alert vs Validation"; `Workflow.md`, Step 6.

---

## Physical Receiving and Reconciliation

Purchase Recording distinguishes three independent sources of Purchase Reality — Order, Invoice/Purchase Document, and Physical Receiving — and reconciles them rather than assuming any one implies another. Physical Receiving is captured mobile-first (label-based or Order-based, fallback-capable), records only facts, and can complete even while discrepancies remain open. A Receiving discrepancy (shortage, Extra/Unexpected Item, damaged quantity, substitution, Invoice/Order mismatch) raises an Alert (Trigger `RECEIVING_DISCREPANCY`) resolved by a responsible Purchasing User as ACCEPT or REJECT/RETURN, at quantity level. A REJECT/RETURN on already-invoiced merchandise creates an Expected Supplier Credit, which may remain open until a future Supplier document reconciles it, with no arbitrary expiration. See `EntityDefinitions.md`, "Receiving Record," "Receiving Line," "Expected Supplier Credit"; `BusinessRules.md`, Rules 25–42; `Workflow.md`, Steps 10–15.

---

## Artificial Intelligence

AI assists by:

- Reading documents
- Extracting information
- Suggesting mappings
- Detecting anomalies
- Proposing normalizations

AI never performs irreversible business decisions.

---

## Design Principles

- One logical purchasing model.
- Purchase Document is the central entity.
- Every purchase becomes historical knowledge.
- Every Ingredient is normalized into grams.
- Recipes never depend on suppliers.
- Reality is recorded, never rewritten.
- Human validation always prevails.
- A commercial configuration deviation is observable and may generate an Alert even when Product identity is unchanged.
- A one-time exception never redefines the approved baseline; only an explicit decision does.
- Order, Invoice and Physical Receiving are three independent sources of Purchase Reality, reconciled, never collapsed into one.
- Receiving records Reality; deciding what to do about a discrepancy is a Purchasing Decision, not a Receiving Employee's responsibility.
- A rejection/return is preserved alongside the original Receiving observation, never rewritten as if the merchandise had never arrived.
