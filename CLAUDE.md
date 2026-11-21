# CLAUDE.md

# RF-One Project Instructions

## Operational database principle and development roles — Product Owner, 2026-11-21 (RF1_OPERATIONAL_DATABASE_001)

Mandatory for every task. The single normative text is
`10 System/Operational Database and Data Governance/README.md` (verbatim approved
original: `SOURCE_DECISION_IT.md` in the same folder); this is a pointer to it.

1. **RF-One owns its information model and its canonical operational database.**
   Clover, OpenTable, ADP, PayPal, Amazon, the future RF POS and any other source
   only supply data. Mandatory flow: source → acquisition connector (extraction and
   format translation only) → common ingestion service → RF-One canonical
   operational database → Domains. Domains never read provider APIs, provider
   schemas or connector staging tables for ordinary business logic; never build a
   Clover (or other provider) engine for one Domain or one period; never duplicate
   the same business fact per module.
2. **Design is done by the Product Owner + ChatGPT; Claude implements.** Implement
   complete, approved specifications faithfully. Do not add workflows, schemas,
   tables, columns, APIs, information models or architectural decisions of your own.
   When a choice the specification does not define emerges, **stop and submit it to
   design** — do not decide it. Do not invent column or table names not verified in
   the existing code.
3. **Codex performs the independent review** using
   `03 Software/Infrastructure/deploy/CODEX_INDEPENDENT_REVIEW_CHECKLIST.md`; hand
   over the commit and its report. Codex does not change requirements.
4. **Release only after explicit Product Owner approval:** no push, merge,
   deployment, destructive migration or production change without specific
   authorization, unless the assignment already expressly grants it.

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

Every Domain lives under one of two families, physically expressed as the two folders directly inside `01 Domains/` (verify against `01 Domains/README.md` and `01 Domains/Domain Architecture.md` §4 before assuming this list is complete — those files are authoritative, this is a pointer to them):

- **Shared Domains** (`01 Domains/Shared Domains/`, formerly named **Cross Domain**) — industry-independent, reusable by any business: Selection, Operational Knowledge, Continuous Productivity Development, Performance, Personnel Management, Taxation, Administration, Purchased.
- **Business Domain** (`01 Domains/Business Domain/`) — industry-specific: Restaurant (currently the only one).

A Shared Domain may consume industry-specific content a Business Domain supplies, but must never structurally depend on one specific Business Domain. `_Shared/` holds domain-independent-but-not-universal knowledge reused across multiple Domains (e.g. `_Shared/Environment/`) — it is not itself a Domain, and lives outside both families, directly under `01 Domains/`. **Do not confuse `_Shared/` (not a Domain; not-yet-universal environment/context knowledge) with the `Shared Domains/` family (Domains that are Domains, just reusable by any Business Domain).**

**Purchased** (`01 Domains/Shared Domains/Purchased/`) is a Shared Domain consumed by Business Domains: it turns what the business was invoiced for into normalized purchased facts (one line per economic item/service/charge on a source document), owning only the purchase fact — never whether it was paid (Bank Reconciliation boundary, owned by the consuming Business Domain). See `01 Domains/Shared Domains/Purchased/README.md`. It does not redefine or merge with Restaurant's existing, Business-Domain-specific `Purchasing` module (see below) — their relationship is an explicitly open question, not decided by Purchased's own definition.

**Selection, Operational Knowledge, Continuous Productivity Development and Performance are each their own top-level Shared Domain** (`01 Domains/Shared Domains/Selection/`, `.../Operational Knowledge/`, `.../Continuous Productivity Development/`, `.../Performance/` — TASK_DOMAINS_003 for Selection; the Cross Domain/Business Domain reorganization (Cross Domain since renamed Shared Domains) for the former Training (now Operational Knowledge) and Performance; a later reorganization for Continuous Productivity Development), not modules of Personnel Management or of Restaurant — usable by any industry, closely related to but not owned by Personnel Management's Personnel Decisions module. Do not nest any of them under either. **Operational Knowledge is the shared repository of retrievable operational information (Operational Knowledge Pills) that Copilot and other RF-One functions may retrieve — it does not train, test, assess, or certify.** It is independent of, and must not be confused with, Continuous Productivity Development, which identifies gaps/opportunities, decides interventions (of which actual human training is only one candidate), measures outcomes, and learns from results. Restaurant's Industry Extension of Selection (role catalog, client/role configurations) lives at `01 Domains/Business Domain/Restaurant/Selection/`, depending on Selection Core, never the reverse.

