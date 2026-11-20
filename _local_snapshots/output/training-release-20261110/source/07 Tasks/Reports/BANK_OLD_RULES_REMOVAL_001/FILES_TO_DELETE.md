# Files to delete — Phase 2 of BANK_OLD_RULES_REMOVAL_001 (final list, 21 files)

**Status (2026-10-14): DELETED.** With the Product Owner's explicit authorization, the 21 files were deleted after
their paths and SHA-256 prefixes were verified against the table below; their absence was then checked. Nothing else
was deleted (the orphan `.pyc` files were left).

Every file below is byte-identical in branch `snapshot/bank-worktree-20261012` (verified with `git hash-object`
against the snapshot blob), so each one can be restored with
`git checkout snapshot/bank-worktree-20261012 -- "<path relative to the worktree>"`.

| # | Absolute path | Bytes | SHA-256 (16) | Snapshot |
|---|---|---|---|---|
| 1 | `C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\rfone_data_store\bank_reconciliation\pattern_discovery.py` | 46853 | `687b81edac3cf83f` | identical |
| 2 | `C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\rfone_data_store\bank_reconciliation\why_rules.py` | 6886 | `0d54c0ef02fe2f7c` | identical |
| 3 | `C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\rfone_data_store\bank_reconciliation\general_rules.py` | 23990 | `60ca71fb89ae3e63` | identical |
| 4 | `C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\rfone_data_store\bank_reconciliation\receiver_candidates.py` | 28476 | `3e78619147f0a657` | identical |
| 5 | `C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\rfone_data_store\bank_reconciliation\structural_why.py` | 25554 | `171a9a119b736f4b` | identical |
| 6 | `C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\rfone_data_store\bank_reconciliation\purpose_evidence.py` | 20269 | `42feb237f446a026` | identical |
| 7 | `C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\rfone_data_store\bank_reconciliation\reconciliation_standards.py` | 12282 | `2e468d9a37b6f342` | identical |
| 8 | `C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\apply_deterministic_bank_classification.py` | 11897 | `9ca803cef7d2529e` | identical |
| 9 | `C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\apply_structural_why.py` | 4850 | `12d7195d19b33e8d` | identical |
| 10 | `C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\apply_who_recognition.py` | 4494 | `27d80404c8559571` | identical |
| 11 | `C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\analyze_bank_purpose_evidence.py` | 8580 | `4e5f52556c571379` | identical |
| 12 | `C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\analyze_historical_import.py` | 19090 | `9ebcf066bbb40e19` | identical |
| 13 | `C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\test_bank_deterministic_classification_who_safety.py` | 13172 | `2c83291aedd4dd97` | identical |
| 14 | `C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\test_bank_structural_why.py` | 14381 | `fa6452691c73a53a` | identical |
| 15 | `C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\test_bank_structural_why_baseline.py` | 16476 | `41439ebb00c8edbc` | identical |
| 16 | `C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\test_bank_who_recognition.py` | 16245 | `dcc90f60ad585078` | identical |
| 17 | `C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\test_bank_who_recognition_merge_safety.py` | 16312 | `ed4d07fc57e4325e` | identical |
| 18 | `C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\test_bank_recognition_expert_system.py` | 23504 | `ea8da8d7c9b1a395` | identical |
| 19 | `C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\test_bank_memo_purpose_classification.py` | 29656 | `c5053cc804ae5c92` | identical |
| 20 | `C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\test_bank_who_why_invariant.py` | 25249 | `03324147a64ee7f6` | identical |
| 21 | `C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Web\tests\test_bank_reconciliation_standards_http.py` | 38072 | `6d52607268ad00fe` | identical |

## Verification that nothing kept uses them

Every `.py`, `.html`, `.js`, `.ps1`, `.cmd`, `.json`, `.ini`, `.toml`, `.cfg` and `.txt` file under `03 Software`
except these 21 was searched for an import, `importlib`/`runpy`/`subprocess` use or a `.py` invocation naming any of
them (`tools/delcheck.py`). Result: **no kept component imports or runs them.** The only occurrences left are words
in the docstrings of two historical migrations (`b6e1c47a20f9`, `f6c2e8a4b1d7`), which are not modified.

Before this list was final, four kept tests still imported `receiver_candidates` and were changed (2026-10-14):
`test_bank_import_and_review_http.py`, `test_bank_reconciliation_page_http.py`, `test_bank_two_stage_review_http.py`
and `test_bank_what_pl_vocabulary.py` only used `receiver_candidates` to prove it was not called (guard removed,
the page checks kept).

## Kept on purpose

`rfone_data_store/bank_reconciliation/deterministic_rules.py` was on the earlier list of 22 and is **kept**: it holds
the structural WHY vocabulary (`seed_structural_reasons`, `structural_why_baseline`) that
`seed_canonical_accounting_catalog.py` uses to install the catalog. Its description-matching part is dead in the
product (still exercised by `test_bank_accounting_classification_semantics.py`) and can be trimmed later together
with that test.

## Command for the person deleting (PowerShell, from any folder)

```powershell
$files = @(
  'C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\rfone_data_store\bank_reconciliation\pattern_discovery.py',
  'C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\rfone_data_store\bank_reconciliation\why_rules.py',
  'C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\rfone_data_store\bank_reconciliation\general_rules.py',
  'C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\rfone_data_store\bank_reconciliation\receiver_candidates.py',
  'C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\rfone_data_store\bank_reconciliation\structural_why.py',
  'C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\rfone_data_store\bank_reconciliation\purpose_evidence.py',
  'C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\rfone_data_store\bank_reconciliation\reconciliation_standards.py',
  'C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\apply_deterministic_bank_classification.py',
  'C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\apply_structural_why.py',
  'C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\apply_who_recognition.py',
  'C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\analyze_bank_purpose_evidence.py',
  'C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\analyze_historical_import.py',
  'C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\test_bank_deterministic_classification_who_safety.py',
  'C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\test_bank_structural_why.py',
  'C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\test_bank_structural_why_baseline.py',
  'C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\test_bank_who_recognition.py',
  'C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\test_bank_who_recognition_merge_safety.py',
  'C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\test_bank_recognition_expert_system.py',
  'C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\test_bank_memo_purpose_classification.py',
  'C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Data Store\test_bank_who_why_invariant.py',
  'C:\Users\servi\OneDrive\AI-RF-ONE\rf-one-bank-simple-who-rules\03 Software\RF-One Web\tests\test_bank_reconciliation_standards_http.py'
)
$files | ForEach-Object { if (Test-Path -LiteralPath $_) { Remove-Item -LiteralPath $_ -Confirm:$false; "deleted $_" } else { "missing $_" } }
```

Afterwards, also remove the matching orphan `.pyc` files under the two `__pycache__` folders (item C5) if wanted;
they are regenerated or ignored by Python.
