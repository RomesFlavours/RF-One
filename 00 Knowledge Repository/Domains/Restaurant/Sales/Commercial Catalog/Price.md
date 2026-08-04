# Price

## Purpose

A Price defines the selling amount of an Item within a specific Price List for a given period of time.

Prices are immutable.

When a price changes, a new Price is created while the previous one remains part of the historical record.

---

# Responsibilities

A Price defines:

- Item
- Price List
- Amount
- Currency
- Validity Period
- Status

It never defines:

- taxes
- discounts
- promotions
- sales channels

These responsibilities belong to dedicated entities.

---

# Identity

Each Price owns a permanent identifier.

A Price never changes after being created.

If the selling amount changes, a new Price is created.

---

# Validity

Every Price defines its validity period.

Typical fields include:

- Effective From
- Effective To

Only one active Price may exist for the same Item within the same Price List at any given time.

---

# Currency

Every Price belongs to a single currency.

Examples:

- USD
- EUR
- CAD
- MXN

The currency should normally match the associated Price List.

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

RF-One never overwrites prices.

Example:

Margherita Pizza

Standard Price List

01 Jan 2026 → 30 Jun 2026

USD 16.90

↓

01 Jul 2026 → Present

USD 17.90

Historical sales always reference the Price that was valid when the transaction occurred.

---

# Relationships

Price

↓

Item

↓

Price List

↓

Sales Transaction

↓

Sales Analytics

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

Price belongs to the Core Commercial Model.

Any business selling products or services may associate Items with one or more Prices through one or more Price Lists.

The mechanism used to select the appropriate Price belongs to the commercial rules of the application.