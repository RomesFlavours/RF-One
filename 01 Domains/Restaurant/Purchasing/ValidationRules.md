# Validation Rules

## Purpose

This document defines how RF-One validates purchasing information.

Validation ensures data quality while preserving the integrity of the original Purchase Document.

Validation never modifies supplier information.

---

# Validation Principles

- The original supplier document is always preserved.
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
- Missing merchandise/economic classification
- Missing Ingredient mapping (Food/Ingredient context only)
- OCR confidence below threshold

---

## Error

Processing cannot continue automatically.

Examples:

- Missing mandatory document identifier
- Missing Purchase Line
- Unreadable document
- Impossible quantity conversion

Errors never invalidate the original supplier document.

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
- Propose merchandise/economic classifications
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
- Confirm merchandise/economic classifications
- Create new Ingredient mappings
- Close Validation Log entries

A known Supplier Product (identified by Supplier + Supplier Item Code) reuses its existing confirmed classification and mapping directly; RF-One never re-interprets a known Supplier Product from zero. This is the same reuse behavior documented for Supplier Product memory (`EntityDefinitions.md`) and is the canonical unresolved-item workflow — a separate "Unclassified Item Log" is not created because the Validation Log already covers unknown classifications and mappings.

Every human action is auditable.

---

# Alert vs Validation

Validation and Alert are both traceable, human-facing mechanisms, but they answer different questions and must not be merged:

```text
Validation issue
  → RF-One lacks sufficient certainty about the factual interpretation/classification
  → example: unknown item identity, unresolved merchandise classification, unresolved
    Ingredient mapping

Alert
  → RF-One knows exactly what happened, but the known Reality deviates from an
    operational expectation (Configured Expectation, or previous-purchase fallback)
    and requires human attention
  → example: known Ricotta, unexpected 1 × 5 kg packaging
```

A single Purchase Line may involve both if Reality requires it (e.g. an unknown Supplier Product that, once resolved, also shows an unexpected packaging).

The same boundary applies to Physical Receiving (`01 Domains/Restaurant/Purchasing/BusinessRules.md`, "Three Sources of Purchase Reality"). A Receiving Discrepancy Alert never requires the observed item's identity to already be certain — an Extra/Unexpected Item may be captured only as a free-text description and photo (`EntityDefinitions.md`, "Receiving Line"). If that description is later resolved to a known or new Supplier Product, that resolution is a Validation matter, not part of the Alert; a single Extra/Unexpected Item can therefore carry both a Validation Log entry (resolving what it is) and a Receiving Discrepancy Alert (resolving what to do about it) at the same time, exactly as for a Purchase Line.

An Alert is not a Validation Log severity level and is not recorded as a Validation Log entry — it is a distinct concept, defined in `EntityDefinitions.md`, "Alert," with its own lifecycle (`BusinessRules.md`, "Alert Lifecycle and Closure"). Where Validation blocks or flags automatic processing pending a factual determination, an Alert does not by itself block Purchase Recording when Product identity is certain (`BusinessRules.md`, Rule 21) — it tracks a required human response in parallel.

Alert is also distinct from a plain Notification: a Notification informs; an Alert requires a traceable human response — acknowledgement and, when applicable, an explicit Human Decision — before it can close (`EntityDefinitions.md`, "Alert"; `03 Software/User Interaction Architecture.md`).

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

- Preserve business reality.
- Never lose information.
- Never overwrite history.
- Every decision must be traceable.
- AI supports validation but never replaces human responsibility.
- Validation and Alert are distinct concepts and are never merged (see "Alert vs Validation" above).