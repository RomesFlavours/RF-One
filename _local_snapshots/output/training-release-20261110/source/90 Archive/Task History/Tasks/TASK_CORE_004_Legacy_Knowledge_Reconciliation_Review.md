# TASK_CORE_004 — Legacy Knowledge Reconciliation Review

## Objective

Review the legacy RF-One knowledge under `Old/X00 Knowledge Repository/` and determine, concept by concept, what must be:

- incorporated into current canonical documentation;
- moved to a Domain rather than Core;
- treated as commercial/product strategy;
- retained only as historical reference;
- explicitly rejected because it conflicts with Core 2.0;
- left unresolved pending Product Owner decision.

This is an **analysis and reconciliation-planning task only**.

Do not modify, move, rename, delete, archive, deprecate, or create any repository file or directory.

The purpose is to ensure that no valuable historical RF-One knowledge is lost before the repository is physically reorganized and `Old/` is moved under the future archive structure.

---

## Mandatory first steps

1. Read `CLAUDE.md` completely.
2. Read:
   - `Tasks/TASK_CORE_001_Conceptual_Architecture.md`
   - `Tasks/TASK_CORE_002_Core_Documentation.md`
   - `Tasks/TASK_CORE_003_Repository_Structure_Review.md`
3. Read the current canonical Core 2.0 documentation, including:
   - `00 Knowledge Repository/Core/README.md`
   - `00 Knowledge Repository/Core/RF-ONE Core Principles.md`
   - `00 Knowledge Repository/Core/ArchitecturePrinciples.md`
   - `00 Knowledge Repository/Core/ImplementationGuidelines.md`
   - `00 Knowledge Repository/Core/Glossary.md`
   - `00 Knowledge Repository/Core/Entity.md`
   - `00 Knowledge Repository/Core/Goal.md`
   - `00 Knowledge Repository/Core/Process.md`
   - `00 Knowledge Repository/Core/Relationship.md`
   - `00 Knowledge Repository/Core/Core Evolution.md`
   - all files under `00 Knowledge Repository/Core/ConceptualArchitecture/`
4. Inspect the relevant current Restaurant Domain documentation where a legacy concept may belong to the Domain rather than Core.
5. Inspect all substantive files under `Old/X00 Knowledge Repository/`.

Do not treat the fact that a legacy document says `Approved` as evidence that it remains authoritative.

Current Core 2.0 documentation has priority where a concept has already been consciously reconciled.

---

# Approved architectural context

The following principles are already approved and must not be reopened in this task.

## Core separation

> **Core ≠ Domain ≠ Product ≠ Runtime**

Core is domain-independent.

A concept must not be promoted into Core merely because it is useful to the Restaurant Domain or to RF-One's commercial strategy.

---

## Subject and Reality

RF-One models:

> **Subject ↔ Reality**

The human Subject must not be assumed rational.

Any representable entity, state, event, belief, memory, emotion, relationship, environment, or other factor may influence a Desire.

No mandatory psychological causal pipeline is assumed.

---

## Desire and Goal

> **Desire ≠ Goal**

A Desire remains valid even if it is irrational, currently infeasible, uncertain, or has no known path.

Reality Check / Clarification is continuous, including before Desire, during Desire formation, before Goal formation, during execution, and after Outcomes.

A Goal does not require a Process to exist first.

---

## Subject Sovereignty

The Subject remains sovereign over consciously confirmed Desire and strategic direction.

RF-One may challenge, contradict, surface blind spots, expose assumptions, and recommend reconsideration.

Operational authority may nevertheless be delegated to RF-One.

---

## Business Autopilot

RF-One is designed as:

> **Business Autopilot under human command**

RF-One may make and execute business Decisions within explicitly delegated authority.

Human control does not imply continuous human operation.

---

## Decision

Decision is a first-class Core concept.

First-class Core concept does not imply Entity.

Runtime persistence is a separate concern.

Decision Record and Decision Memory must not be automatically equated with Entity.

---

## Epistemic Boundary

RF-One must distinguish at least:

- Fact
- Observation
- Evidence
- Belief
- Assumption
- Inference
- Hypothesis
- Unknown

Do not silently convert incomplete knowledge into impossibility or inference into fact.

---

# Product Owner decisions from TASK_CORE_003 review

These decisions are approved for the future repository migration.

## 1. Environment

Future target:

```text
01 Domains/_Shared/Environment/
```

Rationale:

Geography, legal, fiscal, regulatory, standards, and similar material describe shared operating Reality across Domains rather than universal Core ontology.

Do not move it in this task.

---

## 2. Archive strategy

Future target:

```text
90 Archive/
└── Legacy Repository/
    └── [preserve original historical hierarchy as far as practical]
```

