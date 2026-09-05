# Identity, Authority and Accountability

**Version:** 1.0
**Status:** Approved (Core 2.0)
**Module:** Core / ConceptualArchitecture

---

## Related documents

- [00_RF-One_Core_Vision.md](00_RF-One_Core_Vision.md)
- [03_Decision_Action_Outcome_Learning.md](03_Decision_Action_Outcome_Learning.md) — Decision and Action, whose actor and authority this document makes explicit
- [04_Temporal_Coherence_and_Evolution.md](04_Temporal_Coherence_and_Evolution.md) — historical trajectory, which Auditability makes reconstructable
- [05_Epistemic_Boundary_and_Subject_Sovereignty.md](05_Epistemic_Boundary_and_Subject_Sovereignty.md) — Subject Sovereignty, which Authority and Delegation operate under, never override
- [06_Business_Autopilot_and_Intelligence_Engine.md](06_Business_Autopilot_and_Intelligence_Engine.md) — Delegated Authority (Pilot → RF-One), the specific case this document generalizes into Delegation
- [07_Core_Glossary.md](07_Core_Glossary.md)
- See also [../Entity.md](../Entity.md) (Identity, Roles), [../ArchitecturePrinciples.md](../ArchitecturePrinciples.md) (Human Authority, Traceability, Historical Integrity), [../Corporate.md](../Corporate.md), [../Operational Unit.md](../Operational%20Unit.md) and [../OperationalArea.md](../OperationalArea.md) (organizational context scope).
- Technical implementation of these concepts (authentication mechanism, authorization enforcement, RF-One Operational Signature, audit trail storage, security infrastructure) is Runtime/Software concern — see `03 Software/Identity Authority and Security Architecture.md`. This document defines meaning; that document defines mechanism.

---

## Purpose

This document makes **Identity**, **Authority**, **Delegation**, **Accountability** and **Auditability** explicit as first-class, transversal Core concepts. They are not new inventions — Decision already names authority as one of its inputs (see [03_Decision_Action_Outcome_Learning.md](03_Decision_Action_Outcome_Learning.md) §2), Delegated Authority already exists (see [06_Business_Autopilot_and_Intelligence_Engine.md](06_Business_Autopilot_and_Intelligence_Engine.md)), and Traceability/Historical Integrity already exist (see [../ArchitecturePrinciples.md](../ArchitecturePrinciples.md)). This document names them precisely, generalizes Delegation beyond the single Subject→RF-One case, and states the resulting mandatory architectural rule: these concepts are common RF-One infrastructure, never something a Domain or Module defines independently for itself.

Like every other Core concept, Identity/Authority/Delegation/Accountability/Auditability are **domain-independent by construction**: nothing below is Restaurant-specific or Selection-specific.

---

## 1. Why these must be explicit Core concepts

Every Decision and Action already presupposes an answer to four questions:

```text
WHO is acting?                    → Identity
WHAT may that actor do?           → Authority
WHO gave them the right to do it? → Delegation (when authority is not direct)
CAN it be proven afterward?       → Accountability / Auditability
```

Leaving these implicit invites exactly the failure mode `CLAUDE.md` warns against: each Domain quietly inventing its own notion of "who did this" and "were they allowed to," producing duplicate, inconsistent, unauditable mechanisms. Making them explicit Core concepts — defined once, applied by every Domain — prevents that.

---

## 2. Identity

**Identity**, in this context, is not a new alternative to Entity identity (see [../Entity.md](../Entity.md) §4: "Every Entity owns a permanent RF-ONE identifier that never changes and has no business meaning"). It is that same principle applied specifically to whoever or whatever **acts**.

An **Acting Identity** is an Entity assuming the **Actor** role (see [../Entity.md](../Entity.md) §6) in relation to a Decision or Action. Illustrative kinds of Acting Identity — not a closed or mandatory taxonomy — include:

- a Human User;
- RF-One itself, acting as a System;
- an AI Agent, acting within Delegated Authority (§4 below, and [06_Business_Autopilot_and_Intelligence_Engine.md](06_Business_Autopilot_and_Intelligence_Engine.md));
- an External Service / Connector, acting on RF-One's behalf or on a Subject's behalf.

