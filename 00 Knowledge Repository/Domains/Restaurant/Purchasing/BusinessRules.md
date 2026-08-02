# Purchasing Business Rules

## Purpose

This document defines the immutable business rules governing the Purchasing Module.

Business Rules describe how the restaurant purchasing domain behaves.

They are independent from software implementation, database design and user interface.

---

# Rule 1 – Every Purchase Generates One Purchase Document

Every purchasing event must generate exactly one Purchase Document.

The Purchase Document represents the legal and commercial evidence of the purchase.

The acquisition method is irrelevant.

---

# Rule 2 – The Purchase Document Is Immutable

The original Purchase Document is never modified.

Corrections, interpretations and validations are stored separately.

The supplier document always represents business reality.

---

# Rule 3 – Every Purchase Line References One Supplier Product

Each Purchase Line must reference exactly one Supplier Product.

Supplier terminology is always preserved.

---

# Rule 4 – Every Supplier Product References One Ingredient

Every Supplier Product must be mapped to exactly one Ingredient.

The mapping is approved by an authorized user.

Artificial Intelligence may only propose mappings.

Many Supplier Products may reference the same Ingredient.

---

# Rule 5 – Ingredients Are Supplier Independent

Ingredients belong to the Restaurant Domain.

Suppliers never define Ingredients.

Supplier Products only reference existing Ingredients.

---

# Rule 6 – Product and Specifications Define Ingredient Identity

An Ingredient is uniquely identified by:

- Product
- Specifications

Changing one or more Specifications creates a different Ingredient.

---

# Rule 7 – Internal Quantities Are Standardized

Every purchasable Ingredient is internally represented using grams.

Commercial purchasing units are preserved only as supplier information.

---

# Rule 8 – Ingredient Cost Is Standardized

The Purchasing Module calculates:

- Supplier Price
- Real Ingredient Cost
- Effective Cost

The standardized cost is always expressed as cost per gram.

---

# Rule 9 – Document-Level Costs Are Allocated

Costs that do not belong to individual Purchase Lines are proportionally allocated across all purchased products.

Examples include:

- Delivery
- Fuel Surcharge
- Service Fees
- Environmental Fees

The allocation becomes part of the Real Ingredient Cost.

---

# Rule 10 – Temporary Discounts Remain Independent

Temporary commercial discounts affect Food Cost.

They do not modify historical purchasing knowledge.

Supplier evaluation is based on Real Ingredient Cost rather than temporary promotions.

---

# Rule 11 – Purchasing History Is Permanent

Every validated purchase becomes part of the permanent Purchase History.

Historical purchasing information is never overwritten.

New purchases create new history.

---

# Rule 12 – Validation Never Changes Reality

Validation records business anomalies.

Validation never modifies the original Purchase Document.

Every anomaly is stored inside the Validation Log.

---

# Rule 13 – Human Knowledge Has Priority

Artificial Intelligence supports business decisions.

Only authorized users may:

- create Ingredients;
- approve Ingredient mappings;
- resolve Validation Logs;
- make business decisions.

---

# Rule 14 – The Purchasing Module Produces Knowledge

The objective of the Purchasing Module is not to manage suppliers.

Its objective is to transform purchasing information into standardized Restaurant knowledge.

---

# Rule 15 – The Purchase Document Is the Single Source of Truth

Every purchasing calculation originates from the Purchase Document.

No downstream module may alter purchasing history.

Recipes, Inventory, Food Cost and Forecasting consume purchasing knowledge but never modify it.

---

# Design Principles

- Preserve business reality.
- Preserve supplier terminology.
- Standardize purchasing knowledge.
- Separate supplier information from restaurant knowledge.
- Preserve historical information.
- Human knowledge prevails over Artificial Intelligence.