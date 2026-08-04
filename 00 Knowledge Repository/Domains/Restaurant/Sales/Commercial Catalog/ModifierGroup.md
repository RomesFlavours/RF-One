# Modifier Group

## Purpose

A Modifier Group defines a collection of selectable Modifiers that may be applied to an Item during a sales transaction.

Modifier Groups organize customer choices without changing the Item itself.

---

# Responsibilities

A Modifier Group defines:

- available modifiers
- selection rules
- minimum selections
- maximum selections
- required or optional selection
- display order

It never defines:

- prices
- recipes
- inventory
- preparation logic

These responsibilities belong to dedicated entities.

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

# Selection Rules

A Modifier Group may define:

- Minimum Selection
- Maximum Selection
- Required
- Multiple Selection Allowed

Examples

Pizza Toppings

Minimum: 0

Maximum: 5

Multiple Selection: Yes

Cooking Preference

Minimum: 1

Maximum: 1

Multiple Selection: No

---

# Assignment

A Modifier Group may be assigned to one or more Items.

Example

Margherita Pizza

↓

Pizza Toppings

↓

Cooking Preference

↓

Extra Sauces

The same Modifier Group may be reused across multiple Items.

---

# Display

A Modifier Group may define:

- Display Name
- Display Order
- Visibility

These properties affect only the customer experience.

---

# Relationships

Modifier Group

↓

Modifiers

↓

Items

↓

Sales Transactions

---

# Design Principles

Modifier Groups define customer choices.

They do not define how those choices affect production, inventory or recipes.

Operational effects belong to the business domain implementation.

---

# Multi Domain

Modifier Group belongs to the Core Commercial Model.

Restaurant examples:

- Pizza Toppings
- Cooking Preference
- Side Dishes

Retail examples:

- Color
- Size
- Warranty

Service examples:

- Priority Service
- Home Visit
- Gift Wrapping

The concept remains identical across every business domain.