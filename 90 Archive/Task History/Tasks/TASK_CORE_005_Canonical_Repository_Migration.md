# TASK_CORE_005 — Canonical Repository Migration

## Objective

Migrate the RF-One repository to the approved canonical directory structure while preserving Git history, protecting legacy knowledge, updating path references, and making authority boundaries obvious to future developers and AI agents.

This task is authorized to:

- create directories;
- move and rename directories/files using Git-aware moves where practical;
- create/update repository README and structure-governance documentation;
- update path references made stale by the migration;
- create an explicit legacy-reconciliation backlog;
- move the legacy repository into the non-authoritative archive.

This task is **not** authorized to redesign Core concepts, rewrite Domain ontology, change software behavior, or perform the legacy conceptual reconciliations themselves.

Do not make a Git commit.

---

## Mandatory first steps

1. Read `CLAUDE.md` completely.
2. Read:
   - `Tasks/TASK_CORE_001_Conceptual_Architecture.md`
   - `Tasks/TASK_CORE_002_Core_Documentation.md`
   - `Tasks/TASK_CORE_003_Repository_Structure_Review.md`
   - `Tasks/TASK_CORE_004_Legacy_Knowledge_Reconciliation_Review.md`
3. Reinspect the current repository structure and run `git status`.
4. Confirm the working tree is clean except for the task file itself if it has just been added locally.
5. Before moving anything, identify all Markdown links and textual/code references to paths that will change.

If unexpected uncommitted changes are present outside this task, stop and report them before migration.

---

# Approved target structure

The canonical top-level structure is:

```text
RF One/
├── 00 Core/
├── 01 Domains/
├── 02 Products/
├── 03 Software/
├── 04 Generated Documentation/
├── 05 Research/
├── 06 Meetings/
├── 07 Tasks/
├── 08 External/
├── 09 Strategy/
└── 90 Archive/
```

The numbering is intentional.

Do not introduce additional top-level directories unless required by an existing tracked repository file.

---

# Authority model

The migration must make the following authority model explicit.

## `00 Core/`

Highest canonical authority for universal RF-One ontology, conceptual architecture, reasoning principles, epistemic principles, and domain-independent architecture.

Core must not contain Restaurant-specific rules or RF-One company commercial strategy.

---

## `01 Domains/`

Canonical knowledge for reusable Domains built on Core.

A Domain may use only the Core concepts it requires.

Domain knowledge does not redefine universal Core concepts.

Future examples may include:

- Restaurant;
- Workforce;
- Selection;
- Training;
- other business Domains.

---

## `02 Products/`

Canonical Product-level documentation.

Products may combine Core capabilities and multiple Domains.

Products do not redefine Core or Domain semantics.

---

## `03 Software/`

Runtime implementation.

Software is authoritative for actual runtime behavior, but not for the conceptual meaning of Core/Domain concepts.

---

## `04 Generated Documentation/`

Derived/generated material.

It is never the primary architectural source of truth.

Generated documentation must be regenerated from authoritative sources rather than edited as if it defined architecture.

---

## `05 Research/`

Research, exploration, competitor studies, experiments, external technical investigation, and non-canonical analytical material.

Research may influence architecture but does not become canonical automatically.

---

## `06 Meetings/`

Meeting notes and chronological discussion records.

A meeting decision becomes architectural authority only after it is formalized in the appropriate canonical location.

---

## `07 Tasks/`

Approved work instructions, implementation history, Product Owner decisions, execution reports, and reconciliation backlog.

Tasks record why/how changes were made but do not replace current canonical Core/Domain/Product documentation.

---

## `08 External/`

External collaborator/source material.

Material here is reference/input, not RF-One architectural authority.

---

## `09 Strategy/`

Canonical strategy for RF-One as a company/product business, distinct from customer business Domains and from universal Core ontology.

This area is intended for future documentation such as:

- commercial strategy;
- business model;
- value measurement;
- service/delivery strategy;
- product portfolio strategy;
- company-level knowledge governance;
- multi-tenant/shared-intelligence strategy.

