# TASK_DOMAINS_003 — Report

**Task:** Re-elevate Selection to a top-level, transversal Domain
**Origin:** Explicit Product Owner correction, issued mid-way through TASK_SELECTION_002 (multi-résumé batch import), requiring the domain move to be completed before that work continued.
**Status:** Complete.

---

## A. Executive conclusion

Selection — previously a module of the Personnel Management Domain (`01 Domains/Personnel Management/Selection/`, established by TASK_DOMAINS_002) — has been moved back out to its own top-level, transversal Domain at `01 Domains/Selection/`, a sibling of Restaurant, Personnel Management, Taxation and Administration. This reverses TASK_DOMAINS_002's consolidation for Selection specifically; Workforce, Training, Performance and Personnel Decisions remain Personnel Management modules, unaffected.

**Important factual correction to the request that triggered this task:** the request's premise was that Selection lived under `01 Domains/Restaurant/Selection/`. That was not accurate — Selection Core has never lived under Restaurant. Only Restaurant's own Industry Extension of Selection (role catalog, Rome's Flavours Server Role Configuration) lives at `01 Domains/Restaurant/Selection/`, and it already had zero structural dependency on Selection being its parent (the dependency already ran Restaurant → Selection, one of the two directions the Product Owner explicitly sanctioned). This was surfaced to the Product Owner before any file was moved; they confirmed the intended correction was specifically to elevate Selection out of Personnel Management, which this report documents.

No production database was touched. No code behavior changed (this is a documentation/domain-architecture move only) beyond path references in code comments/docstrings.

---

## B. What moved

| | Old location | New location |
|---|---|---|
| Selection Core (Selection.md, SelectionRequirement.md, CandidateEvidence.md, FitAssessment.md, SelectionDecision.md, TrainableGap.md, ResumeScreening/) | `01 Domains/Personnel Management/Selection/` | `01 Domains/Selection/` |
| Restaurant Industry Extension of Selection | `01 Domains/Restaurant/Selection/` | **Unmoved** — already the correct location per the sanctioned "Restaurant → Selection" dependency direction; only its internal path references and header were updated |

Moved with `git mv` to preserve file history.

---

## C. Dependency direction confirmed

- Selection Core (`01 Domains/Selection/`) has **zero** structural dependency on Restaurant, Personnel Management, or any other Domain. It is now literally a top-level sibling.
- Restaurant's Industry Extension (`01 Domains/Restaurant/Selection/`) depends on and extends Selection Core — the sanctioned "Restaurant → Selection capability/configuration" direction. Selection Core has no knowledge of this folder's existence.
- Personnel Management's Personnel Decisions module consumes Selection's output (credible alternatives for a role) without owning it — documented explicitly in both `Selection/README.md` and `Personnel Management/README.md`.

---

## D. Canonical Domain taxonomy after this task

```text
01 Domains/
├── Restaurant/              Domain
│   ├── Purchasing/            module
│   ├── Sales/                 module
│   └── Selection/             Restaurant Industry Extension of the Selection Domain (not a module of Restaurant)
├── Selection/                Domain (top-level, transversal — re-elevated by this task)
│   └── ResumeScreening/        Resume Screening capability
├── Personnel Management/    Domain
│   ├── Workforce/              module (placeholder)
│   ├── Training/                module (placeholder)
│   ├── Performance/            module (documented)
│   └── Personnel Decisions/    module (placeholder)
├── Taxation/                 Domain
├── Administration/           Domain
└── _Shared/                  shared knowledge, not itself a Domain
```

---

## E. Files moved

- `01 Domains/Personnel Management/Selection/` → `01 Domains/Selection/` (git mv; 14 files including `ResumeScreening/`)

## F. Files created

- This report.

## G. Files modified (references corrected)

**Within the moved Selection tree** (relative-path depth fixes: 3-deep-under-`01 Domains` → 2-deep; sibling-module references to Personnel Management's remaining modules updated to the new relative path; "module of Personnel Management" framing rewritten as "top-level Domain" throughout):
- `01 Domains/Selection/README.md`, `Selection.md`, `SelectionDecision.md`, `SelectionRequirement.md`, `CandidateEvidence.md`, `FitAssessment.md`, `TrainableGap.md`
- `01 Domains/Selection/ResumeScreening/README.md`, `CandidateCVProfile.md`, `EvidenceModel.md`, `ExperienceAndTrajectory.md`, `FlagsAndIndicators.md`, `RoleModel.md` (header `Module:` field corrected to reflect Selection as a top-level Domain; internal relative links to `../README.md` etc. were unaffected since the whole subtree moved together)

**Elsewhere in `01 Domains/`:**
- `01 Domains/README.md` — added Selection to the Current Domains table; corrected Personnel Management's module list
- `01 Domains/Domain Architecture.md` — §4 tree diagram, §5 intro/§5.6, §9 item 5, and all `Personnel Management/Selection/` path references corrected
- `01 Domains/Personnel Management/README.md` — module map, relationship diagrams, documentation-status section, and related-documents links corrected; explicit note added pointing to the new Selection Domain location
- `01 Domains/Restaurant/Selection/README.md` — header and body path references corrected; explicit note added that this folder depends on Selection Core, never the reverse
- `01 Domains/Restaurant/Roadmap.md` — "Workforce / Personnel" business-capability entry corrected
- `01 Domains/Restaurant/Server Performance/README.md` — one cross-reference corrected
- `01 Domains/Taxation/TaxEvidence.md` — one cross-reference corrected
- `01 Domains/Administration/Payroll/Labor Cost.md` — one cross-reference corrected

**`03 Software/` (path references in comments/docstrings only — no functional code change):**
- `03 Software/Selection/README.md`
- `03 Software/RF-One Data Store/rfone_data_store/models.py`, `selection/__init__.py`, `selection/analysis.py`, `selection/core/{profile,resume_source,role_model,trajectory,flags,experience_analysis,indicators,information_quality}.py`

**Repository governance:**
- `CLAUDE.md` (both the root `AI-RF-ONE/CLAUDE.md` and `RF One/CLAUDE.md` copies) — Selection added to the canonical top-level Domain list; removed from the "modules of Personnel Management" list; a new paragraph states the dependency-direction rule explicitly
- `PROJECT_STATE.md` — new entry documenting this move

## H. Files intentionally NOT modified

- `07 Tasks/Reports/*.md` (other than this new report) — historical record of what was true when each task ran; not rewritten.
- `90 Archive/` — never current authority, not touched.
- `03 Software/Selection/app.py` and templates — no functional/routing change; the app's Flask routes (`/`, `/upload`, `/candidate/<id>`) are unaffected by this documentation-only domain move, per the instruction not to break working URLs unnecessarily.

---

## I. Tests / consistency checks performed

- Repository-wide grep for `Personnel Management/Selection` (all path variants) across `01 Domains/`, `03 Software/` (`.py`/`.md`) — zero remaining matches after this task.
- Selection engine validation suite (`test_selection_engine.py`) re-run after all code-comment path corrections: unaffected (comment-only changes), still passing.
- No functional code changed by this task; no schema/migration change; no test suite specific to domain-documentation structure exists, so verification was by systematic grep + manual review of every match.

---

## J. Unresolved / open items

- No formal `07 Tasks/TASK_DOMAINS_003_...md` task spec file was created before this report (the Product Owner's chat instruction was treated as the spec, consistent with how corrective/governance work has been handled before — e.g. TASK_REPOSITORY_STABILIZATION_001). If the Product Owner wants a separate spec file for traceability, that can be added.
- `01 Domains/Domain Architecture.md` §9 item 1 ("Sequencing") still describes the historical sequencing question in terms of Selection "now sitting inside Personnel Management" — left as an accurate historical statement about the TASK_DOMAINS_002 state of affairs at the time that question was written, not corrected to present tense, since open questions in that section are a record of when they were raised.
