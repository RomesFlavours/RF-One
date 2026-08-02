# Purchasing Workflow

## Purpose

This document describes the business workflow of the Purchasing Module.

It explains how purchasing knowledge is created from supplier information.

Implementation details are intentionally excluded.

---

# Workflow Overview

The Purchasing Workflow transforms a supplier purchase into standardized Restaurant knowledge.

Every purchase follows the same logical process regardless of how the information is acquired.

```
Supplier

↓

Purchase Order (optional)

↓

Purchase Document

↓

Purchase Line Extraction

↓

Supplier Product Recognition

↓

Ingredient Mapping

↓

Quantity Normalization

↓

Cost Normalization

↓

Validation

↓

Purchase History

↓

Restaurant Knowledge
```

---

# Step 1 – Purchase Document Acquisition

The workflow begins when a Purchase Document becomes available.

Supported acquisition methods include:

- Paper Invoice
- PDF Invoice
- XML
- EDI
- Supplier API
- Manual Entry

The acquisition method does not change the business workflow.

---

# Step 2 – Purchase Document Creation

The original supplier document is preserved.

A Purchase Document is created inside the Purchasing Module.

The Purchase Document becomes the official business representation of the purchase.

---

# Step 3 – Purchase Line Extraction

Every purchased item is extracted as an individual Purchase Line.

Each Purchase Line preserves:

- Supplier description
- Quantity
- Purchase Unit
- Supplier Price

No information is modified during extraction.

---

# Step 4 – Supplier Product Recognition

Each Purchase Line references one Supplier Product.

If the Supplier Product already exists, it is reused.

Otherwise a new Supplier Product is created.

---

# Step 5 – Ingredient Mapping

Every Supplier Product must reference one Ingredient.

If a mapping already exists, it is reused.

Otherwise:

- AI may suggest one or more Ingredients.
- A human validates the final mapping.

Approved mappings become part of the Restaurant Knowledge Base.

---

# Step 6 – Quantity Normalization

Every quantity is converted into the Restaurant standard.

Internal standard:

- grams

Liquids are converted using the Ingredient Density.

Commercial purchasing units remain preserved.

---

# Step 7 – Cost Normalization

The Purchasing Module calculates:

- Supplier Price
- Real Ingredient Cost
- Effective Cost

Document-level costs are proportionally allocated across Purchase Lines.

Temporary discounts remain separate from historical purchasing knowledge.

---

# Step 8 – Validation

Every anomaly generates one Validation Log entry.

Examples include:

- Unknown Supplier Product
- OCR uncertainty
- Unknown unit
- Missing quantity
- Missing price
- Ambiguous Ingredient mapping

Validation never modifies the original Purchase Document.

---

# Step 9 – Purchase History

Once validated, purchasing information becomes part of the permanent Purchase History.

Historical information is never overwritten.

---

# Step 10 – Restaurant Knowledge

Standardized purchasing knowledge becomes immediately available to:

- Recipes
- Inventory
- Food Cost
- Forecasting
- Purchasing Intelligence

The Purchasing Module has completed its responsibility.

---

# Workflow Principles

- Every purchase generates one Purchase Document.
- Every Purchase Document generates Purchase Knowledge.
- Supplier information is preserved.
- Business knowledge is standardized.
- Human validation prevails over AI suggestions.
- Historical information is immutable.
- The workflow is independent of acquisition technology.