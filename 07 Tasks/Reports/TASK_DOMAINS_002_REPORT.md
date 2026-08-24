# TASK_DOMAINS_002 — Report

**Task:** Canonicalize Personnel Management and Move Selection Under It
**Date:** 2026-08-24

---

## A. Summary

Applied the approved architecture in which **Personnel Management** is the transversal Domain responsible for managing people across industries, with **Workforce, Selection, Training, Performance and Personnel Decisions** as its modules. Created `01 Domains/Personnel Management/README.md` documenting purpose, transversal scope, module map, relationship to Core 2.0, relationship to technical Domains, relationship to Customer Feedback/Review, the continuous operating loop, and current documentation status. Moved the previously top-level `01 Domains/Selection/` (created by TASK_SELECTION_002) to `01 Domains/Personnel Management/Selection/` with all seven files preserved and relative Markdown links adjusted for the new depth. Created minimal placeholder `README.md` files for Workforce, Training, Performance and Personnel Decisions. Updated `01 Domains/Domain Architecture.md` and `01 Domains/README.md` to reflect the new canonical structure, and made minimal coherence updates to `01 Domains/Restaurant/README.md` and `Roadmap.md`. No Core, Product, Software, Strategy or Archive content was touched. Nothing was staged or committed.

---

## B. Files created

