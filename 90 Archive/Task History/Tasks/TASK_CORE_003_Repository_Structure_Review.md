# TASK_CORE_003 — RF-One Repository Structure Review

## Objective

Review the entire RF-One repository structure and propose a clean, durable canonical directory architecture.

This is an **inspection and planning task only**.

Do not move, rename, delete, archive, deprecate, create, or modify any repository file or directory in this task.

The purpose is to prepare a later migration task that will reorganize the repository safely without losing historical knowledge, breaking references, or mixing Core, Domain, Product, Runtime, Research, Tasks, and Archive concerns.

---

## Mandatory first steps

1. Read `CLAUDE.md` completely.
2. Read:
   - `Tasks/TASK_CORE_001_Conceptual_Architecture.md`
   - `Tasks/TASK_CORE_002_Core_Documentation.md`
3. Inspect the entire current repository structure.
4. Read the current top-level `README.md`, `PROJECT_STATE.md`, and relevant README/index files that define repository organization.
5. Inspect the current `Old/` structure and identify which materials are historical, still useful, duplicated, superseded, or potentially canonical.
6. Inspect cross-references between Markdown files before proposing any move or rename.

Do not make changes while inspecting.

---

# Approved architectural context

RF-One now uses the following conceptual distinction:

> **Core ≠ Domain ≠ Product ≠ Runtime**

The repository structure should make this distinction obvious.

RF-One Core 2.0 is domain-independent.

The repository must support future growth beyond the Restaurant Domain without forcing unrelated concepts into restaurant-specific folders.

The repository should remain understandable to:

- the Product Owner;
- future developers;
- AI coding agents;
- technical collaborators;
- future Domain authors.

The structure should minimize ambiguity about which documentation is canonical and which material is historical.

---

# Current structural problem to solve

The repository currently contains both active and historical structures, including examples such as:

```text
00 Knowledge Repository/
    Core/
    Domains/
    Environment/

01 Products/

02 Generated Documentation/

03 Software/

04 Research/

05 Meetings/

Old/
    X00 Knowledge Repository/
        00 Vision/
        01 Objectives/
        02 Principles/
        03 Constraints/
        04 Decision Framework/
        05 Knowledge Domains/
        06 Business Model/
        06 Modules/
        07 Glossary/
        08 Change Log/
        09 Interviews/

Shelbi/

Tasks/
```

There are historical files under `Old/` that still contain useful concepts, but some overlap with newer canonical Core definitions.

This creates several risks:

- duplicate definitions;
- ambiguous authority;
- outdated files still marked Approved;
- unclear distinction between historical and canonical knowledge;
- unnecessarily deep paths;
- mixed numbering conventions;
- unclear long-term location for Tasks, Research, Meetings, external collaborator material, generated documentation, and archived concepts.

---

# Desired outcome

Propose a repository structure that is:

- simple;
- scalable;
- domain-independent at the Core level;
- explicit about canonical vs archived material;
- suitable for multiple future Domains;
- suitable for multiple future Products;
- understandable without historical knowledge of the project;
- safe for Git;
- safe for AI coding agents;
- resistant to future duplication.

The final proposal should reduce the need for future major reorganizations.

---

# Candidate canonical structure to evaluate

