# Item

## Purpose

An Item represents a commercial entity that may be published, purchased, sold, consumed, produced or otherwise managed by the system.

It is the fundamental business entity of the Commercial Catalogue.

The Item contains only its permanent identity and descriptive information.

All commercial, operational and analytical behaviors are delegated to specialized entities.

---

# Responsibilities

An Item is responsible for:

- business identity
- business description
- classification
- searchability
- permanent metadata

An Item never defines:

- prices
- taxes
- availability
- catalogue placement
- recipes
- inventory
- purchasing
- sales
- promotions
- analytics

Those responsibilities belong to specialized domains.

---

# Identity

Every Item owns a unique identifier that never changes.

Names, descriptions and commercial publications may evolve over time without affecting the Item identity.

---

# Typical Attributes

- Item Id
- Name
- Short Name
- Description
- Internal Name
- SKU
- Barcode
- Status
- Created At
- Updated At

---

# Classification

Every Item belongs to one Item Category.

Additional classifications may be introduced through specialized entities without modifying the Item itself.

---

# Relationships

Item

↓

Item Category

↓

Catalogue Entry

↓

Price

↓

Tax Category

↓

Availability

↓

Modifier Groups

↓

Recipe (Restaurant Domain)

↓

Inventory (Inventory Domain)

↓

Purchasing (Purchasing Domain)

↓

Sales (Sales Domain)

---

# Design Principles

The Item is intentionally simple.

It contains only information that identifies the business object.

Everything that changes over time belongs to specialized entities.

This guarantees:

- historical consistency
- extensibility
- simpler integrations
- easier AI reasoning
- lower maintenance

---

# Examples

Restaurant

- Margherita Pizza
- Lasagna
- Coca-Cola
- House Wine

Retail

- Olive Oil
- T-Shirt
- Gift Card

Services

- Delivery Fee
- Table Service

---

# Multi Domain

The Item belongs to the Commercial Catalogue domain.

It is independent of any specific industry.

Restaurant, Retail, Hospitality, Healthcare and future domains reuse the same Item while attaching their own domain-specific information through dedicated entities.

---

# Vision

The Item is the single source of truth for every commercial entity managed by RF-One.

It is published through Catalogue Entries, organized by Catalogue Versions, and enriched by specialized domains without ever changing its core identity.