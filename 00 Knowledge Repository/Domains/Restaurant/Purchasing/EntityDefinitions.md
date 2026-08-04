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

# Purchase Document

## Purpose

Represents the official legal and commercial representation of a completed purchase.

The Purchase Document is the central business entity of the Purchasing Module.

## Identity

A Purchase Document preserves the commercial information extracted from the supplier's original document.

The original supplier document is always preserved and never modified.

The business representation may be completed or validated without altering the original document.

## Responsibilities

- Preserve legal purchasing information.
- Group Purchase Lines.
- Preserve document-level charges.
- Preserve purchasing history.

---

# Purchase Line

## Purpose

Represents one purchased item contained within a Purchase Document.

## Identity

Each Purchase Line references exactly one Supplier Product.

The supplier description is preserved exactly as received.

## Responsibilities

- Represent one purchased item.
- Preserve commercial quantity and price.
- Participate in cost normalization.

---

# Supplier Product

## Purpose

Represents the commercial product defined by one specific Supplier.

## Identity

Supplier Products belong exclusively to one Supplier.

Different Suppliers may define different Supplier Products that represent the same Ingredient.

A Supplier Product may exist before being associated with an Ingredient.

## Responsibilities

- Preserve supplier terminology.
- Preserve supplier packaging.
- Link purchasing information to Ingredients.

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

## Identity

An Ingredient is uniquely identified by:

- one Product;
- zero or more Specifications.

Ingredients are supplier independent.

Recipes always reference Ingredients.

## Responsibilities

- Standardize purchasing knowledge.
- Support Recipes.
- Support Food Cost.
- Support Inventory.
- Support Forecasting.
- Support Purchasing Intelligence.

---

# Validation Log

## Purpose

Represents every anomaly detected during acquisition, normalization or validation.

## Identity

Every Validation Log entry records one specific business anomaly.

Validation Logs never modify business reality.

## Responsibilities

- Preserve traceability.
- Record anomalies.
- Support human validation.