**Every meaningful Decision and Action must be attributable to exactly one Acting Identity.** This is the precondition for Accountability (§5).

### 2.1 Stable identity, configurable label

Consistent with [../Entity.md](../Entity.md) §4–§5, an Acting Identity's permanent identifier carries no business meaning and does not change when:

- a visible job title or role label changes;
- the Operational Unit ("Branch") the identity operates from changes;
- Authority granted to that identity changes;
- an organization's own terminology for a role changes.

Visible role/title labels are **Attributes** of the Acting Identity, configurable per organization; the underlying identifier and its accumulated Decision/Action history remain constant. Changing a label must never be capable of silently changing what the identity is accountable for.

---

## 3. Authority

**Authority** is the bounded scope of Decisions and Actions an Acting Identity may perform. It is one of the standing inputs a Decision evaluates (see [03_Decision_Action_Outcome_Learning.md](03_Decision_Action_Outcome_Learning.md) §2); this document elevates it from "an input among others" to a first-class concept with its own shape.

Authority is always evaluated **in context**, not in the abstract. The relevant context is composed from Core concepts that already exist — this document does not introduce a parallel organizational hierarchy:

```text
Acting Identity
→ Corporate / Brand           (see ../Corporate.md)
→ Operational Unit ("Branch") (see ../Operational Unit.md)
→ Domain / Module             (see ../Glossary.md — Domain, Module)
→ resource / Process / object
→ Action
```

An Acting Identity may hold Authority over one Operational Unit and one Domain/Module but not another; Authority is a relationship qualified by scope, not a single global flag. The question Authority answers is never "can this identity see a page," but:

> **"Is this Acting Identity authorized to perform this specific Action on this specific resource, in this specific context?"**

Authority may be, illustratively and non-exhaustively: direct, role-derived, delegated (§4), conditional, temporary, or scoped to part of the context above. Domains may define the specific Authority classes ("VIEW," "APPROVE," "CERTIFY," and so on) they require; the Core does not fix a final enumeration, consistent with how [06_Business_Autopilot_and_Intelligence_Engine.md](06_Business_Autopilot_and_Intelligence_Engine.md) §2 already declines to fix a permission taxonomy.

---

## 4. Delegation

**Delegation** is the general Core relationship by which one authorized Acting Identity or system explicitly confers bounded Authority on another Acting Identity or system.

**Delegated Authority**, already defined in [06_Business_Autopilot_and_Intelligence_Engine.md](06_Business_Autopilot_and_Intelligence_Engine.md), is the specific and most important instance of Delegation in RF-One's operating model: the Pilot (Subject) delegating bounded operational Authority to RF-One. That definition is not changed by this document. What this document adds is that Delegation is not limited to that one case — a Pilot may delegate to a human User, a User with sufficient Authority may in principle delegate a narrower slice of it onward, and RF-One may delegate a bounded task to an External Service — always subject to whatever boundary the original grant carries, and never exceeding it.

A Delegation:

- has an explicit Grantor (the Acting Identity or system that confers it) and Grantee (the Acting Identity or system that receives it);
- is bounded — scoped to specific Authority, context and, where applicable, a time window;
- is itself an Action requiring Accountability: the architecture must preserve **who granted it, when, under what authority, and who revoked it if it was revoked** — a Delegation is not exempt from the Auditability requirement (§6) that governs every other consequential Action.

Delegation never grants more than the Grantor itself holds, and never overrides Subject Sovereignty (see [05_Epistemic_Boundary_and_Subject_Sovereignty.md](05_Epistemic_Boundary_and_Subject_Sovereignty.md) §3): a Pilot may delegate operational Authority while retaining direction, Goals, constraints, override and the ability to revoke.

---

## 5. Accountability

**Accountability** is the ability to attribute a specific Decision or Action to the Acting Identity responsible for it, and to the Authority (direct or Delegated) under which it was performed.

