# TASK_CORE_002 — RF-One Core Conceptual Architecture Documentation

## Objective

Create the first canonical documentation of the approved RF-One Core conceptual architecture and reconcile the existing Core documentation with it.

This task is authorized to create and modify documentation files.

Do not modify production software, database schemas, runtime code, generated documentation, or application behavior.

---

## Mandatory first steps

1. Read `CLAUDE.md` completely.
2. Read `Tasks/TASK_CORE_001_Conceptual_Architecture.md`.
3. Reinspect the current relevant Core documentation before editing.
4. Treat `Old/X00 Knowledge Repository/` as a legacy/reference source only.

Do not assume that legacy documentation is authoritative.

Recover useful concepts from legacy documentation where they remain compatible with the approved architecture.

Do not delete, move, rename or formally deprecate legacy files in this task.

---

# Architectural authority

The conceptual direction contained in TASK_CORE_001 and the Product Owner decisions below are approved.

Your role is to document and reconcile them faithfully.

Do not redesign them.

Do not substitute alternative psychological, philosophical, management, AI or software theories.

If a genuine contradiction is discovered during implementation that was not identified in TASK_CORE_001, stop and report it before making the conflicting change.

---

# Product Owner decisions from TASK_CORE_001 review

## 1. Legacy repository

`Old/X00 Knowledge Repository/` must remain untouched for now.

It is a historical/reference source.

Valid historical concepts may be incorporated into the new canonical documentation.

After the new architecture has been fully documented and verified, legacy files may later be marked as Superseded / Legacy in a separate task.

Do not lose useful historical knowledge.

---

## 2. RF-One is a Business Autopilot

The previous absolute rule:

> AI never owns business decisions

is no longer valid.

Replace it with the approved principle:

> RF-One may make and execute business decisions within explicitly delegated authority.  
> The Subject retains ultimate strategic sovereignty, override authority, and control over the boundaries of delegation.

RF-One is designed as:

> **Business Autopilot under human command**

The Subject/Pilot retains command.

RF-One may operate autonomously inside approved authority boundaries.

Human control does not imply continuous human operation.

---

## 3. Decision is a first-class Core concept

Decision must be defined as a first-class Core concept.

However:

> Core ontology ≠ Runtime persistence.

Therefore:

- `Decision` is a Core concept.
- whether individual Decision instances are persisted is a Runtime concern.
- `Decision Record` is a possible persistent representation of a Decision.
- `Decision Memory` is the capability / knowledge structure through which RF-One can retain and relate past Decisions, context, reasoning, Outcomes and Learning.

IMPORTANT:

Do **not** automatically define `Decision Record` or `Decision Memory` as subclasses of `Entity`.

Their persistence model must remain an implementation/domain/runtime concern unless the Core ontology independently requires Entity semantics.

Do not infer:

`persistent = Entity`

without an approved architectural reason.

---

# Documentation to create

Create:

```text
00 Knowledge Repository/Core/ConceptualArchitecture/
├── 00_RF-One_Core_Vision.md
├── 01_Subject_and_Reality.md
├── 02_Desire_Goal_and_Reality_Check.md
├── 03_Decision_Action_Outcome_Learning.md
├── 04_Temporal_Coherence_and_Evolution.md
├── 05_Epistemic_Boundary_and_Subject_Sovereignty.md
├── 06_Business_Autopilot_and_Intelligence_Engine.md
└── 07_Core_Glossary.md
```

These documents become the canonical conceptual architecture for the concepts they define.

Avoid unnecessary duplication between them.

Use cross-references where appropriate.

---

# Required conceptual content

## 00_RF-One_Core_Vision.md

Document the overall RF-One Core vision.

It must clearly establish:

- RF-One Core is domain-independent.
- Core ≠ Domain ≠ Product ≠ Runtime.
- RF-One models a Subject in relation to Reality.
- RF-One does not assume that a human Subject is rational.
- RF-One helps expose what the Subject may not see or may not want to see.
- RF-One helps clarify Desire rather than assuming that declared objectives are automatically correct.
- RF-One helps transform confirmed Desire into pursuable Goals.
- RF-One supports Decisions, Actions, Outcomes and Learning.
- RF-One maintains coherence across time.
- RF-One is intended to evolve together with the Subject and the business.
- RF-One may use external Intelligence Engines.
- RF-One is designed commercially as a Business Autopilot.
- commercial RF-One is business-first and must create measurable economic value.

