# Validation Rules

## Purpose

This document defines how RF-One validates purchasing information.

Validation ensures data quality while preserving the integrity of the original Purchase Document.

Validation never modifies supplier information.

---

# Validation Principles

- The Purchase Document always remains valid.
- RF-One never edits supplier documents.
- Validation records inconsistencies.
- Human validation has priority over AI interpretation.
- Every anomaly is traceable.

---

# Validation Levels

## Informational

Information that does not affect processing.

Examples:

- Optional field missing
- Unknown supplier note

---

## Warning

The Purchase Document can be processed but requires attention.

Examples:

- Unknown Supplier Product
- New packaging
- Missing mapping
- OCR confidence below threshold

---

## Error

Processing cannot continue automatically.

Examples:

- Missing mandatory document identifier
- Missing Purchase Line
- Unreadable document
- Impossible quantity conversion

Errors never invalidate the Purchase Document.

They only stop automatic processing until validated.

---

# Validation Log

Every anomaly generates one Validation Log entry.

Each entry records:

- Validation Id
- Purchase Document
- Purchase Line (optional)
- Date and Time
- Severity
- Message
- Proposed AI Action
- Human Decision
- Resolution Date

Validation history is never deleted.

---

# AI Validation

AI may:

- Detect anomalies
- Estimate confidence
- Suggest corrections
- Propose Ingredient mappings

AI never:

- Modify supplier documents
- Confirm a correction
- Validate an Ingredient mapping
- Close a Validation Log entry

---

# Human Validation

An authorized user may:

- Accept AI suggestions
- Reject AI suggestions
- Correct extracted values
- Create new Ingredient mappings
- Close Validation Log entries

Every human action is auditable.

---

# Validation Workflow

1. Acquire Purchase Document.
2. Detect anomalies.
3. Create Validation Log entries.
4. Continue automatic processing whenever possible.
5. Request human validation when required.
6. Record every decision.

---

# Design Principles

- Preserve reality.
- Never lose information.
- Never overwrite history.
- Every decision must be traceable.
- AI supports validation but never replaces human responsibility.
