# Architecture Principles

## Purpose

This document defines the architectural principles that every implementation of the Purchasing Module must respect.

These principles are independent from programming language, database or framework.

---

# Domain First

The Purchasing Module is implemented from the Domain Model.

Technology adapts to the Domain.

The Domain never adapts to technology.

---

# Purchase Document Centric

Every purchasing event is represented by exactly one Purchase Document.

Every internal workflow starts from the Purchase Document.

---

# Source Independence

The origin of purchasing data is irrelevant.

PDF, OCR, API, XML, EDI and manual entry must all produce the same logical domain model.

---

# Immutable Reality

Supplier documents represent reality.

RF-One records reality.

RF-One never rewrites reality.

Corrections are represented through Validation Logs and business decisions.

---

# Canonical Knowledge

Supplier terminology remains unchanged.

Business knowledge is expressed through:

- Product
- Specification
- Ingredient

Supplier Products are mapped to canonical Ingredients.

---

# Single Measurement Standard

Every purchasable Ingredient is normalized into:

- grams
- cost per gram

All downstream modules consume the same normalized information.

---

# Human Authority

Business knowledge belongs to the restaurant.

Artificial Intelligence supports human operators but never owns business decisions.

---

# Extensibility

New suppliers, acquisition methods and document formats must be supported without changing the domain model.

The model evolves only when business concepts evolve.

---

# Traceability

Every business decision must be traceable.

The system preserves:

- Original document
- Extracted data
- AI suggestions
- Human decisions
- Validation history

---

# Loose Coupling

The Purchasing Module publishes standardized purchasing knowledge.

Other Restaurant modules consume that knowledge without depending on supplier-specific information.

---

# Design Principles

- Domain before technology.
- Purchase Document is the architectural center.
- Canonical knowledge is supplier-independent.
- Every calculation is performed on normalized data.
- AI augments human expertise.
- Every decision is auditable.
- Preserve simplicity.
