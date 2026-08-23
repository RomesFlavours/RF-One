# Examples

## Purpose

This document defines the reference examples used to validate the Purchasing Module.

Each example represents a complete business scenario.

The objective is to verify that different acquisition methods always produce the same logical Purchase Document.

---

# Example Structure

Each example contains:

- Original source document
- Expected Purchase Document
- Expected Purchase Lines
- Expected Validation Log
- Expected Ingredient Mapping (when applicable)

---

# Example 1

## Source

Paper Invoice (OCR)

## Expected Result

- Purchase Document created
- Purchase Lines extracted
- Supplier identified
- Supplier Products recognized
- Unknown Supplier Products created when necessary
- Validation Log generated if required

---

# Example 2

## Source

PDF Invoice

## Expected Result

Same business result as Example 1.

---

# Example 3

## Source

Supplier API

## Expected Result

Same Purchase Document generated from structured data.

---

# Example 4

## Source

Electronic Invoice (XML / EDI)

## Expected Result

Same Purchase Document generated from electronic data.

---

# Example 5 – Complete Business Scenario

## Source

Supplier Invoice

```
Supplier: Fresh Food Inc.

Product:
Parmesan Cheese 24 Months

Quantity:
2 × 5 kg

Unit Price:
€12.00/kg

Delivery Fee:
€10.00
```

## Expected Result

Purchase Document:

- Created successfully
- Supplier identified

Purchase Line:

- Supplier Product recognized (or created)
- Ingredient mapped (or pending validation)
- Original Quantity = 10 kg
- Normalized Quantity = 10,000 g

Costs:

- Supplier Price calculated
- Delivery Fee proportionally allocated
- Real Ingredient Cost calculated
- Effective Cost calculated

Validation:

- No Validation Log if mapping already exists.
- Validation Log generated if Ingredient mapping is missing.

Purchase History:

- New purchase stored.
- Historical data preserved.

---

# Validation Criteria

Every example must verify:

- Purchase Document creation
- Purchase Line extraction
- Quantity normalization
- Cost normalization
- Ingredient mapping
- Validation Log generation
- Purchase History update

---

# Acceptance Rule

A feature is considered complete only if all reference examples produce the expected business result, regardless of the acquisition source.

---

# Design Principles

- Business behavior has priority over technical implementation.
- Different inputs must generate the same domain model.
- Examples are executable specifications.
- Every new feature should include at least one new reference example.