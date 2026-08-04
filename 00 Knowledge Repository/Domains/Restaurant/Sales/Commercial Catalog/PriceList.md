# Price List 

## Purpose v1,1

A Price List defines a collection of prices that represent a specific pricing strategy.

Instead of storing prices directly inside an Item, RF-One assigns prices through one or more Price Lists.

This allows the same Item to be sold at different prices without modifying the Item itself.

---

# Responsibilities

A Price List defines:

- pricing strategy
- validity period
- currency
- activation status

It never defines:

- Items
- prices
- taxes
- discounts
- promotions
- sales channels

Individual prices are defined by the Price entity.

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

The meaning of each Price List is entirely defined by the business.

---

# Activation

A Price List may be:

- Active
- Inactive

Only active Price Lists may be used during sales transactions.

---

# Validity

A Price List may optionally define:

- Start Date
- End Date

This allows seasonal or temporary pricing without modifying Items or Prices.

Example:

Standard Price List

Always active

Holiday Price List

December 1 → January 6

---

# Currency

Each Price List belongs to a single currency.

Examples:

- USD
- EUR
- CAD
- MXN

Multi-country organizations typically maintain one or more Price Lists for each currency.

---

# Assignment

A Price List does not determine where it is used.

The association between a Price List and a business context is managed by dedicated entities such as:

- Sales Channel
- Customer Group
- Store
- Promotion Engine

This keeps pricing independent from commercial policies.

---

# Relationships

Price List

↓

Prices

↓

Items

↓

Sales Transactions

Sales Channels

Customer Groups

Promotions

---

# Design Principles

A Price List represents a pricing strategy.

Commercial policies determine which Price List is applied during a sale.

Keeping these concepts independent allows:

- multiple pricing strategies
- seasonal pricing
- customer-specific pricing
- regional pricing
- historical pricing

without modifying either the Item or the sales process.

---

# Multi Domain

Price List belongs to the Core Commercial Model.

Any business selling products or services may use multiple Price Lists to support different pricing strategies.

The mechanism used to select the appropriate Price List belongs to the commercial rules of the specific domain.