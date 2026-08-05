# Commercial Catalogue

## Purpose

The Commercial Catalogue defines every commercial entity that an organization may offer to its customers.

It provides a single source of truth for Items and their commercial configuration, independently of sales transactions, operational processes and business domains.

The Commercial Catalogue exists independently from Sales, Inventory, Purchasing, Production and Analytics.

Products and services may be created, published, modified or discontinued without affecting historical business data.

---

# Responsibilities

The Commercial Catalogue is responsible for defining:

- Catalogues
- Catalogue Versions
- Catalog Publications
- Catalogue Entries
- Items
- Item Categories
- Item Groups
- Brands
- Units of Measure
- Prices
- Price Lists
- Tax Categories
- Availability
- Modifier Groups
- Modifiers
- Bundles
- Offers
- Sales Channels

It represents the commercial definition of everything that may be offered to customers.

---

# Design Principles

The Commercial Catalogue contains only commercial definitions.

It never manages:

- Orders
- Sales Transactions
- Payments
- Inventory
- Purchasing
- Recipes
- Production
- Accounting
- Analytics

Those responsibilities belong to dedicated domains.

---

# Domain Architecture

The Commercial Catalogue is organized around four fundamental concepts:

```text
Catalogue
    │
    ▼
Catalogue Version
    │
    ▼
Catalog Publication
    │
    ▼
Sales Channel

Catalogue Version
    │
    ▼
Catalogue Entry
    │
    ├── Item
    ├── Price
    ├── Tax Category
    ├── Availability
    ├── Modifier Groups
    ├── Brand
    ├── Item Category
    └── Unit Of Measure
```

This architecture separates commercial definitions from commercial publication, allowing the same commercial model to be reused across multiple locations, channels and business contexts.

---

# Relationships

The Commercial Catalogue is referenced by multiple business domains, including:

- Sales
- Purchasing
- Inventory
- Production
- Marketing
- Analytics

The Commercial Catalogue owns none of these domains, and none of these domains own the Commercial Catalogue.

---

# Business Principles

A Commercial Catalogue may exist before the business starts selling.

Catalogue Versions may be published independently to different Sales Channels.

Historical business transactions remain valid even when commercial definitions evolve.

Commercial publication is independent from commercial definition.

---

# Goal

The goal of the Commercial Catalogue is to provide a single, consistent, extensible and reusable commercial model that can support multiple industries, locations, sales channels and commercial strategies while remaining independent from any specific POS or business implementation.