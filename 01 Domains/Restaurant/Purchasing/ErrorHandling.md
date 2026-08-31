# Error Handling

## Purpose

This document defines how the Purchasing Module handles unexpected situations without compromising business knowledge.

The objective is to preserve information, maintain traceability and allow recovery.

---

# General Principles

- No original supplier document is ever discarded.
- No business information is silently lost.
- Every failure is traceable.
- Recovery is always preferred over rejection.

---

# Acquisition Errors

Examples:

- Corrupted PDF
- Unreadable image
- API timeout
- XML parsing failure

Behavior:

- Preserve the original source.
- Create an acquisition log.
- Allow reprocessing.

---

# Extraction Errors

Examples:

- OCR uncertainty
- Missing quantity
- Missing price
- Unknown unit

Behavior:

- Extract all recoverable information.
- Create Validation Log entries.
- Continue processing whenever possible.

---

# Normalization Errors

Examples:

- Unknown density
- Unsupported unit
- Impossible conversion

Behavior:

- Preserve original values.
- Stop only the affected normalization.
- Request human validation.

---

# Classification / Mapping Errors

Examples:

- Unknown Supplier Product
- Unknown merchandise/economic classification
- Multiple possible Ingredients
- No matching Ingredient

Behavior:

- Create a new Supplier Product if necessary.
- Request manual classification and/or Ingredient mapping.
- Never guess a classification or mapping — record it in the Validation Log instead.
- Preserve purchasing workflow.

---

# Receiving Capture Errors

Examples:

- Unreadable or missing package/case label
- Damaged packaging preventing label capture
- No matching Order found

Behavior:

- Fall back from label-based to Order-based or manual factual capture (`BusinessRules.md`, "Receiving Is Mobile-First and Fallback-Capable").
- The Receiving session must never fail merely because a preferred capture mechanism fails.
- When no Order/Invoice match exists, capture the item as an Extra/Unexpected Item (mandatory photo) and continue.
- Never block Receiving completion on an unresolved discrepancy; raise a Purchasing Alert instead (`BusinessRules.md`, "Receiving Completion Is Independent of Alert Resolution").

---

# Integration Errors

Failures of OCR, API or external services never invalidate the original supplier document.

The Purchase Document remains pending until processing can continue.

---

# Recovery Principles

Recovery must never:

- overwrite historical data;
- modify supplier information;
- lose audit history.

---

# Design Principles

- Preserve business reality.
- Preserve history.
- Preserve traceability.
- Recover whenever possible.
- Human validation has priority over automation.