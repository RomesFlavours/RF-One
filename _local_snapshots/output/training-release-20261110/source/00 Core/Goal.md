# Goal

**Version:** 3.0
**Status:** Approved (Core 2.0)
**Module:** Core

> Reconciled with the RF-One Core Conceptual Architecture. See [ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md](ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md) for the full conceptual treatment of Desire, Reality Check and Goal.

---

# Purpose

A **Goal** defines the desired outcome that the system intends to achieve.

A Goal defines **what** must be achieved.

It never defines **how**, **who**, or **with which resources** the outcome is obtained.

---

# Definition

A Goal represents a business outcome independently from its implementation.

A Goal is a sufficiently clarified and confirmed representation of a Desire — something the Subject wants — that can be treated as pursuable/actionable within understood Reality:

```text
Desire → Clarification / Reality Check → Confirmed Desire → Goal → Process
```

**A Goal does not require a Process to already exist.** A Process supports the pursuit of a Goal; it is not the ontological precondition for the Goal to exist. This supersedes the earlier rule that a Goal exists only once a Process has been defined for it.

A **Desire** is something the Subject wants that has not yet been sufficiently clarified and confirmed to be treated as pursuable within understood Reality — including a Desire for which no Process is currently known. A Desire remains valid even when it cannot currently become a Goal; see [ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md](ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md).

---

# Principles

## 1. Outcome First

Every Goal defines only the expected outcome.

Execution belongs to the Process.

## 2. Independence from Execution

A Goal never defines:

- execution strategy
- execution order
- actors
- resources
- triggers
- technologies

These belong to the Process or to the runtime system.

## 3. Atomicity

A Goal represents exactly one business outcome.

Complex business objectives are achieved through multiple Processes, each owning its own Goal.

## 4. Identity

A Goal has its own immutable identity.

Changing parameters does not create a new Goal unless the business meaning changes.

## 5. Parameters

Thresholds, targets and tolerances are parameters.

Changing a target changes the Goal configuration, not the Goal identity.

## 6. Verification

Every Goal must be objectively verifiable through:

- a measurable value, or
- a logical condition.

## 7. Relationship with Process

Every Process exists to achieve exactly one Goal.

A Goal may be achievable through different Processes over time.

The system selects the most appropriate Process according to available capabilities and resources.

## 8. Independence from AI

Artificial Intelligence may optimize or generate Processes.

AI never changes the meaning of a Goal.

---

# Summary

A Goal defines **what** must be achieved.

A Process defines **how** it is achieved.

The runtime system decides **who or what** executes the Process.

This separation preserves the stability of the Core while allowing continuous evolution of execution strategies.
