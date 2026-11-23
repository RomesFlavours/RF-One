# Independent review guide: integration/live-2026-11-20

For Codex (or any reviewer) before this branch is merged into `main`. Nothing here asks you to deploy, migrate or change AWS. Please review read-only and report findings.

## What this branch is

One tree that reproduces every live AWS service as of 23 Nov 2026, 15:00 UTC. Base: `main` at 9c154f9 (21 Oct).

| Live service | Image or task | Built from |
|---|---|---|
| rfone-web (App Runner) | rfone-web:wines-20261123-31ec638a6744 | release/registry-web-20261121 (7580fa2) + codex/wines-20261123 (31ec638) |
| rfone-training | rfone-web:training-welcome-def9cb4 | snapshot branch |
| rfone-kitchen | rfone-web:kitchen-local-20261116t151940z | snapshot branch |
| rfone-tips | rfone-tips:tip-role-history-20261118c-tips | snapshot branch |
| rfone-selection | rfone-selection:sel-40b9877 | snapshot branch |
| rfone-email-service (ECS) | rfone-web:email-7291a4ac8419 | snapshot branch |
| rfone-clover-correction-sync (ECS) | rfone-tips@sha256:8ba25ab6... (registry-clover-departments-20261121b-jobs) | release/registry-clover-jobs-20261121 (7b5d35c) |
| rfone-clover-acquisition-job (ECS task :12) | rfone-tips@sha256:970c0fe6... (tip-role-history-20261118d-jobs) | live image, checked 21 Nov |
| Course test sites | rfone-selection-ai-test trainer images | snapshot branches |

Database: rfone-dev at `a1c220261121` (see `RF-One Data Store/migrations/aws_applied_revision.json`).

## Commits to review

- `6633f05` the combined tree (20 Nov).
- `a6f01d7` purchasing/repository.py back to the live web/tips version (the Kitchen version wrote columns the live DB does not have).
- `8c2b130` to `74e2ce4`: Pino's 20 Nov night releases folded in (cherry-picks of c335bc9, 7580fa2, fe7e1a6, d344165, and the manifest part of 7b5d35c). The a1c220261121 migration file stays in this tree because the full chain here contains e9a120261117.
- `4f70471` applied revision record a1c220261121 (from 10e290f).
- `8560a99` Clover worker manifest: fingerprints of this tree's models.py and acquisition.py, so a worker built from this tree passes `clover_connector_release_check.py`.
- `83386c2` test_shared_schema_compatibility.py expects head a1c220261121.

## Where the decisions are recorded

In this folder:
- `merge-report.json`, `final27.json`, `recheck.json`: the 85 shared files that differed between live services and the version kept for each, with the reason.
- `equivalence.json`: for every live service, every file it runs compared with this tree.
- `verify-later.txt`: open points and fixes.
- `FOLD-2026-11-21.md`: the 20 Nov night release and the eight Web/Clover worker differences.
- `FOLD-2026-11-23.md`: the 23 Nov Wines release.

## What was already verified (please challenge it)

1. File equivalence: every file of every live service is in this tree. Every difference is a recorded decision.
2. Runtime: each service was built from this tree on top of its live image and run against a private copy of the live database (deleted afterwards), with email, Clover, AI and texting disabled. Web 64, Training 23, Kitchen 10, Tips 17 pages: same status and redirects as live. Content differences: CSRF tokens, the `data-how-works` key, the help panel on the legacy trainer pages, and "Vegetable Festival" with 2 images on /training/menu. The email worker and Clover worker compile and import.
3. Database: the copy was at a1c220261121, the tree head. No migration is needed to release from this tree. `check_migration_chain.py` passes.
4. Tests: every test file run on this tree and on main, each with a throwaway SQLite DB and no AWS. Failures on this tree that pass on main fail the same way on the live code, or only look for older Italian wording or older menu data. Details in the report Shelbi sent with this guide.

## What we would most like a second opinion on

1. `RF-One Data Store/rfone_data_store/models.py`: the tree keeps `restaurant_id` nullable on 17 tables (web/email version); Tips and the Clover workers declare it NOT NULL. Behaviour on the live DB is the same either way, but which one should be canonical?
2. `RF-One Web/training_integration.py`: hand merge; denial messages use the English wording from the live Training service.
3. The 16 hand merges listed in `merge-report.json`, especially the Clover connector files and Training auth/routes.
4. The Clover worker manifest (`clover_connector_release.json`) now carries this tree's fingerprints for models.py and acquisition.py.

## Known issues that were already there (not caused by the merge)

1. A brand-new database cannot be built: k9a020261110 creates the Kitchen tables from current models, then k9g120261112 adds the same columns again (DuplicateColumn on Postgres too). Proposed: k9g adds each column only if missing.
2. `selection_candidate_accounts` exists in the live DB but no migration creates it.
3. Several tests pin an old head (for example test_projects_service.py, test_interviews.py).
