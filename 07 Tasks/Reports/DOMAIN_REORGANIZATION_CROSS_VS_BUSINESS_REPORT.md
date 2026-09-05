# Domain Reorganization — Cross Domain vs. Business Domain — Report

**Task:** Repository-wide reorganization of `01 Domains/` into a `Cross Domain/` / `Business Domain/` folder taxonomy.
**Origin:** Explicit Product Owner instruction (chat), issued immediately after TASK_DOMAINS_003 (Selection re-elevated to top-level).
**Scope:** Folder/domain reorganization and the broken-reference fixes it causes. No functionality, business rules, or Domain internals were redesigned.

---

## 1. Previous Domain structure

```text
01 Domains/
├── Restaurant/                    Domain (business-specific)
├── Personnel Management/          Domain (transversal)
│   ├── Workforce/                   module
│   ├── Training/                    module
│   ├── Performance/                 module
│   └── Personnel Decisions/         module
├── Selection/                     Domain (transversal — re-elevated by TASK_DOMAINS_003, same day)
├── Taxation/                      Domain (transversal)
├── Administration/                Domain (transversal)
├── _Shared/                       shared knowledge, not itself a Domain
├── README.md
└── Domain Architecture.md
```

## 2. New Domain structure

```text
01 Domains/
├── Cross Domain/
│   ├── Selection/                   (with ResumeScreening/, reports/, .claude/ — moved intact)
│   ├── Training/                    (extracted out of Personnel Management)
│   ├── Performance/                 (extracted out of Personnel Management)
│   ├── Personnel Management/        (remainder: Workforce/, Personnel Decisions/, README.md)
│   ├── Taxation/
│   └── Administration/                (with Payroll/)
├── Business Domain/
│   └── Restaurant/                  (all existing modules unchanged: Purchasing, Sales, Commercial
│                                      Catalog, Organization, Server Performance, Service Copilot,
│                                      Dining Intelligence, Tips, Assets, Model, Selection [industry
│                                      extension], Roadmap.md, README.md, Restaurant Semantic Model.md)
├── _Shared/                        unmoved — not a Domain (see §5)
├── README.md                       unmoved — meta/index document, not a Domain
└── Domain Architecture.md          unmoved — meta/architecture document, not a Domain
```

---

## 3. Domains classified as Cross Domain

| Domain | Basis for classification |
|---|---|
| **Selection** | Explicitly named by the Product Owner. Already self-documented as a universal, cross-industry, transversal Domain (re-affirmed hours earlier by TASK_DOMAINS_003). |
| **Training** | Explicitly named by the Product Owner. Extracted out of Personnel Management to sit directly under Cross Domain, per the Product Owner's own tree diagram, which showed it as a sibling of Selection, not nested. |
| **Performance** | Explicitly named by the Product Owner, extracted the same way as Training. Its own README already states "Restaurant may provide restaurant-specific evidence to Performance, but the Performance engine itself remains Cross Domain" — matching the Product Owner's own worked example verbatim. |
| **Personnel Management** (remainder: Workforce, Personnel Decisions) | Not explicitly named, but self-documented throughout as "the transversal (cross-industry) Domain" with zero Restaurant-specific ontology — an unambiguous match for the stated Cross Domain test ("provides a reusable capability that can operate across different businesses/sectors"). |
| **Taxation** | Self-documented as "Transversal Domain for tax obligations, positions, treatments, scenarios and lawful tax optimization... distinct from Accounting, Finance and Legal Entity Management." Unambiguous. |
| **Administration** | Self-documented as "Transversal Domain for administrative execution of obligations arising from operating a business... Independent from Restaurant, Personnel Management, ADP, and jurisdiction-specific labor law." Unambiguous. |

## 4. Domains classified as Business Domain

| Domain | Basis for classification |
|---|---|
| **Restaurant** | Explicitly named by the Product Owner. Self-documented throughout as "primarily the technical/operational Domain" for one industry — the only Domain in the repository whose ontology, integrations and operational semantics are genuinely industry-specific. |

