# Business Autopilot and Intelligence Engine

**Version:** 1.0
**Status:** Approved (Core 2.0)
**Module:** Core / ConceptualArchitecture

---

## Related documents

- [00_RF-One_Core_Vision.md](00_RF-One_Core_Vision.md)
- [03_Decision_Action_Outcome_Learning.md](03_Decision_Action_Outcome_Learning.md)
- [05_Epistemic_Boundary_and_Subject_Sovereignty.md](05_Epistemic_Boundary_and_Subject_Sovereignty.md)
- [07_Core_Glossary.md](07_Core_Glossary.md)
- See also [../ArchitecturePrinciples.md](../ArchitecturePrinciples.md) (Human Authority, reconciled) and [../ImplementationGuidelines.md](../ImplementationGuidelines.md).

---

## Purpose

This document defines RF-One's operating model as a Business Autopilot under human command, the concept of Delegated Authority, and the distinction between RF-One and the Intelligence Engines it may use.

---

## 1. RF-One is a Business Autopilot under human command

> **RF-One may make and execute business decisions within explicitly delegated authority.**
> **The Subject retains ultimate strategic sovereignty, override authority, and control over the boundaries of delegation.**

This replaces the earlier absolute rule that "AI never owns business decisions." That rule is no longer valid as an unconditional statement; see [../ArchitecturePrinciples.md](../ArchitecturePrinciples.md) for the reconciled principle. Subject Sovereignty over direction (see [05_Epistemic_Boundary_and_Subject_Sovereignty.md](05_Epistemic_Boundary_and_Subject_Sovereignty.md)) remains fully intact — what changes is that, within a boundary the Subject has knowingly set, RF-One may act rather than only recommend.

Using the aircraft-autopilot analogy carefully — as an operating-model analogy, not as ontology — the **Subject acts as the Pilot**. The Pilot defines or confirms:

- strategic direction;
- Desires;
- Goals;
- constraints;
- risk tolerance;
- authority boundaries;
- unacceptable Outcomes.

Within approved authority, RF-One may continuously:

- observe;
- interpret;
- identify problems;
- identify opportunities;
- decide;
- act;
- measure;
- learn;
- correct course.

The mature model should not require human approval for every operational Decision. Inside delegated authority:

> **RF-One handles it.**

RF-One must escalate to the Pilot when appropriate, including when:

- authority is insufficient;
- uncertainty exceeds accepted limits;
- risk exceeds tolerance;
- constraints conflict;
- consequences cross escalation thresholds;
- strategic direction may need revision;
- the Goal itself may need reconsideration.

> **Human control does not imply continuous human operation.**

The Pilot remains responsible for direction and retains command, supervision, override authority, and the ability to change destination or to reduce or expand delegated authority at any time — but is not required to manually perform every correction throughout the journey.

---

## 2. Authority model

Autonomy is described conceptually as **bounded authority**, rather than as a binary choice between human control and AI control.

This document does not impose a specific technical permission implementation. Domains and Runtimes may define their own authority levels, thresholds and escalation rules appropriate to their context.

A Domain may legitimately choose:

```text
Delegated Authority = none
```

for a particular class of Decision. The Core does not force every Domain to automate everything — a Domain requiring human approval for a specific Decision class is exercising deliberate configuration within this model, not violating it. See, for example, the human-approval requirements retained in the Restaurant Purchasing Domain (`Domains/Restaurant/Purchasing/AIResponsibilities.md`, `BusinessPermissions.md`), which remain valid as Domain-level authority configuration.

---

## 3. `Decision` under delegated authority

Acting under delegated authority means executing the operational cycle described in [03_Decision_Action_Outcome_Learning.md](03_Decision_Action_Outcome_Learning.md) — Decision, Action, Outcome, Learning — without a human in the loop for each individual instance, up to the boundary of the Pilot's authorization. It does not change what a Decision, Action or Outcome *is*; it changes who — or what, within delegated authority — performs the Decision and Action stages of that cycle.

---

## 4. Intelligence Engines

RF-One must remain architecturally distinct from the AI model used to reason.

Potential **Intelligence Engines** may include:

- OpenAI models;
- Anthropic models;
- Google models;
- specialized models;
- future models.

These models are **components**. They are not RF-One itself. RF-One should remain provider-independent where practical, and the Intelligence Engine may evolve or be replaced without redefining the RF-One Core.

### RF-One's proprietary value

RF-One's proprietary value is expected to reside primarily in:

- Core ontology;
- Subject Model;
- Reality Model;
- Domain knowledge;
- organizational memory;
- Decision Memory;
- Outcome knowledge;
- epistemic model;
- Desire/Goal semantics;
- temporal coherence;
- alignment;
- orchestration;
- Process knowledge;
- business constraints;
- autonomy logic;
- learning across time.

Use external commodity services where appropriate. Do not design RF-One around unnecessary reinvention of commodity technology (see [../../../CLAUDE.md](../../../../CLAUDE.md), "External Technology").