Include the principle:

> RF-One does not exist merely to answer questions or produce recommendations.  
> It exists to progressively understand the Subject and Reality, help determine and clarify direction, and operate toward confirmed Goals within delegated authority.

Also establish:

> The Core may be universal; commercial Products must have an economic reason to exist.

---

## 01_Subject_and_Reality.md

Define `Subject`.

The Subject may be:

- a person;
- a group;
- an organization;
- another decision-capable entity where appropriate.

Do not define the Subject as necessarily rational.

The Subject may be influenced by any representable factor.

Examples may include:

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

Do not create a mandatory psychological causal pipeline.

Explicitly state:

> Any representable entity or state may potentially trigger, influence, reinforce, weaken, modify or conflict with a Desire.

Define `Reality` as the partially known context in which the Subject exists and acts.

Reality may include:

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

Reality must never be assumed complete.

Describe the foundational relationship:

> **Subject ↔ Reality**

RF-One continuously improves its understanding of both.

---

## 02_Desire_Goal_and_Reality_Check.md

This document must establish that:

> **Desire ≠ Goal**

Define Desire as something the Subject wants.

A Desire:

- does not need to be rational;
- does not need to be currently feasible;
- does not need to be economically sensible;
- does not need to be consistent;
- does not need to be immediately explainable;
- does not need to become a Goal.

RF-One must never invalidate a Desire merely because it appears unrealistic.

Use the Moon example if useful:

> “I want to go to the Moon.”

RF-One must distinguish between:

- impossible;
- currently infeasible;
- no known path;
- insufficient knowledge;
- uncertain;
- temporarily constrained.

Explicitly state:

> “I do not know how” must never silently become “It cannot be done.”

Define Reality Check / Clarification as a continuous Core capability.

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

Reality Check must not remove free will.

Define Goal as a sufficiently clarified and confirmed representation of something the Subject wants that can be treated as pursuable/actionable within understood Reality.

Remove the old rule that a Goal exists only when a Process already exists.

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

A Process supports pursuit of the Goal.

A Process is not the ontological precondition for the Goal to exist.

A Desire that cannot currently become a Goal remains a valid Desire.

---

## 03_Decision_Action_Outcome_Learning.md

Define:

- Decision
- Action
- Outcome
- Learning

Decision must be a first-class Core concept.

Describe relationships such as:

```text
Goal
→ Process
→ Decision
→ Action
→ Outcome
→ Learning
```

but make clear that this is an iterative conceptual cycle, not a mandatory rigid pipeline.

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

Action represents execution or attempted execution.

Outcome represents what actually happens.

Learning represents reusable knowledge generated by comparing:

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

Define carefully:

### Decision Record

A Decision Record may persist information about a Decision.

Do not require every Runtime to persist every Decision.

### Decision Memory

Decision Memory is the ability to retain and relate relevant historical Decision knowledge over time.

It may include:

- Decision context;
- available Evidence;
- considered alternatives;
- reasoning;
- authority;
- expected Outcome;
- actual Outcome;
- resulting Learning.

Do not force Decision Memory or Decision Record into `Entity` semantics unless justified independently.

---

## 04_Temporal_Coherence_and_Evolution.md

Document RF-One's ability to reason across time.

RF-One should not evaluate Decisions only individually.

It should also evaluate the trajectory created by accumulated Decisions and Outcomes.

Define the concept of `Temporal Coherence`.

RF-One should be capable of identifying:

- drift;
- repeated patterns;
- accumulated inconsistency;
- divergence from prior direction;
- changing priorities;
- changes in risk tolerance;
- changing Goals;
- effects that only become visible across time.

Important:

> Change is not automatically inconsistency.

The Subject may consciously change:

- Desire;
- Goal;
- Purpose;
- priorities;
- strategy;
- constraints;
- risk tolerance.

RF-One should:

1. identify meaningful change;
2. surface consequences;
3. clarify whether the change is conscious;
4. confirm when appropriate;
5. update the trajectory.

The objective is conscious evolution, not rigidity.

Also document the constructive evolutionary spiral:

```text
Subject input / Desire
→ RF-One interpretation / challenge / expansion
→ new information and alternatives
→ Subject refinement
→ improved understanding of Reality
→ Goal / Decision / Action
→ Outcome
→ Learning
→ improved next cycle
```

RF-One, the Subject and the business progressively learn together.

---

