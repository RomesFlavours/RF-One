# Decision.md

**Version:** 1.0
**Status:** Approved
**Category:** Core Domain

---

# Purpose

Decision is **not** a Core Domain Entity.

This document defines the role of Decision within RF-ONE and explains why it is not persistent Business Knowledge.

---

# Definition

A Decision is the result of evaluating Business Knowledge in a specific runtime context.

It is produced by the Decision Engine.

It is never part of the persistent business model.

---

# Nature

A Decision is:

- transient;
- contextual;
- generated at runtime;
- reproducible from the same inputs.

It has no independent identity in the Core Domain.

---

# Inputs

A Decision may evaluate:

- Goal
- Process
- Condition
- Constraint
- Resource
- Authorization
- Current Context

These are Core Domain entities.

Decision is not.

---

# Outputs

A Decision may produce:

- Execute Process
- Reject Execution
- Request Authorization
- Wait for Resources
- Escalate to Human
- Generate Exception
- Select Alternative Process

These are runtime results.

---

# Persistence

A Decision is normally not stored as Business Knowledge.

Only an audit trail may be persisted for traceability.

---

# Core Principle

Business Knowledge is persistent.

Decision is computation.

It is not knowledge.

---

# Relationship with the Decision Model

The Decision Model defines how Business Knowledge is evaluated.

A Decision is the outcome of applying that model to the current business context.

Therefore:

- Decision Model belongs to the Knowledge Layer.
- Decision belongs to the Runtime Layer.

---

# Fundamental Principles

- Decision is not a Core Domain Entity.
- Decision has no RF-ID.
- Decision is generated, not defined.
- Decision depends on the current context.
- Identical inputs produce the same Decision.