Do not split the historical repository prematurely into newly interpreted categories such as `Legacy Core`, `Legacy Domains`, etc.

The archive location itself will make the material non-authoritative.

Do not use `.OLD.md` as the primary archival mechanism.

Do not move anything in this task.

---

## 3. External collaborator material

Future target for the current Shelbi material:

```text
08 External/Shelbi/
```

It remains active external/reference material, not canonical RF-One architecture and not historical archive.

Do not move it in this task.

---

## 4. Ingredient placeholder

`00 Knowledge Repository/Domains/Restaurant/Domain/Ingredient.md` remains Domain material.

The phrase `See generated content placeholder` is treated as old scaffolding, not proof that Ingredient belongs under Generated Documentation.

Do not relocate it.

---

## 5. InvoiceIntake

`03 Software/InvoiceIntake/` remains under Software.

A Product may use this software, but Product and Software are distinct layers.

Do not move it.

---

## 6. Legacy reconciliation before archive

Substantive legacy knowledge must be reviewed before `Old/` is archived.

Do not assume that everything under `Old/` is obsolete.

Do not physically archive `Old/` until this reconciliation has been completed and approved.

---

# Main review scope

The review must examine the legacy repository concept-by-concept, not merely file-by-file.

The most important files identified during TASK_CORE_003 are listed below.

---

## A. Objectives

Review:

```text
Old/X00 Knowledge Repository/01 Objectives/Objectives.md
```

TASK_CORE_003 identified potentially valuable concepts including:

- Maximize Economic Profit;
- Cash-Based Profit;
- Unlimited Optimization Scope;
- Legal Compliance;
- Operational vs Strategic time horizons;
- measuring value generated by comparing actual result vs counterfactual.

For each concept determine whether it belongs to:

- universal Core;
- a Business Domain / shared business Domain;
- RF-One commercial strategy;
- Product strategy;
- Decision/Outcome/Learning architecture;
- research/reference only;
- archive only;
- reject because incompatible.

Important:

Do not automatically place `Maximize Economic Profit` in Core.

Core 2.0 is universal and must allow Subjects to pursue non-economic Desires.

RF-One commercial strategy is business-first and economic-value-oriented, but commercial strategy is not automatically ontology.

---

## B. RF-ONE Domain Principles

Review in detail:

```text
Old/X00 Knowledge Repository/06 Business Model/RF-ONE Domain Principles.md
```

TASK_CORE_003 identified potentially useful principles including:

- Ownership vs Assignment are distinct concepts;
- Single Source of Truth;
- Specialization Extends Never Replaces;
- Responsibility/Availability belongs to the smallest responsible Entity;
- Capacity belongs to the physical provider;
- Capabilities Enable Services;
- Facts Are Persisted, Conclusions Are Inferred;
- Early Failure Recognition.

This list is not exhaustive.

Review the entire document.

For each principle classify it as one of:

- already fully represented in current canonical documentation;
- partially represented and worth strengthening;
- valid Core principle;
- valid Domain principle;
- valid Runtime/implementation principle;
- Product/commercial principle;
- obsolete;
- conflicting with Core 2.0;
- unclear / Product Owner decision required.

Do not promote implementation rules into ontology.

Do not demote universal ontology into a Restaurant-specific Domain simply because it was historically documented there.

---

## C. Brand

Compare:

```text
Old/X00 Knowledge Repository/06 Business Model/Brand.md
```

with the current canonical:

```text
00 Knowledge Repository/Core/Brand.md
```

TASK_CORE_003 noted legacy sections such as:

- Customer Experience;
- Product Standards;
- Service Standards;
- Marketing.

Determine whether those concepts were:

- intentionally removed;
- already represented elsewhere;
- valid Domain/Product concepts;
- still appropriate in Core;
- useful but should be separated from the Core definition of Brand.

Take into account the current RF-One direction in which Brand may be derived from business goals and then drive service model, behavior, training, selection, and operating standards.

Do not redesign Brand in this task.

Only identify what knowledge is missing, duplicated, misplaced, or conflicting.

---

## D. Corporate

Compare:

```text
Old/X00 Knowledge Repository/06 Business Model/Corporate.md
```

with:

```text
00 Knowledge Repository/Core/Corporate.md
```

Review legacy concepts including:

- Corporate Processes;
- Corporate Documents;
- any ownership, structure, authority, or organizational relationships that are not fully represented in current canonical documentation.

Classify each missing concept by correct layer.

---

## E. Operational Unit

Compare:

```text
Old/X00 Knowledge Repository/06 Business Model/Operational Unit.md
```

with:

