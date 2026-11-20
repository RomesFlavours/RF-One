# Decision, Action, Outcome and Learning

**Version:** 1.0
**Status:** Approved (Core 2.0)
**Module:** Core / ConceptualArchitecture

---

## Related documents

- [00_RF-One_Core_Vision.md](00_RF-One_Core_Vision.md)
- [02_Desire_Goal_and_Reality_Check.md](02_Desire_Goal_and_Reality_Check.md)
- [04_Temporal_Coherence_and_Evolution.md](04_Temporal_Coherence_and_Evolution.md)
- [07_Core_Glossary.md](07_Core_Glossary.md)
- [08_Net_Outcome_and_Structural_Optimization.md](08_Net_Outcome_and_Structural_Optimization.md) — Gross vs Net/Retained Outcome and lawful structural optimization
- See also [../Entity.md](../Entity.md) and [../Process.md](../Process.md).

---

## Purpose

This document defines Decision, Action, Outcome and Learning as first-class Core concepts, and clarifies the distinction between Decision as a Core concept, Decision Record as a possible persistent representation, and Decision Memory as a capability.

---

## 1. The operational cycle

```text
Goal
→ Process
→ Decision
→ Action
→ Outcome
→ Learning
```

This is an **iterative conceptual cycle, not a mandatory rigid pipeline**. Learning may feed back into any earlier stage, and RF-One does not require every cycle to complete linearly before the next one begins.

---

## 2. Decision

**Decision is a first-class Core concept.**

A Decision may relate to:

- Goal;
- Process;
- available Evidence;
- Reality;
- constraints;
- authority;
- alternatives;
- uncertainty;
- anticipated consequences.

A Decision typically evaluates inputs such as Goal, Process, Condition, Constraint, Resource, Authorization and current Reality, and produces an outcome such as: execute a Process, reject execution, request authorization, wait for resources, escalate to the Subject, generate an exception, or select an alternative Process or course of action. These are illustrative, not an exhaustive or mandatory taxonomy — Domains and Runtimes may define their own.

### 2.1 Core ontology ≠ Runtime persistence

> **Core ontology ≠ Runtime persistence.**

- `Decision` is a Core concept: the act of choosing, given a Goal, Process, Reality and authority.
- Whether individual Decision instances are persisted is a **Runtime** concern.
- `Decision Record` is a **possible** persistent representation of a Decision.
- `Decision Memory` is the capability / knowledge structure through which RF-One can retain and relate past Decisions, context, reasoning, Outcomes and Learning.

**Do not equate "first-class Core concept" with "Entity."** Decision being first-class in the Core does not by itself require Decision, Decision Record or Decision Memory to be modeled with Entity identity semantics (see [../Entity.md](../Entity.md)). Persistence and identity semantics are separate questions from conceptual status, to be resolved by Domain and Runtime design when they are actually needed — not inferred automatically from the Core definition.

### 2.2 Decision Record

A Decision Record may persist information about a Decision — for example its context, the alternatives considered, the reasoning applied, the authority under which it was made, and its expected and actual Outcome. Not every Runtime is required to persist every Decision; whether and how a Decision Record is created is a Domain/Runtime configuration choice.

### 2.3 Decision Memory

Decision Memory is the ability to retain and relate relevant historical Decision knowledge over time. It may include:

- Decision context;
- available Evidence;
- considered alternatives;
- reasoning;
- authority;
- expected Outcome;
- actual Outcome;
- resulting Learning.

Decision Memory is what allows RF-One to reason about Temporal Coherence (see [04_Temporal_Coherence_and_Evolution.md](04_Temporal_Coherence_and_Evolution.md)) and to avoid repeating past mistakes, but it is a capability, not a mandatory data model imposed on every Domain.

---

## 3. Action

**Action** represents execution, or attempted execution, of a Decision.

An Action is what actually happens in Reality as a result of a Decision. Action may be performed by a human, by RF-One within delegated authority, or by another system, depending on the Domain and the authority boundaries in force (see [06_Business_Autopilot_and_Intelligence_Engine.md](06_Business_Autopilot_and_Intelligence_Engine.md)).

---

## 4. Outcome

**Outcome** represents what actually happens as a result of an Action, as observed in Reality.

An Outcome is not automatically the same as what was expected at the time of the Decision — the comparison between expectation and Outcome is precisely what produces Learning.

An Outcome may have layers: a **Gross Outcome** as directly produced by the Action, and — where Reality imposes External Obligations / Claims on it — a **Net / Retained Outcome** that the Subject actually keeps. This does not apply to every Outcome, and does not imply every Goal is economic. See [08_Net_Outcome_and_Structural_Optimization.md](08_Net_Outcome_and_Structural_Optimization.md) for the full treatment.

---

## 5. Learning

**Learning** represents reusable knowledge generated by comparing:

- expectations;
- Decision;
- Action;
- Reality;
- Outcome.

Learning may update:

- understanding of Reality;
- understanding of the Subject;
- Processes;
- assumptions;
- Decisions;
- Goals;
- constraints;
- models.

Outcomes must create reusable knowledge rather than being treated as isolated historical events. This is what allows RF-One to improve over successive cycles rather than repeating the same reasoning from a blank state each time — see [04_Temporal_Coherence_and_Evolution.md](04_Temporal_Coherence_and_Evolution.md).
