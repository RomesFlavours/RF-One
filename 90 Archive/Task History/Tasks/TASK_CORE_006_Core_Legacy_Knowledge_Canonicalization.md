# TASK_CORE_006 — Core Legacy Knowledge Canonicalization

## Objective

Implement the **approved Core-level legacy reconciliations** recorded in:

```text
07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md
```

This task is the first canonicalization phase after the repository migration.

The goal is to recover valid universal RF-One concepts from the legacy repository **without importing obsolete assumptions, Runtime-specific patterns, Domain-specific rules, or commercial strategy into Core**.

This is a documentation-only Core task.

Do not modify software, database, Product, Strategy, Archive, External, Research, Meetings, or Restaurant Domain content.

Do not make a Git commit.

---

# Mandatory first steps

1. Read `CLAUDE.md` completely.
2. Read:
   - `07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md`
   - `07 Tasks/TASK_CORE_004_Legacy_Knowledge_Reconciliation_Review.md`
   - `07 Tasks/TASK_CORE_005_Canonical_Repository_Migration.md`
   - `07 Tasks/Reports/TASK_CORE_005_REPORT.md`
3. Read all current canonical Core documentation relevant to the concepts below, especially:
   - `00 Core/Entity.md`
   - `00 Core/Relationship.md`
   - `00 Core/Glossary.md`
   - `00 Core/Process.md`
   - `00 Core/RF-ONE Core Principles.md`
   - `00 Core/ArchitecturePrinciples.md`
   - `00 Core/ImplementationGuidelines.md`
   - `00 Core/Core Evolution.md`
   - `00 Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md`
   - `00 Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md`
   - `00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md`
   - `00 Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md`
4. Inspect the relevant legacy source files under:
   - `90 Archive/Legacy Repository/X00 Knowledge Repository/06 Business Model/Entity.md`
   - `90 Archive/Legacy Repository/X00 Knowledge Repository/06 Business Model/Process.md`
   - `90 Archive/Legacy Repository/X00 Knowledge Repository/06 Business Model/Relationship.md`
   - `90 Archive/Legacy Repository/X00 Knowledge Repository/06 Business Model/RF-ONE Domain Principles.md`
5. Run `git status` before editing.

The Archive is historical and non-authoritative.

Use it only as source material for concepts already approved in the backlog.

---

# Approved architectural constraints

The following remain authoritative and must not be weakened or reopened.

## Core separation

> **Core ≠ Domain ≠ Product ≠ Runtime**

Only universal RF-One semantics belong in Core.

---

## Subject sovereignty

The Subject retains strategic sovereignty.

RF-One may challenge, reason, decide, and act within Delegated Authority, but must not erase conscious Subject control.

---

## Desire and Goal

> **Desire ≠ Goal**

A Desire does not need to be rational, feasible, economically useful, or immediately actionable.

A Goal is a sufficiently clarified/confirmed representation that can be pursued under understood Reality.

---

## Reality and uncertainty

RF-One must preserve the distinction between:

- demonstrated impossibility;
- current infeasibility;
- no known path;
- insufficient knowledge;
- uncertainty;
- temporary constraint.

Do not convert “we do not know how” into “it cannot be done.”

---

## Decision

Decision is a first-class Core concept.

First-class does not imply Entity.

Persistence remains a separate Runtime concern.

---

## Runtime neutrality

Core must not prescribe database schemas, event-sourcing architectures, persistence rules, provider technologies, or implementation mechanisms unless the concept is genuinely semantic rather than technical.

---

# Authorized canonical updates

The task may modify only these current canonical Core files:

```text
00 Core/Entity.md
00 Core/Relationship.md
00 Core/Glossary.md
00 Core/Process.md
00 Core/RF-ONE Core Principles.md
00 Core/ArchitecturePrinciples.md
00 Core/ImplementationGuidelines.md
00 Core/Core Evolution.md
00 Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md
00 Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md
00 Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md
```

Do not modify every file merely because it is authorized.

Prefer the smallest coherent set of changes.

You may create only the required report file:

```text
07 Tasks/Reports/TASK_CORE_006_REPORT.md
```

No other new files are authorized.

---

# Reconciliation items to implement

## 1. Early Failure Recognition

### Approved principle

RF-One should recognize as early as reasonably possible when:

- a Goal is infeasible under current known conditions;
- a required Constraint cannot be satisfied;
- available evidence does not support proceeding;
- no known path currently exists;
- uncertainty is too high for the current authority/risk boundary.

This is a useful RF-One outcome, not a system failure.

### Required semantic safeguard

Do not collapse:

```text
infeasible now
```

into:

```text
impossible
```

and do not collapse:

```text
no known path
```

