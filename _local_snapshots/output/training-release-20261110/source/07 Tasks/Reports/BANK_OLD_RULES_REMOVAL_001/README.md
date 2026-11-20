# BANK_OLD_RULES_REMOVAL_001 — working record and how to resume

Local cleanup of the old (non-AI) Bank rule system, worktree `rf-one-bank-simple-who-rules`
(branch `feature/bank-simple-who-rules`, uncommitted). AWS is out of scope and untouched.
Specification and the list of code changes: `01 Domains/Shared Domains/Administration/Bank Reconciliation/BANK_OLD_RULES_REMOVAL_001.md`.

**The local cleanup is complete (2026-10-14).** Phase 1 (code) and Phase 2 (deletion of the 21 files, models,
`dbtools.py`, migration `d2b6f8a4c0e7` applied to the live database) are done.

## State on 2026-10-14, after Phase 2

| Item | State |
|---|---|
| Live database | `03 Software/RF-One Data Store/data/rfone.db`, revision **`d2b6f8a4c0e7`**. The 262 kept tables are identical row by row (on their remaining columns) to the backup taken just before; the 7 old tables and the 4 old columns are gone. 3234 movements, 1646 decisions, 95 WHO, 98 WHY, 8 AI rules, 37 interpretations. |
| Backup before the migration | `03 Software/RF-One Data Store/data/rfone_backup_before_d2b6f8a4c0e7_20261014_064712.db` (SHA-256 `c2839215cde1a746ef12aac93d85110944d9e4074c37c6f8e6dfab63a2bc22c0`, identical to the live DB at that moment). To go back: stop 5080, copy it over `rfone.db`, and check out the code of branch `snapshot/bank-worktree-20261012` (or run the migration's downgrade). |
| Server 5080 | Stopped and restarted with "RF-One Local 5080" (`run.ps1 stop` / `start`): it now serves this code at revision `d2b6f8a4c0e7`. |
| AI rules | Plans of the 8 rules over 3234 movements identical to the original code on the original data (`evidence/ai_rule_plans_live_after_migration.json`). Prompt unchanged (`b3915c39b9e0e684`), `INTERPRETATION_VERSION` `structured-v7`; the 37 interpretations untouched. |
| Pending (Product Owner) | The AI prompt wording (`AI_PROMPT_BEFORE_AFTER.md`) stays suspended by decision. |

## Files here

| File | What |
|---|---|
| `FILES_TO_DELETE.md` | The final list of the 21 files to delete, absolute paths, hashes, the importer check, a PowerShell command. |
| `AI_PROMPT_BEFORE_AFTER.md` | The prompt paragraph that still names Standards: before / proposed after; effect on saved interpretations (none). |
| `d2b6f8a4c0e7_drop_old_bank_rule_system.py.draft.txt` | The 2026-10-13 draft, kept as history. Superseded by the installed `migrations/versions/d2b6f8a4c0e7_drop_old_bank_rule_system.py` (which also drops `manual_only` and removes the untouched seeded General Rule of a fresh database). |
| `evidence/db_fingerprint_2026-10-13_start.json`, `…_end.json` | Per-table row count and content hash of the live DB (read-only), before and after. |
| `evidence/ai_rule_plans_old_vs_new.json` | Plans of the 8 AI rules over 3234 movements, old code vs new code: identical (re-checked 2026-10-14). |
| `tools/fingerprint.py` | `python fingerprint.py <db> <out.json>` — read-only fingerprint. |
| `tools/plan_compare.py` | `python -I plan_compare.py "<Data Store dir>" <copy of the db> <out.json>` — run on a COPY. |
| `tools/delcheck.py` | Rebuilds the deletion list and checks that no kept file imports it. |
| `tools/cssunused.py` | Lists `rf-one.css` rules whose classes nothing uses. |
| `tools/migtest.py`, `tools/migschema.py` | The migration trial on a COPY: every kept table compared, integrity, downgrade / upgrade; schema objects before / after. |
| `evidence/migration_test_on_copy_2026-10-14.json`, `evidence/db_fingerprint_2026-10-14_after_migration.json` | The trial result and the live DB after the migration. |

## Test status (Bank suite, after Phase 2: 83 scripts)

82 pass. The one failing, `test_bank_historical_import.py`, needs a certified historical staging run (environment;
it failed before this task too). Checks removed from adapted tests are named in each test's docstring.

## Residues, deliberately left

- **`03 Software/RF-One Data Store/migrate_bank_to_postgres.py` is NOT compatible with the current schema** (revision `d2b6f8a4c0e7`): its table lists still name `bank_who_recognitions` and `bank_recognition_rules`, which no longer exist. It must be updated before it is used again, and must not be run as it is. It was deliberately left unchanged (AWS transfer tooling, out of the scope of this local cleanup).
- Orphan `.pyc` files of the deleted modules in the `__pycache__` folders (harmless).
- The route path `/bank/who-rules/who-options` keeps its historical name (only the WHO lookup remains behind it).