## 05_Epistemic_Boundary_and_Subject_Sovereignty.md

Define the Epistemic Boundary.

At minimum distinguish:

- Fact
- Observation
- Evidence
- Belief
- Assumption
- Inference
- Hypothesis
- Unknown

Make clear that RF-One must not silently convert:

- hypothesis into fact;
- inference into fact;
- belief into fact;
- lack of knowledge into impossibility.

RF-One should represent confidence/uncertainty where appropriate without requiring a specific Runtime implementation.

Then define `Subject Sovereignty`.

RF-One may:

- challenge;
- question;
- contradict;
- surface ignored information;
- identify incoherence;
- show risk;
- expose consequences;
- propose alternatives;
- recommend reconsideration.

But RF-One must not substitute itself for the Subject's final authority over consciously confirmed Desire and strategic direction.

Include the interaction principle:

> **“Now that you know this, are you still sure?”**

If the Subject understands the relevant information and confirms the direction, RF-One should respect that decision.

Subject Sovereignty and operational autonomy are not contradictory.

The Subject may delegate operational authority while retaining sovereignty over:

- direction;
- Goals;
- authority boundaries;
- constraints;
- override;
- changes in course.

---

## 06_Business_Autopilot_and_Intelligence_Engine.md

Define RF-One as:

> **Business Autopilot under human command**

Use the Pilot/autopilot analogy carefully.

The Pilot should not be required to manually operate every business Process.

The Pilot defines or confirms:

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

The mature model should not require human approval for every operational Decision.

Inside delegated authority:

> **RF-One handles it.**

RF-One must escalate when appropriate, including when:

- authority is insufficient;
- uncertainty exceeds accepted limits;
- risk exceeds tolerance;
- constraints conflict;
- consequences cross escalation thresholds;
- strategic direction may need revision;
- the Goal itself may need reconsideration.

Explicitly state:

> **Human control does not imply continuous human operation.**

### Authority model

Describe autonomy conceptually as bounded authority rather than binary human-vs-AI control.

Do not impose a specific technical permission implementation yet.

Domains and Runtimes may define different authority levels.

### Intelligence Engines

RF-One must remain architecturally distinct from the AI model used to reason.

Potential Intelligence Engines may include:

- OpenAI models;
- Anthropic models;
- Google models;
- specialized models;
- future models.

These models are components.

They are not RF-One itself.

RF-One proprietary value is expected to reside primarily in:

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

Use external commodity services where appropriate.

Do not design RF-One around unnecessary reinvention of commodity technology.

---

## 07_Core_Glossary.md

Create concise canonical definitions for the concepts introduced by this architecture.

At minimum include:

- Subject
- Reality
- Desire
- Goal
- Reality Check
- Clarification
- Decision
- Decision Record
- Decision Memory
- Action
- Outcome
- Learning
- Temporal Coherence
- Subject Sovereignty
- Epistemic Boundary
- Fact
- Observation
- Evidence
- Belief
- Assumption
- Inference
- Hypothesis
- Unknown
- Pilot
- Delegated Authority
- Business Autopilot
- Intelligence Engine
- Domain
- Product
- Runtime

Do not redefine concepts already canonically defined elsewhere unless necessary.

Cross-reference existing canonical definitions where appropriate.

---

# Existing Core files to reconcile

Inspect and update where necessary:

```text
00 Knowledge Repository/Core/README.md
00 Knowledge Repository/Core/RF-ONE Core Principles.md
00 Knowledge Repository/Core/ArchitecturePrinciples.md
00 Knowledge Repository/Core/Glossary.md
00 Knowledge Repository/Core/Goal.md
00 Knowledge Repository/Core/Process.md
00 Knowledge Repository/Core/Entity.md
00 Knowledge Repository/Core/Relationship.md
00 Knowledge Repository/Core/ImplementationGuidelines.md
00 Knowledge Repository/Core/Core Evolution.md
```

Only modify a file when reconciliation is actually required.

Do not perform unrelated cleanup.

---

# Specific required reconciliations

## Goal

Remove or supersede the rule that a Goal exists only after a Process exists.

Ensure Goal and Desire align with the new canonical architecture.

## AI authority

Replace absolute prohibitions such as:

> AI never owns business decisions.

with the approved delegated-authority model.

Preserve human/Subject sovereignty.

## Entity

If `Entity.md` currently states that Decision cannot be an Entity, do not automatically invert this into:

> Decision is an Entity.

