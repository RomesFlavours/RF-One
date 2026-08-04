# Tax Category

## Purpose

The Tax Category defines how an Item is taxed during a sales transaction.

It separates fiscal rules from the commercial catalog, allowing the same Item to be sold under different tax regulations without modifying the Item itself.

---

# Responsibilities

A Tax Category defines:

- fiscal classification
- applicable tax rules
- tax reporting classification
- accounting integration

It never defines:

- tax rates
- prices
- discounts
- promotions
- accounting entries

Tax calculation is the responsibility of the Tax Engine.

---

# Examples

Typical Tax Categories include:

- Standard
- Reduced
- Zero Rated
- Tax Exempt
- Alcohol
- Tobacco
- Gift Card
- Service

The available categories depend on the country's tax legislation.

---

# Tax Rate

A Tax Category does not contain tax percentages.

Tax rates change over time.

Historical tax rates are managed separately by the Tax Engine or Fiscal Module.

Example:

Tax Category:
Standard

Historical Rates

2023 → 7%

2025 → 7.5%

The Item always references the same Tax Category.

---

# Identity

Each Tax Category owns a permanent identifier.

Names and descriptions may evolve without affecting historical transactions.

---

# Relationships

Tax Category

↓

Items

↓

Sales Transactions

↓

Tax Engine

↓

Accounting

---

# Design Principles

Tax rules are external to the Item.

Commercial data and fiscal data must remain independent.

This guarantees:

- historical consistency
- country independence
- easier legal updates
- simpler integrations

---

# Multi Country

Different countries may implement completely different tax systems.

Examples

Italy

- IVA 22%
- IVA 10%
- IVA 5%
- IVA Exempt

United States

- Taxable
- Non Taxable

Canada

- GST
- PST
- HST

The Tax Category remains identical regardless of the fiscal model.

---

# Multi Domain

Tax Category belongs to the Core Commercial Model.

Every business that sells products or services may associate Items with one Tax Category.

The fiscal calculation itself belongs to dedicated Fiscal or Accounting modules.