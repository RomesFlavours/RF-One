# Tax Category

## Purpose

A Tax Category defines the fiscal classification applied to an Item during commercial transactions.

It separates fiscal classification from commercial data, allowing Items to be sold under different tax regulations without modifying the Item itself.

Tax calculation is delegated to the Tax Engine.

---

# Responsibilities

A Tax Category is responsible for:

- defining the fiscal classification
- supporting tax reporting
- supporting accounting integration
- providing a stable tax reference

A Tax Category never defines:

- tax rates
- prices
- discounts
- promotions
- accounting entries

Those responsibilities belong to specialized fiscal and accounting domains.

---

# Typical Attributes

- Tax Category Id
- Name
- Description
- Status
- Created At
- Updated At

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

The available Tax Categories depend on local legislation.

---

# Relationships

Tax Category

↓

Items

↓

Catalogue Entries

↓

Sales Transactions

↓

Tax Engine

---

# Design Principles

A Tax Category represents a fiscal classification.

It does not define tax percentages or calculation rules.

Tax calculation belongs exclusively to the Tax Engine.

This separation guarantees:

- historical consistency
- country independence
- easier legal updates
- simpler integrations

---

# Multi Country

Different countries may implement completely different tax systems while reusing the same Tax Category model.

Examples include:

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

---

# Multi Domain

Tax Category belongs to the Commercial Catalogue domain.

Any business selling products or services may associate Items with one Tax Category.

Fiscal calculations belong to dedicated Fiscal and Accounting domains.