No other Business Domain currently exists in the repository.

## 5. Ambiguous / not moved

**None of the six top-level entries under `01 Domains/` were genuinely ambiguous.** Every Domain's own canonical documentation already stated, unprompted, whether it was transversal or industry-specific — so classification did not require guessing.

`_Shared/` was **not** moved into either category — it is explicitly documented (`01 Domains/README.md`) as "domain-independent-but-not-universal shared knowledge reused across multiple Domains," not a Domain itself, matching the task's own "IMPORTANT NON-DOMAIN COMPONENTS" instruction. `README.md` and `Domain Architecture.md` likewise stayed at the `01 Domains/` root — they are the index/meta-architecture documents for the whole `Domains/` tree, not Domains.

**One scope judgment call worth flagging explicitly:** the task's SELECTION section listed software-layer items (migrations, tests, templates, data/storage) as things to preserve, which could be read as instructing a matching reorganization of `03 Software/`. I did **not** restructure `03 Software/` (e.g. did not create `03 Software/Cross Domain/Selection/`) — only `01 Domains/` was split into Cross Domain/Business Domain. Reasoning: (a) the task's own final target tree diagram shows only `Domains/` being split, with "Core / infrastructure / shared architectural layers" left as a separate, unsplit sibling; (b) CLAUDE.md's canonical top-level structure already treats `01 Domains/` (business knowledge) and `03 Software/` (runtime behavior) as fundamentally different categories; (c) the task's own "IMPORTANT NON-DOMAIN COMPONENTS" section says not to move persistence/infrastructure into Cross Domain merely because it's shared; (d) moving live, imported Python packages carries materially higher risk than moving markdown, and the task emphasized safety and no large dependency refactor. I read "preserve ALL Selection functionality... migrations... tests... templates" as "don't lose or break any of this while moving the docs," not as "also relocate it." **If this reading is wrong, say so and I'll redo the software-layer move as a separate, explicitly-scoped pass** — it is a materially different (and riskier) kind of change than the documentation move performed here.

---

## 6. Files/folders moved

Physical moves (via `mv`, preserving content so Git's rename detection could pair them with their prior history):

- `01 Domains/Selection/` → `01 Domains/Cross Domain/Selection/` (27 markdown files, plus the `ResumeScreening/`, `reports/` and `.claude/` subfolders created by other in-progress work — moved intact, untouched beyond path-reference fixes)
- `01 Domains/Personnel Management/Training/` → `01 Domains/Cross Domain/Training/`
- `01 Domains/Personnel Management/Performance/` → `01 Domains/Cross Domain/Performance/`
- `01 Domains/Personnel Management/` (remainder: `Workforce/`, `Personnel Decisions/`, `README.md`) → `01 Domains/Cross Domain/Personnel Management/`
- `01 Domains/Taxation/` → `01 Domains/Cross Domain/Taxation/`
- `01 Domains/Administration/` (with `Payroll/`) → `01 Domains/Cross Domain/Administration/`
- `01 Domains/Restaurant/` (93 markdown files plus binary reference assets) → `01 Domains/Business Domain/Restaurant/`

After staging (`git add -A`), Git confirms:

- **137** paths detected as **renames** (prior Git history preserved)
- **128** paths added as new (content that was already untracked before this reorg — mainly the large, currently-uncommitted Selection subsystem and Selection MVP work from earlier in this session — and now simply lives at its new path)
- **32** paths modified in place (files outside the moved trees whose *references* needed fixing, not their location)
- **0** deletions that aren't paired with a corresponding rename/re-add — i.e., no content was lost

No duplicate exists: `01 Domains/Restaurant`, `01 Domains/Personnel Management`, `01 Domains/Selection`, `01 Domains/Taxation`, `01 Domains/Administration` no longer exist at their old locations (verified directly).

## 7. Path/import references updated

Broken references were fixed with a purpose-built script (not manual editing, given the scale — 153 markdown files under `01 Domains/` alone, plus ~40 more files elsewhere referencing these paths) that:

- **Pass A (absolute-style paths):** substituted the literal prefix (e.g. `01 Domains/Restaurant/` → `01 Domains/Business Domain/Restaurant/`, both plain and `%20`-encoded forms) wherever it appeared in prose, backticks, or code comments, across the whole repository.
- **Pass B (relative markdown links, `01 Domains/**/*.md` only):** for every `[label](../relative/path)` link and every `` `../relative/path` `` backtick mention, resolved what the link's target actually was (accounting for the file's own move), then recomputed the correct new relative path from the file's new location to that same target — not a blind string substitution, since relative-path arithmetic differs by source file and by whether the link crosses a Cross Domain/Business Domain boundary.
- A pre-pass also normalized a handful of links that were **already stale before this task** — several Performance documents (written by other in-progress work) still linked to `Personnel Management/Selection/`, the location from before this morning's TASK_DOMAINS_003 move. These are now correctly pointed at `Cross Domain/Selection/`.

