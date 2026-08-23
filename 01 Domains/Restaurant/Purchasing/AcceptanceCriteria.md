# Acceptance Criteria

## Purpose

This document defines the business acceptance criteria for the Purchasing Module.

A feature is considered complete only when it satisfies these criteria.

---

# General Acceptance Criteria

The module shall:

- Produce the same logical Purchase Document regardless of the acquisition source.
- Preserve every original supplier value.
- Never modify the original supplier document.
- Normalize every purchasable Ingredient into grams.
- Calculate normalized cost per gram.
- Maintain complete purchasing history.
- Record every anomaly in the Validation Log.

---

# Purchase Document

Acceptance Criteria:

- Every purchase generates exactly one Purchase Document.
- Every Purchase Document contains one or more Purchase Lines.
- Original supplier information is preserved.

---

# Supplier Product

Acceptance Criteria:

- Unknown Supplier Products are created automatically.
- Existing Supplier Products are reused.
- Manual Ingredient mapping is required before business use.

---

# Ingredient Mapping

Acceptance Criteria:

- AI may suggest mappings.
- Human approval is mandatory.
- Approved mappings become permanent until explicitly changed.

---

# Cost Calculation

Acceptance Criteria:

- Quantities are normalized into grams.
- Document-level charges are proportionally allocated.
- Supplier Price, Real Ingredient Cost and Effective Cost are calculated correctly.

---

# Validation

Acceptance Criteria:

- Original supplier documents are never discarded.
- Validation Log entries are created whenever required.
- Every validation decision is auditable.

---

# Artificial Intelligence

Acceptance Criteria:

AI shall:

- Read documents.
- Extract purchasing data.
- Detect anomalies.
- Suggest mappings.

AI shall not:

- Modify the original supplier document.
- Approve Ingredient mappings.
- Rewrite purchasing history.
- Perform irreversible business decisions.

---

# Completion Criteria

The Purchasing Module is considered complete when:

- All reference examples produce the expected results.
- All business rules are satisfied.
- All validation rules are enforced.
- Human approval workflow functions correctly.
- Purchasing knowledge is available to the remaining Restaurant Domain modules.

---

# Success Principle

The success of the Purchasing Module is measured by the quality of the purchasing knowledge it produces, not by the technology used to acquire the data.