# Goal

**Version:** 1.0  
**Status:** Approved

---

# Definition

A **Goal** is the objective outcome that a **Process** is engineered to achieve.

A Goal defines **what** must be achieved.

It never defines **how** the result is obtained.

Without an associated Process, a desired outcome is not a Goal. It is a **Desire**.

---

# Principles

## 1. Purpose

Every Goal exists to define the expected outcome of exactly one Process.

Every Process exists because a Goal exists.

---

## 2. Independence from Execution

A Goal never defines:

- execution order
- resources
- actors
- strategy
- triggers

These responsibilities belong to the Process.

---

## 3. Atomicity

A Goal is atomic.

A Goal is represented by exactly:

- one measurable value

or

- one logical rule.

Examples:

- Food Cost ≤ Target
- Lease Signed = True
- Employee Hired = True
- Restaurant Open = True

Complex objectives are achieved through Process decomposition, never through Goal composition.

---

## 4. No Hierarchy

Goals do not contain sub-goals.

Every subprocess owns its own Goal.

A parent Process achieves its Goal through the successful completion of its subprocesses.

---

## 5. Identity

The identity of a Goal is its conceptual meaning.

Names, descriptions and parameters may evolve without changing the Goal, provided the underlying business concept remains the same.

RF-ONE assigns a unique identifier to each Goal in order to unambiguously represent that concept throughout the system.

The identifier represents the Goal; it does not define its meaning.

---

## 6. Parameters

Thresholds and target values are parameters of a Goal.

Example:

Goal:
Control Food Cost

Parameter:
Target = 28%

Changing a parameter does not create a new Goal.

---

## 7. Uniqueness

Every Process owns exactly one Goal.

If the execution strategy changes while the desired outcome remains the same, the Process may evolve or be versioned, but the Goal remains unchanged.

---

## 8. Verification

Every Goal must be objectively verifiable.

Therefore every Goal is expressed by either:

- a measurable value

or

- a logical rule.

---

## 9. Relationship with Desire

Without a Process there is no Goal.

A desired outcome without a Process is modeled as a separate Domain Entity:

**Desire**

When a Process is engineered to pursue a Desire, the corresponding Goal is created.

---

# Summary

A Goal defines **what** must be achieved.

A Process defines **how** to achieve it.

Together they model business intent and business execution while remaining distinct business concepts.
