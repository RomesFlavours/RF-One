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

Purchase Line (PRODUCT — Parmesan Cheese 24 Months):

- Supplier Product recognized (or created)
- Merchandise/Economic Classification = FOOD
- Ingredient mapped (or pending validation)
- Original Quantity = 10 kg
- Normalized Quantity (derived) = 10,000 g

Purchase Line (SURCHARGE — Delivery Fee):

- No Supplier Product, no merchandise classification
- Eligible scope: all PRODUCT lines on this document (only one PRODUCT line here)

Costs (derived, not stored):

- Supplier Price calculated
- Delivery Fee proportionally allocated to the eligible PRODUCT line
- Effective Product Cost calculated

Validation:

- No Validation Log if mapping already exists.
- Validation Log generated if Ingredient mapping is missing.

Purchase History:

- New purchase stored.
- Historical data preserved.

---

# Example 6 – Order-Based Receiving with Shortage

## Source

Order-based mobile Receiving; no readable label available.

```
Supplier: Local Dairy Co.

Order:
Mozzarella — Expected 4

Invoice:
Mozzarella × 4

Receiving (Order-based, Employee confirms actual quantity):
Mozzarella — Received: 3
```

## Expected Result

Receiving Record:

- Completed, CaptureMethod = ORDER_BASED

Receiving Line:

- ObservedQuantity = 3, related Purchase Order Line and Purchase Line both present

Reconciliation (derived):

- Order vs Invoice: MATCH (4 = 4)
- Invoice vs Receiving: SHORT (4 invoiced, 3 received)
- Order vs Receiving: SHORT (4 ordered, 3 received)

Alert:

- Trigger = RECEIVING_DISCREPANCY, ReconciliationOutcome = SHORT, routed to the responsible Purchasing User
- Receiving session remains COMPLETED regardless of the open Alert

---

# Example 7 – Label-Based Receiving with Extra Item

## Source

Label-based mobile Receiving for a structured distributor.

```
Supplier: Gordon Food

Order:
Olive Oil 6 × 1 L

Invoice:
Olive Oil 6 × 1 L

Receiving (label scans):
Olive Oil 6 × 1 L  (label recognized, matches Order/Invoice)
+ EXTRA ITEM: Zucchine, 2 cases, photo attached (no matching Order line)
```

## Expected Result

Receiving Line 1 (Olive Oil):

- Reconciliation: MATCH — no Alert

Receiving Line 2 (Zucchine):

- No related Purchase Order Line → Extra/Unexpected Item
- RawDescription = "Zucchine", ObservedQuantity = 2 cases, PhotoEvidence = required and present
- Alert: Trigger = RECEIVING_DISCREPANCY, ReconciliationOutcome = EXTRA, routed to the responsible Purchasing User
- The Employee did not classify the item; the Employee only recorded the fact and the photo

---

# Example 8 – Damaged Item, Reject/Return, and Expected Supplier Credit

## Source

```
Supplier: Fresh Food Inc.

Order / Invoice:
Parmesan Cheese 24 Months — 10 units, €12.00/unit

Receiving:
Received: 10 units
Damaged: 2 units, photo attached
```

## Expected Result

Receiving:

- ObservedQuantity = 10, DamagedQuantity = 2, PhotoEvidence present
- Alert: Trigger = RECEIVING_DISCREPANCY, ReconciliationOutcome = DAMAGED

Purchasing Decision (quantity level, `BusinessRules.md`, "Partial Quantity"):

- 8 units → ACCEPT
- 2 units → REJECT / RETURN

Because the 2 rejected units were already invoiced:

- Expected Supplier Credit created: ExpectedAmount = €24.00 (2 × €12.00), Status = Open
- The Receiving Line is NOT rewritten — it still shows 10 units received, 2 of them rejected/returned; it never becomes "8 units received"

Credit reconciliation:

- A later Credit Note arrives crediting €14.00 → RecognizedAmount = €14.00, OutstandingAmount = €10.00, Status = Partially Resolved
- A further Credit Note later credits the remaining €10.00 → OutstandingAmount = €0.00, Status = Resolved
- Had the Supplier never issued the remaining €10.00, the Expected Supplier Credit would remain Open indefinitely — no arbitrary expiration is applied

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
- Physical Receiving capture and Order/Invoice/Receiving reconciliation, when applicable
- Purchasing Alert generation and routing, for both configuration deviations and Receiving discrepancies

---

# Acceptance Rule

A feature is considered complete only if all reference examples produce the expected business result, regardless of the acquisition source.

---

# Design Principles

- Business behavior has priority over technical implementation.
- Different inputs must generate the same domain model.
- Examples are executable specifications.
- Every new feature should include at least one new reference example.