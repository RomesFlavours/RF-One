# TASK_CORE_012 — Pre-Commit Congruity and Consistency Review

## Objective

Perform a final **pre-commit congruity, consistency, and scope review** of all currently uncommitted RF-One changes produced by TASK_CORE_006 through TASK_CORE_011.

This task is **analysis-only**.

The purpose is to determine whether the repository is coherent enough to commit as one consolidated architectural/documentation checkpoint.

Do not modify any existing repository file.

Do not stage files.

Do not commit.

The only file you may create is:

```text
07 Tasks/Reports/TASK_CORE_012_REPORT.md
```

---

# Mandatory first steps

1. Read `CLAUDE.md` completely.

2. Run:

```bash
git status
git diff --stat
git diff
```

Also inspect untracked files that will not appear in `git diff`.

3. Read the active canonical and governance files affected by TASK_CORE_006–011, including at minimum:

```text
00 Core/ConceptualArchitecture/02_Desire_Goal_and_Reality_Check.md
00 Core/Core Evolution.md
00 Core/Entity.md
00 Core/Glossary.md
00 Core/Process.md
00 Core/Relationship.md

01 Domains/README.md
01 Domains/Restaurant/README.md
01 Domains/Restaurant/Roadmap.md

07 Tasks/README.md
07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md

09 Strategy/README.md
09 Strategy/00_RF-One_Strategy.md
09 Strategy/01_Economic_Value_and_Measurement.md
09 Strategy/02_Service_Delivery_and_Knowledge_Advantage.md
09 Strategy/03_Shared_Intelligence_and_Knowledge_Governance.md
09 Strategy/04_Business_Capability_Coverage.md

90 Archive/README.md
90 Archive/Task History/README.md

PROJECT_STATE.md
```

4. Read the archived TASK_CORE_006–011 reports as provenance where useful.

5. Inspect the resulting repository structure relevant to:

```text
00 Core/
01 Domains/
07 Tasks/
09 Strategy/
90 Archive/
```

---

# Review goals

The review must answer:

> Are the current uncommitted changes mutually coherent, correctly layered, internally consistent, and safe to commit together?

The review must not merely confirm that each individual task followed its own instructions.

It must evaluate the **combined result**.

---

# Review areas

## A. Layer congruity

Verify the combined repository still respects:

```text
Core ≠ Domain ≠ Product ≠ Runtime ≠ Strategy
```

Check especially that:

- Core contains universal semantics only;
- Strategy contains RF-One company/product-business strategy, not customer Domain ontology;
- Restaurant contains restaurant business semantics and planning;
- no Product specification was accidentally introduced;
- no Runtime/software implementation detail leaked into Core or Strategy;
- archive material is clearly non-authoritative.

Report every actual or potential layer violation.

---

## B. Conceptual consistency

Review the combined changes for contradictions with established RF-One principles, including:

- Subject Sovereignty;
- Desire ≠ Goal;
- Reality Check;
- Epistemic Boundary;
- Decision as first-class Core concept;
- Delegated Authority;
- Human control does not imply continuous human operation;
- temporal coherence;
- reuse must be earned;
- no automatic promotion of local/customer truth to universal truth.

Look for silent inconsistencies introduced across multiple files even if each file is individually reasonable.

---

## C. Terminology consistency

Check repeated terms across Core, Domain, Strategy, and governance documentation.

At minimum review:

- Core;
- Domain;
- Shared Domain;
- Product;
- Runtime;
- Strategy;
- Subject;
- Reality;
- Desire;
- Goal;
- Decision;
- Outcome;
- Learning;
- Delegated Authority;
- Ownership;
- Assignment;
- Commercial Catalog;
- Marketing;
- Reputation;
- Workforce / Personnel;
- Financial Performance;
- Strategic Planning.

Report inconsistent capitalization, conflicting definitions, or the same term being used with incompatible meanings.

Do not redesign terminology merely for stylistic uniformity.

---

## D. Cross-document authority

Verify that canonical documents are authoritative and archived Tasks/Reports are provenance only.

Check for cases where an active canonical document:

- relies on an archived Task/Report as if the Task/Report were the source of truth;
- links to history where it should instead reference another canonical document;
- contradicts a newer canonical statement while citing older history.

Historical references are allowed for provenance.

The issue is authority, not the existence of references.

---

## E. Archive congruity

Verify TASK_CORE_001–010 and their existing reports were archived correctly.

Check:

- no completed TASK_CORE_001–010 remains active under `07 Tasks/`;
- TASK_CORE_011 remains active;
- TASK_CORE_012 remains active;
- Backlog remains active;
- no task/report was lost;
- archive filenames are preserved;
- archive README correctly marks historical material non-authoritative;
- live references use the new archive paths where appropriate;
- historical internal paths inside archived files may remain unchanged when preserving historical truth.

---

## F. Link and path integrity

Search for stale or broken path references caused by repository migration and task-history archival.

At minimum search for:

