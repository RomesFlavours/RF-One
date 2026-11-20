# Entity Definitions

## Purpose

This document defines the business entities of the Purchasing Module.

Entities represent the permanent business concepts of the domain.

An Entity exists because the restaurant needs to preserve its identity over time.

Entities are independent from database implementation, programming language and user interface.

This document describes **what an Entity is**, **why it exists**, and **its responsibilities**.

Entity attributes are documented separately in **DataDictionary.md**.

---

# Supplier

## Purpose

Represents a commercial organization that supplies products to the restaurant.

## Identity

A Supplier maintains its identity independently of:

- products sold;
- Purchase Documents issued;
- acquisition methods.

## Responsibilities

- Receive Purchase Orders.
- Supply Supplier Products.
- Issue Purchase Documents.

---

# Purchase Order

## Purpose

Represents the purchasing request sent by the restaurant to a Supplier.

## Identity

A Purchase Order exists before products are delivered.

One Purchase Order may generate:

- one Purchase Document;
- multiple Purchase Documents;
- partial deliveries.

## Responsibilities

- Request products.
- Preserve purchasing intent.
- Link purchasing requests to delivered goods.

---

# Purchase Order Line

## Purpose

Represents one requested item on a Purchase Order — the minimum information Purchase Recording needs to reconcile what was ordered against what was invoiced and what was physically received (see "Receiving Record," "Receiving Line," below, and `BusinessRules.md`, "Three Sources of Purchase Reality").

## Identity

A Purchase Order Line belongs to exactly one Purchase Order and represents one requested Supplier Product (or, when Supplier Product identity is not yet resolved, a recognizable item description) and the requested quantity.

This module does not design the Order/Purchase Support capability that creates or manages Purchase Order Lines (`README.md`, "Purchase Recording vs Purchase Support"). Purchase Recording only assumes a Purchase Order Line carries enough information — Supplier, item, quantity — to serve as one comparison point in reconciliation.

## Responsibilities

- Preserve the requested item and quantity as the Restaurant's purchasing intent.
- Provide the "Order" side of the Order vs Invoice vs Receiving reconciliation (`BusinessRules.md`, "Three-Way Reconciliation").

---

# Purchase Document

## Purpose

Represents the source commercial document of a completed purchase — an Invoice, Receipt, Credit Note, API purchase record, or other real document a Supplier or acquisition channel produces.

The Purchase Document is the central business entity of the Purchasing Module. Every acquisition channel (see `DataAcquisition.md`) converges on this same entity — the source technology never creates a parallel model of the same purchase.

## Identity

A Purchase Document preserves the commercial information extracted from the supplier's original document, including every header fact genuinely present in the source that may be useful to other Restaurant Domain modules — for example Supplier, document/invoice number, issue/invoice date, delivery date, destination/ship-to/delivery location, customer/account reference, currency, total, payment terms, acquisition method, and source/provenance.

**Principle:** extract what the source knows; do not invent what the source does not know. A header fact absent from the source is preserved as Unknown for that document, never assumed, defaulted, or inferred. No header fact is universally mandatory merely because one Supplier happens to disclose it — different acquisition sources and different Suppliers disclose an overlapping but non-identical set of these facts.

The original supplier document is always preserved and never modified.

The business representation may be completed or validated without altering the original document.

## Responsibilities

- Preserve legal purchasing information, including every disclosed header fact.
- Group Purchase Lines.
- Preserve document-level charges and discounts as Purchase Lines (see "Purchase Line" below).
- Preserve purchasing history.

---

# Purchase Line

## Purpose

Represents one real line of a Purchase Document — a purchased product, a document-level surcharge, or a document-level discount. Every real line present on the source document is preserved as one Purchase Line, regardless of its economic nature.

## Identity

Each Purchase Line has a `line_type`:

```text
PRODUCT     — a product actually purchased
SURCHARGE   — a document-level charge (e.g. Fuel Surcharge, Delivery Surcharge,
              Service Fee, Environmental Fee)
DISCOUNT    — a document-level commercial discount or bonus
```

The supplier's raw description and source amount are preserved exactly as received, regardless of `line_type`.

A Purchase Line's relationship to Supplier Product depends on its `line_type` — see "Supplier Product Relationship" below. Only a `PRODUCT` Purchase Line may reference a Supplier Product or carry a merchandise/economic classification; a surcharge or a discount is not a product and never carries either.

## Supplier Product Relationship