Evaluate, but do not blindly adopt, the following candidate:

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
└── 90 Archive/
```

Possible intent:

### `00 Core/`

Universal RF-One ontology, conceptual architecture, architecture principles, canonical glossary, Core evolution, and other domain-independent knowledge.

Possible internal structure:

```text
00 Core/
├── ConceptualArchitecture/
├── Concepts/
├── Architecture/
├── Evolution/
└── README.md
```

Do not over-engineer subdirectories if the current file volume does not justify them.

---

### `01 Domains/`

Reusable domain knowledge built on the Core.

Examples may eventually include:

```text
01 Domains/
├── Restaurant/
├── Workforce/
├── Selection/
├── Training/
└── ...
```

A Domain should not automatically equal a Product.

---

### `02 Products/`

Commercial products or product configurations that combine Core capabilities and Domains.

Do not place universal Core definitions here.

---

### `03 Software/`

Runtime implementation.

Possible categories may include:

- AI;
- Backend;
- Database;
- Frontend;
- Infrastructure;
- prototypes/tools such as InvoiceIntake.

Do not move conceptual documentation into Software merely because developers use it.

---

### `04 Generated Documentation/`

Documentation generated from implementation or specifications.

Examples:

- API;
- Database;
- Agent Specifications;
- Functional Specifications;
- Prompt Library;
- Test Cases.

Generated documentation must remain clearly distinguishable from canonical human-authored architecture.

---

### `05 Research/`

Market research, competitor studies, technical research, external references, exploratory work.

Research does not become canonical architecture automatically.

---

### `06 Meetings/`

Meeting notes and chronological discussion records.

Meeting notes must not silently become architectural authority.

---

### `07 Tasks/`

Approved implementation tasks and repository work instructions.

Tasks record execution history and Product Owner decisions, but should not replace canonical architecture.

---

### `08 External/`

Evaluate whether external collaborator/source material should have a dedicated neutral location.

For example, current `Shelbi/` material may belong under a structure such as:

```text
08 External/
└── Shelbi/
```

or another clearer category.

Do not move it in this task.

If a separate external-material area is unnecessary, explain why.

---

### `90 Archive/`

Historical, superseded, deprecated, or replaced material that should remain available but must not be treated as canonical.

Possible internal structure:

```text
90 Archive/
├── Legacy Core/
├── Legacy Domains/
├── Historical Repository Structures/
├── Deprecated Concepts/
└── Historical Documentation/
```

Do not create excessive archive categories unless they provide real value.

---

# Archive policy to evaluate

The Product Owner wants old material retained rather than deleted when it may have historical or conceptual value.

Evaluate a rule such as:

> If a file is in the canonical structure, it is potentially authoritative according to its status and owning documentation.
>
> If a file is under `90 Archive/`, it is historical/reference material and must not be treated as current architectural authority.

Compare this approach with renaming individual files using `.OLD`.

Preferred filename form if `.OLD` is ever used:

```text
Decision.OLD.md
```

rather than:

```text
Decision.md.OLD
```

because the first keeps the Markdown extension.

However, evaluate whether a centralized `90 Archive/` structure is cleaner than widespread `.OLD` suffixes.

Do not implement either approach in this task.

---

# Canonical authority rules to propose

The report should recommend explicit rules for determining authority.

At minimum consider:

1. Canonical Core documentation.
2. Domain documentation.
3. Product documentation.
4. Runtime/software documentation.
5. Generated documentation.
6. Research.
7. Meetings.
8. Tasks.
9. External reference material.
10. Archive.

The future repository should make it difficult for an AI agent or developer to accidentally use archived material as current architecture.

Consider whether each major directory should have a short `README.md` explaining:

- purpose;
- what belongs there;
- what does not belong there;
- authority level;
- relationship to other layers.

---

# Specific review areas

## 1. `00 Knowledge Repository`

Determine whether the wrapper directory `00 Knowledge Repository/` still provides useful meaning.

Evaluate whether:

```text
00 Knowledge Repository/Core/
00 Knowledge Repository/Domains/
00 Knowledge Repository/Environment/
```

should become direct top-level areas such as:

```text
00 Core/
01 Domains/
```

and determine the correct destination of `Environment/`.

Do not assume `Environment` deserves a top-level directory; inspect its actual content and role.

---

## 2. Core files

Review the current Core files and the new:

```text
00 Knowledge Repository/Core/ConceptualArchitecture/
```

Propose the cleanest future organization without creating unnecessary fragmentation.

Identify whether existing files such as:

- `ArchitecturePrinciples.md`
- `Core Evolution.md`
- `Entity.md`
- `Glossary.md`
- `Goal.md`
- `Process.md`
- `Relationship.md`
- `RF-ONE Core Principles.md`
- `ImplementationGuidelines.md`

should remain together, be grouped into sensible subdirectories, or be absorbed/replaced by newer canonical documentation.

Do not decide that a file is obsolete merely because a newer document overlaps it.

Identify exact overlap first.

---

## 3. Domains

Inspect the Restaurant Domain and determine whether its current structure is coherent enough to migrate directly.

Identify:

- true Domain knowledge;
- external integration/vendor mapping;
- reference assets;
- domain-specific implementation documentation;
- possible Product-specific material incorrectly located under Domain;
- possible generated/runtime material incorrectly located under Domain.

Do not redesign the Restaurant Domain in this task.

Only identify structural placement issues.

---

## 4. Products

Inspect `01 Products/`.

Determine its current content and whether the proposed future `02 Products/` layer should remain independent from Domains.

Report empty, placeholder, or unused structures.

Do not delete them.

---

## 5. Software and Generated Documentation

Review the relationship between:

```text
02 Generated Documentation/
03 Software/
```

Determine whether numbering/order should change in the canonical structure.

Ensure generated outputs cannot be confused with source-of-truth architecture.

---

## 6. Research, Meetings, External material

Review:

- `04 Research/`
- `05 Meetings/`
- `Shelbi/`

Recommend stable long-term placement.

External collaborator documents should remain identifiable as external source/reference material and should not silently become canonical RF-One architecture.

---

## 7. Tasks

Evaluate whether `Tasks/` should become a numbered top-level directory.

Recommend a naming convention for future task files.

Current examples:

```text
TASK_CORE_001_Conceptual_Architecture.md
TASK_CORE_002_Core_Documentation.md
TASK_CORE_003_Repository_Structure_Review.md
```

Preserve task history.

---

## 8. Old repository

Inspect all of:

```text
Old/X00 Knowledge Repository/
```

Classify its contents into categories such as:

- superseded;
- partially migrated;
- still uniquely valuable;
- duplicated;
- historical only;
- unresolved;
- candidate for future canonical migration.

Do not modify any file.

Do not mark anything deprecated yet.

Do not assume everything in `Old/` is obsolete.

The report must identify any file whose only surviving version of a useful concept still exists under `Old/`.

---

# Migration safety

The later migration task must preserve Git history as much as reasonably possible.

Therefore, when proposing moves/renames:

- prefer Git-detectable renames/moves;
- avoid unnecessary content rewrites during the same move;
- separate structural moves from conceptual rewrites where practical;
- identify cross-reference updates required by path changes;
- identify README/index updates required;
- identify any scripts or code that reference documentation paths;
- identify workspace/project configuration that depends on paths.

Do not execute any move in this task.

---

# File naming conventions

Recommend a consistent filename convention.

Evaluate:

- spaces vs underscores;
- numbered prefixes;
- capitalization;
- abbreviations;
- `.OLD.md` usage;
- README placement.

Do not rename anything yet.

The recommendation should prioritize:

- Windows compatibility;
- VS Code usability;
- Git usability;
- readable paths;
- predictable AI-agent navigation.

Avoid gratuitous renaming solely for aesthetic reasons.

---

# Numbering strategy

Evaluate whether the top-level numbering should be:

```text
00 Core
01 Domains
02 Products
03 Software
04 Generated Documentation
05 Research
06 Meetings
07 Tasks
08 External
90 Archive
```

or another ordering.

Explain the reason for every proposed top-level directory.

Do not introduce a directory unless it has a clear durable responsibility.

---

# Expected output

Return a **Repository Structure Review Report** with exactly these sections.

## A. Current repository map

Summarize the actual current top-level structure and important second-level structures.

Identify empty or placeholder directories where relevant.

---

## B. Structural problems

List genuine problems in the current organization.

For each:

- current path;
- problem;
- practical risk;
- recommended direction.

---

## C. Canonical target structure

Provide the complete proposed future top-level structure.

Include second-level structure only where necessary to make the proposal understandable.

For every top-level directory, state:

- purpose;
- authority level;
- what belongs there;
- what must not belong there.

---

## D. Migration map

Provide a table:

| Current path | Proposed path | Action | Reason |
|---|---|---|---|

Use actions such as:

- KEEP
- MOVE
- RENAME
- ARCHIVE
- MERGE
- REVIEW
- LEAVE UNTIL LATER

Do not execute them.

---

## E. Archive strategy

Recommend the canonical archive policy.

Explicitly answer:

1. Should `Old/` become `90 Archive/`?
2. Should individual files use `.OLD.md`?
3. When should a file be archived rather than deleted?
4. How should archived files be prevented from being treated as authoritative?
5. Should archived files retain their original directory context?

---

## F. Canonical authority model

Define a simple authority hierarchy for future developers and AI agents.

Explain which locations are:

- canonical;
- domain-authoritative;
- product-authoritative;
- runtime-authoritative;
- generated;
- research/reference;
- historical/non-authoritative.

---

## G. Cross-reference impact

Identify files that would need path/reference updates if the migration is approved.

Include:

- Markdown links;
- README/index references;
- `CLAUDE.md`;
- `PROJECT_STATE.md`;
- workspace configuration;
- scripts/code, if any;
- generated documentation references.

Do not update them.

---

## H. Legacy knowledge at risk

List any material currently under `Old/` that must be preserved or consciously migrated before the old structure can safely be archived.

This section is important.

Do not recommend wholesale archival until this has been evaluated.

---

## I. Recommended migration sequence

Provide the safest step-by-step sequence for a future TASK_CORE_004.

The sequence should minimize:

- broken references;
- accidental knowledge loss;
- ambiguous authority;
- Git history noise.

---

## J. Genuine blockers / Product Owner decisions

List only decisions that truly require Product Owner approval before migration.

Do not ask questions that can be answered by inspecting the repository.

---

# Restrictions

Do not:

- modify any file;
- create directories;
- rename directories;
- move files;
- delete files;
- add `.OLD`;
- mark files deprecated;
- update links;
- commit Git changes;
- rewrite architecture;
- redesign Domains;
- clean up unrelated content.

This task is analysis only.

---

# Final instruction

Stop after delivering the Repository Structure Review Report.

Do not begin migration.

Do not make any repository change without explicit Product Owner approval.
