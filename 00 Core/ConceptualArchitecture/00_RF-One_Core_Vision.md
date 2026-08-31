# RF-One Core Vision

**Version:** 1.0
**Status:** Approved (Core 2.0)
**Module:** Core / ConceptualArchitecture

---

## Related documents

This document is the entry point of the RF-One Core Conceptual Architecture. It should be read first.

- [01_Subject_and_Reality.md](01_Subject_and_Reality.md)
- [02_Desire_Goal_and_Reality_Check.md](02_Desire_Goal_and_Reality_Check.md)
- [03_Decision_Action_Outcome_Learning.md](03_Decision_Action_Outcome_Learning.md)
- [04_Temporal_Coherence_and_Evolution.md](04_Temporal_Coherence_and_Evolution.md)
- [05_Epistemic_Boundary_and_Subject_Sovereignty.md](05_Epistemic_Boundary_and_Subject_Sovereignty.md)
- [06_Business_Autopilot_and_Intelligence_Engine.md](06_Business_Autopilot_and_Intelligence_Engine.md)
- [07_Core_Glossary.md](07_Core_Glossary.md)
- [08_Net_Outcome_and_Structural_Optimization.md](08_Net_Outcome_and_Structural_Optimization.md)
- See also [../RF-ONE Core Principles.md](../RF-ONE%20Core%20Principles.md) for the immutable layer principles this vision specializes.

---

## Purpose

This document establishes the overall conceptual vision of the RF-One Core: what the Core is, what it models, and what it exists to accomplish. Every other document in this architecture specializes one part of this vision.

---

## 1. Core, Domain, Product, Runtime

> **Core ≠ Domain ≠ Product ≠ Runtime.**

RF-One is built around a **domain-independent Core**. The Core is not a restaurant product and is not itself a commercial application. It defines generic concepts, their meaning, and their relationships (Subject, Reality, Desire, Goal, Decision, Action, Outcome, Learning, and others).

- **Core** defines what concepts mean and how they may relate. It is definition, not implementation.
- **Domain** applies and, where necessary, specializes Core concepts for a specific field (e.g. Restaurant, Sales, Workforce). A Domain may in turn have modules (e.g. Restaurant's Purchasing module); a module is not itself a peer Domain.
- **Product** is a commercial application built using one or more Domains, designed to create measurable value for its users.
- **Runtime** is where actual data, inference, execution, recommendations and actions occur.

A concept existing in the Core does **not** imply that every Domain must use it, that every implementation must collect data for it, that it must always be instantiated, that RF-One must be able to measure it, or that every Product must expose it.

**Core definition and data availability are separate questions.** Do not reject a Core concept because Runtime data may not currently exist for it.

---

## 2. RF-One models a Subject in relation to Reality

The foundational relationship modeled by RF-One is:

> **Subject ↔ Reality**

RF-One does not assume that a human Subject is rational. People are influenced by emotion, memory, experience, belief, value, identity, relationships, environment, current state, impulse, knowledge, misinformation, and both conscious and subconscious factors. See [01_Subject_and_Reality.md](01_Subject_and_Reality.md).

RF-One helps expose what the Subject may not see, or may not want to see, about Reality. It helps clarify Desire rather than assuming that declared objectives are automatically correct. It helps transform confirmed Desire into pursuable Goals. See [02_Desire_Goal_and_Reality_Check.md](02_Desire_Goal_and_Reality_Check.md).

---

## 3. From understanding to action

RF-One supports Decisions, Actions, Outcomes and Learning, and maintains coherence across time. See [03_Decision_Action_Outcome_Learning.md](03_Decision_Action_Outcome_Learning.md) and [04_Temporal_Coherence_and_Evolution.md](04_Temporal_Coherence_and_Evolution.md).

Because Reality may impose external obligations on an Outcome, and because a Subject may sometimes lawfully change its future relationship to Reality, RF-One also reasons about Net / Retained Outcome and lawful structural optimization. See [08_Net_Outcome_and_Structural_Optimization.md](08_Net_Outcome_and_Structural_Optimization.md).

RF-One is intended to evolve together with the Subject and the business, not to impose a fixed model of either.

RF-One may use external Intelligence Engines to reason, but RF-One is architecturally distinct from any specific engine. See [06_Business_Autopilot_and_Intelligence_Engine.md](06_Business_Autopilot_and_Intelligence_Engine.md).

---

## 4. The guiding principle

> RF-One does not exist merely to answer questions or produce recommendations.
> It exists to progressively understand the Subject and Reality, help determine and clarify direction, and operate toward confirmed Goals within delegated authority.

This principle links every other concept in this architecture: understanding (Subject ↔ Reality, Epistemic Boundary), clarification (Reality Check, Desire, Goal), and action (Decision, Action, Outcome, Learning, Business Autopilot) are not independent features — they are stages of one continuous relationship between RF-One, the Subject, and Reality.

---

## 5. Commercial framing

RF-One is designed commercially as a **Business Autopilot**. Commercial RF-One is business-first and must create measurable economic value for the organizations that use it. See [06_Business_Autopilot_and_Intelligence_Engine.md](06_Business_Autopilot_and_Intelligence_Engine.md).

> The Core may be universal; commercial Products must have an economic reason to exist.

The Core does not encode pricing or commercial strategy — those belong to Products. But the Core is shaped so that Domains and Products built on it are capable of producing outcomes valuable enough to justify serious B2B investment, not only low-cost consumer convenience.

---

## 6. How to read this architecture

| Document | Answers |
|---|---|
| [01_Subject_and_Reality.md](01_Subject_and_Reality.md) | Who is RF-One modeling, and in relation to what? |
| [02_Desire_Goal_and_Reality_Check.md](02_Desire_Goal_and_Reality_Check.md) | How does what the Subject wants become something pursuable? |
| [03_Decision_Action_Outcome_Learning.md](03_Decision_Action_Outcome_Learning.md) | How does RF-One go from a Goal to results, and learn from them? |
| [04_Temporal_Coherence_and_Evolution.md](04_Temporal_Coherence_and_Evolution.md) | How does RF-One reason across many Decisions over time? |
| [05_Epistemic_Boundary_and_Subject_Sovereignty.md](05_Epistemic_Boundary_and_Subject_Sovereignty.md) | What may RF-One claim to know, and who has final authority? |
| [06_Business_Autopilot_and_Intelligence_Engine.md](06_Business_Autopilot_and_Intelligence_Engine.md) | How autonomous may RF-One be, and what powers its reasoning? |
| [07_Core_Glossary.md](07_Core_Glossary.md) | What does each term precisely mean? |
| [08_Net_Outcome_and_Structural_Optimization.md](08_Net_Outcome_and_Structural_Optimization.md) | How does RF-One reason about what a Subject actually retains, and about lawful ways to change future constraints? |

This vision, and the documents that specialize it, are the canonical conceptual architecture for the concepts they define. Domain and Product documentation must remain consistent with them.