```text
PRODUCT    → may/reference a Supplier Product, when supplier product identity
             is available from the source
SURCHARGE  → Supplier Product = NULL / not applicable
DISCOUNT   → Supplier Product = NULL / not applicable
```

This replaces the earlier, now-rejected rule that every Purchase Line must reference exactly one Supplier Product — that rule conflated products with document-level charges and discounts, which are never products.

## Responsibilities

- Represent one real purchased item, surcharge, or discount, exactly as it appears on the source document.
- Preserve commercial quantity and price when applicable (`PRODUCT` lines).
- Participate in cost normalization and in the derivation of Effective Product Cost (see `BusinessRules.md`).

---

# Supplier Product

## Purpose

Represents the commercial product defined by one specific Supplier.

## Identity

Supplier Products belong exclusively to one Supplier.

Different Suppliers may define different Supplier Products that represent the same Ingredient.

A Supplier Product may exist before being associated with a merchandise/economic classification or an Ingredient.

**Supplier Product memory:** the pair (Supplier, Supplier Item Code) identifies a Supplier Product across purchases over time. A known pair reuses the existing Supplier Product and its confirmed classification/mappings without re-interpreting the raw description from zero. A new pair creates/recognizes a candidate Supplier Product: AI may propose a classification or mapping, a human validates it, and approved knowledge becomes reusable. A later correction to a Supplier Product's classification or mapping updates memory going forward; it never rewrites the historical Purchase Lines already recorded under the prior classification (see "Persist Facts — Derive Calculations," `DataDictionary.md`).