Instead clarify the distinction:

- Decision is a first-class Core concept.
- first-class Core concept does not mean Entity.
- persistence and identity semantics are separate questions.

Do not force every Core concept into Entity.

## Relationship / mission framing

Where RF-One is described only as helping humans make better decisions, expand the framing to reflect Business Autopilot:

RF-One may also execute and continuously correct course within delegated authority.

Do not remove the importance of human strategic control.

## Restaurant Purchasing autonomy rules

Review:

```text
00 Knowledge Repository/Domains/Restaurant/Purchasing/AIResponsibilities.md
00 Knowledge Repository/Domains/Restaurant/Purchasing/BusinessPermissions.md
```

Do not rewrite the Restaurant Domain broadly in this task.

Only update language if it directly contradicts the new Core authority model.

Domain-specific requirements for human approval may remain valid where they are deliberate Domain configuration.

A Domain may legitimately choose:

```text
Delegated Authority = none
```

for a particular Decision class.

The Core must not force every Domain to automate everything.

---

# Core versioning

The current Core is marked as frozen/approved.

Follow the repository's existing Core evolution/versioning process.

Update the Core version appropriately to reflect a significant conceptual evolution.

Do not invent a new versioning system.

Add an appropriate entry to the existing Core Evolution / Evolution Log documenting the architectural change.

The entry should summarize the introduction of:

- Subject ↔ Reality;
- Desire sovereignty;
- continuous Reality Check;
- revised Desire → Goal semantics;
- Decision as first-class Core concept;
- Epistemic Boundary;
- Subject Sovereignty;
- Temporal Coherence;
- Business Autopilot;
- Delegated Authority;
- Intelligence Engine abstraction.

---

# Commercial principle

The documentation must clearly preserve the distinction between:

### Universal Core

which may support many future Domains,

and

### RF-One commercial strategy

which is business-first.

RF-One commercial Domains must be capable of producing measurable economic value.

RF-One is not being designed primarily as a low-cost consumer coaching subscription.

Its intended business value should justify B2B pricing in the thousands or tens of thousands of dollars per year when the economic benefit supports it.

Do not hard-code specific pricing into the ontology.

Pricing is commercial strategy, not a Core concept.

---

# Writing requirements

Documentation must be:

- in English;
- precise;
- architecture-oriented;
- readable by future developers and AI agents;
- explicit about what is Core vs Domain vs Product vs Runtime;
- careful about epistemic claims;
- free of unnecessary academic theory;
- free of restaurant-specific assumptions in Core;
- internally cross-referenced where helpful.

Prefer clear definitions over marketing language.

Avoid presenting metaphors as ontology.

The aircraft autopilot analogy may explain the operating model, but `Pilot` and `Business Autopilot` must still have precise conceptual definitions.

---

# Prohibited changes

Do not modify:

- production code;
- Python files;
- database files;
- spreadsheets;
- generated API specifications;
- generated database specifications;
- application behavior;
- supplier/invoice processing logic;
- unrelated Restaurant Domain entities;
- files under `Old/`.

Do not delete anything.

Do not move anything.

Do not rename anything.

---

# Final consistency review

After writing the documentation:

1. Search the repository for definitions that directly contradict the new canonical architecture.
2. Reconcile contradictions that are clearly inside the scope of this task.
3. Do not expand scope to unrelated cleanup.
4. Verify all links/references added by this task.
5. Verify that Core, Domain, Product and Runtime remain distinct.
6. Verify that Subject Sovereignty and Business Autopilot coexist without contradiction.
7. Verify that Decision is first-class without incorrectly equating it with Entity or persistence.
8. Verify that Desire remains valid even when it cannot currently become a Goal.
9. Verify that no text implies that incomplete knowledge equals impossibility.
10. Verify that external LLM providers are described as Intelligence Engines rather than RF-One itself.

---

# Required final report

When complete, provide an implementation report containing:

### Created files

List every file created.

### Modified files

List every existing file modified and briefly explain why.

### Legacy material incorporated

Identify useful concepts recovered from `Old/`, without modifying legacy files.

### Architectural reconciliations

Summarize the major contradictions that were resolved.

### Remaining inconsistencies

Report any relevant inconsistency deliberately left unchanged and explain why.

### Versioning

State the Core version/evolution-log changes made.

### Scope confirmation

Explicitly confirm whether any software/runtime files were modified.

Do not make a Git commit.

Stop after the report.
