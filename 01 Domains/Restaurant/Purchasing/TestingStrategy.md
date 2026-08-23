# Testing Strategy

## Purpose

This document defines how the Purchasing Module shall be tested.

Testing verifies business behavior rather than implementation details.

---

# Testing Philosophy

The objective of testing is to verify that the Purchasing Module always produces the correct business knowledge regardless of:

- Acquisition source
- Supplier
- Document format
- Technology

---

# Unit Tests

Unit tests verify isolated business rules.

Examples:

- Quantity normalization
- Cost per gram calculation
- Cost allocation
- Density conversion
- Validation rule evaluation

---

# Integration Tests

Integration tests verify interaction between components.

Examples:

- OCR -> Purchase Document
- API -> Purchase Document
- XML -> Purchase Document
- Purchase Document -> Ingredient Mapping

Every integration must generate the same logical Purchase Document and the same business result.

---

# Business Scenario Tests

Business scenarios validate complete workflows.

Examples:

- New Supplier
- New Supplier Product
- Existing Supplier Product
- Missing Product
- Unknown Ingredient
- Fuel surcharge allocation
- Credit note processing

---

# Regression Tests

Every resolved defect becomes a permanent regression test.

No future release may reintroduce a previously solved business problem.

---

# Acceptance Tests

Acceptance tests are based on the official Examples.

A release is accepted only when every reference example produces the expected business result.

---

# AI Evaluation

AI is evaluated using:

- OCR accuracy
- Extraction accuracy
- Mapping suggestion accuracy
- False positive rate
- Human acceptance rate

Business correctness has priority over AI confidence.

---

# Performance Tests

Verify:

- Large Purchase Documents
- Large Purchase History
- Concurrent document processing
- Batch imports

---

# Design Principles

- Test business behavior.
- Test complete workflows.
- Test with real supplier documents.
- Preserve regression history.
- Business correctness is the primary success metric.