Supplier source data (e.g. the supplier's own item code, category/section label, brand, manufacturer code, pack size) is preserved as source fact, separately from any RF-One semantics (merchandise classification, Ingredient mapping) later attached to the same Supplier Product. A supplier's own category or section label never automatically implies an RF-One classification — see "Merchandise / Economic Classification" below.

## Responsibilities

- Preserve supplier terminology, packaging and source identifiers.
- Preserve supplier source facts separately from RF-One classification/mapping.
- Link purchasing information to a merchandise/economic classification and, when applicable, to an Ingredient.

---

# Merchandise / Economic Classification

## Purpose

Represents the economic nature of a purchased product — the classification RF-One needs to determine what kind of expense a `PRODUCT` Purchase Line represents, independently of whether that product also has a culinary/Ingredient identity.

## Identity

Initial classification values:

```text
FOOD
DRINK
SUPPLIES
OTHER (future categories as required by reality)
```

A merchandise/economic classification is attached to a `PRODUCT` Purchase Line (via its Supplier Product, once known) when the classification is known. `SURCHARGE` and `DISCOUNT` lines never carry a merchandise/economic classification — they are not products.

This classification is broader than, and distinct from, Ingredient mapping (see "Ingredient" below): every purchased product that is a real economic expense can in principle be classified, but only products in the Food/Ingredient context also require Ingredient mapping. A classification of `SUPPLIES` does not require Ingredient mapping; a classification of `FOOD` may map further to an Ingredient.

Like a Supplier Product mapping, a merchandise/economic classification is proposed by AI and confirmed by a human before becoming reusable knowledge (see "Supplier Product," above, and `Workflow.md`).

## Responsibilities

- Determine the economic nature of a purchased product.
- Support derived category allocation (e.g. Food = $X, Drink = $Y, Supplies = $Z) consumed downstream by Administration (see `BusinessRules.md`, "Purchasing Precedes Administration and Taxation").
- Provide the entry point for Ingredient mapping when the classification indicates the Food/Ingredient context applies.

---

# Product

## Purpose

Represents the generic culinary concept.

Examples:

- Tomato
- Flour
- Olive Oil
- Parmesan Cheese

## Identity

Products are supplier independent.

Products cannot be purchased directly.

## Responsibilities

- Define the generic culinary concept.
- Group Ingredients sharing the same culinary identity.

---

# Specification

## Purpose

Represents one business characteristic that qualifies a Product.

Examples:

- Organic
- Italian
- San Marzano
- PDO
- 24 Months

## Identity

Specifications have no business meaning without a Product.

## Responsibilities

- Qualify Products.
- Contribute to Ingredient identity.

---

# Ingredient

## Purpose

Represents the canonical culinary entity used throughout the Restaurant Domain.

Ingredient mapping is a downstream semantics applicable to `PRODUCT` Purchase Lines whose merchandise/economic classification places them in the Food/Ingredient context (typically `FOOD`). It is not a universal requirement for every purchased product — a `SUPPLIES` or `DRINK`-classified product is not required to map to an Ingredient unless the restaurant's own recipe/costing needs genuinely require it.

## Identity

An Ingredient is uniquely identified by:

- one Product;
- zero or more Specifications.

Ingredients are supplier independent.

Recipes always reference Ingredients.

## Responsibilities

- Standardize purchasing knowledge for the Food/Ingredient context.
- Support Recipes.
- Support Food Cost.
- Support Inventory.
- Support Forecasting.
- Support Purchasing Intelligence.

---

# Product Identity vs Commercial Configuration

## Purpose

Formalizes that a Product/Ingredient's identity (`EntityDefinitions.md`, "Ingredient" — one Product plus zero or more Specifications) is independent of the commercial configuration in which it happens to be purchased.

## Identity

A Product/Ingredient does not change identity merely because its packaging or commercial configuration changes.

```text
Ricotta            → same Product/Ingredient identity
  20 × 500 g       → one commercial configuration
  1 × 5 kg         → a different commercial configuration

Olive Oil          → same Product/Ingredient identity
  4 × 1 GAL        → one packaging
  6 × 1 L          → a different packaging
```

A packaging/configuration change must not automatically create a new Ingredient or Product (Rule 6, `BusinessRules.md`, still governs Ingredient identity: only a different Product or different Specifications create a different Ingredient — pack count, pack size, unit and similar commercial facts are not Specifications).

Commercial configuration is nonetheless never treated as irrelevant. It can affect normalized cost, freshness, shelf life after opening, waste, yield, storage requirements, operational usability, product quality and recipe/food cost consequences — see "Configured Expectation" and "Alert" below, and `BusinessRules.md`, "Purchase Configuration Variation Is Observable Even When Identity Is Unchanged."

## Responsibilities

- Keep Product/Ingredient identity stable across packaging/configuration changes.
- Preserve the commercial configuration actually observed on each Purchase Line as source fact (`DataDictionary.md`, "Purchase Line").
- Provide the basis against which Purchase Recording detects a meaningful configuration deviation (see "Configured Expectation" below).

---

# Configured Expectation

## Purpose

Represents approved operational knowledge about what the Restaurant considers a normal/acceptable commercial configuration for a given Supplier Product — for example packaging, pack count, pack size, unit, brand, variant or grade.

A Configured Expectation is the highest-priority reference Purchase Recording uses to detect a configuration deviation (`BusinessRules.md`, "Two Reference Levels for Variation Detection"). It exists only once a human has approved it; nothing is a Configured Expectation merely because it was purchased once.

## Identity

A Configured Expectation belongs to exactly one Supplier Product.

A Configured Expectation may hold one or more acceptable configurations — a Human Decision to "accept as alternative" (see "Alert" below) adds a further acceptable configuration without removing the existing one.

A Configured Expectation changes only prospectively, through an explicit Human Decision. It is never inferred automatically from a single observed purchase, and it never rewrites historical Purchase Lines already recorded (`BusinessRules.md`, Rule 11; `DataDictionary.md`, "Persist Facts — Derive Calculations").

## Responsibilities

- Represent the Restaurant's approved expectation for a Supplier Product's commercial configuration.
- Take precedence over the previous-purchase fallback when present (see "Previous Purchase" below).
- Absorb Human Decisions that are Configuration Learning (change the expectation, or add an approved alternative) — see `BusinessRules.md`, "Configuration Learning vs Module Capability Gap."
- Remain unaffected by a Human Decision that only accepts a single purchase as a one-time exception.

---

# Previous Purchase (Fallback Reference)

## Purpose

Represents the empirical fallback Purchase Recording uses to detect a configuration deviation when no Configured Expectation exists yet for a Supplier Product: the most recent prior Purchase Line for the same Supplier + Supplier Product.

## Identity

The previous purchase is historical Purchase Reality, already recorded (`EntityDefinitions.md`, "Purchase Line"). It is consulted for comparison, never modified.

A previous purchase used as a fallback reference never becomes an approved rule by itself — only an explicit Human Decision creates or changes a Configured Expectation (see above).

## Responsibilities

- Provide a comparison basis when no Configured Expectation is applicable.
- Remain purely observational: using it for comparison does not elevate it to approved knowledge.

---

# Receiving Record

## Purpose

Represents the Restaurant's observation of what physically arrived from a Supplier at a given Location and time — Physical Receiving, one of the three independent sources of Purchase Reality (`BusinessRules.md`, "Three Sources of Purchase Reality"). A Receiving Record is evidence of what was observed; it is not itself a Purchasing Decision (`BusinessRules.md`, "Receiving Is Observation, Not Decision").

## Identity

A Receiving Record belongs to one Supplier, at one Location, captured by one Receiving User at one receiving timestamp. It references a related Purchase Order when known and a related Purchase Document/Invoice when known — neither is required to start or complete a Receiving Record (`DataAcquisition.md` governs how a Purchase Document itself is acquired; a Receiving Record is a distinct capture, not a Purchase Document acquisition channel).

A Receiving Record is captured through one of two conceptual modes — label-based or Order-based — and the capture mode is fallback-capable: a Receiving Record is never blocked merely because its preferred capture mode fails (`BusinessRules.md`, "Receiving Method Is Fallback-Capable").

A Receiving Record reaches a **Completed** status once the receiving Employee finishes the session. Completion is independent of whether every Receiving Line reconciles cleanly — open discrepancies do not prevent completion (`BusinessRules.md`, "Receiving Completion Is Independent of Alert Resolution").

## Responsibilities

- Preserve the Restaurant's factual observation of a physical delivery: Supplier, related Order/Purchase Document when known, Location, timestamp, Receiving User, capture method, source evidence, and completion status.
- Group Receiving Lines.
- Provide the "Receiving" side of the Order vs Invoice vs Receiving reconciliation.
- Remain a record of Reality, never a decision about the commercial acceptability of what it records.

---

# Receiving Line

## Purpose

Represents one observed item on a Receiving Record — one Item and quantity the Restaurant actually observed arriving, together with any damage or evidence recorded against it.

## Identity

A Receiving Line references, when known, the related Purchase Order Line and the related `PRODUCT` Purchase Line it corresponds to. A Receiving Line with no related Purchase Order Line is an **Extra/Unexpected Item** — merchandise physically delivered but not present in the Order (`BusinessRules.md`, "Extra/Unexpected Item Always Generates an Alert"). Both cases are the same entity; they differ only in whether a related Order Line exists.

A Receiving Line preserves the observed quantity and, when recognizable, the observed commercial configuration (packaging, pack count, pack size, unit, brand, variant, grade — the same source facts as a `PRODUCT` Purchase Line, `DataDictionary.md`). It may also preserve a damaged quantity, which is a portion of the observed quantity, not a separate line (`BusinessRules.md`, "Partial Quantity").

Photographic evidence is mandatory whenever a Receiving Line represents an Extra/Unexpected Item or carries a damaged quantity (`BusinessRules.md`, "Extra/Unexpected Item Always Generates an Alert," "Damaged Item Is a Factual Receiving Observation").

## Responsibilities

- Preserve one observed item, its observed quantity and, when applicable, its observed configuration, exactly as captured — by label recognition, by Order-based quantity confirmation, or by manual/free-text entry when neither applies.
- Preserve damaged quantity and mandatory photographic evidence, when applicable.
- Preserve mandatory photographic evidence and a free-text description for an Extra/Unexpected Item.
- Provide one comparison point for reconciliation; never itself resolve or classify the deviation it may reveal (`BusinessRules.md`, "Receiving Is Observation, Not Decision").

---

# Alert

## Purpose

Represents a case where RF-One knows what actually happened but the observed Reality deviates from an operational expectation in a way that requires human attention.

An Alert is distinct from a Notification and from a Validation Log entry — see `ValidationRules.md`, "Alert vs Validation," and `03 Software/User Interaction Architecture.md`.

## Alert Trigger

An Alert is raised by exactly one of two triggers:

```text
CONFIGURATION_DEVIATION
  → a PRODUCT Purchase Line's observed commercial configuration deviates from a
    Configured Expectation, or from the previous-purchase fallback
    (BusinessRules.md, Rules 19-20)

RECEIVING_DISCREPANCY
  → a Receiving Line reveals a shortage, an Extra/Unexpected Item, a damaged
    quantity, a substitution, or a mismatch among Order, Invoice and Receiving
    (BusinessRules.md, "Three-Way Reconciliation")
```

The trigger determines which Human Decisions are meaningful for that Alert (see "Identity" below).

## Identity

An Alert raised by `CONFIGURATION_DEVIATION` is always associated with the `PRODUCT` Purchase Line (and, through it, the Supplier Product and Purchase Document) whose observed configuration triggered it.

An Alert raised by `RECEIVING_DISCREPANCY` is always associated with the Receiving Line that revealed it, and, when they exist, the related Purchase Order Line and `PRODUCT` Purchase Line. An Extra/Unexpected Item's Alert has no related Purchase Order Line or Purchase Line by definition — the Receiving Line is its only anchor.

An Alert has a responsible User/role and remains **OPEN** until it receives an explicit human acknowledgement and, when a decision is required, a recorded Human Decision (`BusinessRules.md`, "Alert Lifecycle and Closure").

Raising an Alert never blocks Purchase Recording, or Receiving, by itself: when the underlying facts (Product identity, or the physical observation) are certain, the Purchase Line or Receiving Line is recorded correctly and the Alert remains open in parallel (`BusinessRules.md`, "Alert Does Not Block Purchase Recording When Identity Is Certain," "Receiving Completion Is Independent of Alert Resolution"). An Alert is not a mechanism for expressing identity uncertainty — that case belongs to Validation (`ValidationRules.md`).

## Responsibilities

- Signal a meaningful deviation between observed Reality and an operational expectation, whichever of the two Alert Triggers applies.
- Preserve the deviation and its context (what was expected/ordered/invoiced, what was observed) without altering any of it.
- Track responsible User/role, acknowledgement, Human Decision, who decided, when, and closure.
- Route a `CONFIGURATION_DEVIATION` Human Decision to the correct effect: one-time acceptance, an added alternative, a changed expectation, or an escalated capability gap (`BusinessRules.md`, "Configuration Learning vs Module Capability Gap").
- Route a `RECEIVING_DISCREPANCY` Human Decision to the correct effect: ACCEPT or REJECT/RETURN, and, when REJECT/RETURN applies to already-invoiced merchandise, the creation of an Expected Supplier Credit (`BusinessRules.md`, "Purchasing Decision on a Receiving Discrepancy," "Expected Supplier Credit," below).

---

# Expected Supplier Credit

## Purpose

Represents the Restaurant's operational expectation that a Supplier owes an economic correction, because merchandise already invoiced was rejected/returned following a Receiving discrepancy decision (`BusinessRules.md`, "Rejection Preserves Historical Reality").

## Identity

An Expected Supplier Credit is created only when a `REJECT / RETURN` Human Decision applies to a Receiving Line whose merchandise was already invoiced (i.e., a related `PRODUCT` Purchase Line exists). It traces back to the Alert that carried the decision, and through it to the rejected quantity, the original Purchase Document/Purchase Line, and the Receiving Record/Receiving Line.

An Expected Supplier Credit may be satisfied, fully or partially, by one or more later Purchase Documents — typically a Credit Note, or a credit/adjustment carried on a later Invoice (no second credit-document ontology is created). The outstanding amount is derived, never persisted as canonical truth (`DataDictionary.md`, "Persist Facts — Derive Calculations").

An Expected Supplier Credit remains **OPEN** for as long as it takes to resolve — there is no arbitrary expiration (`BusinessRules.md`, "No Arbitrary Expiration for Long-Lived Open Supplier Issues"). It resolves only when the recognized applicable Supplier Credits satisfy the expected amount, or when a responsible User explicitly resolves it by another valid decision.

## Responsibilities

- Preserve the economic expectation created by a REJECT/RETURN decision on already-invoiced merchandise.
- Preserve every linked satisfying Purchase Document/credit fact, without ever rewriting the original rejection.
- Support reconciliation against future Supplier Purchase Documents (`BusinessRules.md`, "Credit Reconciliation Against Future Supplier Documents").
- Remain open, and keep or regenerate a Purchasing Alert as appropriate, until genuinely resolved.

---

# Validation Log

## Purpose

Represents every anomaly detected during acquisition, normalization, classification, mapping or validation — including an unknown Supplier Product, an unknown merchandise/economic classification, or an unresolved Ingredient mapping.

## Identity

Every Validation Log entry records one specific business anomaly.

Validation Logs never modify business reality.

## Responsibilities

- Preserve traceability.
- Record anomalies, including unknown/unclassified products — RF-One never invents a classification or a mapping; an unknown case is recorded here for human review rather than guessed (see `ValidationRules.md`).
- Support human validation.