Accountability is what makes Identity and Authority useful rather than merely descriptive: it is the property that lets RF-One answer, after the fact, "who decided this, and were they entitled to."

### 5.1 AI Recommendation vs. AI-Authorized Execution

[03_Decision_Action_Outcome_Learning.md](03_Decision_Action_Outcome_Learning.md) §3 already states that an Action "may be performed by a human, by RF-One within delegated authority, or by another system." Accountability requires this to be made explicit and recorded for every Action whose Acting Identity is an AI Agent:

```text
AI RECOMMENDATION       — AI produces analysis, a suggestion, or a proposed
                           Decision; a human or other authorized Acting
                           Identity remains the one who actually decides.

AI-AUTHORIZED EXECUTION — RF-One itself is the Acting Identity that decides
                           and acts, strictly within explicit Delegated
                           Authority (§4; see also
                           06_Business_Autopilot_and_Intelligence_Engine.md).
```

An AI Agent does not acquire Authority merely because it is technically capable of executing an action. Absent an explicit, in-force Delegation, AI output is a Recommendation informing another Acting Identity's Decision — never an Action attributed to the AI Agent itself.

---

## 6. Auditability

**Auditability** is the ability to reconstruct, after the fact:

- who (which Acting Identity) did what;
- when;
- in what context (Corporate/Operational Unit/Domain/Module, §3);
- under what Authority, direct or Delegated (§3–§4);
- against which object/resource;
- the state before and the state after;
- what applicable data, rule or Process version was in force.

Auditability is a **capability**, not a mandate that every Decision be persisted — this is the same "Core ontology ≠ Runtime persistence" separation [03_Decision_Action_Outcome_Learning.md](03_Decision_Action_Outcome_Learning.md) §2.1 already establishes for Decision Records. What Auditability does mandate is that wherever RF-One does record a consequential Decision or Action, that record is:

- attributable to an Acting Identity (§2) and an Authority (§3);
- consistent with **Historical Integrity** (see [../ArchitecturePrinciples.md](../ArchitecturePrinciples.md)): never silently overwritten — corrections generate new records, exactly as Historical Integrity already requires for business history in general;
- reconstructable in relation to **Temporal Coherence** (see [04_Temporal_Coherence_and_Evolution.md](04_Temporal_Coherence_and_Evolution.md)): not only individually correct, but able to support reasoning about the trajectory of Decisions and Actions over time.

---

## 7. Relationship to existing Core concepts

| This document | Extends / makes explicit |
|---|---|
| Identity (§2) | [../Entity.md](../Entity.md) §4 (permanent identifier), §6 (Actor role) |
| Authority (§3) | [03_Decision_Action_Outcome_Learning.md](03_Decision_Action_Outcome_Learning.md) §2 (authority as a Decision input) |
| Delegation (§4) | [06_Business_Autopilot_and_Intelligence_Engine.md](06_Business_Autopilot_and_Intelligence_Engine.md) (Delegated Authority — the Pilot→RF-One instance) |
| Accountability (§5) | [03_Decision_Action_Outcome_Learning.md](03_Decision_Action_Outcome_Learning.md) §3 (Action's actor) |
| Auditability (§6) | [../ArchitecturePrinciples.md](../ArchitecturePrinciples.md) (Traceability, Historical Integrity), [04_Temporal_Coherence_and_Evolution.md](04_Temporal_Coherence_and_Evolution.md) |

Nothing in this document reopens or redefines Subject Sovereignty, the Business Autopilot model, or the Decision/Action/Outcome/Learning cycle. It names concepts those documents already relied on implicitly.

---

## 8. What this document does not define

Consistent with Core's definition-not-implementation nature (see [00_RF-One_Core_Vision.md](00_RF-One_Core_Vision.md)):

- no concrete authentication mechanism or provider;
- no concrete permission/authorization engine;
- no concrete audit table, log schema or storage technology;
- no concrete Company/Branch configuration for any specific Product or customer;
- no fixed enumeration of Authority classes or Delegation workflows.

These are Runtime and Software concerns — see `03 Software/Identity Authority and Security Architecture.md` — or Product-level configuration — see `02 Products/`.
