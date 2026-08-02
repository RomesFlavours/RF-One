# Glossary

## Purpose

This document defines the common vocabulary used throughout the Restaurant Domain.

Every term has one and only one business meaning.

---

# Supplier

A commercial organization that sells products to the restaurant.

---

# Supplier Product

The commercial product identified and described by a specific Supplier.

Supplier terminology is always preserved.

---

# Product

The generic culinary concept.

Examples:

- Tomato
- Olive Oil
- Parmesan Cheese

A Product is never purchased directly.

---

# Specification

A characteristic that qualifies a Product.

Examples:

- Italian
- DOP
- Organic
- 24 Months
- San Marzano

---

# Ingredient

The canonical culinary entity.

An Ingredient is uniquely identified by:

Product + Specifications

---

# Purchase Order

A request sent to a Supplier asking for products.

---

# Purchase Document

The legal and commercial document issued by the Supplier that represents a purchase.

It is the central entity of the Purchasing Module.

---

# Purchase Line

A single purchased item contained within a Purchase Document.

---

# Purchase History

The complete historical record of every purchase.

Historical data is never overwritten.

---

# Validation Log

The record of every anomaly detected during acquisition, normalization or validation.

---

# Supplier Price

The commercial price requested by the Supplier before any allocation.

---

# Real Ingredient Cost

The Supplier Price plus the proportional allocation of document-level costs.

---

# Effective Cost

The Real Ingredient Cost after temporary economic adjustments such as discounts, rebates or credit notes.

---

# Ingredient Mapping

The association between a Supplier Product and an Ingredient.

Mappings are validated by an authorized user.

---

# Normalization

The process of converting heterogeneous purchasing information into the Restaurant Domain standard.

All quantities are normalized into grams.

---

# Canonical Knowledge

Business knowledge expressed independently from Suppliers and acquisition technologies.

---

# Artificial Intelligence

A decision-support component that assists users by extracting information, detecting anomalies and proposing actions.

AI never owns business knowledge.

---

# Human Validation

The business approval process performed by an authorized user.

Human validation always has priority over AI suggestions.
