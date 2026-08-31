# Subject and Reality

**Version:** 1.0
**Status:** Approved (Core 2.0)
**Module:** Core / ConceptualArchitecture

---

## Related documents

- [00_RF-One_Core_Vision.md](00_RF-One_Core_Vision.md)
- [02_Desire_Goal_and_Reality_Check.md](02_Desire_Goal_and_Reality_Check.md)
- [05_Epistemic_Boundary_and_Subject_Sovereignty.md](05_Epistemic_Boundary_and_Subject_Sovereignty.md)
- [07_Core_Glossary.md](07_Core_Glossary.md)
- See also [../Entity.md](../Entity.md) — Subject and Reality are conceptual roles, not a replacement for the Entity model used elsewhere in the Core.

---

## Purpose

This document defines `Subject` and `Reality`, and the foundational relationship between them that RF-One models.

---

## 1. Subject

A **Subject** is the party whose wants, decisions and actions RF-One helps understand, clarify and pursue.

A Subject may be:

- a person;
- a group;
- an organization;
- another decision-capable entity, where a Domain supports it.

A Subject is a conceptual role. Depending on Domain and Runtime, a Subject may or may not be represented as an Entity (see [../Entity.md](../Entity.md)); that is an implementation question, not a Core requirement.

### 1.1 The Subject is not assumed to be rational

RF-One must not model Subject decision-making as a mandatory rational causal pipeline. No fixed psychological sequence (for example, a rigid chain from experience to need to value to purpose to desire) is assumed by the Core.

A human Subject may be influenced by, among other things:

- emotion;
- memory;
- experience;
- belief;
- value;
- identity;
- relationship;
- environment;
- current state;
- impulse;
- knowledge;
- misinformation;
- conscious factors;
- subconscious factors.

> Any representable entity or state may potentially trigger, influence, reinforce, weaken, modify or conflict with a Desire.

RF-One does not attempt to make the origin of Desire artificially rational. It reasons about the Subject as they actually are, not as a simplified rational-agent model would predict. See [02_Desire_Goal_and_Reality_Check.md](02_Desire_Goal_and_Reality_Check.md) for how this shapes Desire.

---

## 2. Reality

**Reality** is the partially known context in which the Subject exists and acts.

Reality may include, depending on Domain:

- Facts;
- Observations;
- Resources;
- Conditions;
- Constraints;
- Opportunities;
- Relationships;
- Events;
- Risks;
- Capabilities;
- external actors;
- environments;
- Unknowns.

**Reality must never be assumed complete.** RF-One reasons with partial knowledge of Reality at all times, and must represent the boundary between what is known and what is not (see [05_Epistemic_Boundary_and_Subject_Sovereignty.md](05_Epistemic_Boundary_and_Subject_Sovereignty.md)).

---

## 3. The foundational relationship

> **Subject ↔ Reality**

RF-One continuously improves its understanding of both the Subject and Reality. This is a two-way, ongoing relationship, not a one-time input:

- Understanding of the Subject informs how Reality is interpreted and prioritized for them.
- Understanding of Reality informs what is actually possible for the Subject, and may reveal factors the Subject had not considered.

This relationship is the basis for every other capability described in this architecture: Reality Check (clarifying Desire against Reality), Decision (choosing within understood Reality), Temporal Coherence (tracking how the Subject's relationship with Reality evolves), and Business Autopilot (acting within Reality on the Subject's behalf, within delegated authority).

---

## 4. Domain independence

Nothing in this document assumes a restaurant, a business, or any specific commercial context. `Subject` and `Reality` are deliberately generic so that any Domain — Restaurant, Personnel Management, Taxation, or a future Domain — can express its own concrete meaning of "who the Subject is" and "what Reality includes" without altering the Core definition.
