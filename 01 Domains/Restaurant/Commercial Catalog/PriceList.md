# Price List

## Purpose

A Price List defines a pricing strategy used to assign prices to commercial Items.

Instead of storing prices directly inside an Item, RF-One assigns prices through one or more Price Lists.

This allows the same Item to have different prices without modifying the Item itself.

---

# Responsibilities

A Price List is responsible for:

- defining a pricing strategy
- defining a validity period
- defining a currency
- defining its activation status

A Price List never defines:

- Items
- price values
- taxes
- discounts
- promotions
- sales channels

Individual prices are defined by the Price entity.

---

# Typical Attributes

- Price List Id
- Name
- Description
- Currency
- Status
- Effective From
- Effective To
- Created At
- Updated At

---

# Examples

Typical Price Lists include:

- Standard
- Holiday
- Summer
- Employee
- VIP
- Wholesale
- Franchise
- Promotional

The business determines the meaning of each Price List.

---

# Relationships

Price List

↓

Prices

↓

Catalogue Entries

↓

Catalogue Versions

---

# Design Principles

A Price List represents a pricing strategy.

It does not determine where or when it is used.

Commercial domains decide which Price List applies in each business context.

Keeping these concepts independent allows:

- multiple pricing strategies
- seasonal pricing
- customer-specific pricing
- regional pricing
- historical pricing

without modifying Items or Catalogue Versions.

---

# Multi Domain

Price List belongs to the Commercial Catalogue domain.

Any business selling products or services may define multiple Price Lists to support different pricing strategies.