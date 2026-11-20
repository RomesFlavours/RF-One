# TASK_CORE_005 — Canonical Repository Migration Report

**Status:** Completed. No Git commit was made — all changes are staged/unstaged in the working tree, awaiting Product Owner review.

---

## A. Migration summary

1. Corrected the known misplaced README: `00 Knowledge Repository/Domains/README.md` (Purchasing Module content) moved to `00 Knowledge Repository/Domains/Restaurant/Purchasing/README.md` — the destination had no existing README, so no conflict.
2. Moved `00 Knowledge Repository/Core/` → `00 Core/` (including `ConceptualArchitecture/`), via `git mv`.
3. Moved `00 Knowledge Repository/Domains/Restaurant/` → `01 Domains/Restaurant/`, via `git mv`.
4. Renamed `01 Domains/Restaurant/Domain/` → `01 Domains/Restaurant/Model/` (Ingredient, OU-Restaurant, OperationalArea, Product, PurchasingModel, Specification — content unchanged), via `git mv`.
5. Moved `00 Knowledge Repository/Environment/` → `01 Domains/_Shared/Environment/`, via `git mv`.
6. Removed the now-empty obsolete wrapper `00 Knowledge Repository/` (and its empty `Domains/` remnant) — verified empty before removal.
7. Created `02 Products/` (the old `01 Products/` was empty and untracked; removed after creating the canonical directory with a README).
8. Created `04 Generated Documentation/` with a README (the old `02 Generated Documentation/` and its six empty subfolders were empty/untracked; removed after creation — see Section I for the "no placeholder subfolders" rationale).
9. Created `05 Research/` with a README (old `04 Research/` was empty/untracked; removed).
10. Created `06 Meetings/` with a README (old `05 Meetings/` was empty/untracked; removed).
11. Moved `Tasks/` → `07 Tasks/`: the two tracked files (`TASK_CORE_001`, `TASK_CORE_002`) via `git mv`; the three untracked files (`TASK_CORE_003`, `TASK_CORE_004`, `TASK_CORE_005`) via a plain filesystem move (they were untracked before and remain untracked at the new path — no history to preserve). Created `07 Tasks/Reports/` and `07 Tasks/Backlog/`. Removed the now-empty `Tasks/`.
12. Moved `Shelbi/` → `08 External/Shelbi/` via `git mv` (single directory rename; the empty `STage/` subfolder moved along with the physical directory rename).
13. Created `09 Strategy/` with a README only (no substantive strategy content, per instructions).
14. Created `07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md` (see Section F).
15. Created `90 Archive/` and `90 Archive/Legacy Repository/`, then moved `Old/X00 Knowledge Repository/` → `90 Archive/Legacy Repository/X00 Knowledge Repository/` via a single `git mv` on the directory — the entire original internal hierarchy (`00 Vision/` … `09 Interviews/`) was preserved unsplit. Removed the now-empty `Old/`.
16. Created/updated 11 top-level README files (Section C).
17. Rewrote root `README.md` and `PROJECT_STATE.md` (Section C).
18. Updated `CLAUDE.md` (outside this Git repository — see Section D) with a canonical top-level structure reference.
19. Updated two stale path references in `03 Software/InvoiceIntake/` (Section D/H) and one internal Core cross-reference link depth (Section D).

---

## B. Final repository tree

```text
RF One/
├── 00 Core/
│   ├── ConceptualArchitecture/        (8 files, unchanged content except one link fix)
│   ├── ArchitecturePrinciples.md, Brand.md, Core Evolution.md, Corporate.md,
│   │   Entity.md, ExternalDataMappingPrinciples.md, Glossary.md, Goal.md,
│   │   ImplementationGuidelines.md, Operational Unit.md, OperationalArea.md,
│   │   Process.md, README.md (reconciled), RF-ONE Core Principles.md, Relationship.md
├── 01 Domains/
│   ├── README.md (new)
│   ├── Restaurant/
│   │   ├── Assets/ReferenceDocuments/  (6 jpg + 1 pdf)
│   │   ├── Commercial Catalog/         (19 files)
│   │   ├── Model/                      (renamed from Domain/: 6 files)
│   │   ├── Purchasing/                 (15 files + the recovered README.md)
│   │   ├── Sales/                      (Clover/, Toast/, Combo.md)
│   │   ├── Menu.md, ServiceSequence.md, README.md
│   └── _Shared/
│       └── Environment/README.md
├── 02 Products/
│   └── README.md (new)
├── 03 Software/                        (unchanged internally; README.md added at this level)
│   ├── AI/, Backend/, Database/, Frontend/, Infrastructure/  (untracked, unchanged)
│   └── InvoiceIntake/                  (2 files touched — comment/prose only, see Section H)
├── 04 Generated Documentation/
│   └── README.md (new)
├── 05 Research/
│   └── README.md (new)
├── 06 Meetings/
│   └── README.md (new)
├── 07 Tasks/
│   ├── README.md (new)
│   ├── TASK_CORE_001…005.md
│   ├── Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md (new)
│   └── Reports/TASK_CORE_005_REPORT.md (this file)
├── 08 External/
│   ├── README.md (new)
│   └── Shelbi/                         (5 PDFs + empty STage/)
├── 09 Strategy/
│   └── README.md (new)
├── 90 Archive/
│   ├── README.md (new)
│   └── Legacy Repository/
│       └── X00 Knowledge Repository/   (original 00 Vision…09 Interviews hierarchy, unmodified)
├── PROJECT_STATE.md (rewritten)
├── README.md (rewritten)
├── RF-One.code-workspace (unchanged)
└── .gitignore (unchanged)
```

