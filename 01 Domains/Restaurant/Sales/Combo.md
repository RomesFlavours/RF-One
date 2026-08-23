# Combo

## Purpose

A Combo represents a commercial offering composed of two or more Items.

The structure of a Combo is defined by the originating commercial system or POS.

RF-One stores the Combo and, when available, the relationship between the Combo and its component Items.

---

# Responsibilities

A Combo is responsible for:

- identifying the parent Item
- referencing component Items
- defining component quantities
- defining component sequence (optional)

A Combo never defines:

- pricing rules
- discounts
- promotions
- selection logic
- sales workflow

Those responsibilities belong to the originating commercial system or specialized business domains.

---

# Typical Attributes

- Combo Id
- Parent Item
- Status
- Created At
- Updated At

---

# Components

A Combo references one or more Items.

Each component may define:

- Item
- Quantity
- Sequence (optional)

The interpretation of component information depends on the originating system.

---

# Supported Scenarios

RF-One supports different levels of information.

Scenario 1

The originating system exposes only the Combo Item.

Scenario 2

The originating system exposes the Combo Item and all component Items.

RF-One preserves whichever model is provided without inferring missing information.

---

# Relationships

Combo

↓

Parent Item

↓

Component Items

---

# Design Principles

A Combo extends the Commercial Catalogue without imposing a specific implementation.

RF-One preserves information received from external systems while remaining independent of any particular POS.

---

# Benefits

Combos provide:

- reusable commercial bundles
- compatibility with multiple POS systems
- simplified commercial modeling
- accurate analytical representation
- AI-friendly bundle analysis

---

# Multi Domain

Combo belongs to the Commercial Catalogue domain.

It may represent predefined bundles of products or services in restaurants, retail, hospitality, healthcare and future business domains.