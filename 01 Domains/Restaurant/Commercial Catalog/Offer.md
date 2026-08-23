# Offer

## Purpose

An Offer represents a commercial proposition made available to customers.

It combines one or more commercial entities into a marketable offering without modifying the underlying commercial catalogue.

An Offer is a native RF-One concept that supports commercial packaging independently of pricing, promotions and sales transactions.

---

# Responsibilities

An Offer is responsible for:

- defining a commercial proposition
- grouping commercial entities
- defining commercial presentation
- supporting commercial publishing

An Offer never defines:

- prices
- discounts
- promotions
- inventory
- purchasing
- sales transactions

Those responsibilities belong to specialized domains.

---

# Typical Attributes

- Offer Id
- Name
- Description
- Status
- Created At
- Updated At

---

# Components

An Offer may reference one or more commercial entities.

Supported components include:

- Item
- Bundle
- Catalogue Version
- Availability
- Price List

The same commercial entity may belong to multiple Offers.

---

# Examples

Restaurant

- Lunch Special
- Family Dinner
- Valentine's Experience

Retail

- Christmas Promotion
- Starter Package
- Office Bundle

Services

- Annual Membership
- Premium Support
- Maintenance Package

---

# Relationships

Offer

↓

Items

↓

Bundles

↓

Catalogue Versions

↓

Price Lists

↓

Availability

---

# Design Principles

An Offer is a commercial proposition presented to customers.

It reuses existing commercial entities without duplicating them.

Commercial behavior remains delegated to specialized domains.

---

# Benefits

Offers provide:

- reusable commercial propositions
- simplified merchandising
- flexible commercial packaging
- AI-friendly commercial modeling
- separation between commercial definition and commercial presentation

---

# Multi Domain

Offer belongs to the Commercial Catalogue domain.

It is industry independent and may represent commercial propositions across restaurants, retail, hospitality, healthcare and future business domains.