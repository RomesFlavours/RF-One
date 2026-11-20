# Desire, Goal and Reality Check

**Version:** 1.1
**Status:** Approved (Core 2.0)
**Module:** Core / ConceptualArchitecture

---

## Related documents

- [00_RF-One_Core_Vision.md](00_RF-One_Core_Vision.md)
- [01_Subject_and_Reality.md](01_Subject_and_Reality.md)
- [03_Decision_Action_Outcome_Learning.md](03_Decision_Action_Outcome_Learning.md)
- [07_Core_Glossary.md](07_Core_Glossary.md)
- See also [../Goal.md](../Goal.md) — the pre-existing Goal document, reconciled with this architecture — and [../Process.md](../Process.md).

---

## Purpose

This document establishes that Desire and Goal are different concepts, defines the continuous Reality Check / Clarification capability that connects them, and defines what a Goal is once confirmed.

---

## 1. Desire ≠ Goal

> **Desire ≠ Goal**

A **Desire** is something the Subject wants. A Desire:

- does not need to be rational;
- does not need to be currently feasible;
- does not need to be economically sensible;
- does not need to be consistent;
- does not need to be immediately explainable;
- does not need to become a Goal.

RF-One must never invalidate a Desire merely because it appears unrealistic.

### The Moon example

> "I want to go to the Moon."

RF-One must not treat this as impossible by default. The Subject may be an astronaut, may be capable of becoming one, may mean something different by the statement, or relevant Reality may simply still be unknown to RF-One.

RF-One must distinguish between:

- **impossible** — demonstrated to be unachievable;
- **currently infeasible** — achievable in principle, not now;
- **no known path** — no route has been identified yet;
- **insufficient knowledge** — RF-One or the Subject lacks the information to judge;
- **uncertain** — feasibility depends on unresolved factors;
- **temporarily constrained** — blocked by a condition that may change.

> **"I do not know how" must never silently become "It cannot be done."**

A Desire that cannot currently become a Goal **remains a valid Desire**. It is not deleted, and it is not devalued. It may later become actionable if Reality changes or new knowledge becomes available.

*(A Desire's origin does not affect its nature — it may come from the Subject's own reasoning, from RF-One surfacing an opportunity, or elsewhere; and a Domain or Runtime may choose to track a Desire's lifecycle explicitly, for example as Proposed, Under Evaluation, Confirmed, Deferred or Archived. That lifecycle is a Domain/Runtime concern, not part of the Core definition of Desire itself.)*

---

## 2. Reality Check / Clarification is continuous

**Reality Check** (also called **Clarification**) is a continuous Core capability, not a single stage that happens once, immediately after a Desire is stated.

It may occur:

- before Desire;
- while Desire is forming;
- after Desire is expressed;
- before Goal formation;
- during Goal pursuit;
- before major Decisions;
- after Outcomes;
- whenever Reality changes.

Reality Check may surface:

- facts;
- contradictions;
- hidden assumptions;
- missing information;
- ignored consequences;
- conflicts among Desires;
- conflicts with prior priorities;
- risks;
- opportunities;
- uncertainty;
- relevant information the Subject may consciously or unconsciously avoid.

**Reality Check must not remove free will.** Its purpose is to improve clarity before the Subject confirms a direction — not to decide for the Subject. See [05_Epistemic_Boundary_and_Subject_Sovereignty.md](05_Epistemic_Boundary_and_Subject_Sovereignty.md) for how this coexists with Subject Sovereignty.

---

## 3. From Desire to Goal

A **Goal** is a sufficiently clarified and confirmed representation of something the Subject wants that can be treated as pursuable/actionable within understood Reality.

The conceptual direction is:

```text
Desire
  ↕
Clarification / Reality Check
  ↓
Confirmed Desire
  ↓
Goal
  ↓
Process
```

A **Process** supports pursuit of the Goal (see [../Process.md](../Process.md)). **A Process is not the ontological precondition for the Goal to exist.** A Goal may exist — clarified, confirmed, pursuable in principle — before any Process to pursue it has been designed or selected. This supersedes the earlier rule that a Goal exists only once a Process has been defined; see [../Goal.md](../Goal.md) for the reconciled definition.

The transition from Desire to Goal may require consideration of Resources, Conditions, Constraints, Knowledge, Capabilities, Time, Risk, Dependencies, and uncertainty — but these inform *whether and how* a Desire becomes a Goal, they do not retroactively make the Desire itself invalid if the answer is "not yet."

---

## 4. Early Failure Recognition is a valuable outcome

Recognizing — as early as reasonably possible — that a Goal is infeasible under currently known conditions, that a required Constraint cannot be satisfied, that available evidence does not support proceeding, that no known path currently exists, or that uncertainty is too high for the current authority/risk boundary, is a useful RF-One outcome. It is not a system failure.

This early recognition must preserve the distinctions established in Section 1:

- **infeasible now** must never collapse into **impossible**;
- **no known path** must never collapse into **no path exists**.

Recognizing infeasibility, an unsatisfied Constraint, insufficient evidence, or an unresolved authority/risk boundary early is itself valuable information. It may return a Goal to Desire status (Section 1), trigger a Reality Check (Section 2), or surface an authority/risk escalation — see [05_Epistemic_Boundary_and_Subject_Sovereignty.md](05_Epistemic_Boundary_and_Subject_Sovereignty.md) and [06_Business_Autopilot_and_Intelligence_Engine.md](06_Business_Autopilot_and_Intelligence_Engine.md) — rather than silently continuing toward an outcome current knowledge does not support.

---

## 5. Relationship to Action

Once a Goal exists and a Process is available or selected to pursue it, RF-One moves into the operational cycle of Decision, Action, Outcome and Learning — see [03_Decision_Action_Outcome_Learning.md](03_Decision_Action_Outcome_Learning.md).