```text
00 Knowledge Repository/
Old/
Tasks/
07 Tasks/TASK_CORE_001
07 Tasks/TASK_CORE_002
07 Tasks/TASK_CORE_003
07 Tasks/TASK_CORE_004
07 Tasks/TASK_CORE_005
07 Tasks/TASK_CORE_006
07 Tasks/TASK_CORE_007
07 Tasks/TASK_CORE_008
07 Tasks/TASK_CORE_009
07 Tasks/TASK_CORE_010
07 Tasks/Reports/TASK_CORE_005
07 Tasks/Reports/TASK_CORE_006
07 Tasks/Reports/TASK_CORE_007
07 Tasks/Reports/TASK_CORE_008
07 Tasks/Reports/TASK_CORE_009
07 Tasks/Reports/TASK_CORE_010
../../../CLAUDE.md
```

Distinguish between:

- stale live/canonical paths that require correction;
- intentionally historical paths inside archived material.

Verify Markdown links from active documents resolve where practical.

---

## G. Repository structure congruity

Verify the current top-level structure still matches the approved canonical structure:

```text
00 Core/
01 Domains/
02 Products/
03 Software/
04 Generated Documentation/
05 Research/
06 Meetings/
07 Tasks/
08 External/
09 Strategy/
90 Archive/
```

Check for:

- accidental duplicate roots;
- orphaned old folders;
- misplaced active documentation;
- missing expected README/governance files;
- active work accidentally archived;
- historical work accidentally left active.

---

## H. Commercial Catalog / Shared Domain decisions

Verify all current documents agree on the approved decision:

- Commercial Catalog stays under Restaurant now;
- it is the highest-confidence future Shared Domain extraction candidate;
- extraction is triggered by a genuine second Domain or Product requiring the same semantics;
- no Shared Domain is created merely for symmetry;
- extraction is expected to be whole-model unless later evidence creates a natural seam.

Report any conflicting wording.

---

## I. Marketing / Reputation / Workforce / Finance / Planning decisions

Verify all current planning documents agree that:

- Marketing is not permanently Restaurant-only and not already Shared;
- generic Marketing is a future Shared candidate, with Restaurant-specific execution potentially remaining specialized;
- Reputation remains deferred and is not currently a standalone Domain;
- Workforce semantics should precede Selection/Training/Performance capabilities;
- Equipment/Facilities remain deferred;
- Financial Performance follows Product/use-case-first, ontology-later;
- Strategic Planning does not currently require a new Domain;
- Customer remains Restaurant-local for now;
- Supplier remains Purchasing-local for now;
- Business Profile is not a separate Domain.

Report discrepancies.

---

## J. Scope / accidental-change review

Use Git diff and filesystem inspection to determine whether the current working tree contains any modifications unrelated to TASK_CORE_006–011.

Identify:

- unexpected file edits;
- accidental line-ending or encoding rewrites;
- large diffs inconsistent with intended small documentation changes;
- accidental content loss;
- duplicate files;
- temporary files;
- editor artifacts.

Do not fix them.

Report exact paths.

---

## K. Pre-commit suitability

Give one final verdict:

### PASS
The current working tree is coherent and suitable to commit as one consolidated checkpoint.

### PASS WITH MINOR FIXES
The architecture is coherent, but specific small corrections should be made before commit.

### BLOCK
Material contradictions, broken structure, or risky unintended changes exist and should be resolved before commit.

If verdict is not `PASS`, list each required correction as:

```text
Issue
Path
Why it matters
Smallest safe correction
```

Do not implement the correction.

---

# Required report

Create:

```text
07 Tasks/Reports/TASK_CORE_012_REPORT.md
```

with exactly these sections:

## A. Executive verdict

State PASS / PASS WITH MINOR FIXES / BLOCK.

## B. Layer congruity

## C. Conceptual consistency

## D. Terminology consistency

## E. Authority and provenance

## F. Archive and task-history integrity

## G. Link/path integrity

## H. Repository structure integrity

## I. Cross-layer decision consistency

Cover Commercial Catalog, Marketing, Reputation, Workforce, Equipment/Facilities, Financial Performance, Strategic Planning, Customer, Supplier, and Business Profile.

## J. Git diff / accidental-change review

## K. Required corrections before commit

If none, state:

```text
None.
```

## L. Recommended commit scope

State whether TASK_CORE_006–011 plus the current canonicalization/archival changes are suitable for one consolidated commit.

Do not invent a commit message unless useful.

## M. Git status / scope confirmation

Confirm:

- no existing file modified by TASK_CORE_012;
- no staging;
- no commit;
- only `07 Tasks/Reports/TASK_CORE_012_REPORT.md` created.

---

# Restrictions

Do not:

- modify any existing file;
- move any file;
- rename any file;
- delete any file;
- stage any file;
- commit;
- create any file except `07 Tasks/Reports/TASK_CORE_012_REPORT.md`;
- fix issues you discover.

This task is review only.

---

# Final response

After creating the report, return only:

1. the verdict (`PASS`, `PASS WITH MINOR FIXES`, or `BLOCK`);
2. a short summary;
3. the exact report path:

```text
07 Tasks/Reports/TASK_CORE_012_REPORT.md
```

Then stop.
