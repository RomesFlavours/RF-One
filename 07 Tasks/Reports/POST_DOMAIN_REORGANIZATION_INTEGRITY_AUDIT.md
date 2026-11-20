# Post-Domain-Reorganization Integrity Audit

**Type:** Read-only verification audit. No file was moved, renamed, refactored, fixed, staged, or committed by this audit.
**Scope:** Entire RF-One repository, post Cross Domain / Business Domain reorganization.
**Date:** 2026-09-03

---

## 1. Executive result

**PASS WITH ISSUES**

The physical folder reorganization itself is clean: no duplicate Domain locations, no lost files, no broken imports, all 616 available test checks pass. The issues found are entirely in **conceptual documentation that was not updated to match the physical move** — mechanical path references were fixed correctly, but prose/diagrams describing "which modules belong to which Domain" were not, producing internal contradictions in several canonical documents (most notably: two files now show Training and Performance simultaneously as nested Personnel Management modules *and*, via their own working links, as extracted Cross Domain siblings). Nothing here blocks day-to-day work; everything here should be read before anyone else authors new documentation based on the stale prose.

---

## 2. Actual current repository tree

```text
RF One/
├── .claude/  .env  .gitignore  .git/
├── 00 Core/
├── 01 Domains/
│   ├── Cross Domain/
│   │   ├── Selection/            (+ ResumeScreening/, reports/, .claude/)
│   │   ├── Training/
│   │   ├── Performance/
│   │   ├── Personnel Management/ (+ Workforce/, Personnel Decisions/)
│   │   ├── Taxation/
│   │   └── Administration/       (+ Payroll/)
│   ├── Business Domain/
│   │   └── Restaurant/           (Purchasing, Sales, Commercial Catalog, Organization, Model,
│   │                               Server Performance, Service Copilot, Dining Intelligence,
│   │                               Tips, Assets, Selection [industry extension], Roadmap.md,
│   │                               README.md, Restaurant Semantic Model.md)
│   ├── _Shared/                  (Environment/ — not a Domain)
│   ├── README.md
│   └── Domain Architecture.md
├── 02 Products/                  (README.md only — no content yet)
├── 03 Software/
│   ├── AI/  Backend/  Database/  Frontend/  Infrastructure/   (all empty, pre-existing, unrelated to this reorg)
│   ├── Clover Data Explorer/
│   ├── InvoiceIntake/
│   ├── RF-One Data Store/        (rfone_data_store package: selection/, payroll/, purchasing/, tips/, profile/, ingestion/; migrations/; many test_*.py)
│   ├── Selection/                (Flask app: app.py, templates/, test_batch_upload.py, data/, uploads/)
│   ├── README.md, User Interaction Architecture.md
├── 04 Generated Documentation/   (README.md only)
├── 05 Research/                  (README.md only)
├── 06 Meetings/                  (README.md only)
├── 07 Tasks/                     (task specs at root; Reports/; Backlog/)
├── 08 External/                  (6 files)
├── 09 Strategy/
├── 90 Archive/
├── CLAUDE.md, OpenQuestions.md, PROJECT_STATE.md, README.md, RF-One.code-workspace
```

`02 Products/`, `04 Generated Documentation/`, `05 Research/`, `06 Meetings/` each contain only their placeholder `README.md` — no Domain content, so unaffected by this reorg by definition.

---

## 3. Current Cross Domain list

`01 Domains/Cross Domain/`: **Selection, Training, Performance, Personnel Management, Taxation, Administration**

## 4. Current Business Domain list

`01 Domains/Business Domain/`: **Restaurant**

---

## 5. Classification concerns

