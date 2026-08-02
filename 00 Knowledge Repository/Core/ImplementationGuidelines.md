# Implementation Guidelines

## Purpose

This document provides implementation guidelines for developers building the Purchasing Module.

These guidelines translate the Domain Model into implementation principles without prescribing a specific technology stack.

---

# Domain Before Technology

The Domain Model is the primary source of truth.

Classes, services, APIs and database structures must reflect the business model rather than the chosen framework.

---

# Entity Identity

Business entities must have stable identifiers independent from supplier identifiers.

Internal identifiers must never depend on supplier codes.

---

# Preserve Original Data

Always preserve:

- Original Purchase Document
- Original Supplier Product description
- Original quantities
- Original prices

Normalization creates additional information but never replaces the original values.

---

# AI Isolation

Artificial Intelligence must be implemented as a supporting service.

Business Rules must remain valid even if AI is temporarily unavailable.

---

# Validation

Validation must be separated from acquisition.

A document may be acquired successfully while still containing unresolved validation issues.

---

# Normalization

Normalization must produce deterministic results.

The same input must always generate the same normalized values.

---

# Extensibility

New suppliers and acquisition methods must be added through extension points.

Existing business entities should not require modification.

---

# Audit Trail

Every significant operation should be traceable, including:

- Acquisition
- Normalization
- AI suggestions
- Human validation
- Business decisions

---

# Error Recovery

Unexpected failures must never cause loss of:

- Purchase Documents
- Purchase Lines
- Validation history
- Human decisions

---

# Design Principles

- Preserve business meaning.
- Preserve historical information.
- Separate acquisition, validation and normalization.
- Keep AI independent from business rules.
- Favor extension over modification.
