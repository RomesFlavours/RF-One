# Modifier

## Purpose

A Modifier represents a selectable option that customizes an Item without creating a new Item.

Modifiers allow customers to personalize products or services while preserving the identity of the original Item.

The same Modifier may be reused across multiple Modifier Groups.

---

# Responsibilities

A Modifier is responsible for:

- defining a commercial option
- defining a customer-visible name
- providing an optional description
- defining its activation status

A Modifier never defines:

- prices
- recipes
- inventory
- production logic
- tax rules

Those responsibilities belong to specialized domains.

---

# Typical Attributes

- Modifier Id
- Name
- Description
- Status
- Created At
- Updated At

---

# Examples

Pizza Toppings

- Extra Mozzarella
- Mushrooms
- Pepperoni
- Anchovies

Cooking Preference

- Rare
- Medium Rare
- Medium
- Well Done

Drink Options

- No Ice
- Extra Ice
- Lemon Slice

Service Options

- Gift Wrapping
- Priority Service

---

# Relationships

Modifier

↓

Modifier Group

↓

Catalogue Entry

↓

Catalogue Version

---

# Design Principles

A Modifier represents a commercial option available to the customer.

It does not define pricing, production, inventory or operational behavior.

Business domains determine how a selected Modifier affects pricing, production and fulfillment.

---

# Benefits

Modifiers provide:

- reusable customer options
- flexible product customization
- simplified catalogue configuration
- consistent customer experience
- AI-friendly commercial modeling

---

# Multi Domain

Modifier belongs to the Commercial Catalogue domain.

Restaurants, retail, hospitality, healthcare and future business domains may define completely different Modifiers while sharing the same underlying model.