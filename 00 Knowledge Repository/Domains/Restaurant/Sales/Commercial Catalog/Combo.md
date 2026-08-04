# Combo

## Purpose

A Combo represents a commercial offering composed of one or more Items.

The structure of a Combo is defined by the originating POS or commercial system.

RF-One stores the Combo and, when available, the relationship between the Combo and its component Items.

---

# Responsibilities

A Combo defines:

- parent Item
- component Items
- component quantities
- component order (optional)

It never defines:

- pricing rules
- discounts
- promotions
- selection logic
- sales workflow

These responsibilities belong to the originating commercial system.

---

# Examples

Lunch Combo

- Hamburger
- French Fries
- Soft Drink

Family Meal

- Pizza Margherita
- Pizza Diavola
- Garlic Bread
- Coca Cola

Breakfast Combo

- Coffee
- Croissant
- Orange Juice

---

# Components

A Combo references one or more Items.

Each component may define:

- Item
- Quantity
- Sequence (optional)

The interpretation of component information depends on the originating POS.

---

# Optional Structure

Not every POS exposes Combo details.

Possible scenarios include:

Scenario 1

The POS exposes only the Combo Item.

Scenario 2

The POS exposes the Combo Item and all component Items.

RF-One supports both models.

---

# Relationships

Combo

↓

Parent Item

↓

Component Items

↓

Sales Transactions

↓

Sales Analytics

---

# Design Principles

A Combo extends the commercial catalog without imposing a specific implementation.

RF-One preserves the information received from the originating system without generating or inferring missing component relationships.

---

# Multi Domain

Combo belongs to the Core Commercial Model.

The concept may be applied to any business that sells predefined bundles of products or services.

Examples include:

- Restaurant meal deals
- Retail product bundles
- Service packages
- Subscription plans