---

## C. README/governance files

| File | Action | Why |
|---|---|---|
| `00 Core/README.md` | Reconciled (not replaced) | Added an explicit "Authority" section and three missing Core-document table rows (Corporate.md, Brand.md, Operational Unit.md); all pre-existing content preserved. |
| `01 Domains/README.md` | Created | Did not exist canonically before (the old path held misplaced Purchasing content). |
| `02 Products/README.md` | Created | New layer. |
| `03 Software/README.md` | Created | Did not exist at the Software root before (only `InvoiceIntake/README.md` existed). |
| `04 Generated Documentation/README.md` | Created | New canonical location; documents intended subareas in prose instead of scaffolding empty subfolders. |
| `05 Research/README.md` | Created | New canonical location. |
| `06 Meetings/README.md` | Created | New canonical location. |
| `07 Tasks/README.md` | Created | Documents the `Reports/`/`Backlog/` convention. |
| `08 External/README.md` | Created | States external material is reference-only per instructions. |
| `09 Strategy/README.md` | Created | Establishes the layer only, no substantive strategy content, per instructions. |
| `90 Archive/README.md` | Created | States the non-authoritative rule verbatim, per instructions. |
| `README.md` (root) | Rewritten | Was an obsolete "Bootstrap repository" stub; now explains the repository at a glance and links to the canonical structure. |
| `PROJECT_STATE.md` | Rewritten | Was an obsolete "Status: Bootstrap" snapshot; now reflects Core 2.0, the Restaurant Domain, InvoiceIntake, and the completed migration. |
| `CLAUDE.md` | Updated (minimal) | Added a "canonical top-level structure" block to the existing "Repository Structure" section; no architectural instructions were redesigned. **Note:** `CLAUDE.md` lives at `AI-RF-ONE/CLAUDE.md`, one directory above the `RF One` Git repository root — it is not tracked by this repository's Git history, so this edit will not appear in `git status` for `RF One`. |

---

## D. Path references updated

| File | What changed |
|---|---|
| `00 Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md` | Fixed a pre-existing relative-link depth mismatch to `CLAUDE.md` (link text said `../../../CLAUDE.md`, the href said `../../../../CLAUDE.md` — the href happened to be numerically correct for the *old* location by coincidence of CLAUDE.md living outside the repo; both are now `../../../CLAUDE.md`, correct for the new location three levels above `ConceptualArchitecture/`). |
| `03 Software/InvoiceIntake/excel_store.py` | Line 6, inside the module docstring: `00 Knowledge Repository/Domains/Restaurant/Purchasing/DataDictionary.md` → `01 Domains/Restaurant/Purchasing/DataDictionary.md`. Comment/docstring text only — see Section H. |
| `03 Software/InvoiceIntake/README.md` | Three prose references updated: the "Knowledge Repository" wording replaced with the concrete `01 Domains/Restaurant/Purchasing/DataDictionary.md` and `01 Domains/Restaurant/Assets/ReferenceDocuments/` paths. |
| `CLAUDE.md` | Added the canonical structure block (Section C) — not a stale-reference fix, since it previously contained no path references at all. |
| `README.md`, `PROJECT_STATE.md` | Rewritten in full (Section C) — superseded rather than reference-patched, since they were pre-migration Bootstrap-era stubs. |

