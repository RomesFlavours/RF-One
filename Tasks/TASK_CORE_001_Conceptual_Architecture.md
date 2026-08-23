# TASK-CORE-001 — RF-One Core Conceptual Architecture Impact Review

## Objective

Inspect the RF-One repository and identify the documentation and architectural impact of the approved RF-One Core conceptual direction described below.

This is an **inspection and impact-analysis task only**.

Do not modify, create, rename, move or delete any repository file yet.

---

## Mandatory first step

Read `CLAUDE.md` completely before doing anything else.

Then inspect the repository structure and all existing documentation that may define or depend on RF-One Core concepts.

Pay particular attention to any existing definitions of:

- Core
- Subject
- Desire
- Goal
- Resource
- Condition
- Constraint
- Process
- Decision
- Action
- Outcome
- Learning
- Purpose
- Value
- Belief
- Reality
- autonomy
- AI / intelligence architecture
- restaurant-specific assumptions inside Core

---

# Approved conceptual direction

The following architecture has already been conceptually approved.

Your task is **not to redesign it**.

Your task is to determine how it should be represented consistently in the existing repository and what existing documentation would need reconciliation.

---

## 1. Core is domain-independent

RF-One Core is not a restaurant product and must not be defined through a specific commercial application.

The architecture must preserve the distinction:

**Core ≠ Domain ≠ Product ≠ Runtime**

Core defines reusable concepts, relationships and reasoning principles.

Domains configure and use the subset of Core concepts they require.

Products may combine multiple Domains.

Runtime implementations determine how those concepts are instantiated, observed, inferred, stored and executed.

The existence of a concept in Core does not imply that:

- every Domain must use it;
- every Product must expose it;
- every Runtime must collect it;
- every concept can always be measured directly;
- every concept must always be instantiated.

---

## 2. RF-One models a Subject in relation to Reality

The foundational relationship is:

**Subject ↔ Reality**

The Subject may be:

- a person;
- a group;
- an organization;
- or another decision-capable entity when a Domain supports it.

Reality represents the known or partially known environment in which the Subject exists and acts.

Reality may include, depending on Domain:

- facts;
- observations;
- resources;
- conditions;
- constraints;
- opportunities;
- relationships;
- environments;
- events;
- capabilities;
- risks;
- external actors;
- unknowns.

The model must not assume that Reality is ever completely known.

---

## 3. The Subject must not be assumed to be rational

RF-One must not model human decision-making as a mandatory rational causal pipeline.

A human Subject may be:

- emotional;
- contradictory;
- impulsive;
- uncertain;
- misinformed;
- influenced by current state;
- influenced by memories;
- influenced by relationships;
- influenced by beliefs;
- influenced by values;
- influenced by identity;
- influenced by experiences;
- influenced by environmental stimuli;
- influenced by conscious or subconscious factors.

No fixed psychological sequence such as:

`Experience → Need → Value → Purpose → Desire`

is assumed by Core.

Any representable entity may potentially:

- trigger;
- influence;
- reinforce;
- weaken;
- modify;
- or conflict with

a Desire.

RF-One does not attempt to make the origin of Desire artificially rational.

---

## 4. Desire is sovereign

A Desire represents something the Subject wants.

The Subject is free to have any Desire.

A Desire does not need to be:

- rational;
- feasible;
- internally consistent;
- economically sensible;
- immediately actionable;
- currently explainable.

RF-One must never invalidate a Desire merely because it appears unrealistic.

Example:

A Subject may Desire to go to the Moon.

RF-One must not assume this is impossible.

The Subject may be an astronaut, may be capable of becoming one, may mean something different by the statement, or relevant Reality may still be unknown.

---

## 5. Reality Check is continuous

Reality Check / Clarification is not a stage that occurs only after Desire.

It is a continuous Core capability.

It may operate:

- before a Desire emerges;
- while the Subject is forming or clarifying a Desire;
- after a Desire is expressed;
- before Goal formation;
- during Goal pursuit;
- before important Decisions;
- after Outcomes;
- whenever new information changes the known Reality.

RF-One should help the Subject see:

- relevant facts;
- contradictions;
- unsupported assumptions;
- ignored consequences;
- conflicts among Desires;
- conflicts with previously expressed priorities;
- risks;
- constraints;
- opportunities;
- uncertainty;
- information the Subject may consciously or unconsciously be avoiding.

