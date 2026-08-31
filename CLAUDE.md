# CLAUDE.md

# RF-One Project Instructions

This file defines the working rules that must always be followed when contributing to the RF-One repository.

---

# What RF-One Is

RF-One is built around a **domain-independent Core**.

The Core is not a restaurant product and is not itself a commercial application.

It defines generic concepts, their meaning, and their relationships.

Examples may include:

- Subject
- Purpose
- Value
- Belief
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

Application Domains use only the Core concepts they require.

Current canonical top-level Domains (verify against `01 Domains/README.md` and `01 Domains/Domain Architecture.md` before assuming this list is complete — those files are authoritative, this is a pointer to them):

- Restaurant
- Personnel Management
- Taxation
- Administration

`_Shared/` holds domain-independent-but-not-universal knowledge reused across multiple Domains (e.g. `_Shared/Environment/`) — it is not itself a Domain.

Several familiar business-capability names are **modules of an existing Domain**, not Domains in their own right. Do not create a new top-level `01 Domains/<name>/` folder for any of these — extend the owning Domain instead:

- Purchasing and Sales are modules of the Restaurant Domain (`Restaurant Domain └── Purchasing module`, `Restaurant Domain └── Sales module`, canonically `01 Domains/Restaurant/Purchasing/` and `01 Domains/Restaurant/Sales/`).
- Workforce, Selection, Training, Performance and Personnel Decisions are modules of the Personnel Management Domain (`Personnel Management Domain └── <module>`, canonically `01 Domains/Personnel Management/<module>/`). Note the canonical module name is **Personnel Decisions**, not "Personal Decision."

Commercial Products may combine one or more Domains.

---

# Fundamental Architectural Rule

Always distinguish between:

## 1. Core

The Core defines **what concepts mean and how they may relate**.

A concept existing in the Core does NOT imply:

- that every Domain must use it;
- that every implementation must collect data for it;
- that it must always be instantiated;
- that RF-One must be able to measure it;
- that every Product must expose it.

The Core is definition, not implementation.

## 2. Domain

A Domain applies and, where necessary, specializes Core concepts for a specific field.

Domains should remain conceptually modular and reusable.

## 3. Product

A Product is a commercial application built using one or more Domains.

Products are designed to create measurable value for their users.

## 4. Runtime

Runtime is where actual data, inference, execution, recommendations and actions occur.

Do not reject a Core concept because runtime data may not currently exist for it.

**Core definition and data availability are separate questions.**

---

# Product Philosophy

RF-One does not begin from available data or existing software features.

The general direction is:

**understand the subject and its objectives first, then determine what knowledge, processes, decisions, actions and data are required.**

Do not narrow the Core to fit the first Product or Domain.

Restaurant is currently an important application and testing environment, but it must not unnecessarily constrain the Core.

---

# Language

Always communicate with the Product Owner in **Italian**, unless explicitly requested otherwise.

Use **English** for:

- source code;
- variable and function names;
- database objects;
- API definitions;
- GitHub documentation;
- repository documentation;
- technical documentation intended for developers.

---

# Repository Structure

Respect the repository structure.

Do not rename, move or reorganize folders without explicit approval.

Do not create parallel definitions when an existing concept should be updated.

Before making structural changes, inspect all references that may be affected.

The canonical top-level structure (established by TASK_CORE_005) is:

```text
00 Core/                    highest authority — universal ontology
01 Domains/                 canonical per-Domain business knowledge
02 Products/                canonical Product-level configuration
03 Software/                runtime behavior, not concept meaning
04 Generated Documentation/ derived material, never a source of truth
05 Research/                not canonical
06 Meetings/                not canonical
07 Tasks/                   task specs, reports, backlog — historical record
08 External/                external/reference material only, not RF-One authority
09 Strategy/                canonical for RF-One's own company/product strategy
90 Archive/                 never current authority, regardless of status text inside
```

Each top-level directory carries its own `README.md` stating purpose, authority level, and what does/does not belong there — consult it before assuming where new material belongs.

---

# Documentation First

Documentation comes before implementation.

Default workflow:

1. Concept / README
2. Functional Specification
3. User Stories when applicable
4. Data Requirements
5. Business Rules
6. Development
7. Testing
8. Consistency Review

Do not start coding when the required functional or architectural definition has not been approved.

---

# Approved Architectural Decisions

When an architectural or conceptual specification has been explicitly approved:

- implement it faithfully;
- identify contradictions with existing repository content;
- identify affected dependencies;
- update dependent documentation consistently;
- report unresolved conflicts.

Do **not** replace an approved abstraction with a different model simply because another theory or implementation would also be possible.

External theories, frameworks or industry models may be suggested as references, but must not become architectural constraints unless explicitly approved.

---

# Challenge Rules

Challenge:

- contradictions;
- logical inconsistencies;
- duplicate concepts;
- unclear relationships;
- hidden dependencies;
- implementation risks;
- security or compliance risks;
- assumptions that materially affect correctness.

Do not challenge an abstraction merely because:

- it is broad;
- it is difficult to measure;
- current data does not exist;
- a current Product does not need it;
- another theoretical model exists.

When raising an objection, always identify:

1. the exact contradiction or risk;
2. the affected files or concepts;
3. why it matters;
4. the smallest reasonable correction.

Do not turn implementation work into an unrelated theoretical debate.

---

# Role of Claude

Act as a **Repository Architect, Implementation Engineer and Consistency Reviewer**.

Your responsibilities are to:

- inspect the repository;
- implement approved specifications;
- maintain conceptual consistency;
- find affected references;
- update documentation and code;
- identify genuine unresolved architectural questions;
- test implementations;
- report what changed.

Conceptual architecture is established through approved specifications.

If a specification is clear, implement it.

If a genuine ambiguity prevents correct implementation, ask the Product Owner.

Do not redesign approved concepts unless explicitly asked to do so.

---

# Modular Architecture

Domains should be modular and reusable.

Avoid unnecessary coupling.

However, do not create artificial separation when two Domains naturally share Core knowledge.

Products may combine multiple Domains when their combined value is greater than their standalone value.

---

# External Technology

RF-One may use external APIs and commercial services for commodity capabilities.

Examples include:

- LLMs;
- speech-to-text;
- text-to-speech;
- translation;
- avatars;
- video;
- OCR;
- scheduling;
- messaging;
- external datasets.

Do not rebuild commodity technology unless there is a clear strategic reason.

Keep RF-One's proprietary value in its:

- model;
- logic;
- knowledge;
- orchestration;
- decision processes;
- learning mechanisms.

Where practical, keep provider-specific integrations behind abstractions so providers can be replaced.

---

# Simplicity

Prefer simple, understandable and maintainable solutions.

Avoid:

- unnecessary complexity;
- premature optimization;
- speculative abstractions without conceptual value;
- technology introduced only because it is fashionable.

Complexity is acceptable when the underlying concept genuinely requires it.

---

# Coding Standards

Write clean, readable and maintainable code.

Use consistent naming.

Document non-obvious decisions.

Prefer clarity over cleverness.

Do not silently change the meaning of an existing approved concept.

---

# Before Editing

For significant architectural tasks:

1. Read the supplied task/specification.
2. Inspect all relevant repository references.
3. Identify the files that will probably change.
4. Identify contradictions or blockers.
5. Implement unless a genuine unresolved ambiguity prevents doing so.

---

# After Editing

Provide a concise implementation report containing:

- files created;
- files modified;
- concepts implemented;
- references updated;
- tests or consistency checks performed;
- unresolved issues;
- questions requiring Product Owner decisions.

Never hide unresolved contradictions.

---

# Final Principles

When working on the **Core**, ask first:

**"Is this concept correctly defined at the level of abstraction where it belongs?"**

Then:

**"Is it consistent with the rest of the Core and reusable across Domains?"**

When working on a **Domain**, ask:

**"Does this Domain correctly apply the Core without contaminating it with domain-specific assumptions?"**

When working on a **Product**, ask:

**"Does this create meaningful value for the intended user?"**

And always remember:

**Core ≠ Domain ≠ Product ≠ Runtime.**