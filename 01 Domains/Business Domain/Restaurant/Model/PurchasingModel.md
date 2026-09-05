# Purchasing Module Map (Restaurant Domain)

## Purpose

This document defines the business entities that compose the Purchasing Module and the relationships between them.

It provides the conceptual map of the module independently from implementation, database design or user interface.

Business rules are documented elsewhere.

---

# Domain Overview

The Purchasing Module transforms supplier purchasing information into canonical Restaurant knowledge.

Its central business entity is the Purchase Document.

Every other entity exists to support the acquisition, normalization and historical preservation of purchasing information.

---

# Core Entities

```
Supplier
    │
    ├── Purchase Order
    │        │
    │        └── Purchase Order Line (Item, Quantity — minimum needed for
    │                                 reconciliation; Order module not designed)
    │
    ├── Purchase Document
    │        │
    │        ├── Purchase Line (line_type = PRODUCT)
    │        │        │
    │        │        └── Supplier Product (when known)
    │        │                  │
    │        │                  ▼
    │        │        Merchandise / Economic Classification
    │        │                  │
    │        │                  ▼ (Food/Ingredient context only)
    │        │             Ingredient
    │        │                  ▲
    │        │                  │
    │        │          Product + Specifications
    │        │
    │        ├── Purchase Line (line_type = SURCHARGE)
    │        │        (no Supplier Product, no classification)
    │        │
    │        ├── Purchase Line (line_type = DISCOUNT)
    │        │        (no Supplier Product, no classification)
    │        │
    │        └── Validation Log
    │
    └── Receiving Record (physical observation — Order and Purchase Document
                related when known, neither required)
             │
             └── Receiving Line (observed item; no related Purchase Order Line
                                  → Extra/Unexpected Item)

Supplier Product
    │
    └── Configured Expectation (approved commercial configuration, when set)

Alert (Trigger = CONFIGURATION_DEVIATION or RECEIVING_DISCREPANCY)
    │
    ├── CONFIGURATION_DEVIATION → Purchase Line vs Configured Expectation /
    │                             previous purchase (Purchasing/EntityDefinitions.md, "Alert")
    │
    └── RECEIVING_DISCREPANCY → Receiving Line vs Purchase Order Line / Purchase Line
                                  (three-way reconciliation) → Human Decision
                                  ACCEPT or REJECT/RETURN
                                       │
                                       └── REJECT/RETURN + already invoiced
                                                → Expected Supplier Credit
                                                → future Credit Note / Invoice adjustment
                                                → Credit reconciliation
```

---

# Entity Responsibilities

## Supplier

Represents the commercial organization providing products to the restaurant.

---

## Purchase Order

Represents the purchasing request sent to a Supplier.

One Purchase Order may generate one or more Purchase Documents.

---

## Purchase Document

Represents the legal and commercial document issued by the Supplier.

It is the central business entity of the Purchasing Module.

---

## Purchase Line

Represents one real line contained in a Purchase Document — a purchased product (`PRODUCT`), a document-level surcharge (`SURCHARGE`), or a document-level discount (`DISCOUNT`).

Only a `PRODUCT` Purchase Line may reference a Supplier Product; `SURCHARGE` and `DISCOUNT` lines never do (see `Purchasing/EntityDefinitions.md`).

---

## Supplier Product

Represents the commercial product defined by one specific Supplier.

Supplier Products preserve supplier terminology.

Multiple Supplier Products may represent the same Ingredient.

---

## Ingredient

Represents the canonical culinary entity used throughout the Restaurant Domain.

Ingredients are supplier independent.

---

## Product

Represents the generic culinary concept.

Products become Ingredients through Specifications.

---

## Specification

Represents one business characteristic that qualifies a Product.

The combination of Product and Specifications uniquely identifies an Ingredient.

---

## Validation Log

Stores every anomaly detected during acquisition, extraction, normalization and validation.

Validation Logs preserve business traceability.

---

## Configured Expectation

Represents the Restaurant's approved commercial configuration(s) for a Supplier Product (e.g. packaging, pack count, pack size, unit, brand, variant, grade).

Takes precedence over the previous-purchase fallback when detecting a variation. Changes only through an explicit Human Decision; never rewrites historical Purchase Lines.

---

## Alert

Represents a case where RF-One knows what actually happened but Reality deviates from an operational expectation. Raised by one of two triggers: a `PRODUCT` Purchase Line's observed commercial configuration deviating from the Configured Expectation/previous purchase, or a Receiving Line revealing a discrepancy against the Order/Invoice (three-way reconciliation).

Distinct from Validation Log (identity/interpretation uncertainty) and from a plain Notification (no response required). Remains Open until acknowledged and, when required, decided by a responsible User.

---

## Purchase Order Line

Represents one requested item and quantity on a Purchase Order — the minimum information needed to serve as the "Order" side of reconciliation. The Order/Purchase Support capability that creates it is not designed here.

---

## Receiving Record / Receiving Line

Represents the Restaurant's own observation of what physically arrived — Physical Receiving, independent of the Order and of the Purchase Document. A Receiving Line with no related Purchase Order Line is an Extra/Unexpected Item. Receiving records Reality; it never decides commercial acceptability.

---

## Expected Supplier Credit

Represents the operational expectation that a Supplier owes an economic correction, created when already-invoiced merchandise is rejected/returned. Resolved, fully or partially, by a later Credit Note or invoice adjustment; remains Open indefinitely until genuinely satisfied.

---

# Business Flow

```
Supplier

↓

Purchase Order

↓

Purchase Document

↓

Purchase Line (PRODUCT)

↓

Supplier Product

↓

Merchandise / Economic Classification

↓ (Food/Ingredient context only)

Ingredient

↓

Recipe / Inventory / Food Cost
```

Derived category totals (Food, Drink, Supplies) from the classification step are exposed to Administration regardless of whether the Food/Ingredient/Recipe branch applies — see `Purchasing/BusinessRules.md`, "Purchasing Precedes Administration and Taxation."

---

# Module Boundaries

The Purchasing Module provides standardized purchasing knowledge.

The following modules consume that knowledge:

- Recipes
- Inventory
- Food Cost
- Forecasting
- Purchasing Intelligence

The Purchasing Module never depends on their internal implementation.

---

# Architectural Principles

- Purchase Document is the central business entity.
- Ingredients are the canonical purchasing target.
- Supplier terminology is always preserved.
- Business knowledge is supplier independent.
- Product plus Specifications uniquely identify an Ingredient.
- Validation never modifies business reality.
- A commercial configuration change never changes Product/Ingredient identity by itself.
- A Configured Expectation, once approved, prevails over the previous-purchase fallback.
- Order, Invoice and Physical Receiving are three independent sources of Purchase Reality, reconciled rather than collapsed into one.
- A rejection/return is preserved alongside the original Receiving observation, never rewritten as if the merchandise had never arrived.