Reality Check does not remove free will.

Its purpose is to improve clarity before the Subject confirms a direction.

---

## 6. Desire and Goal are different concepts

**Desire ≠ Goal**

A Desire is something the Subject wants.

A Goal is a Desire, or a derived representation of that Desire, that has been sufficiently clarified and can be represented as something pursuable or actionable within understood Reality.

The transition is therefore conceptually closer to:

`Desire ↔ Clarification / Reality Check → Confirmed Desire → Goal`

rather than a simple automatic conversion.

The transition may require consideration of:

- Resources;
- Conditions;
- Constraints;
- Knowledge;
- Capabilities;
- Time;
- Risk;
- Dependencies;
- uncertainty.

---

## 7. A Desire does not disappear because it cannot currently become a Goal

RF-One must distinguish between:

- demonstrated impossibility;
- current infeasibility;
- no currently known path;
- insufficient information;
- uncertainty;
- temporary constraints.

RF-One must not convert:

**“I do not know how”**

into:

**“It cannot be done.”**

A Desire may remain valid while being classified as currently non-actionable.

It may later become actionable if Reality changes or new knowledge becomes available.

---

## 8. Subject Sovereignty is a Core principle

RF-One may:

- question;
- challenge;
- contradict;
- expose inconsistencies;
- surface information;
- identify risk;
- show consequences;
- recommend reconsideration;
- escalate uncertainty;
- propose alternatives.

RF-One must not replace the Subject as the final authority over the Subject's own consciously confirmed Desire.

A fundamental interaction pattern is:

**“Now that you know this, are you still sure?”**

If the Subject understands the relevant situation and consciously confirms the Desire or direction, RF-One should respect that confirmation and help determine how to pursue it.

Subject Sovereignty must remain distinct from operational delegation.

---

## 9. Epistemic Boundary

RF-One must explicitly distinguish different knowledge states.

At minimum, review how the Core should represent or distinguish:

- Fact
- Observation
- Evidence
- Belief
- Assumption
- Inference
- Hypothesis
- Unknown

The system must never silently convert inference or hypothesis into fact.

The deeper RF-One reasons about a Subject or Reality, the more important this epistemic distinction becomes.

---

## 10. Operational cycle

Once Goals exist, RF-One supports an iterative operational cycle including:

`Goal → Process → Decision → Action → Outcome → Learning`

This is not necessarily a rigid linear pipeline.

Learning may update:

- Reality understanding;
- Subject understanding;
- Processes;
- future Decisions;
- Goals;
- constraints;
- assumptions;
- models.

Outcomes must create reusable knowledge rather than being treated as isolated historical events.

---

## 11. RF-One reasons across time

RF-One must evaluate more than individual Decisions.

It should also understand the **trajectory** produced by Decisions over time.

A series of locally reasonable Decisions may collectively produce strategic or personal drift.

RF-One should therefore be able to identify:

- drift;
- accumulated inconsistency;
- repeated patterns;
- divergence from prior strategic direction;
- emerging conflicts;
- changes in priorities;
- effects of repeated Decisions.

This creates a concept of **temporal coherence**.

---

## 12. Change is not automatically inconsistency

The Subject is allowed to evolve.

A conscious change of:

- Desire;
- Goal;
- Purpose;
- strategy;
- priorities;
- constraints;
- risk tolerance

must not automatically be treated as an error.

RF-One should make the change explicit, expose the consequences, confirm the change with the Subject where appropriate, and update the trajectory.

The objective is not rigidity.

The objective is conscious evolution.

---

## 13. RF-One and the Subject evolve together

RF-One should support an iterative constructive loop where interaction itself improves understanding.

Conceptually:

`Subject input / Desire`
→ `RF-One interpretation, challenge and expansion`
→ `new information / alternatives`
→ `Subject refinement`
→ `better Reality understanding`
→ `Goal / Decision / Action`
→ `Outcome`
→ `Learning`
→ `better next interaction`

The process may be viewed as an upward spiral of increasing understanding rather than a closed repetitive loop.

The system should accumulate context and learning over time.

---

## 14. RF-One is a Business Autopilot

RF-One's mature business operating model is not limited to recommendation.

RF-One is designed to function as a:

**Business Autopilot under human command**

The Subject acts as the Pilot.

The Pilot defines or confirms:

