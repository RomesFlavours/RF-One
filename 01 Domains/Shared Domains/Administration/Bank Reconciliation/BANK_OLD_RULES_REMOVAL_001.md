# Bank — removal of the old (non-AI) rule system's residues (BANK_OLD_RULES_REMOVAL_001)

**Task:** BANK_OLD_RULES_REMOVAL_001 (Product Owner decision, 2026-10-13 — local cleanup only, AWS untouched)
**Status:** done locally on `feature/bank-simple-who-rules` (not committed), 2026-10-14: Phase 1 (code) and Phase 2
(21 files deleted, models, `dbtools.py`, migration `d2b6f8a4c0e7` applied to the live database after a trial on a copy
and a backup). Working record, evidence and backup: `07 Tasks/Reports/BANK_OLD_RULES_REMOVAL_001/README.md`.
**Builds on:** `BANK_RULES_RESET_001.md` (2026-10-12: classification only through AI Rules and by a person).
**Schema:** migration `d2b6f8a4c0e7` (revises `a3c7e5b9d1f4`) drops the seven tables, the three columns pointing at
them and `bank_occurrences.manual_only`; it refuses while any of them holds data (the untouched General Rule seeded by
`f4a8c2d6e9b3` on a fresh database is removed first).

---

## Why

BANK_RULES_RESET_001 stopped every page, route and import step of the old rule system, but left its code as
"libraries" and its seven tables in place (empty). This task removes what is left, keeps every function the current
Bank still needs, and preserves all data.

## Phase 1 — done (code edits, no file deleted, no data changed)

The product no longer imports any module of the old rule system, and no product code reads or writes its seven tables
or the three columns that point at them (`bank_transaction_explanations.recognition_rule_id`,
`bank_transaction_explanations.reconciliation_standard_id`, `bank_transaction_allocations.reconciliation_standard_id`).
On the live database every one of those columns is NULL, no row has the destination source `STANDARD` and the seven
tables are empty, so every removed branch was unreachable: behaviour is unchanged.

| Area | Change |
|---|---|
| `ai_rules` | `own_account_ids` now lives here (matched internal transfers); `general_rules._own_account_ids` is no longer used. Standard provenance of For Whom, the Standard protections and the "current WHO written by WHO rule #n" overlap removed. The text sent to the AI and the option label are **unchanged** (see Open questions). |
| `ai_rule_operations` | No longer carries `recognition_rule_id` into new decisions. |
| `recognition` | Only the decision writer remains (`_create_decision_row`, `record_human_decision`, `reclassify_transaction`, snapshots) plus the text normalization. Removed: rule matching, the automatic proposal at import (`deduce_for_transaction`, `redecide_for_transaction`, `_propose`), the structural WHY call (`purpose_reason_for`), learning (`create_or_reuse_rule`, `learn_description`, broaden / memo learning) and the demotion of contradicted rules. |
| `who_rules` | Reduced to the WHO lookups still used: `check_new_who`, `existing_identity`, `who_options` (and `_PURPOSE_FIELDS`). |
| `who_recognition` | Reduced to `who_key` and `CanonicalWhoResolver.by_identity` (without recognition rules). The structural recognizer and `recognize_transactions` (writer of `bank_who_recognitions`) removed. |
| `configuration`, Configuration > WHO | Recognition rules can no longer be created, edited or listed (column, modal editor, `RuleInput`, `save_who(rules=…)`). |
| `who_merge`, Configuration > WHO > Merge | A merge no longer moves rows of the old tables; the preview no longer counts them. |
| `row_reconciliation`, Review > Reconciled | Save as New Standard / Set as Standard removed from the service; the Standard info box, "standard" WHO source and Standard data removed from the page. |
| `reconciliation_status` | The AUTOMATIC branch (Standard lineage) removed; CONFIRMED / NEEDS REVIEW unchanged. |
| `economic_allocation` | `reconciliation_standard_id` and the STANDARD destination removed from allocations written from now on. |
| `review_queues`, `row_reconciliation` | Own-account movements are the matched internal transfers only (structural WHO recognitions retired). |
| `service` | `record_recognition_decision` no longer learns; outdated descriptions corrected. |
| Home | "Recognized by learned rule" counter removed (an automatic WHO now comes from an AI rule: "Other automatic"). |
| `bank_who_rule_routes` | The unused `GET /bank/who-rules/who/<id>` removed; `who-options` kept (the "new WHO" dialog uses it). |
| `rf-one.css` | 138 lines of styles of the Rules, WHO Rule, General Rules, Learning and WHO Classification pages removed. |
| Instructions page, comments | Text describing learned rules and the WHO Rule modal corrected. |
| `activate_reconciliation_control_start.py` | No longer counts `bank_who_recognitions`. |