**Deliberately left unchanged:** every path reference inside `07 Tasks/TASK_CORE_001…005.md` and the single historical reference inside `00 Core/Core Evolution.md`'s Core 2.0 evolution-log entry (`Old/X00 Knowledge Repository/...`). These describe what was true when those documents were written and remain historically accurate; rewriting them would misrepresent history. No internal link within `00 Core/` other than the one listed above needed changes, because the relative structure between `00 Core/*.md` and `00 Core/ConceptualArchitecture/*.md` was preserved 1:1 during the move.

---

## E. Legacy archive confirmation

- Exact destination: `90 Archive/Legacy Repository/X00 Knowledge Repository/`, preserving the original internal hierarchy (`00 Vision/`, `01 Objectives/`, `02 Principles/`, `03 Constraints/`, `04 Decision Framework/`, `05 Knowledge Domains/`, `06 Business Model/`, `06 Modules/`, `07 Glossary/`, `08 Change Log/`, `09 Interviews/`) unsplit, as required (no `Legacy Core/` / `Legacy Domains/` reinterpretation).
- All 36 previously-tracked files under `Old/` show as Git renames (`R`) to the new location — none were re-created, edited, or content-rewritten.
- No `.OLD.md` suffixes were added anywhere.
- The `Why RF-ONE Must Be Delivered as a Service, Not as Software.pdf` and all other archived files were moved as opaque binary/text renames; their contents were not opened for editing (only verified to still exist at the new path).
- The legacy backlog (Section F) was created **before** the archive move, per the required sequencing.

---

## F. Legacy backlog confirmation

Created: `07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md`.

It records, verbatim from the approved decisions in `07 Tasks/TASK_CORE_005_Canonical_Repository_Migration.md`:

- **Section A (Core):** Early Failure Recognition, Optimization hierarchy (rewritten, not the literal "Mission" wording), Recursive Process, and Ownership-vs-Assignment / Specialization-extends / Entity-versioning / Temporal-semantics approved as future Core patterns — each with a likely target file. Process-persistent-status and the Hybrid Event Model were recorded as explicitly **rejected** as universal Core rules (routed to Runtime/implementation pattern instead). Capacity/Availability/Responsibility generalization and Capabilities-Enable-Services were recorded as **not yet approved**, pending more Domain evidence.
- **Section B:** the historical Operational Unit physical-business lifecycle recorded as a Shared-Domain/Domain candidate, not a Core lifecycle.
- **Section C:** Corporate Legal Identity, Corporate Documents, and AI Governance — each routed to Shared/Domain, Runtime, or `09 Strategy/` respectively, with an explicit "do not duplicate layers" rule.
- **Section D:** Brand Marketing details routed to Shared Domain; the "Goals → Brand → Service Model → Behaviors → Selection/Training/Performance" direction explicitly flagged as a **future** architecture/domain task, not implemented now.
- **Section E:** commercial-strategy items (Maximize Economic Profit, Unlimited Optimization Scope rewritten, counterfactual value measurement) routed to `09 Strategy/`, explicitly kept out of Core ontology.
- **Section F:** the "RF-One can never be sold as software" claim downgraded from immutable law to a reviewable commercial/service-delivery strategy; shared-intelligence cross-tenant learning explicitly conditioned on tenant isolation, privacy, and governance.
- **Section G:** the legacy Knowledge Domains taxonomy recorded as a capability/coverage map, not modern `Domain` ontology.
- **Section H:** interview-driven Knowledge Engineering preserved as an optional method.
- **Section I:** Corporate legal detail explicitly deprioritized.

This backlog is not canonical architecture; it is a binding tracking document.

---

## G. External material

- Confirmed destination: `08 External/Shelbi/`.
- All 5 tracked PDFs (`Management Team - Diagnosis and Meeting Plan.pdf`, `RF-One Model Review - Shelbi Fox.pdf`, `RF-One Strategic Reply - Shelbi Fox.pdf`, `Romes-Flavours-Project-Outline.pdf`, `Training-Content-Shot-List.pdf`) show as Git renames and were verified present at the new path.
- The empty `STage/` subfolder was preserved (moved along with the directory).
- No PDF content was opened for editing; only existence was verified.

---

## H. Software impact

Two files under `03 Software/` were touched — both comment/docstring/prose only:

| File | Nature of change | Logic changed? |
|---|---|---|
| `03 Software/InvoiceIntake/excel_store.py` | One line inside the module-level docstring (lines 1–11), updating a documentation path reference | **No.** No code, no `import`, no `open()`/`Path()` call, no function body was touched. Verified by reading the full docstring context before editing and confirming the only prior mention of the old path in this file was this comment (per the TASK_CORE_003 review's earlier grep, and re-confirmed in this task's own reference search). |
| `03 Software/InvoiceIntake/README.md` | Three prose sentences updated to reference the new canonical path instead of "Knowledge Repository" | **No.** This is documentation, not executable code. |