```text
00 Knowledge Repository/Core/Operational Unit.md
```

Review legacy concepts including:

- Known Specializations;
- Lifecycle;
- any resource/capacity/responsibility semantics absent from the current file.

Determine whether they remain valid.

---

## F. Knowledge Domains taxonomy

Review:

```text
Old/X00 Knowledge Repository/05 Knowledge Domains/README.md
```

TASK_CORE_003 identified a taxonomy of approximately 18 areas such as:

- Financial Performance;
- Sales;
- Menu;
- Recipes;
- Purchasing;
- Inventory;
- Suppliers;
- Operations;
- Personnel;
- Equipment;
- Facilities;
- Marketing;
- Reputation;
- Strategic Planning;
- AI;
- and others.

Determine whether this taxonomy should become:

- a canonical Restaurant Domain roadmap;
- a broader Business Domain map;
- research/planning material;
- future Product coverage map;
- historical only.

Do not assume a historical `Knowledge Domain` maps directly to the current architectural concept `Domain`.

This distinction is critical.

---

## G. Service vs Software strategy

Review:

```text
Old/X00 Knowledge Repository/06 Business Model/Why RF-ONE Must Be Delivered as a Service, Not as Software.pdf
```

Extract and summarize the strategic claims.

Determine whether each claim belongs to:

- Product/commercial strategy;
- operating model;
- architecture;
- deployment/runtime;
- historical business rationale.

Do not place service-delivery strategy in Core ontology unless there is a genuine universal architectural reason.

If the PDF cannot be fully inspected in the available environment, explicitly report that limitation instead of guessing.

---

## H. Already reconciled legacy concepts

Review only to confirm that no still-useful material was omitted:

```text
Old/X00 Knowledge Repository/06 Business Model/Desire.md
Old/X00 Knowledge Repository/06 Business Model/Decision.md
Old/X00 Knowledge Repository/06 Business Model/Goal.md
Old/X00 Knowledge Repository/06 Business Model/Process.md
```

Core 2.0 has already superseded key claims from these files.

Do not reopen approved changes such as:

- Desire → Process → Goal;
- Goal requiring an existing Process;
- Decision being only transient computation;
- AI being limited to recommendation.

Only report any additional useful concept that was not already carried forward.

---

## I. Remaining substantive legacy files

Inspect all other non-trivial legacy files.

Do not limit the review to the files named above.

For each substantive file, determine whether it contains knowledge that is:

- already canonical;
- missing from current canonical documentation;
- misplaced by layer;
- obsolete;
- contradictory;
- historical only.

Stub and empty files may be grouped rather than reviewed line by line.

---

# Layer classification model

Every legacy concept that is still valuable must be assigned to one of the following target layers.

## 1. Core

Use only for universal RF-One concepts, relationships, reasoning principles, epistemic principles, authority principles, or abstractions that are genuinely reusable across Domains.

Examples:

- Subject;
- Reality;
- Desire;
- Goal;
- Decision;
- epistemic states;
- generic Entity semantics.

---

## 2. Shared Domain knowledge

Future target may include structures such as:

```text
01 Domains/_Shared/
```

Use for reusable business/operating knowledge that is not universal ontology but may apply across multiple business Domains.

Examples may include regulatory context, shared economic concepts, common business structures, etc.

Do not create these directories in this task.

---

## 3. Specific Domain

Use for knowledge that belongs to a specific Domain such as Restaurant.

Example:

- recipe semantics;
- menu concepts;
- restaurant purchasing rules;
- restaurant service sequence.

---

## 4. Product

Use for a commercial configuration that combines Domains, capabilities, packages, customer-specific operating choices, or go-to-market decisions.

---

## 5. Software / Runtime

Use for implementation behavior, persistence choices, technical architecture, provider integrations, runtime constraints, permission implementation, APIs, etc.

---

## 6. Commercial strategy

Use for business model, pricing logic, measurable economic value positioning, service-delivery strategy, market strategy, and related decisions that are important to RF-One as a company but are not ontology.

Commercial strategy may later require its own canonical location.

Do not invent the location in this task unless necessary for the recommendation.

---

## 7. Research / Reference

Use for useful material that informs RF-One but is not yet approved as architecture or operating policy.

---

## 8. Archive only

Use for concepts that have historical value but should not be carried into current canonical knowledge.

---

# Reconciliation rules

## Preserve meaning, not wording

Do not recommend copying legacy text verbatim merely because it exists.

Identify the underlying concept.

Determine whether the concept remains valid.

Recommend where the concept should live.

---

## Do not flatten layers

A business principle is not automatically Core.

A commercial objective is not automatically Goal ontology.

An implementation pattern is not automatically a Domain rule.