**Defect fixed on the way:** the Reconciled row editor still referenced `edSaveStd`, the removed "Save as New
Standard" button, in its validation (`bank_reconciliation.html`), which raises a JavaScript `ReferenceError` in the
current version.

**Verified:** the live database is unchanged (per-table content fingerprint, read-only); on a copy of it, the plans of
the 8 active AI rules over the 3,234 movements (outcome, note, WHO / WHY after, overlaps, with and without "Crea WHO
mancanti") are identical with the previous code and with this one; every Bank page answers on a server started on a
copy of the database; the Bank test suite: after Phase 2, 82 of 83 scripts pass — the one failing,
`test_bank_historical_import.py`, needs a certified historical staging run (environment, failing before this task
too). Checks that only exercised removed features were removed from the kept tests, each noted in the docstring.

## Phase 2 — done (2026-10-14)

### 1. Files to delete

The final list — **21 files**, absolute paths, hashes and the check that no kept component imports them — is
`07 Tasks/Reports/BANK_OLD_RULES_REMOVAL_001/FILES_TO_DELETE.md`. All are preserved, byte-identical, in branch
`snapshot/bank-worktree-20261012`. `deterministic_rules.py`, on an earlier list, is **kept**: it holds the structural
WHY vocabulary the catalog seed (`seed_canonical_accounting_catalog.py`) installs.

### 2. Then, in one change

1. `models.py`: remove the seven classes (`BankRecognitionRule`, `BankWhoRecognition`, `BankReconciliationStandard`,
   `BankGeneralRule`, `BankWhyRule`, `BankPatternSuggestion`, `BankLearningRun`), the three columns,
   `DESTINATION_SOURCE_STANDARD` and `BankOccurrence.manual_only`.
2. Install the migration `d2b6f8a4c0e7` (revises `a3c7e5b9d1f4`): it refuses to run while any of the seven tables
   holds a row or any of the three columns holds a value; downgrade recreates them empty. It must first be
   extended to drop `bank_occurrences.manual_only` too (refusing while any WHO has it set). Historical migrations
   are not modified. The draft and the full resume procedure are in `07 Tasks/Reports/BANK_OLD_RULES_REMOVAL_001/`.
3. `Bank Local Environment/bank_local_env/dbtools.py`: remove `bank_recognition_rules`, `bank_general_rules` and
   `bank_reconciliation_standards` from `KEY_TABLES` (the tables compared by name between two databases).
4. Run the suite; back up the database; stop 5080, apply the migration, start 5080.

## Known incompatibility

**`03 Software/RF-One Data Store/migrate_bank_to_postgres.py` is NOT compatible with the current schema** (revision `d2b6f8a4c0e7`): its table lists still name `bank_who_recognitions` and `bank_recognition_rules`, which no longer exist. It must be updated before it is used again, and must not be run as it is. It was deliberately left unchanged (AWS transfer tooling, out of the scope of this local cleanup).

## Product Owner decisions (2026-10-14) — implemented

1. **Status "Automatic"** — removed (constant, Export figure, Review legend, row marks), not reused for AI rules.
   No transaction status changed: nothing could have it.
2. **Manual Only WHO** (`bank_occurrences.manual_only`) — it only kept a WHO out of the old WHO Rules and
   Classification Learning; neither the AI rules nor manual reconciliation ever read it. Removed from the WHO merge
   and from Configuration; the column is dropped in Phase 2.
3. **"Standard" in the interface** — removed from every label (the override option is now "Sostituisci anche WHO/WHY
   manuali o confermati") and from the protections listed in a Preview. The text sent to the AI is unchanged
   (`PROMPT_OVERRIDE_LABEL` keeps the former option name there); the proposed change and its effect — none on the
   37 saved interpretations — are in `07 Tasks/Reports/BANK_OLD_RULES_REMOVAL_001/AI_PROMPT_BEFORE_AFTER.md`, for
   approval.