No other file under `03 Software/` (including `app.py`, `ocr_engine.py`, `parser.py`, templates, `requirements.txt`, or any data file) was opened, read for editing, or modified. No functional/operational path usage was found anywhere in the codebase — the only two references were textual (comment and README prose), so nothing required stopping/reporting under the "functional path" escalation rule.

---

## I. Validation

**`git status` summary** (full detail in the working tree; condensed here):

- 130 pure renames (`R`) — all content-preserving moves detected by Git.
- 2 rename+modify (`RM`) — `00 Core/README.md` and `00 Core/ConceptualArchitecture/06_Business_Autopilot_and_Intelligence_Engine.md`, each renamed then intentionally edited (README reconciliation; link-depth fix).
- 4 plain modifications (`M`) — `03 Software/InvoiceIntake/README.md`, `03 Software/InvoiceIntake/excel_store.py`, root `PROJECT_STATE.md`, root `README.md`.
- 14 untracked new paths (`??`) — the 10 new top-level READMEs, the new empty-but-created `02 Products/`, `04 Generated Documentation/`, `05 Research/`, `06 Meetings/`, `09 Strategy/` directories (tracked only via their README), the new `07 Tasks/Backlog/` directory, and the three Task files (003–005) that were already untracked before this migration and simply moved.
- Tracked-file count before and after: **151 in both cases** — confirmed via `git ls-files | wc -l`, i.e. no tracked file was lost.

**Link/reference verification result:**

- Systematically searched the whole repository for every old path pattern named in the task (`00 Knowledge Repository`, `01 Products`, `02 Generated Documentation`, `04 Research`, `05 Meetings`, `Tasks/`, `Shelbi/`, `Old/`, `Domains/Restaurant/Domain/`). Every remaining hit is inside a historical Task specification (`07 Tasks/TASK_CORE_001…005.md`) or a historical evolution-log narrative entry (`00 Core/Core Evolution.md`) or this report's/the backlog's own narrative description of the migration — all expected and intentionally left unchanged.
- Internal Markdown links between `00 Core/*.md` and `00 Core/ConceptualArchitecture/*.md` verified to still resolve (relative structure preserved 1:1); the one pre-existing depth mismatch (link to `CLAUDE.md`) was corrected.
- Verified the recovered `01 Domains/Restaurant/Purchasing/README.md` landed correctly and no conflicting README pre-existed at that path.

**Unexpected issues:** None. The working tree was clean at the start except for the three new, not-yet-committed Task files, exactly as anticipated by the task's mandatory first steps.

**Files deliberately left unchanged:**

- All content inside `90 Archive/Legacy Repository/X00 Knowledge Repository/` (moved, not edited).
- All content inside `08 External/Shelbi/` (moved, not edited).
- All historical Task specifications' internal old-path references.
- The historical entry in `00 Core/Core Evolution.md` describing the pre-migration `Old/` path.
- `03 Software/InvoiceIntake/app.py`, `ocr_engine.py`, `parser.py`, templates, `requirements.txt`, and data files — no reference to a changed path was found in any of them.
- `RF-One.code-workspace` — its `../RF-One` reference points to the repository folder itself from its parent directory and is unaffected by any internal reorganization.
- Zero-byte Domain files (e.g. the empty `Sales/Clover/*.md`, `Sales/Toast/README.md`, `Restaurant/Menu.md`, `Restaurant/ServiceSequence.md`) — moved with their parent directories but not reviewed or deleted, per instructions.

---

## J. Scope confirmation

- **No conceptual Core redesign:** confirmed. Every file under `00 Core/` retains its original content except two link/authority-documentation edits (Section D/C), which touch presentation and cross-references, not concept definitions. No Entity/Process/Brand/Corporate/Operational Unit/Goal/Relationship/Decision definition was rewritten.
- **No legacy content deletion:** confirmed. Every file that existed under `Old/` before this task exists, unmodified, under `90 Archive/Legacy Repository/` after this task (verified via matching tracked-file counts and Git rename detection).
- **No production behavior change:** confirmed. The only two Software-layer edits were a docstring comment and a README paragraph; no Python logic, no data file, and no application behavior was altered.
- **No Git commit:** confirmed. All changes described above remain staged/unstaged in the working tree. No `git commit` was executed at any point in this task.

---

**End of report.**
