# Modifier

## Purpose

A Modifier represents a selectable option that customizes an Item during a sales transaction.

Modifiers allow customers to personalize products or services without creating new Items.

---

# Responsibilities

A Modifier defines:

- commercial option
- customer-visible name
- optional description
- additional price
- display order
- activation status

It never defines:

- recipes
- inventory
- preparation logic
- tax rules
- production workflow

These responsibilities belong to dedicated business domains.

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

# Pricing

A Modifier may:

- have no additional cost
- increase the Item price
- decrease the Item price

The price adjustment applies only when the Modifier is selected.

---

# Availability

A Modifier may be:

- Active
- Inactive

Inactive Modifiers remain available for historical transactions but cannot be selected in new sales.

---

# Assignment

A Modifier belongs to one or more Modifier Groups.

The same Modifier may be reused across multiple Modifier Groups.

---

# Relationships

Modifier

↓

Modifier Group

↓

Items

↓

Sales Transactions

---

# Design Principles

A Modifier represents a commercial option available to the customer.

It does not define how the business fulfills that option.

Operational behavior belongs to the corresponding business domain.

---

# Multi Domain

Modifier belongs to the Core Commercial Model.

Restaurant examples:

- Extra Cheese
- No Onion
- Well Done

Retail examples:

- Gift Wrapping
- Extended Warranty

Service examples:

- Express Delivery
- Home Service

The concept remains identical across every business domain.