# Item Category

## Purpose

The Item Category classifies Items into logical commercial groups.

Categories provide organization, reporting, analytics and business rules without modifying the Item itself.

Every Item belongs to exactly one primary Item Category.

---

# Responsibilities

An Item Category defines:

- commercial classification
- reporting hierarchy
- analytics grouping
- default behaviors
- navigation support

It never defines:

- prices
- taxes
- availability
- recipes
- inventory

---

# Examples

Food

- Appetizers
- Pasta
- Pizza
- Main Courses
- Desserts

Drinks

- Soft Drinks
- Beer
- Wine
- Cocktails
- Coffee

Retail

- Merchandise
- Gift Cards
- Olive Oil

Services

- Delivery Fee
- Catering
- Table Service

---

# Hierarchical Structure

Categories may form a hierarchy.

Example

Food
    ├── Pizza
    ├── Pasta
    ├── Meat
    ├── Seafood
    └── Dessert

Drink
    ├── Beer
    ├── Wine
    ├── Spirits
    └── Soft Drinks

Hierarchy is optional.

Simple businesses may use a flat structure.

---

# Identity

Each Item Category has a permanent identifier.

Names may change without affecting references.

---

# Display Information

Typical fields include:

- Name
- Short Name
- Description
- Display Order
- Icon
- Color (optional)

These properties help user interfaces but have no business meaning.

---

# Default Behavior

An Item Category may provide default values for:

- Tax Category
- Modifier Groups
- Sales Channels
- Menu Placement

These defaults simplify configuration.

Individual Items may override them.

---

# Analytics

Categories are frequently used for:

- Sales by Category
- Revenue Mix
- Profitability
- Customer Preferences
- Seasonal Trends
- AI Recommendations

The Item Category is one of the primary aggregation dimensions inside RF-One Analytics.

---

# Relationships

Item Category

↓

Items

↓

Menus

↓

Sales Analytics

↓

Business Intelligence

---

# Design Principles

Categories classify Items.

They never contain Item-specific information.

Business logic belongs to dedicated entities.

Classification should remain stable over time.

---

# Multi Domain

Item Category belongs to the Core Commercial Model.

Restaurant implementations may define categories such as:

- Pizza
- Pasta
- Wine

Retail implementations may define:

- Electronics
- Clothing
- Accessories

Healthcare implementations may define:

- Consultation
- Examination
- Therapy

The concept remains identical across every business domain.