# Error Handling

## Purpose

This document defines how the Purchasing Module handles unexpected situations without compromising business knowledge.

The objective is to preserve information, maintain traceability and allow recovery.

---

# General Principles

- No Purchase Document is ever discarded.
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

# Mapping Errors

Examples:

- Unknown Supplier Product
- Multiple possible Ingredients
- No matching Ingredient

Behavior:

- Create a new Supplier Product if necessary.
- Request manual Ingredient mapping.
- Preserve purchasing workflow.

---

# Integration Errors

Failures of OCR, API or external services never invalidate an existing Purchase Document.

The document remains pending until processing can continue.

---

# Recovery Principles

Recovery must never:

- overwrite historical data;
- modify supplier information;
- lose audit history.

---

# Design Principles

- Preserve reality.
- Preserve history.
- Preserve traceability.
- Recover whenever possible.
- Human validation has priority over automation.
