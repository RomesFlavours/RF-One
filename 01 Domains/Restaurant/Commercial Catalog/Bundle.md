# Bundle

## Purpose

A Bundle represents a reusable commercial offering composed of two or more commercial entities.

Unlike a Combo, which is defined by the originating POS, a Bundle is a native RF-One concept used to create commercial packages independently of any external system.

A Bundle may contain Items, other Bundles and, when supported, external Combos.

---

# Responsibilities

A Bundle is responsible for:

- grouping commercial entities
- defining reusable commercial packages
- supporting merchandising
- supporting marketing campaigns
- simplifying commercial configuration

A Bundle never defines:

- inventory
- purchasing
- production workflow
- sales transactions

Those responsibilities belong to specialized business domains.

---

# Typical Attributes

- Bundle Id
- Name
- Description
- Status
- Created At
- Updated At

---

# Components

A Bundle may contain one or more commercial entities.

Supported components include:

- Item
- Bundle
- Combo (optional)

Each component may define:

- Quantity
- Display Order
- Optional Notes

The same component may belong to multiple Bundles.

---

# Examples

Restaurant

- Family Dinner
- Italian Experience
- Wine Tasting

Retail

- Christmas Basket
- Starter Kit
- Office Package

Services

- Premium Membership
- Installation Package
- Annual Maintenance

---

# Relationships

Bundle

↓

Items

↓

Bundles

↓

Combos (optional)

↓

Catalogue Entries

---

# Design Principles

A Bundle is a commercial construct created by RF-One.

It is independent of any specific POS implementation.

Bundles promote reuse and simplify the creation of complex commercial offerings without duplicating Items.

---

# Benefits

Bundles provide:

- reusable commercial packages
- simplified merchandising
- flexible product composition
- AI-friendly commercial modeling
- independence from external systems

---

# Multi Domain

Bundle belongs to the Commercial Catalogue domain.

It is industry independent and may represent commercial packages in restaurants, retail, hospitality, healthcare and future business domains.