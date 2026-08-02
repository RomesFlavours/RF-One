# Purchasing Domain Map

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
    │
    └── Purchase Document
            │
            ├── Purchase Line
            │        │
            │        └── Supplier Product
            │                  │
            │                  ▼
            │             Ingredient
            │                  ▲
            │                  │
            │          Product + Specifications
            │
            └── Validation Log
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

Represents one purchased item contained in a Purchase Document.

Every Purchase Line references one Supplier Product.

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

# Business Flow

```
Supplier

↓

Purchase Order

↓

Purchase Document

↓

Purchase Line

↓

Supplier Product

↓

Ingredient

↓

Recipe / Inventory / Food Cost
```

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