into:

```text
no path exists
```

### Likely target

```text
00 Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md
```

Optionally strengthen `RF-ONE Core Principles.md` only if doing so materially improves canonical clarity.

Do not create a new Entity or state machine for this concept.

---

## 2. Recursive Process / abstraction independence

### Approved principle

A Process may be recursively decomposed.

A lower-level Process does not require a separate universal Core type such as `Activity`.

Granularity alone does not create a fundamentally different class of thing.

Examples:

```text
Process
→ sub-Process
→ sub-Process
```

may all remain Process.

### Required semantic safeguard

Do not require every Domain or Runtime to model Process decomposition explicitly.

Do not introduce persistence requirements.

### Target

```text
00 Core/Process.md
```

---

## 3. Modern optimization hierarchy

The legacy literal rule:

```text
Mission > Domain Principles > Business Rules > Goal > Execution
```

is explicitly rejected as a direct Core import.

### Approved replacement

Optimization and execution must remain subordinate to the currently applicable combination of:

- consciously confirmed Subject direction;
- active Goal(s);
- Constraints;
- Subject Sovereignty;
- Delegated Authority;
- applicable law/policy;
- known risk limits;
- relevant Reality.

Efficiency or optimization must never silently override these higher-order boundaries.

### Important

Do not introduce `Mission` as a new Core primitive.

Do not force a single rigid total ordering when multiple Goals, Constraints, risks, or authority boundaries coexist.

### Likely targets

```text
00 Core/Process.md
00 Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md
```

Use the smallest necessary change.

---

## 4. Entity versioning as an optional Core pattern

### Approved principle

RF-One Core must be able to represent:

```text
stable conceptual identity
```

separately from:

```text
versioned definitions / configurations
```

when a Domain requires it.

Example pattern:

```text
Recipe
→ Recipe Version 1
→ Recipe Version 2
```

The example is illustrative only and must not make Recipe a Core concept.

### Required safeguards

Do not say every Entity must be versioned.

Do not say every version must be a persistent Entity.

Do not prescribe version tables, schema fields, or storage.

Do not confuse:

- Entity identity;
- temporal validity;
- versioned definition;
- audit history.

### Target

```text
00 Core/Entity.md
```

---

## 5. Temporal semantics

### Approved principle

Core must be able to represent that concepts, relationships, configurations, and states may have temporal validity and may change over time.

RF-One should be able to reason about:

- what was true;
- what is true;
- what is expected or intended to become true;
- when a definition or relationship applied;
- historical trajectories.

This must align with existing Temporal Coherence.

### Required safeguards

Do not mandate:

```text
EffectiveFrom
EffectiveTo
```

or any other database field.

Do not imply that every Entity has the same lifecycle.

Do not merge temporal validity with version identity.

### Likely targets

```text
00 Core/Entity.md
00 Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md
```

Prefer clarification over duplicated definitions.

---

## 6. Ownership vs Assignment

### Approved principle

Ownership and Assignment are distinct relationship meanings.

Something may be:

- owned by one Subject/Entity;
- assigned to another;
- operated by another;
- responsible to another;
- available to another;

without those relationships being equivalent.

### Required safeguards

Do not prescribe universal cardinalities.

Do not prescribe a database model.

Do not assume ownership implies operational responsibility.

Do not assume assignment transfers ownership.

### Likely targets

```text
00 Core/Relationship.md
00 Core/Glossary.md
```

Add glossary definitions only if needed for unambiguous reuse.

---

## 7. Specialization extends rather than erases identity

### Approved principle

A specialized concept may extend a more general concept without silently replacing or erasing the general concept's meaning and identity.

A specialization may add:

- Constraints;
- Relationships;
- attributes;
- rules;
- behavior;
- Domain semantics.

It should not redefine the parent concept so aggressively that the parent ceases to mean the same thing.

### Required safeguard

Do not force inheritance as a software implementation pattern.

This is a conceptual modeling principle, not an object-oriented programming rule.

### Likely target

```text
00 Core/Entity.md
```

Optionally `ArchitecturePrinciples.md` if a cross-Core statement is truly warranted.

---

# Explicitly rejected / deferred legacy items

The following must **not** be imported into Core in this task.

## Process persistent status

Do not add:

> Process status must never be persisted.

Persistence/derivation remains Runtime/Domain dependent.

---

## Hybrid Event Model

Do not add a universal rule that:

> immutable Events generate Entity state.

Event sourcing is not approved as universal Core architecture.

---

## Capacity / Availability / Responsibility placement

Do not generalize into universal Core rules such as:

- Capacity belongs to the physical provider;
- Availability belongs to the smallest responsible Entity;
- Responsibility belongs to the smallest responsible Entity.