Do not populate substantive strategy in this task beyond a README explaining the layer.

---

## `90 Archive/`

Historical/non-authoritative material.

Nothing under `90 Archive/` is current RF-One architectural authority regardless of what status text appears inside an archived historical document.

Historical files should remain unmodified whenever possible.

---

# Approved migration map

Perform the following structural migration.

## Core

Move:

```text
00 Knowledge Repository/Core/
```

to:

```text
00 Core/
```

Preserve internal structure.

In particular:

```text
00 Knowledge Repository/Core/ConceptualArchitecture/
```

becomes:

```text
00 Core/ConceptualArchitecture/
```

Prefer `git mv` or moves that Git can reliably detect as renames.

Do not rewrite file contents during the physical move except later in this task where path/index updates are explicitly required.

---

## Domains

Before moving the Domain tree, correct the known misplaced README.

Current:

```text
00 Knowledge Repository/Domains/README.md
```

contains Purchasing Module documentation rather than a Domains-level README.

Move that content/file to:

```text
00 Knowledge Repository/Domains/Restaurant/Purchasing/README.md
```

provided there is no existing `README.md` at that destination.

If a destination README unexpectedly exists, stop and report the conflict.

Then move:

```text
00 Knowledge Repository/Domains/Restaurant/
```

to:

```text
01 Domains/Restaurant/
```

Rename:

```text
01 Domains/Restaurant/Domain/
```

to:

```text
01 Domains/Restaurant/Model/
```

Rationale:

`Domain/` inside `Domains/Restaurant/` creates avoidable conceptual ambiguity.

`Model/` is a neutral container for the current Ingredient, OU-Restaurant, OperationalArea, Product, PurchasingModel, Specification material without asserting that every file is necessarily an Entity.

Do not change the conceptual content of those files in this task.

---

## Shared Environment

Move:

```text
00 Knowledge Repository/Environment/
```

to:

```text
01 Domains/_Shared/Environment/
```

Approved rationale:

Geography, legal, fiscal, regulatory, standards, and similar material describe shared operating Reality across Domains rather than universal Core ontology.

Do not expand the current stub content in this task beyond path/index adjustments if necessary.

---

## Remove obsolete wrapper

After Core, Domains, and Environment have been moved, the directory:

```text
00 Knowledge Repository/
```

should no longer contain active canonical material.

If anything remains there unexpectedly, stop and report it before removing the empty wrapper.

Do not delete substantive unexpected files.

---

## Products

Move/rename:

```text
01 Products/
```

to:

```text
02 Products/
```

If the current directory is empty and therefore not tracked by Git, simply create the target canonical directory with a README as specified below.

---

## Software

Keep:

```text
03 Software/
```

at the same path.

Do not reorganize its internal modules in this task.

`InvoiceIntake/` remains Software.

Do not move it to Products.

---

## Generated Documentation

Move/rename:

```text
02 Generated Documentation/
```

to:

```text
04 Generated Documentation/
```

Preserve existing subdirectory intent.

If currently empty/untracked, create the target structure only where a README or tracked file is needed.

Do not create unnecessary empty subdirectories solely to mimic local scaffolding unless their purpose is already documented and durable.

---

## Research

Move/rename:

```text
04 Research/
```

to:

```text
05 Research/
```

If empty/untracked, create the canonical directory with README only.

---

## Meetings

Move/rename:

```text
05 Meetings/
```

to:

```text
06 Meetings/
```

If empty/untracked, create the canonical directory with README only.

---

## Tasks

Move:

```text
Tasks/
```

to:

```text
07 Tasks/
```

Preserve all task files.

Create:

```text
07 Tasks/Reports/
```

and:

```text
07 Tasks/Backlog/
```

only because they have explicit durable responsibilities defined in this task.

Do not move existing TASK files into Reports or Backlog.

Task specifications stay directly under `07 Tasks/` unless a later task defines a different convention.