A Restaurant concept is not automatically universal.

---

## Avoid duplicate canonical sources

If a concept is already fully represented in a current canonical document, recommend no additional canonical definition.

Cross-reference rather than duplicate where appropriate.

---

## Explicitly identify contradictions

For every legacy claim that conflicts with Core 2.0, identify:

- legacy file;
- legacy claim;
- current canonical replacement;
- whether any non-conflicting part should still be preserved.

---

## Preserve uncertainty

If classification is genuinely ambiguous, mark it as requiring Product Owner decision.

Do not resolve philosophical or strategic ambiguity by assumption.

---

# Expected output

Return a **Legacy Knowledge Reconciliation Report** with exactly the following sections.

## A. Executive summary

State:

- how much meaningful knowledge remains only in `Old/`;
- whether `Old/` can currently be archived safely;
- the major categories of knowledge still needing migration.

---

## B. Legacy concept inventory

Provide a table:

| Legacy source | Concept / principle | Current canonical coverage | Recommended target layer | Recommendation | Confidence |
|---|---|---|---|---|---|

Use recommendations such as:

- ALREADY CANONICAL
- INCORPORATE
- STRENGTHEN CURRENT
- MOVE TO DOMAIN
- MOVE TO SHARED DOMAIN
- MOVE TO PRODUCT
- MOVE TO COMMERCIAL STRATEGY
- MOVE TO SOFTWARE/RUNTIME
- RESEARCH ONLY
- ARCHIVE ONLY
- REJECT / SUPERSEDED
- PRODUCT OWNER DECISION

Confidence should be:

- High
- Medium
- Low

---

## C. Core candidates

List only legacy concepts that genuinely appear to deserve incorporation into universal Core.

For each provide:

- source;
- concise legacy idea;
- why it is universal;
- current Core gap;
- exact canonical file that should eventually receive it;
- whether it changes ontology or only documentation.

Be conservative.

---

## D. Domain candidates

Separate into:

### Shared Domain candidates

and

### Restaurant Domain candidates

Explain why each concept is Domain knowledge rather than Core.

---

## E. Commercial / Product strategy candidates

List valuable legacy concepts related to:

- economic objectives;
- value measurement;
- service model;
- business model;
- pricing/ROI logic;
- product positioning;
- strategic scope.

Do not incorrectly force them into Core.

Recommend whether RF-One needs a future canonical Commercial Strategy area.

---

## F. Runtime / implementation candidates

List legacy concepts that belong to Software/Runtime rather than Core or Domain.

---

## G. Already superseded concepts

List legacy claims that are explicitly superseded by Core 2.0.

For each point to the canonical replacement.

---

## H. Historical-only material

Identify material that should simply remain historical/reference after migration.

Stub/empty files may be grouped.

---

## I. Brand / Corporate / Operational Unit reconciliation

Provide a focused comparison for these three entities.

For each:

- valuable legacy sections not represented today;
- likely correct layer;
- recommendation;
- whether a future canonical update is needed.

---

## J. Knowledge Domains taxonomy recommendation

Explain what the old `Knowledge Domains` taxonomy actually represents in modern RF-One terms.

Explicitly answer:

- Is it ontology?
- Is it a Domain structure?
- Is it a Product roadmap?
- Is it a capability/coverage map?
- Should any part become canonical?

---

## K. Service-vs-Software document

Summarize the PDF's useful strategic claims.

Classify each major claim by layer.

If the document could not be fully read, say so explicitly.

---

## L. Knowledge migration plan

Provide the safest sequence for a future documentation-reconciliation task.

Do not perform the migration.

The sequence should identify:

1. which canonical files to update first;
2. which new canonical strategy/domain documents may be required;
3. which old documents can then be considered safely superseded;
4. which items must remain unresolved.

---

## M. Product Owner decisions required

List only genuine unresolved decisions.

Do not ask questions that can be answered from the repository.

---

## N. Archive readiness

End with one of:

> `OLD REPOSITORY IS SAFE TO ARCHIVE AFTER APPROVED RECONCILIATIONS ABOVE`

or

> `OLD REPOSITORY IS NOT YET SAFE TO ARCHIVE`

Explain why.

---

# Restrictions

Do not:

- modify any file;
- create any file;
- move any file;
- rename any file;
- delete any file;
- alter `Old/`;
- update Core;
- update Domain documentation;
- change README files;
- change PROJECT_STATE;
- change software;
- change database files;
- make a Git commit;
- begin repository migration.

This task is analysis only.

---

# Final instruction

Stop after delivering the Legacy Knowledge Reconciliation Report.

Wait for explicit Product Owner approval before any canonical documentation is modified.
