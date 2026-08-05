# Price

## Purpose

A Price defines the monetary value assigned to an Item within a specific Price List.

Prices are immutable.

Whenever a price changes, a new Price is created while the previous one remains part of the historical record.

---

# Responsibilities

A Price is responsible for:

- defining the monetary amount
- associating an Item with a Price List
- defining its validity period
- defining its status

A Price never defines:

- taxes
- discounts
- promotions
- sales channels

Those responsibilities belong to specialized entities and domains.

---

# Typical Attributes

- Price Id
- Item
- Price List
- Amount
- Currency
- Effective From
- Effective To
- Status
- Created At

---

# Validity

Every Price defines its validity period.

Typical fields include:

- Effective From
- Effective To

Only one active Price may exist for the same Item within the same Price List at any given time.

---

# Status

A Price may be:

- Scheduled
- Active
- Expired
- Cancelled

Status is determined by its validity period or business decisions.

---

# Historical Pricing

RF-One never modifies existing Prices.

Whenever a selling price changes, a new Price is created.

Historical transactions always reference the Price that was valid when the transaction occurred.

This guarantees complete pricing history.

---

# Relationships

Price

↓

Item

↓

Price List

↓

Catalogue Entry

↓

Sales Transactions

---

# Design Principles

Prices are immutable.

Historical information must never be lost.

Pricing strategies evolve by creating new Price records rather than modifying existing ones.

This guarantees:

- historical consistency
- accurate reporting
- reliable analytics
- AI-friendly historical analysis

---

# Multi Domain

Price belongs to the Commercial Catalogue domain.

Any business selling products or services may associate Items with multiple Prices through one or more Price Lists.

Commercial domains determine which Price is applied in each business context.