Several familiar business-capability names are **modules of an existing Domain**, not Domains in their own right. Do not create a new top-level `01 Domains/<name>/` folder for any of these — extend the owning Domain instead:

- Purchasing and Sales are modules of the Restaurant Domain (`Restaurant Domain └── Purchasing module`, `Restaurant Domain └── Sales module`, canonically `01 Domains/Business Domain/Restaurant/Purchasing/` and `01 Domains/Business Domain/Restaurant/Sales/`). Restaurant's Purchasing module is not the same thing as the Purchased Shared Domain above; see that Domain's README for the currently-open question about their relationship.
- Workforce and Personnel Decisions are modules of the Personnel Management Domain (`Personnel Management Domain └── <module>`, canonically `01 Domains/Shared Domains/Personnel Management/<module>/`). Note the canonical module name is **Personnel Decisions**, not "Personal Decision." **Operational Knowledge, Continuous Productivity Development and Performance are NOT modules of Personnel Management** — despite the similar naming pattern, all three are independent top-level Shared Domains (see above); do not re-nest them under Personnel Management.

**"BD" is an accepted textual abbreviation for "Business Domain"** in RF-One documents (never a folder/path rename — `Business Domain/` stays spelled out on disk).

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
10 System/                  system-level capabilities spanning the whole platform (not a Domain, not a Product)
90 Archive/                 never current authority, regardless of status text inside
```

Top-level directory `README.md` files, where present, describe purpose and authority; inspect the actual tree before relying on one. `07 Tasks/README.md` is absent at the reviewed baseline, so do not invent or assume its contents.

---

# Mandatory Repository Context Before Any Task

At the start of **every** task, read this file and the repository `README.md`. Identify the exact checked-out branch/commit, the approved task and the affected canonical documents; read the applicable `00 Core/`, `01 Domains/`, `02 Products/`, `09 Strategy/` and `10 System/` sources before changing code or documentation. Use `03 Software/` for implementation behavior, not to override canonical business meaning. Historical task reports (`07 Tasks/`) and `PROJECT_STATE.md` are evidence and dated snapshots, not substitutes for current approved specifications.

Before implementation, provide a compact **source-of-authority checklist**: task/specification, canonical paths consulted, requirements/invariants, prohibited changes, affected dependencies, unresolved contradictions. Do not proceed on an unresolved material business decision. When an approved specification is supplied in chat but not yet committed, explicitly flag the documentation update needed; never pretend another agent can see the chat.

Work only on the intended branch; never silently change `main`, Shelbi's integration branch, production data or AWS. A local checkout is not automatically synchronized with GitHub: verify the intended ref before work and use explicit Git fetch/pull and push/PR procedures. Never claim automatic synchronization.

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

Act as an **Implementation Engineer** executing approved Product Owner specifications, not as an autonomous product architect or business-rule designer.

Your responsibilities are to:

- read the approved task and relevant canonical Core, Domain, Product and System documentation before editing;
- identify applicable rules, constraints, dependencies and any contradictory or missing decisions;
- implement the approved behavior faithfully, without adding unapproved workflows, validations, blockers, entities or abstractions;
- update affected technical references without silently changing approved conceptual decisions;
- run appropriate tests and report evidence, changes, limitations and unresolved questions.

The Product Owner and ChatGPT conduct product/functional architecture and approve decisions. Claude implements the approved specification. Codex performs an **independent technical review** of the implementation against the approved specification and canonical documentation before any deployment authorization. The Product Owner authorizes integration/deployment after reviewing the evidence. Claude's own tests and consistency checks do not replace Codex's independent review.

If a specification conflicts with canonical documentation or leaves a material business decision unresolved, stop that affected work, cite the exact files/sections and ask for a Product Owner decision. Do not infer approval from existing code, old task reports or a plausible design. A request to investigate, review, redesign, or propose alternatives is **not** authorization to select or implement an architectural or functional change. Claude may choose only technical implementation details that preserve the approved specification. Any change to business workflow, data schema, API contract, authorization behavior, user-visible behavior, or canonical model requires an explicit, documented Product Owner decision formulated with ChatGPT **before implementation**. Claude may present options with tradeoffs but cannot approve or implement one on its own.

Required sequence for implementation work: **Product Owner + ChatGPT specification → Claude implementation and tests → Codex independent review → Product Owner authorization for merge/deploy**. Do not merge or deploy merely because code or tests are ready.

The "Repository Architect" role means keeping the repository's structure,
references and documentation consistent with approved decisions. It does not
authorize designing new architecture, data models, workflows or APIs: under
RF1_OPERATIONAL_DATABASE_001 §7 design belongs to the Product Owner + ChatGPT,
implementation to Claude, independent review to Codex (see the section
*Operational database principle and development roles* at the top of this file).

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

For business data sources (POS, reservation, payroll, payment, marketplace and
any future source) this is mandatory, not merely "where practical": data reaches
the Domains only through the connector → common ingestion → RF-One canonical
operational database path of RF1_OPERATIONAL_DATABASE_001
(`10 System/Operational Database and Data Governance/README.md`).

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

Before **every** implementation task, including supposedly small or technical changes:

1. Read the approved task/specification and relevant canonical documentation.
2. Inspect the affected references, interfaces, source-of-truth rules and dependencies.
3. Identify the files that may change, expected behavior, and prohibited changes.
4. Separate technical implementation choices within the approved design from functional or architectural decisions that require Product Owner approval.
5. If a change to business flow, data schema, API contract, permissions, user-visible behavior or canonical model is required but not explicitly approved, **stop only that affected work**; report the exact decision needed to the Product Owner and ChatGPT. Never treat a request to analyze or redesign as approval to implement.
6. Implement **only the portion covered by an explicit approved specification**; otherwise report the blocker. No presumed approval because a design seems reasonable or an ambiguity appears minor.

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

# RF-One UI Rules

**Standing instruction, applied automatically to every RF-One interface
task.** Full text and implementation pointers:
`03 Software/Shared UI/UI Rules.md`. In short:

1. Times shown to a person are the Location's local time (its
   `Location.timezone`), never UTC. UTC stays internal.
2. Employees in operational displays are "Surname I." ("Ceban T."), never
   a technical id, unless the full name is genuinely needed.
3. Frequent actions are available where they are needed, calling the one
   central implementation — never a copy — so the person does not have to
   open a sub-page just to perform them.
4. Every sub-page shows its clickable hierarchical path (breadcrumb)
   instead of a generic "Home" link; the path reflects the real structure
   and never invents levels.
5. After an action started from a list row (Edit, Save, Cancel, Confirm…)
   the person is back on that same record, at the same place on screen,
   with focus on the button used — never at the top of the list, also
   after a reload (`rf-one-row-return.js`, rows marked `data-rr-key`).

Every future UI refinement reuses these rules.

---

# Bank Local Environment

The local Bank working environment (both PCs) is run ONLY through
`03 Software/Infrastructure/Bank Local Environment/` (Configura PC, Avvia
Bank, Chiudi Bank / Cambia PC) — never by an ad-hoc launcher or by opening
a database inside OneDrive. When the Product Owner asks to **interpret the
AI Rules waiting** («Interpreta le AI Rules in attesa»), follow
`SESSION_INTERPRETATION.md` in that folder.

---

# Bank on AWS — no further local data transfer

On 2026-10-17 (BANK_REINSTALL_001) the cleaned local Bank database was loaded once into AWS. From then on the
local Bank database is **never** transferred to AWS again: Bank releases carry code and migrations only and
preserve the online data (`03 Software/Infrastructure/README.md`, "Bank reinstallato su AWS").

---

# RF-One Report Standard

**Standing instruction, applied automatically to every RF-One task.** It is
never to be re-requested from the Product Owner and never needs repeating
inside an individual command. It governs every Domain, Module, deploy,
test, import, migration, UAT and any other RF-One work.

Every RF-One task ends with a final **REPORT**. The REPORT must:

- carry the title **REPORT**, clearly visible;
- be organized in numbered sections;
- use plain, human, understandable language;
- use compact tables wherever they make a comparison easier;
- clearly distinguish **observed facts** from **interpretations** and from
  **solutions adopted or proposed**;
- state what was changed and, where relevant, what was deliberately **not**
  changed;
- surface problems, missing capabilities, and any decisions the Product
  Owner still has to make;
- include the success criteria and the outcome of each;
- end with the references needed for traceability, backup or restore.

After the REPORT, always emit the RF-One completion **beep**. The beep is
the absolute last action of the work — **no text may appear after it.**

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