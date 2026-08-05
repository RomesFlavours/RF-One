# Item Category

## Purpose

An Item Category classifies Items into logical commercial groups.

Categories organize the Commercial Catalogue, simplify navigation, support reporting and analytics, and provide optional default configurations.

Every Item belongs to one primary Item Category.

---

# Responsibilities

An Item Category is responsible for:

- commercial classification
- logical organization
- navigation support
- reporting aggregation
- analytics grouping
- optional default configuration

An Item Category never defines:

- Item identity
- prices
- inventory
- purchasing
- recipes
- sales transactions
- analytics rules

Those responsibilities belong to specialized entities and domains.

---

# Hierarchy

Item Categories may optionally form a hierarchical structure.

Example

Food
    ├── Pizza
    ├── Pasta
    ├── Meat
    ├── Seafood
    └── Desserts

Drinks
    ├── Soft Drinks
    ├── Beer
    ├── Wine
    └── Cocktails

The hierarchy is optional.

Flat classifications are equally supported.

---

# Typical Attributes

- Category Id
- Name
- Short Name
- Description
- Parent Category (optional)
- Display Order
- Icon (optional)
- Status
- Created At
- Updated At

---

# Default Configuration

A Category may define default values such as:

- Tax Category
- Modifier Groups
- Sales Channels

Individual Catalogue Entries or Items may override these defaults where permitted.

---

# Relationships

Item Category

↓

Items

↓

Catalogue Entries

↓

Catalogue Versions

↓

Commercial Reporting

↓

Analytics

---

# Design Principles

Categories classify Items.

They never contain Item-specific information.

Classification should remain stable over time.

Business behavior belongs to specialized entities.

---

# Benefits

Item Categories provide:

- consistent organization
- simplified navigation
- reporting aggregation
- reusable defaults
- AI-friendly classification

---

# Multi Domain

Item Category belongs to the Commercial Catalogue domain.

The concept is industry independent.

Restaurants, retail, hospitality, healthcare and future business domains may define completely different category structures while sharing the same underlying model.