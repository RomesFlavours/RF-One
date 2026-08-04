# Item

## Purpose

The Item represents any commercial entity that can be sold by an Operational Unit.

It is the core entity of the Commercial Catalog.

Every commercial operation references an Item.

Prices, taxes, availability, menus, modifiers and analytics are defined through specialized entities connected to the Item.

The Item itself never contains operational rules.

---

# Responsibilities

An Item defines:

- commercial identity
- commercial description
- customer visibility
- searchability
- classification

An Item never defines:

- price
- taxes
- availability
- menu placement
- discounts
- promotions

Those responsibilities belong to dedicated entities.

---

# Examples

Food

- Margherita Pizza
- Lasagna
- Carbonara

Drinks

- Coca Cola
- Beer
- Wine Bottle

Services

- Delivery Fee
- Table Service

Retail

- Olive Oil
- T-Shirt
- Gift Card

---

# Identity

Every Item owns a unique identifier that never changes.

Names and descriptions may evolve over time without changing the Item identity.

---

# Customer Information

Typical customer-facing information includes:

- Name
- Short Name
- Description
- Images
- Allergens
- Nutritional Information (optional)
- Marketing Description

---

# Internal Information

Operational data may include:

- Internal Name
- SKU
- Barcode
- POS Code
- Accounting Code

These identifiers exist only for integrations and internal processes.

---

# Classification

Each Item belongs to one Item Category.

Examples:

Food

Drink

Dessert

Wine

Beer

Service

Retail

Gift Card

Merchandise

The classification allows reporting, taxation and menu organization.

---

# Relationships

Item

↓

Item Category

↓

Price

↓

Tax Category

↓

Availability

↓

Modifier Groups

↓

Menus

↓

Sales Channels

↓

Recipes (Restaurant Domain)

↓

Inventory (Inventory Domain)

↓

Purchasing (Purchasing Domain)

---

# Design Principles

The Item must remain intentionally simple.

Commercial behavior must never be stored directly inside the Item.

Every business rule belongs to specialized entities.

This guarantees:

- historical consistency

- extensibility

- simpler integrations

- easier AI reasoning

- lower maintenance

---

# Multi Domain

The Item belongs to the Core Commercial Model.

Restaurant-specific information such as recipes, ingredients, preparation time or kitchen workflow are defined inside the Restaurant Domain.

Retail implementations may associate Items with inventory only.

Service businesses may associate Items with appointments or subscriptions.

The Item remains identical across every industry.