---

## External

Move:

```text
Shelbi/
```

to:

```text
08 External/Shelbi/
```

Preserve all files and internal directories.

Do not alter the PDF contents.

This material remains active external/reference material, not archive.

---

## Strategy

Create:

```text
09 Strategy/
```

with a `README.md` only.

Do not create substantive commercial strategy documents yet.

The next reconciliation task will populate approved strategy content.

---

## Archive

Create:

```text
90 Archive/
```

and:

```text
90 Archive/Legacy Repository/
```

Before moving `Old/`, create the approved legacy reconciliation backlog described below.

After that backlog exists, move:

```text
Old/X00 Knowledge Repository/
```

to:

```text
90 Archive/Legacy Repository/X00 Knowledge Repository/
```

Preserve the historical hierarchy under `X00 Knowledge Repository/`.

Do not split it into newly interpreted `Legacy Core/`, `Legacy Domains/`, etc.

Do not add `.OLD.md` suffixes.

Do not rewrite archived documents.

If other files/directories remain under `Old/`, preserve them under:

```text
90 Archive/Legacy Repository/
```

while maintaining original relative context.

After confirmed successful moves, remove only empty obsolete wrapper directories.

---

# Approved legacy knowledge backlog

Before physically archiving `Old/`, create:

```text
07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md
```

This file is not canonical architecture.

It is a binding Product Owner-approved backlog ensuring that valuable legacy concepts are not forgotten after archival.

The backlog must record the following decisions.

---

## A. Core items approved for future incorporation/strengthening

### Early Failure Recognition

Approved.

Future canonical intent:

Recognizing early that a Goal is infeasible under known conditions, or that no known path currently exists, is a valuable RF-One outcome rather than a system failure.

This must preserve the Core 2.0 distinction between:

- demonstrated impossibility;
- current infeasibility;
- no known path;
- insufficient knowledge;
- uncertainty.

Likely target:

```text
00 Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md
```

Do not implement the conceptual edit in this migration task.

---

### Optimization hierarchy

The old literal rule:

```text
Mission > Domain Principles > Business Rules > Goal > Execution
```

is **not** approved as-is.

Approved future principle:

Optimization and execution must remain subordinate to:

- consciously confirmed Subject direction;
- active Goals;
- Constraints;
- Subject Sovereignty;
- Delegated Authority;
- applicable law/policy;
- known risk limits.

Do not introduce `Mission` as a new Core primitive from legacy material without a separate architectural decision.

Likely targets:

```text
00 Core/Process.md
00 Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md
```

---

### Recursive Process

Approved for future incorporation.

A Process may be recursively decomposed without requiring a separate universal ontology for `Activity`.

Granularity does not automatically create a different class of thing.

Likely target:

```text
00 Core/Process.md
```

---

### Process persistent status

The old rule:

> Process status must never be persisted; it must always be inferred.

is **not approved as a universal Core rule**.

Persistence vs derivation is a Runtime/Domain concern unless a specific semantic distinction is independently justified.

Do not carry this legacy rule into Core.

Record it as REJECTED AS UNIVERSAL CORE / possible implementation pattern.

---

### Entity versioning

Approved as an optional Core pattern, not as a requirement that every Entity must have a Version Entity.

Future intent:

RF-One Core should be able to represent stable conceptual identity separately from versioned definitions where a Domain requires it.

Likely target:

```text
00 Core/Entity.md
```

---

### Temporal semantics

Approved as a Core capability/pattern.

Do not mandate specific database fields such as `EffectiveFrom` / `EffectiveTo` at ontology level.

Future intent:

Core must allow temporal validity and historical reconstruction where a Domain/Runtime requires it.

Likely target:

```text
00 Core/Entity.md
```

---

### Hybrid Event Model

Do **not** promote the historical Event-sourcing style model into universal Core ontology.

The claim that immutable Events must universally generate Entity state is an implementation/runtime architectural pattern.

Record as:

```text
MOVE TO SOFTWARE/RUNTIME / future architecture pattern
```

unless a later architectural task establishes stronger universal semantics.

---

### Ownership vs Assignment

Approved for future clarification as a generic modeling distinction where useful.

Ownership and Assignment must not be treated as synonyms.

Do not yet prescribe a universal cardinality or data model.

Likely target:

```text
00 Core/Relationship.md
00 Core/Glossary.md
```

---

### Specialization extends rather than erases identity

Approved for future strengthening as a generic Core modeling pattern.

A specialization may extend a more general concept without silently replacing the identity/meaning of the general concept.

Likely target:

```text
00 Core/Entity.md
```

---

### Capacity / Availability / Responsibility placement

Do **not** generalize the historical rules:

- Capacity belongs to physical provider;
- Availability belongs to smallest responsible Entity;
- Responsibility belongs to smallest responsible Entity;

into universal Core principles yet.

Keep existing valid specific rules where they currently live.

Record for future review when multiple Domains provide enough evidence to generalize.

---

### Capabilities Enable Services

Do not elevate into a new universal Core principle in this migration task.

Record for later review as a possible Relationship/Domain modeling pattern.

---

### Simplicity Before Generalization

Treat as an architecture/development principle, not ontology.

If later incorporated, likely target:

```text
CLAUDE.md
00 Core/ImplementationGuidelines.md
```

Do not implement now.

---

## B. Operational Unit legacy items

Do not import the historical physical-business lifecycle:

```text
Planning
→ Legal Creation
→ Site Acquisition
→ Construction/Setup
→ Licensing
→ Operational
→ Closed...
```

as a universal Core lifecycle.

It is too specific to certain physical/business Operational Units.

Record it as a candidate for:

```text
01 Domains/_Shared/
```

or a relevant specific Domain.

The generic Core Entity lifecycle remains separate.

---

## C. Corporate legacy items

### Legal identity fields

Do not expand Core now with detailed jurisdiction-specific legal fields.

Record for Shared Domain / future Legal-Governance Domain review.

### Corporate Documents

Keep out of Core.

Candidate for future Domain/Runtime data model.

### AI Governance

Approved distinction:

- universal Delegated Authority / Subject Sovereignty principles remain Core;
- RF-One company governance policy belongs under `09 Strategy/`;
- production workflow for AI-proposed knowledge evolution belongs to Product/Software Runtime.

Do not duplicate these layers.

---

## D. Brand legacy items

Marketing execution details are not Core Brand ontology.

Record as Shared Domain / future Marketing capability knowledge.

The broader approved future direction remains:

```text
Goals
→ Brand
→ Service Model
→ Behaviors
→ Selection / Training / Performance
```

but this relationship is a future architectural/domain task and must not be silently implemented during repository migration.

Future Domains such as Workforce, Selection, and Training remain valid planned directions.

---

## E. Commercial strategy items

The following legacy concepts are approved for future review/canonicalization under `09 Strategy/`, not Core:

- measurable economic value as RF-One commercial objective;
- Cash-Based Profit as a historical business metric candidate;
- operational vs strategic economic horizons;
- counterfactual measurement of value generated;
- Business Knowledge Platform positioning;
- service/SaaS delivery rationale;
- shared-intelligence/network-effect strategy;
- company-level knowledge governance;
- Product portfolio strategy.

### Maximize Economic Profit

Do not encode as universal Core Goal.

Treat as RF-One commercial/business strategy only.

### Unlimited Optimization Scope

Do not preserve the old absolute wording.

Approved future interpretation:

RF-One may optimize across any business area for which it has:

- relevant Domain knowledge;
- sufficient Reality information;
- Delegated Authority;
- compatible confirmed Goals;
- applicable Constraints;
- acceptable risk;
- legal/policy permission.

This is a commercial/product scope principle, not ontology.

### Counterfactual value measurement

Approved as strategically important for demonstrating B2B value.

Do not redefine generic Core Outcome solely around financial counterfactuals.