- Desires;
- Goals;
- strategic direction;
- constraints;
- risk tolerance;
- authority boundaries;
- unacceptable outcomes.

Within delegated authority, RF-One should be capable of continuously:

- observing the business;
- interpreting Reality;
- detecting deviations and opportunities;
- making Decisions;
- executing Actions;
- measuring Outcomes;
- learning;
- correcting course.

The mature default should not necessarily be:

**“recommend everything to a human.”**

Within approved authority, the desired behavior is:

**RF-One handles it.**

---

## 15. Human control does not mean continuous human operation

The Pilot retains:

- command;
- supervision;
- override authority;
- ability to change destination;
- ability to reduce or expand delegated authority.

RF-One should escalate when:

- authority is insufficient;
- uncertainty is too high;
- risk exceeds accepted limits;
- constraints conflict;
- strategic direction may need revision;
- the Goal itself may no longer be appropriate;
- consequences cross defined thresholds.

The analogy is aircraft autopilot:

the Pilot remains responsible for direction and can intervene, but does not manually perform every correction required throughout the journey.

**Human control does not imply continuous human operation.**

---

## 16. The intelligence model is interchangeable

RF-One must not be architecturally identical to a specific LLM provider.

Models such as:

- OpenAI GPT;
- Anthropic Claude;
- Google models;
- future models;
- specialized models

may function as **Intelligence Engines**.

They are components of RF-One, not RF-One itself.

RF-One should remain provider-independent where practical.

The intelligence engine may evolve or be replaced without redefining the RF-One Core.

---

## 17. RF-One proprietary value

RF-One's proprietary value is expected to reside primarily in areas such as:

- Core ontology;
- Subject Model;
- Reality Model;
- Domain knowledge;
- accumulated organizational knowledge;
- Decision Memory;
- Outcome history;
- epistemic model;
- Desire / Goal semantics;
- temporal coherence;
- alignment logic;
- reasoning orchestration;
- Process knowledge;
- business rules;
- constraints;
- autonomous operating logic;
- learning across time;
- cross-domain intelligence.

Commodity technical primitives may be provided through external services when appropriate.

RF-One should not rebuild technology merely because it is possible to rebuild it.

---

## 18. Business-first commercial strategy

The Core may eventually support domains such as Personal Decision Intelligence.

However, RF-One's commercial strategy is business-first.

RF-One is being designed to create measurable economic value through business.

The intended commercial model is not primarily based on low-cost consumer subscriptions.

Commercial Domains should be capable of supporting pricing measured in:

**thousands or tens of thousands of dollars per year**

because they generate significantly greater measurable economic value for the customer.

Examples of value may include:

- increased profit;
- reduced labor waste;
- improved purchasing;
- better capacity utilization;
- reduced hiring mistakes;
- reduced turnover;
- faster training;
- improved performance;
- better allocation of capital;
- reduced management dependency;
- avoided costly Decisions;
- identified opportunities;
- improved operating consistency.

A Domain may be conceptually interesting, but a commercial Product must answer:

**Who pays?  
Why do they pay?  
What measurable economic value does RF-One create?**

---

# Expected output

After inspecting the repository, provide an **Architectural Impact Report** containing only the following sections:

## A. Existing relevant structure

Identify the current directories and files that already document concepts affected by this task.

For each important file, briefly state why it is relevant.

## B. Conceptual conflicts

Identify existing definitions that genuinely conflict with the approved direction.

For every conflict provide:

- exact file;
- existing concept or definition;
- approved concept it conflicts with;
- why reconciliation is required.

Do not report a conflict merely because the approved model is more abstract or broader.

## C. Duplicate or overlapping definitions

Identify places where the same concept currently appears in multiple locations and could become inconsistent.

## D. Proposed documentation structure

Propose the smallest coherent documentation structure needed to represent this architecture.

Do not create files yet.

A possible structure to evaluate is:

```text
Core/
└── ConceptualArchitecture/
    ├── 00_RF-One_Core_Vision.md
    ├── 01_Subject_and_Reality.md
    ├── 02_Desire_Goal_and_Reality_Check.md
    ├── 03_Decision_Action_Outcome_Learning.md
    ├── 04_Temporal_Coherence_and_Evolution.md
    ├── 05_Epistemic_Boundary_and_Subject_Sovereignty.md
    ├── 06_Business_Autopilot_and_Intelligence_Engine.md
    └── 07_Core_Glossary.md