| Domain | Current classification | Internally consistent with its own documentation? |
|---|---|---|
| Selection | Cross Domain | **Yes.** `Selection/README.md` describes itself as "a universal, cross-industry, transversal Domain... a sibling of Restaurant, Personnel Management, Taxation and Administration." |
| Restaurant | Business Domain | **Yes.** `Restaurant/README.md` describes itself as "primarily the technical/operational Domain" for one industry. |
| Taxation | Cross Domain | **Yes.** Self-describes as transversal, industry-independent. |
| Administration | Cross Domain | **Yes.** Self-describes as transversal, "Independent from Restaurant, Personnel Management." |
| Personnel Management | Cross Domain | **Yes**, at the Domain level (self-describes as "a universal business Domain"). **No**, at the module-map level — see below. |
| **Training** | Cross Domain (physically extracted from Personnel Management) | **No — contradicted.** `Training/README.md` still says "Training consumes technical knowledge... from whichever technical Domain the role belongs to" (fine on its own) but every OTHER canonical document that mentions Training (`Domain Architecture.md` §4, `01 Domains/README.md`, `Personnel Management/README.md`'s own module map, both `CLAUDE.md` files) still states or diagrams Training as a **module of Personnel Management**, not as an extracted Cross Domain sibling. |
| **Performance** | Cross Domain (physically extracted from Personnel Management) | **Same contradiction as Training** — see below, §15. |

**No Domain's classification is itself ambiguous** (every Domain's own top-level self-description matches its physical placement). The concern is narrower and more concrete: **Training and Performance's physical location no longer matches how several authoritative documents describe them conceptually** (as Personnel Management modules). This is reported in full in §15.

---

## 6. Duplicate/obsolete Domain findings

**None.** Verified directly:

- `01 Domains/Restaurant/`, `01 Domains/Personnel Management/`, `01 Domains/Selection/`, `01 Domains/Taxation/`, `01 Domains/Administration/`, `01 Domains/Training/`, `01 Domains/Performance/` (old locations) — **do not exist**.
- No second copy of any moved Domain exists anywhere else in the repository (checked `90 Archive/` explicitly — clean).
- `01 Domains/Business Domain/Restaurant/Selection/` is the legitimate, pre-existing Restaurant Industry Extension of Selection — not a duplicate of `Cross Domain/Selection/`.
- `03 Software/RF-One Data Store/rfone_data_store/selection/` and `03 Software/Selection/` are legitimate software implementation folders, correctly not treated as duplicate Domain content.

---

## 7. Broken active path references (Category A)

**One found**, both narrow and non-functional (a doc-comment, not code logic):

`03 Software/RF-One Data Store/rfone_data_store/selection/core/__init__.py`, lines 4–5:

```python
restaurant, FOH/BOH, or any other industry concept (01 Domains/Personnel
Management/Selection/ResumeScreening/README.md, "Domain architecture").
```

This path is wrapped across two source lines ("Personnel" / "Management" split by the line break). The prior reorganization's mechanical path-fixing pass matched single-line occurrences of `01 Domains/Personnel Management/`; because this one is split by a newline, it was never matched and still points to the pre-TASK_DOMAINS_003 location (`Personnel Management/Selection/`), which is now doubly wrong (Selection moved out of Personnel Management, then to Cross Domain). **Does not affect behavior** — it's a comment establishing an architectural rule ("Nothing in this package may import from `..industry`"), and that rule itself is still correctly enforced in code; only the citation path is stale.

A targeted multiline search for the same line-wrapping pattern elsewhere in the repository found no other instance.

---

## 8. Harmless historical path references (Category B)

**301 mentions of old absolute-style Domain paths, all confined to `07 Tasks/`** (28 files: task specs still at `07 Tasks/` root whose corresponding `_REPORT.md` already exists — i.e., completed tasks; every file under `07 Tasks/Reports/`; `07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md`). Zero such mentions exist in any active area (`00 Core`, `01 Domains`, `02 Products`, `03 Software`, `04–06`, `08 External`, `09 Strategy`, or the root `CLAUDE.md` / `PROJECT_STATE.md` / `README.md` / `OpenQuestions.md`).