Future Product/Strategy logic may compare:

```text
actual outcome
vs
estimated counterfactual outcome without RF-One intervention
```

to estimate value generated.

---

## F. Service / SaaS / shared intelligence legacy material

Preserve the strategic insight that RF-One's proprietary value is primarily accumulated knowledge, ontology, orchestration, decision/outcome learning, and Domain intelligence rather than commodity software primitives.

However, do not retain the absolute historical claim:

> RF-One can never be sold as software.

as an immutable architectural law.

Record it as a commercial/service-delivery strategy subject to future Product Owner review.

### Shared intelligence

Any future cross-customer learning strategy must explicitly preserve:

- tenant isolation;
- confidentiality;
- privacy;
- contractual restrictions;
- data ownership;
- provenance;
- governance;
- abstraction/anonymization where required.

Do not assume that customer-specific knowledge may be freely shared across tenants.

Only generalized/approved knowledge may become platform-level knowledge under an explicit governance model.

---

## G. Knowledge Domains taxonomy

The historical `Knowledge Domains` list is approved for preservation as a capability/coverage map, not as modern RF-One architectural `Domain` ontology.

Future action:

- use relevant Restaurant areas as input to a Restaurant Domain roadmap;
- classify cross-business areas separately;
- do not rename all historical Knowledge Domains into top-level modern Domains.

---

## H. Interview-driven Knowledge Engineering

Preserve as an optional knowledge-acquisition method, not a mandatory RF-One architecture.

The historical interview template may remain in Archive for now.

A future Research/Methods task may create a modern interview methodology under:

```text
05 Research/Methods/
```

if needed.

---

## I. Corporate legal detail priority

Detailed Corporate Legal Identity / Corporate Documents are low-priority backlog.

Do not expand Core or Domain now solely to preserve those fields.

The legacy source will remain available in Archive.

---

# README requirements

Create or update a concise `README.md` in each canonical top-level directory.

Each README must state:

1. purpose;
2. authority level;
3. what belongs there;
4. what does not belong there;
5. relationship to Core/Domain/Product/Runtime where relevant.

At minimum create/update:

```text
00 Core/README.md
01 Domains/README.md
02 Products/README.md
03 Software/README.md
04 Generated Documentation/README.md
05 Research/README.md
06 Meetings/README.md
07 Tasks/README.md
08 External/README.md
09 Strategy/README.md
90 Archive/README.md
```

If `00 Core/README.md` already exists after the move, reconcile it rather than replacing useful content.

The `90 Archive/README.md` must prominently state:

> Nothing under `90 Archive/` is current canonical RF-One authority, regardless of historical `Approved` or similar status text inside archived documents.

The `08 External/README.md` must state that external material is input/reference and becomes RF-One authority only when explicitly incorporated into canonical documentation.

---

# Root README and PROJECT_STATE

Update:

```text
README.md
PROJECT_STATE.md
```

They are currently obsolete Bootstrap-era entry points.

Do not turn them into long conceptual documents.

## Root `README.md`

It should briefly explain:

- what RF-One is at repository level;
- current canonical directory structure;
- the Core ≠ Domain ≠ Product ≠ Runtime distinction;
- that Core 2.0 is current;
- where canonical architecture lives;
- where external/archive/non-authoritative material lives.

## `PROJECT_STATE.md`

Update to a factual current-state snapshot.

At minimum include:

- Core 2.0 documented;
- Restaurant Domain exists and is under active development;
- InvoiceIntake exists as current software/prototype tooling;
- Business Autopilot conceptual architecture documented;
- repository canonical migration completed by TASK_CORE_005;
- next planned work includes approved legacy knowledge canonicalization and expansion of business Domains/Products.

Do not invent completion claims not supported by the repository.

---

# CLAUDE.md

Review `CLAUDE.md` after migration.

Update only if necessary to reflect:

- new canonical top-level paths;
- `90 Archive/` non-authoritative rule;
- `08 External/` reference-only rule;
- `09 Strategy/` role;
- current `Core ≠ Domain ≠ Product ≠ Runtime` navigation.

Do not redesign its architectural instructions.

---

# Path/reference updates

After physical migration, search the repository for all old paths.

At minimum search for:

```text
00 Knowledge Repository
01 Products
02 Generated Documentation
04 Research
05 Meetings
Tasks/
Shelbi/
Old/
Domains/Restaurant/Domain/
```

Update only references made stale by the migration.

This includes Markdown, README prose, workspace instructions, comments, or documentation.

### Software references

The known historical path reference in:

```text
03 Software/InvoiceIntake/excel_store.py
```

may be updated **only if it is a comment/docstring/path reference**.

Do not change software logic.

Also update stale prose path references in:

```text
03 Software/InvoiceIntake/README.md
```

No other production-code modification is authorized.

If a path is used functionally by code rather than only in a comment/docstring, stop and report before changing it.

---

# Empty/scaffolding directories

Do not preserve every empty local directory merely because it currently exists.

Git does not track empty directories.

A canonical top-level directory should exist because its README is tracked.

For meaningful durable subdirectory scaffolding, prefer a README explaining purpose rather than `.gitkeep` where practical.

Do not generate dozens of placeholder files.

Do not delete existing zero-byte Domain files in this task.

They may be reviewed later.

---

# Git/history safety

Use `git mv` for tracked moves/renames where practical.

Avoid mixing conceptual rewrites into the same move.

Do not edit historical files under the moved Archive.

After all moves:

1. run `git status`;
2. run a staged/un-staged diff summary as appropriate;
3. verify Git recognizes major moves as renames where possible;
4. verify no substantive file disappeared unexpectedly;
5. verify archived PDFs and external PDFs still exist at their target paths.

Do not commit.

---

# Link verification

After migration:

1. search all Markdown links;
2. verify internal Core links;
3. verify links between moved Core files still resolve;
4. verify any path references in Task files if they are intended to reference current paths rather than historical paths.

Important:

Historical Task specifications may legitimately contain old paths because they record what was true when the task ran.

Do **not** rewrite historical Task content merely to make old paths look current.

Only update a historical task if it contains an operational path that must remain executable in the present; otherwise preserve historical accuracy.

---

# Scope restrictions

Do not:

- change Core ontology;
- implement the legacy reconciliation backlog;
- rewrite Entity/Process/Brand/Corporate/Operational Unit concepts;
- create Workforce/Selection/Training Domains yet;
- change database schemas;
- change InvoiceIntake behavior;
- refactor Python;
- delete legacy documents;
- edit archived legacy content;
- edit external PDFs;
- make a Git commit.

This task is structural migration and governance only.

---

# Required report file

At the end, create:

```text
07 Tasks/Reports/TASK_CORE_005_REPORT.md
```

The report must contain:

## A. Migration summary

What was moved/renamed/created.

## B. Final repository tree

Top-level and important second-level structure.

## C. README/governance files

Files created/updated and why.

## D. Path references updated

Every file where a stale path was changed.

## E. Legacy archive confirmation

Confirm the exact destination of the old repository and confirm archived files were not rewritten.

## F. Legacy backlog confirmation

Confirm creation of:

```text
07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md
```

and summarize the approved decisions recorded there.

## G. External material

Confirm Shelbi material destination and that files remain intact.

## H. Software impact

Explicitly list any software file touched and confirm whether only comment/docstring/path text changed.

## I. Validation

Include:

- `git status` summary;
- link/reference verification result;
- unexpected issues;
- files deliberately left unchanged.

## J. Scope confirmation

Explicitly confirm:

- no conceptual Core redesign;
- no legacy content deletion;
- no production behavior change;
- no Git commit.

---

# Final response

After creating the report file, return a concise summary and point to:

```text
07 Tasks/Reports/TASK_CORE_005_REPORT.md
```

Do not make a Git commit.

Stop.