Leave current specific valid rules where they already exist.

---

## Capabilities Enable Services

Do not elevate into a new universal Core principle.

---

## Operational Unit physical lifecycle

Do not import:

```text
Planning
→ Legal Creation
→ Site Acquisition
→ Construction
→ Licensing
→ Operational
→ Closed
```

into universal Core lifecycle semantics.

This remains future Domain/Shared-Domain work.

---

## Corporate legal fields

Do not add jurisdiction-specific Corporate legal identity fields to Core.

---

## Commercial strategy

Do not add any of the following to Core:

- Maximize Economic Profit;
- Cash-Based Profit;
- Unlimited Optimization Scope;
- SaaS-only strategy;
- shared-intelligence commercial model;
- counterfactual B2B value measurement as a universal Outcome definition.

These belong to future `09 Strategy/` work.

---

# Documentation quality requirements

For every modified Core file:

1. Preserve existing valid Core 2.0 content.
2. Integrate new knowledge naturally rather than appending an obvious “legacy” section.
3. Avoid duplicated definitions across multiple files.
4. Prefer references to canonical concepts already defined elsewhere.
5. Keep Core terminology consistent with `ConceptualArchitecture/07_Core_Glossary.md` and `Glossary.md`.
6. Do not create new capitalized Core concepts casually.
7. If a new term appears to require ontology, stop and report rather than inventing it.

---

# Version/status handling

If the repository uses document version/status headers:

- increment versions only where substantive canonical content changes justify it;
- preserve existing status conventions;
- do not mark experimental wording `Approved` unless the file's existing governance model makes the change part of the already-approved backlog;
- record this reconciliation in `00 Core/Core Evolution.md`.

The Core Evolution entry should state that TASK_CORE_006 incorporated approved universal concepts from the legacy reconciliation backlog while explicitly keeping rejected Runtime/Domain/commercial patterns out of Core.

Do not rewrite historical evolution entries.

---

# Validation

After editing:

1. Search the modified Core files for contradictions with:
   - Subject Sovereignty;
   - Desire ≠ Goal;
   - Delegated Authority;
   - Epistemic Boundary;
   - Core ≠ Domain ≠ Product ≠ Runtime.
2. Search for accidental introduction of:
   - mandatory Event sourcing;
   - mandatory Process status derivation;
   - `Mission` as a new Core primitive;
   - universal physical-business lifecycle;
   - economic-profit objective as universal Core Goal.
3. Verify Markdown links in modified files.
4. Run `git status`.
5. Do not stage or commit unless staging is necessary for your internal inspection; leave final Git commit to the Product Owner.

---

# Required report

Create:

```text
07 Tasks/Reports/TASK_CORE_006_REPORT.md
```

with exactly these sections.

## A. Summary

What approved legacy concepts were incorporated.

## B. Files modified

For each file:

- exact path;
- conceptual change;
- reason.

## C. Early Failure Recognition

State exactly how it was incorporated and how impossibility vs infeasibility vs unknown path remain distinct.

## D. Process reconciliation

State exactly how recursive Process and the modern optimization hierarchy were represented.

Confirm that no universal Process persistence rule was added.

## E. Entity reconciliation

State exactly how:

- optional versioning;
- temporal semantics;
- specialization;

were represented.

Confirm that no mandatory Event-sourcing model was added.

## F. Relationship reconciliation

State exactly how Ownership vs Assignment was represented.

## G. Explicit exclusions

Confirm that the following were not imported into Core:

- Hybrid Event Model as universal rule;
- no-persistent-status rule;
- Capacity/Availability/Responsibility generalization;
- Operational Unit physical lifecycle;
- Corporate legal fields;
- commercial strategy items.

## H. Core consistency review

Report any remaining contradictions or ambiguities discovered.

Do not fix out-of-scope issues silently.

## I. Git status / scope confirmation

Confirm:

- no software modification;
- no Domain modification;
- no Strategy modification;
- no Archive modification;
- no Git commit.

---

# Restrictions

Do not:

- modify `01 Domains/`;
- modify `02 Products/`;
- modify `03 Software/`;
- modify `04 Generated Documentation/`;
- modify `05 Research/`;
- modify `06 Meetings/`;
- modify `08 External/`;
- modify `09 Strategy/`;
- modify `90 Archive/`;
- change Runtime behavior;
- change database schemas;
- create new Core entities without explicit approval;
- introduce a new `Mission` primitive;
- make a Git commit.

---

# Final response

After creating the report, return only:

1. a short completion summary;
2. the exact report path:

```text
07 Tasks/Reports/TASK_CORE_006_REPORT.md
```

Then stop.