| Path | Purpose |
|---|---|
| `01 Domains/Personnel Management/README.md` | Personnel Management Domain: purpose, transversal scope, module map, relationship to Core 2.0 (Subject/Reality, Goal, Decision/Action/Outcome/Learning, Temporal Coherence, Epistemic Boundary/Subject Sovereignty, Constraint/Relationship/Ownership/Assignment), relationship to technical Domains, relationship to Customer Feedback/Review, continuous operating loop, KPI principle, current documentation status. |
| `01 Domains/Personnel Management/Workforce/README.md` | Minimal placeholder: purpose, module boundary ("who"), relationship to other modules, relationship to Core, relationship to technical Domains, deferred-modeling note. |
| `01 Domains/Personnel Management/Training/README.md` | Minimal placeholder: purpose, module boundary ("how do we close an evidenced gap"), relationship to other modules (consumes Selection's TrainableGap, feeds Performance), relationship to Core, relationship to technical Domains, deferred-modeling note. |
| `01 Domains/Personnel Management/Performance/README.md` | Minimal placeholder: purpose, module boundary ("what did the person actually produce"), no universal score / no fixed KPI list, relationship to other modules, relationship to Core, relationship to technical Domains, relationship to Customer Feedback/Review, deferred-modeling note. |
| `01 Domains/Personnel Management/Personnel Decisions/README.md` | Minimal placeholder: purpose (Core Decision applied to people), module boundary, possible conclusions, expected-value comparison (no automatic thresholds), relationship to other modules, relationship to Core, relationship to technical Domains, deferred-modeling note. |
| `07 Tasks/Reports/TASK_DOMAINS_002_REPORT.md` | This report. |

---

## C. Files moved

`01 Domains/Selection/` → `01 Domains/Personnel Management/Selection/` (plain filesystem move; the folder was untracked in git, so `git mv` was not applicable — no staging occurred either way). All seven original files preserved with unchanged filenames:

| File | Preserved |
|---|---|
| `README.md` | Yes |
| `Selection.md` | Yes |
| `SelectionRequirement.md` | Yes |
| `CandidateEvidence.md` | Yes |
| `FitAssessment.md` | Yes |
| `SelectionDecision.md` | Yes |
| `TrainableGap.md` | Yes |

No duplicate `01 Domains/Selection/` remains (verified: the path no longer exists).

---

## D. Files modified

| Path | Change |
|---|---|
| `01 Domains/Personnel Management/Selection/*.md` (all 7 files) | Relative link depth adjusted for the new nesting level: `../../00 Core/...` → `../../../00 Core/...` (38 link targets across 6 files) and `../Restaurant/...` → `../../Restaurant/...` (2 link targets in `README.md`). Display-text brackets mirroring the same paths were updated identically for consistency. No conceptual content changed — Selection remains conceptually the same; only its architectural parent (and the resulting relative paths) changed. |
| `01 Domains/Domain Architecture.md` | Updated Related documents (points to `Personnel Management/README.md` and `Personnel Management/Selection/README.md` instead of `Selection/README.md`; added this task's spec link). §1 Purpose rewritten to describe Personnel Management as the created transversal Domain (with its five modules) and Customer Feedback/Review as the remaining candidates, rather than five separate candidates. §2 updated the Selection cross-reference path. §4 rewritten from "Current transversal Domain candidates" (a flat list of seven) to "Current transversal Domains and candidates" — a tree showing Personnel Management as the transversal Domain with Workforce/Selection/Training/Performance/Personnel Decisions as modules, and Customer Feedback/Review as the remaining candidates; explicitly states this supersedes the earlier flat-list framing. §5 heading and subsections renamed from "Selection / Workforce / Personnel Management / Performance / Training distinctions" to "Workforce / Selection / Training / Performance / Personnel Decisions distinctions"; §5.3 renamed from "Personnel Management manages the current person" to "Personnel Decisions decides what happens to the current person" (Personnel Management is now the parent Domain name, not a module — the module that decides retain/develop/move/replace is Personnel Decisions); §5.6 relationship summary updated to reference Personnel Decisions and to note all five are modules of Personnel Management. §9 open questions updated: item 1 (sequencing) reflects that Selection now sits inside Personnel Management; item 2 renamed to "Personnel Decisions vs. Workforce boundary"; item 4 rephrased in terms of modules; item 5 (naming) records that Personnel Management and its five module names are now fixed, leaving only Customer Feedback/Review naming open. Version bumped to 1.1, status updated. |
| `01 Domains/README.md` | Purpose section: the `Domain Architecture.md` cross-reference now names Personnel Management as the transversal Domain (with its modules) and Customer Feedback/Review as the remaining candidates, instead of listing seven flat candidates including Selection. Current Domains table: replaced the `Selection/` row with a `Personnel Management/` row describing the transversal Domain and its module map, noting Selection is the only module documented in depth so far. Closing sentence updated to reference future transversal Domain candidates (Customer Feedback, Review) instead of "Workforce, Training." |
| `01 Domains/Restaurant/README.md` | One sentence in the header note updated: names Personnel Management as the transversal Domain (Workforce, Selection, Training, Performance, Personnel Decisions) instead of listing five items including Selection and Personnel Management as separate candidates. |
| `01 Domains/Restaurant/Roadmap.md` | "Related documents" line updated to reference Personnel Management as the transversal Domain rather than a flat candidate list. §3's "Workforce / Personnel" entry rewritten to state this area is now the Personnel Management transversal Domain (created by this task), record that Selection is documented while Workforce/Training/Performance/Personnel Decisions remain placeholders, and update the approved-direction chain and cross-references accordingly. No sequencing principle was reversed — establishing Workforce in depth remains the previously recorded preference; the note now also acknowledges Selection was authorized ahead of it, consistent with what TASK_SELECTION_002 already recorded. |

No other files were modified. No file under `00 Core/`, `02 Products/`, `03 Software/`, `08 External/`, `09 Strategy/` or `90 Archive/` was touched.

---

## E. Personnel Management boundary

Personnel Management is documented as the transversal (cross-industry) Domain that manages people: who occupies roles, who else could credibly occupy them, whether people meet the standard, what they actually produce, and what should be done about the current occupant. It is not owned by Restaurant or any other technical Domain — Restaurant supplies technical content (role requirements, standards, operational context, operational evidence, expected outcomes) that Personnel Management's modules consume, mirroring the relationship already established for Selection alone in TASK_DOMAINS_001/TASK_SELECTION_002 and now generalized to the whole Domain. Personnel Management does not redefine Core; each module specializes Core concepts (Subject/Reality, Goal, Decision/Action/Outcome/Learning, Temporal Coherence, Epistemic Boundary/Subject Sovereignty, Constraint/Relationship/Ownership/Assignment) only where a genuine Personnel-Management-specific meaning is required.

---

## F. Module boundaries

- **Workforce** — who currently occupies or can occupy organizational roles (structural occupancy). Placeholder only; potential future concepts (Person/Worker, Role, Position, Assignment, Responsibility, Availability, Schedule, Employment Relationship) are named as dependencies, not modeled.
- **Selection** — continuously identifies and evaluates economically viable human alternatives for roles, vacancy or not (`Selection continuously creates credible human alternatives for roles, whether or not the role is currently vacant.`). Documented in depth: Selection, SelectionRequirement, CandidateEvidence, FitAssessment, SelectionDecision, TrainableGap — all preserved unchanged in meaning from TASK_SELECTION_002.
- **Training** — closes evidenced gaps (from Selection's TrainableGap or from observed Performance) when operationally and economically justified; consumes the target Domain's standard, the observed gap, role/context, learning methods, and later Performance evidence to close the loop. Placeholder only; no curriculum, duration table, or delivery mechanism defined.
- **Performance** — what a person actually produces in Reality; may consume Restaurant-example evidence (sales, margin, service time, throughput, product mix, customer feedback, reviews, quality, financial outcomes) or equivalent evidence from another technical Domain. Placeholder only. **No universal scalar score and no fixed KPI list are defined**, consistent with the existing KPI-discovery principle (Domain Architecture.md §8).
- **Personnel Decisions** — applies Core Decision semantics to the person currently in the role; possible conclusions (retain, continue observing, correct, train, develop, move/reassign, change responsibilities, replace) are illustrative, not exhaustive or mandatory. May compare expected value of the current person against an alternative's expected value net of recruitment/training/transition cost and uncertainty/risk — recorded as a guiding comparison, **not a rigid formula, and no automatic termination threshold is defined**. Placeholder only; Core Decision itself is not redefined.

---

## G. Selection migration

`01 Domains/Selection/` → `01 Domains/Personnel Management/Selection/`. All seven canonical files (`README.md`, `Selection.md`, `SelectionRequirement.md`, `CandidateEvidence.md`, `FitAssessment.md`, `SelectionDecision.md`, `TrainableGap.md`) preserved with identical content except for relative-link depth adjustments (see §D above). No concept was redesigned, renamed, or reworded beyond what the new parent path required. Selection's own internal sibling links (e.g. `[Selection.md](Selection.md)`, `[README.md](README.md)`) were left untouched, since the files remain siblings of one another after the move. The old `01 Domains/Selection/` path no longer exists (verified after the move).

---

## H. Relationship with Restaurant

Restaurant remains primarily the technical/operational Domain (front-of-house/kitchen operations, service processes, menu/recipe execution, restaurant-specific purchasing/inventory semantics, restaurant-specific technical role requirements, operational constraints/outcomes). Restaurant supplies Personnel Management with restaurant role requirements, technical capabilities, operational standards, restaurant-specific context, operational evidence and expected outcomes; Restaurant does not own Workforce, Selection, Training, Performance or Personnel Decisions. `Restaurant/README.md` and `Restaurant/Roadmap.md` received only minimal cross-reference wording updates (naming Personnel Management as the transversal Domain that now owns these five modules) — no reorganization of Restaurant content occurred, and no Restaurant module, entity or roadmap area was moved, renamed or redesigned.

---

## I. Customer Feedback / Review boundary

Customer Feedback and Review remain separate transversal Domain candidates, explicitly outside Personnel Management. `Personnel Management/README.md` states this directly and notes that Performance may consume their evidence when relevant (e.g. a customer comment naming a specific employee) without owning or defining either Domain. No `Customer Feedback/` or `Review/` folder was created. `Domain Architecture.md` §6 (the Customer Feedback/Review distinction) and §9 open question 3 were left substantively unchanged, since this task does not resolve that linkage.

---

## J. Economic personnel-management loop

Documented in `Personnel Management/README.md`, "Continuous operating loop," reproducing the task's specified structure:

```text
Observed Performance
→ communicate / correct / opportunity to improve
→ Training where economically justified
→ observe again

in parallel:

Selection
→ find credible alternatives

then:

Personnel Decision
→ compare current expected value with available alternatives
→ retain / develop / move / replace
```

together with the expected-value comparison block (current person vs. available alternative net of recruitment/training/transition cost and uncertainty/risk). Both are explicitly labeled a guiding principle, not a rigid formula or automatic decision mechanism.

---

## K. Deferred modeling

Not modeled in this task, per the task's restrictions:

- Workforce entities, relationships, business rules and data requirements (Person/Worker, Role, Position, Assignment, Responsibility, Availability, Schedule, Employment Relationship).
- Training entities, curricula, learning methods, durations and business rules.
- Performance entities, evidence sources, indicators and business rules; no universal scalar score; no fixed KPI list; no KPI-discovery algorithm.
- Personnel Decision entities, decision records, authority thresholds and business rules; no automatic firing/termination rule.
- No Product or Runtime design (UI, workflow automation, persistence schema, integrations) for any module.
- No Customer Feedback or Review folder.

---

## L. Open Product Owner decisions

1. **Sequencing of remaining modules.** Selection is documented in depth; Workforce, Training, Performance and Personnel Decisions are currently placeholders only. `Domain Architecture.md` §9 previously recorded that Workforce should be established before Training/Performance are designed in depth. Confirm whether that sequencing still holds now that Personnel Management exists as the parent Domain, or whether another module (e.g. Performance, to anchor future KPI-discovery work) should be prioritized next.
2. **Personnel Decisions vs. Workforce boundary in practice.** Both concern "the person in the role" from different angles (structural occupancy vs. ongoing relationship/performance management). Confirm this boundary holds once concrete Workforce entities (e.g. Assignment, Employment Relationship) are modeled, or whether some concepts naturally belong to both modules.
3. **Status/versioning of the new placeholders.** The four new module READMEs and the Personnel Management README are marked `Version 0.1 / Draft`, consistent with Selection's own original draft status. Confirm whether these should be promoted to `Approved` as architectural boundary statements, independent of when their detailed concept modeling occurs.
4. **Restaurant/Roadmap.md §3 wording.** The minimal update made there records that Selection was authorized ahead of Workforce and that Personnel Management now exists structurally. Confirm this wording is sufficient, or whether the Product Owner wants a more explicit statement of the current modeling priority order for Workforce/Training/Performance/Personnel Decisions.

---

## M. Git status / scope confirmation

`git status` immediately before writing this report:

```text
Changes not staged for commit:
  modified:   01 Domains/README.md
  modified:   01 Domains/Restaurant/README.md
  modified:   01 Domains/Restaurant/Roadmap.md

Untracked files:
  01 Domains/Domain Architecture.md
  01 Domains/Personnel Management/                                              (includes migrated Selection/ and new module READMEs)
  07 Tasks/Reports/TASK_DOMAINS_001_REPORT.md                                   (pre-existing)
  07 Tasks/Reports/TASK_SELECTION_002_REPORT.md                                 (pre-existing)
  07 Tasks/TASK_DOMAINS_001_Document_Cross_Domain_Architecture_Conclusions.md   (pre-existing)
  07 Tasks/TASK_DOMAINS_002_Canonicalize_Personnel_Management_and_Move_Selection.md  (this task's spec)
  07 Tasks/TASK_SELECTION_002_Create_Canonical_Selection_Domain_Foundation.md   (pre-existing)
```

Confirmed:

- `01 Domains/Personnel Management/` exists as a top-level transversal Domain, containing `Workforce/`, `Selection/`, `Training/`, `Performance/` and `Personnel Decisions/`.
- `01 Domains/Selection/` no longer exists as a top-level path (verified after the move).
- All seven Selection files preserved under the new path.
- No modification to `00 Core/`, `02 Products/`, `03 Software/`, `08 External/`, `09 Strategy/` or `90 Archive/`.
- No `Customer Feedback/` or `Review/` folder created.
- No Product/Runtime design introduced.
- No `git add` run; no commit performed.