**Totals:** 112 files modified, 187 absolute-path substitutions, 239 relative-link recomputations.

`07 Tasks/` (specs, reports, backlog) was deliberately **excluded** from all rewriting — CLAUDE.md itself classifies that directory as "historical record," so old path mentions inside completed task specs/reports describe what was true when they were written and are left as-is. `90 Archive/` was likewise excluded (never current authority).

Representative files updated: `CLAUDE.md` (both copies), `PROJECT_STATE.md`, `01 Domains/README.md`, `01 Domains/Domain Architecture.md`, every README/concept file inside the moved domains, `09 Strategy/04_Business_Capability_Coverage.md`, and ~20 Python docstrings/comments under `rfone_data_store/selection/` and `rfone_data_store/models.py` that referenced the old doc paths in comments (no functional code changed).

## 8. Dependency issues discovered

**None new.** Checked explicitly: `Cross Domain/Selection`, `Cross Domain/Training`, and `Cross Domain/Performance` do reference `Business Domain/Restaurant` in a few places (e.g. Training's README: "Restaurant wine-service or kitchen-process standards"; Selection.md: "Restaurant's requirements for a Kitchen Manager") — but these are the same **pre-existing, sanctioned "Business Domain supplies content, Cross Domain consumes it"** relationships that already existed before this reorg (illustrative prose and explicit "Restaurant is the first application context, not the architectural owner" framing), not new structural/import dependencies introduced by the move. No Cross Domain file imports, requires, or structurally depends on Restaurant existing.

One pre-existing architectural note surfaced (not a new violation, not silently redesigned): `Cross Domain/Performance`'s Workforce and Personnel Decisions references now correctly read `../Personnel Management/Workforce/` and `../Personnel Management/Personnel Decisions/` — Performance depends on two modules that stayed nested inside the (now sibling) Personnel Management Domain rather than becoming top-level themselves, since the Product Owner's instruction only named Selection, Training and Performance for extraction, not Workforce or Personnel Decisions. This is a legitimate cross-Domain-family reference (Cross Domain → Cross Domain), not a violation of the Business-Domain-independence rule, but it does mean Performance's dependency graph now spans two Cross Domain folders instead of one — flagged here per the task's own "document rather than silently redesign" instruction, in case the Product Owner wants Workforce/Personnel Decisions extracted too for full symmetry with Training/Performance/Selection.

## 9. Tests / validation performed

1. **Repository paths verified** — `find`/`ls` confirm the new tree exists exactly as planned and no old-location folder remains.
2. **Imports/compile verified** — every `.py` file under `rfone_data_store/` and `03 Software/Selection/` byte-compiles cleanly (`python -m py_compile`) after the reference-fixing pass.
3. **Targeted tests run:**
   - `create_database.py` (schema validation): **29/29 passed**.
   - `test_selection_engine.py` (`selection_validation.py`): **339/339 passed** (this suite has grown substantially from other in-progress work since this session started; all pass post-move).
   - `test_batch_upload.py` (Flask-level, real HTTP routes): **38/38 passed**.
4. **Selection starts/tests correctly** — confirmed by the above; the Flask app's Selection routes and the `rfone_data_store.selection` package both function normally (they never depended on the `01 Domains/` doc paths at runtime — those only appeared in comments/docstrings, now corrected).
5. **Training/Performance references resolve** — spot-checked and covered by Pass B; no remaining stale link found (see §10).
6. **Restaurant references resolve** — spot-checked (`Restaurant Semantic Model.md`, `Roadmap.md`, `Server Performance/README.md`, Dining Intelligence files referencing Performance) and covered by Pass B.
7. **Stale-reference sweep** — repository-wide grep for every old absolute prefix (`01 Domains/Restaurant/`, `01 Domains/Personnel Management/`, `01 Domains/Taxation/`, `01 Domains/Administration/`, `01 Domains/Selection/`), excluding `07 Tasks/` and `90 Archive/`: **zero matches**.
8. **Git status checked** — `git add -A` then inspected: 137 renames, 128 new adds, 32 modifies, no unpaired deletions (see §6).

## 10. Remaining stale-path findings

**None found** in the automated absolute-path sweep (§9.7) after the fix pass. Two categories are knowingly **not** covered and may still contain old-style paths, by design:

- `07 Tasks/*.md` (specs, reports, backlog) and `90 Archive/` — intentionally excluded as historical record (see §7).
- Relative markdown links **outside** `01 Domains/` (e.g. inside `00 Core/`, `09 Strategy/`, `02 Products/`) were not subject to Pass B's relative-link recomputation, only Pass A's absolute-path substitution. A manual scan of `00 Core/` and `09 Strategy/` found no relative links pointing into `01 Domains/` in the first place (cross-layer references in this repository consistently use the absolute `01 Domains/...` style, which Pass A does cover) — but this wasn't verified with the same rigor as the intra-`01 Domains/` relative links, so it's flagged rather than silently assumed complete.

## 11. Final Git status summary

```text
137 R  (renamed — history preserved)
128 A  (newly staged; content was already untracked before this reorg)
 32 M  (reference-only edits in files that did not move)
  0 unexplained deletions
```

All changes are currently **staged** (`git add -A` was run to enable Git's rename detection and produce the summary above) but **not committed** — no commit was made, consistent with only committing when explicitly asked.

---

## NEW DOMAIN FOLDER TREE

```text
01 Domains/
├── Cross Domain/
│   ├── Selection/
│   │   ├── ResumeScreening/
│   │   ├── reports/
│   │   └── (Selection.md, SelectionRequirement.md, CandidateEvidence.md, FitAssessment.md,
│   │        SelectionDecision.md, TrainableGap.md, README.md, ...)
│   ├── Training/
│   │   └── README.md
│   ├── Performance/
│   │   └── (Performance.md, PerformanceEvidence.md, PerformanceMeasure.md,
│   │        PerformanceIndicator.md, PerformanceContext.md, README.md)
│   ├── Personnel Management/
│   │   ├── Workforce/
│   │   ├── Personnel Decisions/
│   │   └── README.md
│   ├── Taxation/
│   │   └── (Taxation.md, TaxEvidence.md, TaxPosition.md, TaxStrategy.md, ..., README.md)
│   └── Administration/
│       ├── Payroll/
│       └── (Personnel Cost.md, README.md, ...)
├── Business Domain/
│   └── Restaurant/
│       ├── Purchasing/
│       ├── Sales/
│       ├── Commercial Catalog/
│       ├── Organization/
│       ├── Model/
│       ├── Server Performance/
│       ├── Service Copilot/
│       ├── Dining Intelligence/
│       ├── Tips/
│       ├── Assets/
│       ├── Selection/            (Restaurant's Industry Extension of Cross Domain/Selection)
│       ├── Roadmap.md, README.md, Restaurant Semantic Model.md
├── _Shared/                      (not a Domain — shared knowledge)
├── README.md
└── Domain Architecture.md
```