This matches CLAUDE.md's own classification of `07 Tasks/` as "task specs, reports, backlog — historical record": these files describe what was true at the time they were written and are not expected to track later reorganizations. Two files worth naming individually since they were unfamiliar going into this audit and predate the reorg (Aug 27 and Aug 29, reorg happened Sept 3): `07 Tasks/Reports/PRE_COMMIT_AUDIT.md` and `07 Tasks/Reports/PURCHASING_CURRENT_STATE_AUDIT.md` — both legitimate historical snapshots, correctly untouched.

**One item flagged as Category C rather than pure B**, since a backlog (unlike a report) is arguably still consulted forward-looking: `07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md` (dated Aug 31, also pre-reorg) mentions old Domain paths. Whether this still needs active reconciliation against the new structure is a Product Owner call, not assumed here.

No relative-link staleness was found outside `01 Domains/` either: `00 Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md` and `09 Strategy/04_Business_Capability_Coverage.md` are the only two files with relative links crossing into `01 Domains/`, and both resolve correctly (one to the unmoved `01 Domains/README.md`, the other already updated to `01 Domains/Business Domain/Restaurant/Roadmap.md`).

---

## 9. Software ↔ Domain integrity

- **Imports:** every module under `rfone_data_store/selection/` (46 files: `analysis`, `persistence`, `import_pipeline`, `application_service`, `candidate_flag_service`, `decision_service`, `fit_assessment_service`, `identity_service`, `in_person_interview_service`, `normalization`, `outcome_service`, `phone_interview_service`, `primary_screening_ai_evaluator`, `primary_screening_service`, `queue_service`, `requirements_service`, `resume_evidence_matcher`, `selection_notes_service`, `signal_detector`, `signal_service`, `stage_service`, `workflow_projection_service`, every `core/*` and `parsing/*` submodule, `industry/*`) imports cleanly with no errors.
- **Entry point:** `03 Software/Selection/app.py` loads successfully; Flask registers **125 routes**; `GET /` returns HTTP 200 against a fresh throwaway database.
- **Path constants:** `app.py`'s `UPLOAD_DIR`/`DATA_DIR` and `rfone_data_store/database.py`'s default SQLite path are all relative to their own module location (`os.path.dirname(__file__)`-based), never to `01 Domains/` — the Domain reorg cannot break these by construction.
- **Documentation references inside code** (docstrings/comments citing `01 Domains/...` paths): all correct **except** the one line-wrapped miss in §7.
- **Migrations, tests, templates:** all present, all resolve, all pass (§14).
- **Software-layer restructuring:** **not performed** by the prior reorg (by design — see that task's own report, §5) and **does not appear necessary** on functional grounds — nothing in `03 Software/` broke, and nothing in `03 Software/` structurally requires mirroring the `01 Domains/` Cross/Business split to keep working. This is a factual statement about current behavior, not a recommendation either way on whether such a restructuring would be desirable for other reasons.

---

## 10. Cross-Domain dependency findings

**Documentation layer (`01 Domains/`):** `Cross Domain/Selection`, `Cross Domain/Training`, and `Cross Domain/Performance` each mention Restaurant, but every instance is the pre-existing, sanctioned "Business Domain supplies technical content, Cross Domain consumes it as an input" pattern (e.g. Training's README: "Restaurant wine-service or kitchen-process standards"; `Selection.md`: "Restaurant's requirements for a Kitchen Manager"; Performance's README explicitly states "Restaurant examples... are used... to validate that Performance concepts are genuinely reusable — not to define Performance around Restaurant"). None of these are structural/import dependencies; all pre-date this reorg and were not introduced by it.

**Software layer (`03 Software/`) — factual finding, pre-existing, not caused by this reorg:** `rfone_data_store/selection/analysis.py` line 27 contains a direct import:

```python
from .industry import restaurant as restaurant_industry
```

This is a hard-coded import of the Restaurant Industry Extension from Selection's Runtime analysis engine. `core/__init__.py`'s own docstring establishes the rule that nothing *inside* `core/` may import `..industry` — and indeed nothing in `core/` does — but `analysis.py` sits one level up (in `selection/` proper, not `core/`) and is exactly where that boundary is deliberately crossed for the current single-client deployment. `analysis.py`'s own docstring already documents this as a known, temporary simplification ("A future multi-client deployment would look this up per-client instead of importing one industry module directly — not needed yet"). Reported here as a factual condition relevant to §6's dependency-direction question; not a new issue, not evaluated for whether it should change.

No hard-coded dependency from Training's or Performance's *code* onto Restaurant was found (neither has a comparable Runtime implementation yet to check).

---

## 11. Core/Shared infrastructure findings

**No misplacement found.** `00 Core/` was not touched by either reorg and contains no Domain-specific content. `01 Domains/_Shared/` (currently just `Environment/`) remains at the `01 Domains/` root, correctly outside both `Cross Domain/` and `Business Domain/` — consistent with `01 Domains/README.md`'s own statement that `_Shared/` is "not itself a Domain." No shared/common infrastructure (persistence, adapters, utilities) was found nested inside `Cross Domain/` by either reorg.

---

## 12. Git integrity findings

Current `git status` (inspected only — nothing staged, committed, or reset by this audit; the existing staged state was produced by the **prior** reorg task, not by this audit):

```text
137  R   renamed, prior history preserved
116  A   staged add, unchanged since staging
 13  AM  staged add, further modified afterward (ongoing concurrent work)
 31  M   staged, content-modified in place (reference fixes in files that did not move)
  1  MM  staged-modified, further modified again afterward (rfone_data_store/models.py)
  3  ??  new untracked files created after the prior task's staging
```

`git diff --cached --stat`: 298 files changed, 33,610 insertions(+), 2,875 deletions(-), **zero unpaired deletions** (every `D` is paired with a matching `A`/rename — no content silently lost).

**The 3 untracked (`??`) files:**
- `01 Domains/Cross Domain/Selection/reports/TASK_5A_ALIGNMENT_CHECK_REPORT.md` — a report, harmless.
- `03 Software/RF-One Data Store/migrations/versions/a3f8e1c6d9b4_add_selection_5a_align_events_and_outcome_metadata.py` — a migration, harmless (already applied successfully in this audit's test runs).
- **`03 Software/Selection/smoke_5amf.db` — flagged.** A 1.5 MB SQLite database file sitting directly in `03 Software/Selection/` (not under the gitignored `data/` or `uploads/` subfolders). Checked: **not covered by any `.gitignore` pattern** (`git check-ignore` returns nothing) — if a future `git add -A` / `git commit` is run without noticing it, this file would be committed. Its contents were not opened by this audit (repository privacy convention: never inspect candidate PII beyond what's needed). Given the filename ("smoke_...") it is very likely a disposable smoke-test artifact, not intentional data, but its untracked, unignored state is a genuine git-hygiene finding independent of the Domain reorg.

No accidental mass deletions, no duplicate add/delete pairs, and no evidence of files lost during the moves were found.

---

## 13. Import/package findings

All clean. `python -m py_compile` succeeds for every `.py` file under `rfone_data_store/` and `03 Software/Selection/`. A full import of every submodule of `rfone_data_store.selection` (see §9's file list) succeeds with no `ImportError`/`ModuleNotFoundError`/`AttributeError`. No import references an old `01 Domains` path (Python imports never did — they use package names — so this was never at risk from the Domain move; confirmed anyway).

---

## 14. Tests executed and results

All run against a single fresh, throwaway SQLite database (never the real `data/rfone.db` or `data/selection.db`):

| Command | Result | Related to reorg? |
|---|---|---|
| `python create_database.py` (schema validation) | **29/29 passed** | No failures |
| `python test_selection_engine.py` | **364/364 passed** | No failures |
| `python test_organization_validation.py` | **14/14 passed** | No failures |
| `python test_payroll_engine.py` | **52/52 passed** | No failures |
| `python test_purchasing_engine.py` | **24/24 passed** | No failures |
| `python test_restaurant_profile_bootstrap.py` | **14/14 passed** | No failures |
| `python test_sales_validation.py` | **27/27 passed** | No failures |
| `python test_tips_engine.py` | **54/54 passed** | No failures |
| `python test_batch_upload.py` (Flask, real HTTP) | **38/38 passed** | No failures |

**Total: 616/616 checks passed, zero failures.** No dedicated Training or Performance test suite exists in the repository (both remain documentation-only/placeholder modules with no Runtime implementation to test) — this is a pre-existing condition, not something the reorg broke.

---

## 15. Documentation inconsistencies

**This is the substantive finding of this audit.** The physical move correctly extracted Training and Performance out of Personnel Management into `Cross Domain/Training/` and `Cross Domain/Performance/` as direct siblings — and every *link* to them was correctly fixed to point one level further up. But no document's *prose or diagrams* were updated to say Training and Performance are no longer Personnel Management's modules, producing internally contradictory documents:

1. **`01 Domains/Cross Domain/Personnel Management/README.md`** — self-contradictory within one file. Its own "Module map" ASCII tree still draws Training and Performance as child nodes:
   ```text
   Personnel Management
   ├── Workforce
   ├── Training
   ├── Performance
   └── Personnel Decisions
   ```
   immediately followed by the sentence "These are **modules of one transversal Domain**, not independent top-level Domains" — yet the table two lines below links `[Training/](../Training/README.md)` and `[Performance/](../Performance/README.md)`, i.e. `../`, a *sibling* path, not a child path. The diagram and the prose say "nested module"; the working links say "extracted sibling."

2. **`01 Domains/Domain Architecture.md` §4** — the repository's own authoritative "current transversal Domains" reference — draws the identical stale tree (Training and Performance nested under Personnel Management with `├──`/`└──`) and states "Workforce, Training, Performance and Personnel Decisions are modules of one transversal Domain, Personnel Management" (§4) and again in §5. Never mentions "Cross Domain" or "Business Domain" as physical categories anywhere in the document, despite being titled "Cross-Domain Conclusions" and being the document `01 Domains/README.md` points readers to for exactly this information.

3. **`01 Domains/README.md`** — "Current Domains" table describes Personnel Management's modules as "Workforce, Training, Performance and Personnel Decisions" (implying all four are still its modules) and gives bare paths like `` `Restaurant/README.md` `` and `` `Selection/README.md` `` with no `Cross Domain/`/`Business Domain/` prefix at all — these are backtick-quoted plain text, not markdown links, so the prior reorg's link-fixing pass did not touch them (it only recomputed actual `[label](href)` links and `` `../relative`` `` backtick paths, not bare same-level mentions like these). The table never mentions the Cross Domain / Business Domain grouping.

4. **`RF One/CLAUDE.md`** (git-tracked copy) — line 51: "Workforce, Training, Performance and Personnel Decisions are modules of the Personnel Management Domain (`Personnel Management Domain └── <module>`, canonically `01 Domains/Cross Domain/Personnel Management/<module>/`)." The *path prefix* was correctly updated to `Cross Domain/`, but the *claim* is now factually wrong for two of the four named modules — Training and Performance are no longer under `01 Domains/Cross Domain/Personnel Management/<module>/` at all; they are at `01 Domains/Cross Domain/Training/` and `01 Domains/Cross Domain/Performance/` directly.

5. **`c:\Users\servi\OneDrive\AI-RF-ONE\CLAUDE.md`** (the parent-folder copy, **outside this Git repository** — confirmed `AI-RF-ONE/` has no `.git` of its own) — doubly stale: still says `01 Domains/Selection/` (missing even the Cross Domain step from the *prior* reorg) and `01 Domains/Restaurant/Selection/` (missing Business Domain), and makes the same "modules of Personnel Management" claim about Training/Performance as item 4. Flagged for completeness since it demonstrably governs the same project's instructions, but it is not part of the Git repository this audit's Git-integrity checks (§12) cover.

No document anywhere in the repository (outside this audit's own report and the prior reorg's own report, both in `07 Tasks/Reports/`) states in prose, as an architectural fact, "Training and Performance were extracted from Personnel Management into Cross Domain as direct siblings." A reader relying on `Domain Architecture.md`, `01 Domains/README.md`, `Personnel Management/README.md`, or either `CLAUDE.md` alone would conclude Training and Performance are still Personnel Management modules — which is no longer true of their physical location.

---

## 16. Critical issues

None. Nothing found blocks functionality, causes data loss, or produces a broken build/test.

## 17. Non-critical issues

1. Stale line-wrapped path comment in `rfone_data_store/selection/core/__init__.py` (§7).
2. Untracked, un-gitignored `03 Software/Selection/smoke_5amf.db` (§12).
3. Five documents whose prose/diagrams contradict the actual post-reorg location of Training and Performance (§15, items 1–5).
4. `01 Domains/README.md`'s Domain table never states the Cross Domain / Business Domain grouping explicitly (§15, item 3) — same root cause as above, listed separately because it's a gap in *completeness* (never mentions the new taxonomy) rather than a *contradiction*.
5. `07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md` contains old-path mentions and, unlike a report, may still be actively consulted (§8).

## 18. Items requiring a decision from us

- Whether `Domain Architecture.md`, `01 Domains/README.md`, `Personnel Management/README.md`, and both `CLAUDE.md` files should be updated to state the Cross Domain / Business Domain taxonomy explicitly and correct the Training/Performance module-map claim — and if so, whether that's one follow-up task or several.
- Whether the parent-folder `AI-RF-ONE/CLAUDE.md` (outside this Git repository) should be brought in sync with the in-repo copy, and if so, by what mechanism, given it isn't part of this repository.
- Whether `03 Software/Selection/smoke_5amf.db` should be deleted, gitignored, or left as-is.
- Whether `LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md` needs a fresh reconciliation pass against the new Domain taxonomy or should remain a frozen historical record like everything else in `07 Tasks/`.
- Whether `rfone_data_store/selection/analysis.py`'s hard import of the Restaurant industry extension (§10) — already self-documented as a temporary single-client simplification — is still an acceptable state or should be tracked as follow-up work.

---

## Summary table

| ISSUE | LOCATION | SEVERITY | WHY IT MATTERS | REQUIRES ACTION |
|---|---|---|---|---|
| Training/Performance still documented as Personnel Management modules despite being physically extracted to Cross Domain | `Domain Architecture.md` §4/§5, `Personnel Management/README.md`, `01 Domains/README.md`, `CLAUDE.md` (both copies) | Medium | Repository's own authoritative architecture docs contradict the actual folder structure; anyone reading only the docs will misunderstand where Training/Performance live | Yes — decide scope of doc update |
| `01 Domains/README.md` never states the Cross Domain/Business Domain grouping | `01 Domains/README.md` | Medium | Entry-point document for `01 Domains/` doesn't explain the top-level taxonomy that now physically exists | Yes |
| Parent-folder `CLAUDE.md` doubly stale (missing both the Selection top-level move and the Cross/Business split) | `c:\Users\servi\OneDrive\AI-RF-ONE\CLAUDE.md` (outside this Git repo) | Medium | Same project's instructions, inconsistent with the in-repo copy and with actual structure | Yes — decide how to sync a file outside this repo |
| Stale line-wrapped path comment | `rfone_data_store/selection/core/__init__.py` lines 4–5 | Low | Misleading doc-comment only; the rule it documents is still correctly enforced in code | Optional |
| Untracked, un-gitignored smoke-test database | `03 Software/Selection/smoke_5amf.db` | Low | Could be accidentally committed; unclear if it holds test or real data (not inspected) | Yes — decide delete/ignore/keep |
| Legacy backlog file contains pre-reorg paths | `07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md` | Low | Backlogs are typically forward-referenced, unlike reports; may or may not need reconciliation | Optional |
| Hard-coded Restaurant industry import in Selection's analysis engine | `rfone_data_store/selection/analysis.py` line 27 | Low (pre-existing, self-documented) | Only path in the Runtime layer where Selection structurally depends on Restaurant; already flagged by its own author as temporary | Optional |
