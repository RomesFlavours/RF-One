# Modifier Group

## Purpose

A Modifier Group defines a collection of Modifiers that may be presented together as a set of customer choices.

Modifier Groups organize configurable options without modifying the Item itself.

The same Modifier Group may be reused across multiple Catalogue Entries.

---

# Responsibilities

A Modifier Group is responsible for:

- organizing related Modifiers
- defining selection rules
- defining minimum selections
- defining maximum selections
- defining required or optional selection
- defining display order

A Modifier Group never defines:

- prices
- recipes
- inventory
- production logic

Those responsibilities belong to specialized domains.

---

# Typical Attributes

- Modifier Group Id
- Name
- Description
- Minimum Selection
- Maximum Selection
- Required
- Multiple Selection Allowed
- Display Order
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

Drink Size

- Small
- Medium
- Large

Extras

- Extra Sauce
- No Onion
- Dressing on Side

---

# Relationships

Modifier Group

↓

Modifiers

↓

Catalogue Entries

↓

Catalogue Versions

---

# Design Principles

Modifier Groups define customer choices.

They do not define how those choices affect production, inventory, pricing or recipes.

Operational behavior belongs to specialized domains.

---

# Benefits

Modifier Groups provide:

- reusable option sets
- consistent customer experience
- simplified catalogue configuration
- flexible merchandising
- AI-friendly commercial modeling

---

# Multi Domain

Modifier Group belongs to the Commercial Catalogue domain.

Restaurants, retail, hospitality, healthcare and future business domains may define completely different Modifier Groups while reusing the same underlying model.