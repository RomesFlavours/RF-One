# PRE_COMMIT_AUDIT

**Type:** Read-only working-tree audit (no files modified, staged, committed or pushed)
**Scope:** `git status` / `git diff` / `git diff --stat` / `git diff --name-status` / `git log` / `git check-ignore` against the current working tree
**Date:** 2026-08-27

---

## A. Summary

```text
Total changed/new/deleted entries: 146
  Modified (M):                     13
  Deleted (D):                      14
  Added / new — untracked (??):    119
  Renamed (R):                       0  (git rename detection found none)
Staged (index) entries:              0  — nothing is staged; `git diff --cached` is empty
```

No files are staged. Everything below is unstaged working-tree state.

**Most important finding, ahead of the detail below:** during this same working session, a report file (`07 Tasks/Reports/TASK_LABOR_COST_001_REPORT.md`) and its source task spec (`07 Tasks/TASK_LABOR_COST_001_...md`) were confirmed written/read successfully, then found **absent from disk** minutes later when this audit began — with no git trace of their deletion (they were never tracked). At the same time, `07 Tasks/Reports/` is completely empty on disk even though git still tracks 6 report files there (now showing as `D`), and `07 Tasks/` top level is empty of task-spec files even though git tracks 7 of them there (also `D`). None of the missing files were moved to `90 Archive/` (the repo's documented archive location). This looks like an out-of-band filesystem event (not a git operation, not an action taken by this audit or the prior task), and is detailed in Section D.1.

---

## B. File list grouped by area

Status legend: `M` modified, `D` deleted (tracked, missing from working tree), `??` untracked/new.

### 00 Core (9 changed — 1 M-family set + 1 new file, cross-reference ripple)

| Status | Path | Why it changed (from diff) |
|---|---|---|
| ?? | `00 Core/ConceptualArchitecture/08_Net_Outcome_and_Structural_Optimization.md` | New Core document: Gross vs Net/Retained Outcome, External Obligations/Claims, Constraint Shaping, Counterfactual Structural Comparison, Lawful Optimization boundary. |
| M | `00 Core/ConceptualArchitecture/00_RF-One_Core_Vision.md` | Adds `08_...` to the doc index/table and a short body cross-reference. |
| M | `00 Core/ConceptualArchitecture/03_Decision_Action_Outcome_Learning.md` | Adds the Gross/Net Outcome distinction and a cross-reference to `08_...`. |
| M | `00 Core/ConceptualArchitecture/04_Temporal_Coherence_and_Evolution.md` | Adds a cross-reference noting obligation/structural rules are temporally/contextually situated. |
| M | `00 Core/ConceptualArchitecture/05_Epistemic_Boundary_and_Subject_Sovereignty.md` | Adds a sentence: legal/tax/regulatory interpretation is Belief/Inference, never silently Fact; cross-reference to `08_...` §7. |
| M | `00 Core/ConceptualArchitecture/07_Core_Glossary.md` | Adds 6 new glossary entries (Gross Outcome, Net/Retained Outcome, External Obligation/Claim, Constraint Shaping, Counterfactual Structural Comparison, Lawful Optimization) and extends the doc-range reference to `08_...`. |
| M | `00 Core/Core Evolution.md` | New dated entry: "Version: Core 2.0 (TASK_CORE_013)", 2026-08-26 — documents exactly the change set above. |
| M | `00 Core/README.md` | `ConceptualArchitecture/` row description extended to mention Net/Retained Outcome and Lawful Structural Optimization. |
| M | `00 Core/RF-ONE Core Principles.md` | Version bumped 6.0→6.1; adds **Principle 20** (Net/Retained Outcome, Constraint Shaping, lawful-vs-evasion boundary); intro paragraph updated. |

### 01 Domains (34 changed)

| Status | Path | Why it changed |
|---|---|---|
| M | `01 Domains/README.md` | Adds `Taxation/` and `Administration/` rows to the Current Domains table (Administration row also reflects this session's `Personnel Cost.md` work). |
| M | `01 Domains/Restaurant/README.md` | Adds a pointer to the new `Restaurant Semantic Model.md`; adds "Organization" and "Tips" to Current Modules. |
| M | `01 Domains/Restaurant/Roadmap.md` | Adds table rows for Restaurant Organization (TASK_RESTAURANT_001/003), Restaurant Semantic Model (TASK_RESTAURANT_002), and Tips (TASK_TIPS_001/002). |
| M | `01 Domains/Restaurant/Model/OperationalArea.md` | Adds a "Note (TASK_RESTAURANT_001)" pointing to the new, distinct `Organization/Operational Area.md` / `Physical Area.md` concepts; body otherwise unchanged. |
| ?? | `01 Domains/Administration/README.md` | Administration Domain root — new (this session's TASK_LABOR_COST_001 edit of a file that already existed untracked from TASK_PAYROLL_001; module map now lists `Personnel Cost.md`). |
| ?? | `01 Domains/Administration/Personnel Cost.md` | **New this session** — canonical `Total Employee Cost` / `Unallocated Personnel Cost` / `Total Personnel Cost` model (TASK_LABOR_COST_001). |
| ?? | `01 Domains/Administration/Payroll/README.md` | Payroll module root (TASK_PAYROLL_001); file table/related-docs edited this session to point at `Personnel Cost.md`. |
| ?? | `01 Domains/Administration/Payroll/Labor Cost.md` | `Payroll Employer Cost` (TASK_PAYROLL_001); "Fully Loaded Labor Cost" section rewritten this session as a legacy synonym for `Total Employee Cost` (TASK_LABOR_COST_001). |
| ?? | `01 Domains/Administration/Payroll/Compensation Terms.md` | TASK_PAYROLL_001 — Employee-specific temporal compensation. |
| ?? | `01 Domains/Administration/Payroll/Payroll Processing.md` | TASK_PAYROLL_001 — PayrollRun, Bonus/Tips/jurisdiction boundaries. |
| ?? | `01 Domains/Administration/Payroll/Payroll Provider Result.md` | TASK_PAYROLL_001 — ADP provider-result semantics. |
| ?? | `01 Domains/Administration/Payroll/Payroll Schedule and Period.md` | TASK_PAYROLL_001 — schedule/period/workweek concepts. |
| ?? | `01 Domains/Restaurant/Restaurant Semantic Model.md` | TASK_RESTAURANT_002 — canonical, configuration-independent Restaurant Domain semantics. |
| ?? | `01 Domains/Restaurant/Sales/Restaurant%20Sales%20Model.md` | Sales-side canonical model — **filename itself is malformed**, see Section D.2. |
| ?? | `01 Domains/Restaurant/Organization/README.md` | TASK_RESTAURANT_001 — Organization module root. |
| ?? | `01 Domains/Restaurant/Organization/Restaurant Profile.md` | TASK_RESTAURANT_001/003 — Restaurant identity ↔ Location, profile bootstrap. |
| ?? | `01 Domains/Restaurant/Organization/Operational Area.md` | TASK_RESTAURANT_001 — functional grouping (FOH/BOH/BAR/MANAGEMENT), distinct from Physical Area. |
| ?? | `01 Domains/Restaurant/Organization/Physical Area.md` | TASK_RESTAURANT_001 — physical place concept, distinct from Operational Area. |
| ?? | `01 Domains/Restaurant/Organization/Restaurant Role.md` | TASK_RESTAURANT_001 — Restaurant Role distinct from Clover SourceRole/systemRole. |
| ?? | `01 Domains/Restaurant/Organization/Employee Assignment.md` | TASK_RESTAURANT_001 — temporal Employee↔Area↔Role assignment; Tips/Payroll resolution contract. |
| ?? | `01 Domains/Restaurant/Tips/README.md` | TASK_TIPS_001/002 — Tips module root. |
| ?? | `01 Domains/Restaurant/Tips/Tip.md` | TASK_TIPS_001 — Tip as observable Payment-attached fact. |
| ?? | `01 Domains/Restaurant/Tips/Tip Policy.md` | TASK_TIPS_001/002 — Tip Policy/Component model. |
| ?? | `01 Domains/Restaurant/Tips/Tip Allocation.md` | TASK_TIPS_002 — post-hoc allocation semantics. |
| ?? | `01 Domains/Taxation/README.md` | Taxation Domain root — transversal Domain, referenced by the new Core `08_...` doc and by `01 Domains/README.md`'s updated table. **No corresponding task spec/report found anywhere (active or archived)** — see Section D.3. |
| ?? | `01 Domains/Taxation/Taxation.md` | Taxation core concept. |
| ?? | `01 Domains/Taxation/TaxObligation.md` | Taxation sub-concept. |
| ?? | `01 Domains/Taxation/TaxPosition.md` | Taxation sub-concept. |
| ?? | `01 Domains/Taxation/TaxTreatment.md` | Taxation sub-concept. |
| ?? | `01 Domains/Taxation/TaxImpact.md` | Taxation sub-concept. |
| ?? | `01 Domains/Taxation/TaxEvidence.md` | Taxation sub-concept. |
| ?? | `01 Domains/Taxation/TaxJurisdiction.md` | Taxation sub-concept. |
| ?? | `01 Domains/Taxation/TaxScenario.md` | Taxation sub-concept. |
| ?? | `01 Domains/Taxation/TaxStrategy.md` | Taxation sub-concept. |

### 03 Software (87 changed — all untracked, none modified/deleted)

All 87 entries are `??` (new). Grouped by subfolder rather than repeated per-file, since each subfolder is one cohesive deliverable:

| Status | Path group | Count | Why it changed |
|---|---|---|---|
| ?? | `03 Software/Clover Data Explorer/*.md` (7 files: `README`, `CLOVER_DATA_CAPABILITY_MATRIX`, `CLOVER_DATA_DISCOVERY`, `CLOVER_EXPORT_MAPPING`, `CLOVER_EXPORT_RECONCILIATION`, `CLOVER_RESTAURANT_DATA_MAPPING`, `CLOVER_SOURCE_RELATIONSHIP_MAP`, `CLOVER_ATOMIC_DERIVED_FACTS`) | 8 | TASK_CLOVER_001 — Clover API discovery/mapping/reconciliation documentation. |
| ?? | `03 Software/Clover Data Explorer/clover_explorer/*.py` (client, config, discovery, export_*, orchestrator, pagination, raw_store, api_cache, time_money, `__init__`) | 13 | TASK_CLOVER_001 — the read-only Clover data exporter package itself. |
| ?? | `03 Software/Clover Data Explorer/*.py` (top-level scripts: `run_export.py`, `check_connection.py`, `build_dashboard_exports.py`, `compare_dashboard_exports.py`, `fetch_profile_bootstrap_snapshot.py`) + `requirements.txt` | 6 | TASK_CLOVER_001 — CLI entry points and dependency pin. |
| ?? | `03 Software/RF-One Data Store/*.md` (`README`, `DATABASE_SCHEMA`, `CLOVER_INGESTION`, `CLOVER_INGESTION_RECONCILIATION`, `RESTAURANT_PROFILE`, `PAYROLL`) | 6 | TASK_DATABASE_001/002/TASK_RESTAURANT_00x/TASK_PAYROLL_001 — Runtime schema and module documentation. |
| ?? | `03 Software/RF-One Data Store/rfone_data_store/*.py` (top-level: `database.py`, `models.py`, `schema_validation.py`, `profile_validation.py`, `tips_validation.py`, `payroll_validation.py`, `__init__.py`) | 7 | Core ORM models and per-module validation suites (Database/Restaurant Profile/Tips/Payroll tasks). |
| ?? | `03 Software/RF-One Data Store/rfone_data_store/ingestion/**/*.py` (common + `clover/` reader, parser, mapping, ingest, enrichment, reconciliation, `__init__` ×2) | 8 | TASK_DATABASE_002/003/004 — Clover ingestion pipeline into RF-One Data Store. |
| ?? | `03 Software/RF-One Data Store/rfone_data_store/profile/*.py` (`bootstrap.py`, `source_snapshot.py`, `__init__.py`) | 3 | TASK_RESTAURANT_003 — Restaurant Profile bootstrap from Clover configuration. |
| ?? | `03 Software/RF-One Data Store/rfone_data_store/tips/*.py` (`engine.py`, `resolvers.py`, `rounding.py`, `__init__.py`) | 4 | TASK_TIPS_001/002 — Tip calculation engine. |
| ?? | `03 Software/RF-One Data Store/rfone_data_store/payroll/*.py` (`schedule.py`, `compensation.py`, `labor_cost.py`, `adp_importer.py`, `__init__.py`) | 5 | TASK_PAYROLL_001 — Payroll schedule/compensation/labor-cost/ADP-import logic. |
| ?? | `03 Software/RF-One Data Store/{create_database,bootstrap_restaurant_profile,ingest_clover,enrich_clover_cache,calculate_tips,import_payroll_results,inspect_database,validate_ingestion,validate_tips_readiness}.py` | 9 | CLI entry points for the above modules. |
| ?? | `03 Software/RF-One Data Store/test_{payroll_engine,restaurant_profile_bootstrap,tips_engine}.py` | 3 | Synthetic test suites for Payroll/Restaurant Profile/Tips (referenced by the corresponding task reports). |
| ?? | `03 Software/RF-One Data Store/migrations/**` (`env.py`, `script.py.mako`, `README`, 6 versioned migration files under `versions/`) | 9 | Alembic migration history: baseline schema, source roles, restaurant profile areas/roles, restaurant profile bootstrap, tip policy, payroll schema. |
| ?? | `03 Software/RF-One Data Store/{alembic.ini,requirements.txt,data/.gitkeep}` | 3 | Alembic config (template `driver://user:pass@localhost/dbname` only, not a real connection string — verified), dependency pin, empty-directory placeholder. |

### 07 Tasks (14 changed — all Deleted, none new/modified)

| Status | Path | Why it's flagged (no archival trace) |
|---|---|---|
| D | `07 Tasks/README.md` | Tracked in HEAD; absent from working tree; not present under `90 Archive/`. |
| D | `07 Tasks/Reports/TASK_CORE_011_REPORT.md` | Same. |
| D | `07 Tasks/Reports/TASK_CORE_012_REPORT.md` | Same. |
| D | `07 Tasks/Reports/TASK_DOMAINS_001_REPORT.md` | Same. |
| D | `07 Tasks/Reports/TASK_DOMAINS_002_REPORT.md` | Same. |
| D | `07 Tasks/Reports/TASK_PERSONNEL_001_REPORT.md` | Same. |
| D | `07 Tasks/Reports/TASK_SELECTION_002_REPORT.md` | Same. |
| D | `07 Tasks/TASK_CLOVER_001_Build_Read_Only_Clover_Data_Exporter.md` | Same. |
| D | `07 Tasks/TASK_CORE_011_Completed_Task_History_Archive_Cleanup.md` | Same. |
| D | `07 Tasks/TASK_CORE_012_Pre_Commit_Congruity_and_Consistency_Review.md` | Same. |
| D | `07 Tasks/TASK_DOMAINS_001_Document_Cross_Domain_Architecture_Conclusions.md` | Same. |
| D | `07 Tasks/TASK_DOMAINS_002_Canonicalize_Personnel_Management_and_Move_Selection.md` | Same. |
| D | `07 Tasks/TASK_PERSONNEL_001_Model_Performance_Module.md` | Same. |
| D | `07 Tasks/TASK_SELECTION_002_Create_Canonical_Selection_Domain_Foundation.md` | Same. |

`07 Tasks/Backlog/LEGACY_KNOWLEDGE_RECONCILIATION_BACKLOG.md` remains tracked and unmodified (not in the diff). `07 Tasks/Reports/` is otherwise empty on disk — see Section D.1 for why several additional, never-tracked files (including this session's own `TASK_LABOR_COST_001_REPORT.md`) are also missing without appearing anywhere in this table.

### Root

| Status | Path | Why it changed |
|---|---|---|
| M | `.gitignore` | Extended from 3 lines to 24: adds ignore rules for Clover raw/reference/generated export data, RF-One Data Store `.db`/`.sqlite`/`.bak`/ingestion-result files, and Payroll provider export files (`PayrollDetail*.xlsx`, `*.xlsb`, `data/payroll_imports/`). |
| ?? | `OpenQuestions.md` | New (never previously committed). Root open-questions log; this session moved its one entry ("Unallocated Labor Cost" allocation question) to a `Resolved` section per TASK_LABOR_COST_001. |

---

## C. Expected changes

Grouped by the task each change set is clearly traceable to:

| Task (as evidenced by content) | Files |
|---|---|
| **TASK_CORE_013** (Net/Retained Outcome, Core 2.0) | All 9 `00 Core/` entries in Section B. |
| **TASK_PAYROLL_001** (Payroll data model, ADP import, Labor Cost) | `01 Domains/Administration/README.md`, `Payroll/*.md` (5 files); `03 Software/RF-One Data Store/rfone_data_store/payroll/*.py`, `payroll_validation.py`, `import_payroll_results.py`, `test_payroll_engine.py`, `PAYROLL.md`, migration `47b3d9bb8108_add_payroll_schema.py`. |
| **TASK_LABOR_COST_001** (this session — Employee/Personnel Cost semantics) | `01 Domains/Administration/Personnel Cost.md` (new); edits inside `Payroll/Labor Cost.md`, `Payroll/README.md`, `Administration/README.md`, `01 Domains/README.md`; `OpenQuestions.md` (resolution). |
| **TASK_RESTAURANT_001 / 002 / 003** (Restaurant Organization, Semantic Model, Profile bootstrap) | `01 Domains/Restaurant/Organization/*.md` (6 files), `Restaurant Semantic Model.md`, `01 Domains/Restaurant/Model/OperationalArea.md` (M), `01 Domains/Restaurant/README.md` (M), `Roadmap.md` (M); `03 Software/RF-One Data Store/rfone_data_store/profile/*.py`, `bootstrap_restaurant_profile.py`, `test_restaurant_profile_bootstrap.py`, `RESTAURANT_PROFILE.md`, `profile_validation.py`, migrations `2ae7e5a3d715_...`, `e6df7aa7d83b_...`, `9516f3bd1495_...`, `7afe7c953207_...`. |
| **TASK_TIPS_001 / 002** (Tip allocation model and engine) | `01 Domains/Restaurant/Tips/*.md` (4 files); `03 Software/RF-One Data Store/rfone_data_store/tips/*.py`, `tips_validation.py`, `calculate_tips.py`, `test_tips_engine.py`, `validate_tips_readiness.py`, migration `dc31a1741fd8_add_tip_policy_and_calculation_schema.py`. |
| **TASK_CLOVER_001 / TASK_DATABASE_001–004** (Clover Data Explorer + RF-One Data Store + ingestion) | All of `03 Software/Clover Data Explorer/` (28 files); `03 Software/RF-One Data Store/{README,DATABASE_SCHEMA,CLOVER_INGESTION,CLOVER_INGESTION_RECONCILIATION}.md`, `rfone_data_store/ingestion/**`, `create_database.py`, `ingest_clover.py`, `enrich_clover_cache.py`, `inspect_database.py`, `validate_ingestion.py`, `alembic.ini`, `requirements.txt`, `data/.gitkeep`, `migrations/env.py`, `migrations/script.py.mako`, `migrations/README`. |
| **Restaurant Sales Model** (unconfirmed task id) | `01 Domains/Restaurant/Sales/Restaurant%20Sales%20Model.md` — content is a plausible Sales-side canonical model referenced by other approved docs, but the filename defect (Section D.2) and missing task provenance mean it should be confirmed, not assumed. |
| **Taxation Domain** (unconfirmed task id) | `01 Domains/Taxation/*.md` (9 files) — see Section D.3; content is internally coherent and consistent with the new Core `08_Net_Outcome_and_Structural_Optimization.md`, but no `07 Tasks/` spec or report for it exists anywhere in the working tree or in `90 Archive/`. |

---

## D. Suspicious / unexpected changes

### D.1 — `07 Tasks/` mass disappearance (HIGH PRIORITY — investigate before any commit)

- `07 Tasks/Reports/` and `07 Tasks/` (top level) are **completely empty on disk** except for the untouched `Backlog/` subfolder.
- Git still tracks 14 files there from prior commits (`7bab2a8`, `6f46529`); their absence shows as `D` in `git status` (Section B).
- None of these 14 files were moved to `90 Archive/Task History/` — that folder currently contains only the outputs of the earlier `TASK_CORE_011` archival (`TASK_CORE_001`–`010` and their reports), which is the repo's own documented precedent for how completed task history should be retired (move, never delete — `TASK_CORE_011_REPORT.md`'s own content, retrieved via `git show HEAD:...`, states "Nothing was deleted").
- Beyond the 14 tracked deletions, **additional files that were never committed are also gone without any git trace**: this session's own `07 Tasks/TASK_LABOR_COST_001_Formalize_Employee_Cost_and_Personnel_Cost_Semantics.md` (read successfully at the start of the prior turn) and `07 Tasks/Reports/TASK_LABOR_COST_001_REPORT.md` (written successfully at the end of the prior turn) are both absent now. Since they were never tracked, git shows nothing for them — they simply vanished from the filesystem.
- This pattern (an entire directory's contents removed, spanning both tracked and untracked files, with none archived) is not consistent with any task's documented behavior and did not happen through this audit (which made no writes). It suggests an out-of-band filesystem event — a sync conflict/rollback (the repo lives under OneDrive), an external cleanup process, or another concurrent session/tool — rather than a deliberate, documented repository operation.
- **Recommendation:** do not commit the 14 `D` entries as deletions. Investigate the cause (check OneDrive sync/version history for `07 Tasks/`) before deciding whether to restore (`git checkout -- "07 Tasks/..."` would restore the 14 tracked files from `HEAD`) or to perform a real, documented archive-and-delete task. The untracked losses (this session's Labor Cost task spec/report) cannot be recovered from git and would need to be re-created from conversation history if still needed.

### D.2 — Malformed filename: literal `%20` instead of spaces

`01 Domains/Restaurant/Sales/Restaurant%20Sales%20Model.md` is the actual on-disk filename — it contains the literal three characters `%`, `2`, `0` in place of spaces, unlike every other file in the repository (which use real spaces, e.g. `Restaurant Semantic Model.md`). Evidence this is a defect, not intentional:
- `01 Domains/Restaurant/Organization/Physical Area.md` and `03 Software/Clover Data Explorer/CLOVER_RESTAURANT_DATA_MAPPING.md` both cite it in prose as `Restaurant Sales Model.md` (real spaces) — the name they expect.
- `01 Domains/Restaurant/Restaurant Semantic Model.md` links to it correctly only because Markdown link targets legitimately URL-encode spaces as `%20` — that one link happens to work, but only because encoding-in-a-URL and encoding-in-a-filename collided.
- `03 Software/RF-One Data Store/DATABASE_SCHEMA.md` already cites the broken form (`Restaurant%20Sales%20Model.md`) in plain prose, suggesting the defect has already propagated into at least one other document by copy-paste.

**Recommendation:** rename to `Restaurant Sales Model.md` (real spaces) before committing, and fix the one downstream citation that already copied the broken form. Not fixed by this audit per the "do not modify" instruction.

### D.3 — Taxation Domain: no task provenance found

`01 Domains/Taxation/` (9 files, listed in Section B) is untracked and reads as a complete, coherent transversal Domain — consistent with the new Core `08_Net_Outcome_and_Structural_Optimization.md` and with `01 Domains/README.md`'s updated Domains table. However, no `07 Tasks/TASK_TAXATION_*` spec or report exists anywhere in the current working tree, `90 Archive/`, or (per `git log`) any prior commit. Given Section D.1's finding that `07 Tasks/` content is disappearing out-of-band, this may simply be another casualty of the same event rather than a genuinely provenance-less Domain — but as it stands, it cannot be confirmed against an approved task specification.

**Recommendation:** confirm with the Product Owner whether a Taxation task was executed (and its spec/report lost per D.1) before treating this Domain as approved for commit.

### D.4 — Local data / generated / cache — verified correctly excluded (informational only)

Checked and confirmed **not** part of the diff and **correctly** matched by `.gitignore` (`git check-ignore -v`):
- `03 Software/RF-One Data Store/data/rfone.db` (14.3 MB), `rfone.staging.db` (13.9 MB), `rfone.db.bak`, `rfone.db.pre_payroll_migration.bak`, `last_ingestion_result.json` — real, populated local databases (per the Payroll task report: real Employee/payroll data). Correctly git-ignored; not staged; not untracked.
- `03 Software/Clover Data Explorer/data/` — ~76 MB / 3,905 files of raw/reference/generated Clover exports and an API response cache (order/payment/card-transaction JSON). Correctly git-ignored in full (confirmed via `git status --ignored`).
- `.env` (repo root) — correctly git-ignored; not untracked.

No database, spreadsheet export, API cache, or `.env` file appears anywhere in the 146 changed/new/deleted entries. No IDE files (`.vscode/`, `.idea/`), OS files (`Thumbs.db`, `.DS_Store`), or `__pycache__/`/`*.pyc` artifacts appear in the diff either.

### D.5 — Line-ending churn on every `M` file

Every `git diff` against a modified tracked file emitted `warning: ... LF will be replaced by CRLF the next time Git touches it` (all 13 `M` files). This is Git's autocrlf conversion on this Windows checkout, not a content problem — the diffs themselves show only real content additions, no whole-file rewrites from EOL churn. Flagged only so a future `git add` of these files is not mistaken for introducing EOL noise; no action needed for this audit.

### D.6 — Sensitive-data scan

Grepped `03 Software/` for hardcoded `api_key`/`secret`/`password`/`token`/`client_id`/`client_secret`-shaped literals: **no matches**. `clover_explorer/config.py` reads credentials only from environment variables / a local (git-ignored) `.env`, and explicitly documents that the token is never logged or written to output. `alembic.ini`'s `sqlalchemy.url` is the unmodified Alembic template placeholder (`driver://user:pass@localhost/dbname`), not a real connection string. No employee name, SSN, or payment reference was found in any of the 146 changed/new paths — the one file that historically discussed real values in detail (`TASK_PAYROLL_001_REPORT.md`) is itself among the files now missing per D.1, and was already written to explicitly exclude such values from its own text.

---

## E. Gitignore verification

`.gitignore`'s new rules (added by the `M` diff in Section B) were each verified with `git check-ignore -v` against the actual files present on disk:

| Rule | Verified against | Result |
|---|---|---|
| `03 Software/RF-One Data Store/data/*.db` | `rfone.db`, `rfone.staging.db` | Correctly ignored |
| `03 Software/RF-One Data Store/data/*.bak` | `rfone.db.bak`, `rfone.db.pre_payroll_migration.bak` | Correctly ignored |
| `03 Software/RF-One Data Store/data/last_ingestion_result.json` | present on disk | Correctly ignored |
| `03 Software/Clover Data Explorer/data/{raw,reference_exports,generated_exports}/` | ~3,900 files present on disk | Correctly ignored |
| `.env` | present at repo root | Correctly ignored |
| `**/PayrollDetail*.xlsx`, `**/*.xlsb` | none currently present inside the repo (the real ADP sample lives under the user's `Downloads/`, outside the repo, per the Payroll task's own report) | No matching file exists to test against; rule is in place proactively |

`03 Software/RF-One Data Store/data/.gitkeep` is correctly **not** ignored (it is the intentional placeholder keeping the otherwise-ignored `data/` directory present in git) and appears as untracked/new, which is expected and safe to add.

No locally-present sensitive file was found outside the ignore rules. One pre-existing, already-tracked spreadsheet unrelated to this diff, `03 Software/InvoiceIntake/data/PurchaseDocuments.xlsx`, was noticed while scanning for `.xlsx` files repo-wide; it is unmodified (not part of this diff) and was committed in an earlier, unrelated commit — noted here only for completeness, not a finding.

No gap was found: nothing currently on disk both (a) matches a category `.gitignore` intends to exclude and (b) is not already excluded.

---

## F. Diff risk classification

| Group | Files | Risk |
|---|---|---|
| `00 Core/` (Net Outcome, Core 2.0 / TASK_CORE_013) | 9 | **SAFE** |
| `.gitignore` | 1 | **SAFE** |
| `01 Domains/Administration/` (Payroll + Personnel Cost) | 8 | **SAFE** |
| `01 Domains/Restaurant/Organization/`, `Restaurant Semantic Model.md`, `Model/OperationalArea.md` (M), `Restaurant/README.md` (M), `Roadmap.md` (M) | 10 | **SAFE** |
| `01 Domains/Restaurant/Sales/Restaurant%20Sales%20Model.md` | 1 | **REVIEW** — content likely fine; filename defect (D.2) should be fixed first |
| `01 Domains/Restaurant/Tips/` | 4 | **SAFE** |
| `01 Domains/Taxation/` | 9 | **REVIEW** — content coherent but no confirmed task provenance (D.3) |
| `03 Software/Clover Data Explorer/` | 28 | **SAFE** |
| `03 Software/RF-One Data Store/` | 59 | **SAFE** |
| `OpenQuestions.md` | 1 | **SAFE** |
| `07 Tasks/` (14 `D` entries) | 14 | **DO NOT COMMIT** (as deletions) — see D.1 |

Totals: **SAFE 119** · **REVIEW 10** · **DO NOT COMMIT 14** (sums to 143; the 3 root/summary lines above double as category headers, not additional files — see Section B for the exhaustive per-file listing that these totals are drawn from).

---

## G. Recommended commit scope

**Include in the next commit** (119 SAFE files): all of `00 Core/`, `.gitignore`, `01 Domains/Administration/`, `01 Domains/Restaurant/Organization/` + `Restaurant Semantic Model.md` + the 4 Restaurant `M` files + `01 Domains/Restaurant/Tips/`, all of `03 Software/Clover Data Explorer/` and `03 Software/RF-One Data Store/`, and `OpenQuestions.md`.

**Hold for a quick fix, then include** (2 REVIEW files): `01 Domains/Restaurant/Sales/Restaurant%20Sales%20Model.md` (rename to remove the literal `%20`, fix the one already-copied bad citation in `DATABASE_SCHEMA.md`) — this is one file logically, listed once under REVIEW.

**Hold pending Product Owner confirmation** (9 REVIEW files): `01 Domains/Taxation/*` — confirm a real task authorized this Domain before committing it as canonical.

**Do not commit yet** (14 DO NOT COMMIT entries): the `07 Tasks/` deletions. Investigate Section D.1 first — either restore the 14 tracked files (`git checkout -- "07 Tasks/..."`) and keep them, or, if a genuine archive-cleanup task is intended, re-run it properly (move to `90 Archive/`, document it with its own task report, and only then let the deletions land in a commit).

---

## H. Suggested commit message

Applies once the `07 Tasks/` deletions (D.1) and the Taxation/filename REVIEW items (D.2, D.3) are resolved and only the SAFE scope from Section G is staged:

```text
Add Net/Retained Outcome Core extension, Administration/Payroll/Personnel Cost,
Restaurant Organization/Tips domains, and Clover/RF-One Data Store implementation

- Core 2.0 (TASK_CORE_013): Gross vs Net/Retained Outcome, External
  Obligations/Claims, Constraint Shaping, Counterfactual Structural
  Comparison, Lawful Optimization boundary (Principle 20).
- Administration Domain: Payroll (schedule, compensation terms, processing,
  ADP provider result, labor cost) and the canonical Personnel Cost model
  (Total Employee Cost / Unallocated Personnel Cost / Total Personnel Cost,
  causal attribution, no artificial overhead allocation).
- Restaurant Domain: Organization (Profile, Operational Area, Physical Area,
  Restaurant Role, temporal Employee Assignment), Restaurant Semantic Model,
  and Tips (Tip, Tip Policy, Tip Allocation).
- 03 Software: Clover Data Explorer (read-only export tooling) and RF-One
  Data Store (schema, migrations, Clover ingestion, Restaurant Profile
  bootstrap, Tips engine, Payroll/ADP import, validation suites).
- Resolve OpenQuestions.md's generic-personnel-overhead-allocation question.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
```

---

## Note on this report's own location

This report was written to `07 Tasks/Reports/PRE_COMMIT_AUDIT.md`, inside the same directory whose contents are the subject of Section D.1's main finding. If the underlying cause of D.1 is still active (e.g. a live sync process), this file could be at similar risk — worth confirming it is still present before relying on it.
