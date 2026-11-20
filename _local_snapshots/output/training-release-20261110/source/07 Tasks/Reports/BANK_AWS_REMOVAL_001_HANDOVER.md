# BANK_AWS_REMOVAL_001 — Handover (Bank removed from AWS)

Read this before deploying anything to AWS, before merging this branch, and before running any migration on a
database that holds Bank data.

Product Owner decision (2026-10-14): Bank is removed from AWS as if it had never been published; every other Domain
keeps working with its data. The local Bank (the working environment on the PCs) must keep working; its cleanup is
done by a separate session and is **not** the same operation as the AWS removal.

## 1. State of AWS after the removal (2026-10-14, ~02:30 UTC)

| Component | State |
|---|---|
| RDS `rfone-dev` / DB `rfone` | Alembic revision **`84354dc654ce`** (single row in `alembic_version`). 224 tables; the 53 Bank tables and the 4 `BANK` rows of `rfone_account_domain_access` are gone |
| `rfone-web` | Built from this branch @ `617e867` (= live `0576ea1` minus Bank). `/bank*` → 404. No `RFONE_AI_PROVIDER` / `RFONE_BEDROCK_MODEL_ID` |
| `rfone-tips`, `rfone-selection` | **Not redeployed.** Their images still carry the Data Store with the Bank code, dormant (see §6, R1). `rfone-selection` cannot start a new instance against the current RDS revision (§6, R0) |
| IAM / network | Policy `rfone-web-bedrock-invoke-bank-ai-rules`, endpoint `vpce-0010040e932d4ab8f` (`bedrock-runtime`) and security group `sg-0e917f65f52ad30ad` deleted |
| Recovery points | RDS snapshot `rfone-dev-pre-bank-removal-20261014t021458z` (and every earlier snapshot); source backup `s3://rfone-tips-deploy-418674484214/backups/rfone-web-source-pre-bank-removal-20261014t021533z.zip` |

Details of what was dropped and why each table was judged Bank-only: `03 Software/Infrastructure/README.md`
§ "Bank rimosso da AWS" and the docstring of `migrations/versions/84354dc654ce_remove_bank.py`.

## 2. Migration chain

`84354dc654ce` (remove Bank, irreversible: `downgrade` refuses) → `7b1d4f9a2c6e` (merge of the Bank line
`a3c7e5b9d1f4` and main `e8c4a2f6b1d3`, BANK_AWS_001) → …

Heads per branch on 2026-10-14 (computed from the migration files):

| Branch / database | Head | Contains `7b1d4f9a2c6e` | Contains `84354dc654ce` |
|---|---|---|---|
| **RDS live** | `84354dc654ce` | yes | yes |
| `release/remove-bank-aws` (this branch) | `84354dc654ce` | yes | yes |
| `origin/main` @ `f63bf66` | `7b1d4f9a2c6e` | yes | **no** |
| local `main` @ `ec9c6c4` (diverged from `origin/main`) | `b6e4d2a8c1f9` | **no** | **no** |
| `feature/bank-simple-who-rules` @ `aca3c58` (local Bank line) | `b7f1c3e5a9d2` | **no** | **no** |
| Invoice Intake, uncommitted in `RF One/` | `b3f9d2c6e4a1`, `540ee75caa65` (hang off old revisions) | no | no |

Rule: **a branch may be deployed to AWS only if its migration chain contains `84354dc654ce`** and its single head
descends from it. Any new revision for AWS (Invoice Intake included) must have `84354dc654ce` — or a later revision
of this chain — as ancestor.

## 3. Risk of deploying from a branch that is not aligned

`rfone-web` and `rfone-tips` do not run migrations at boot; for them migrations are applied by hand (release
procedure, step 6), so a wrong deploy fails when someone migrates, or at the first request that touches a missing
table. **`rfone-selection` is different: `Selection/app.py` calls `run_migrations_to_head()` at import, against
RDS, at every instance start** — see R0 in §6.

| Deployed from | What happens |
|---|---|
| `origin/main` | Bank pages come back, then fail with errors on the first query (their tables no longer exist); `alembic upgrade` fails with "Can't locate revision 84354dc654ce"; Compensation `f63bf66` (never released) would go live at the same time |
| local `main` | The ORM does not know 28 revisions that are live (Bank-line merge, account item access / Organization, Project Management Responsible, etc.): Organization and Projects pages can fail; `alembic` cannot read the live revision |
| `feature/bank-simple-who-rules` | Same as above, plus the whole Bank UI against a database without Bank tables |
| `rfone-tips` / `rfone-selection` rebuilt from any of the above | Brings back the older Data Store; same migration mismatch |

Until `main` is aligned (§4.4), deploy only from `release/remove-bank-aws` or from a branch built on top of it.

## 4. Handover to the session that is cleaning the local Bank

### 4.1 Do not run `84354dc654ce` on a database that holds Bank data

`84354dc654ce` drops every Bank table. On a local database (SQLite) it runs too — it was written to work there. An
`alembic upgrade head` on the local working database with a code tree that contains this revision **deletes the
local Bank data**. Before any upgrade of a local database: back it up, run `alembic heads`, and stop if
`84354dc654ce` is in the chain.

### 4.2 Do not import the AWS removal into the local Bank line

This branch deletes, for AWS only: `rfone_data_store/bank_reconciliation/`, the PayPal connector, the 53 Bank ORM
classes in `models.py`, the Bank web routes/templates/scripts/styles, the `BANK` Domain entry, and the local
environment hook (`inject_local_environment` in `app.py` and the `local_env` banner in `base.html`, which the
"Avvia Bank" environment uses). The local Bank needs all of these. Do not merge `release/remove-bank-aws` into the
local Bank line and do not cherry-pick `617e867` there.

Safe to take from this branch, if useful: `test_projects_service.py` (its migration-history part now runs on its
own database) — only once the chain it targets contains `84354dc654ce`.

### 4.3 What the local session owns

The local cleanup decides what "Bank ripulito" is. Nothing on AWS depends on the local state any more: AWS holds
no Bank table and no Bank code in `rfone-web`. Local data never reaches AWS automatically; the last transfer was
2026-10-13 (BANK_AWS_001 §2.9) and those data are now deleted on AWS (recoverable only from the snapshots).

### 4.4 Aligning `main`

`origin/main` and local `main` have diverged (local `main` lacks the BANK_AWS_001 line). Aligning them is a
Product Owner decision. Whatever the result, the `main` that will be deployed must contain `84354dc654ce` and must
not contain the Bank code unless the clean Bank is being reinstalled (§5).

## 5. Reinstalling the clean Bank later — how to stay compatible (not done)

1. **New revisions only, after `84354dc654ce`.** The clean Bank schema arrives as one or more NEW revisions whose
   ancestor is `84354dc654ce`. Never edit, re-run or reuse the IDs of the old Bank revisions (they are recorded
   as applied in the RDS history), and never downgrade through `84354dc654ce`.
2. **Created from zero on AWS.** On RDS the Bank tables are absent, so the reinstall revision creates them
   (`create_table`). Table names may be reused — nothing is left under them. Shared targets that still exist and keep
   their ids: `legal_entities` (ids 1, 2, 3), `rfone_accounts`, `suppliers`, `employees`, `purchase_documents`.
3. **Local databases that keep Bank data** must reach the same chain without executing the drop. Options, to be
   decided by the Product Owner:
   - A — make the reinstall revision idempotent: create a table only when absent; when present, verify that its
     structure is exactly the expected one and refuse otherwise; and give `84354dc654ce` a guard so it drops
     only with an explicit confirmation (e.g. an environment variable naming the revision). The guard changes
     nothing on RDS, where the revision has already run. **Recommended.**
   - B — migrate local Bank data through export/import into a database already at the new chain.
   - C — `alembic stamp` the local database past `84354dc654ce`, then rely on the idempotent revision of option A.
4. **Data on AWS** come back only through an explicitly authorized transfer, rehearsed on a disposable
   `rfone_pgval_*` clone first (the BANK_AWS_001 method), never as a side effect of a migration.
5. **What has to be granted again:** the `BANK` entry in `domain_registry.py`; `BANK` rows in
   `rfone_account_domain_access` for the chosen accounts; and, only if the AI Rules run on Bedrock, the IAM policy,
   the `bedrock-runtime` endpoint with its security group, and the two `rfone-web` variables (BANK_AWS_001 §2.3,
   §2.6, §2.10). Each of these is a permission or network change that needs its own approval.
6. Rehearse the whole chain on a disposable clone before RDS; take a snapshot first.

## 6. Residual work (open)

| # | Item | Why it is open | How to close it |
|---|---|---|---|
| R0 — **priority** | `rfone-selection` cannot start a new instance. Its live image (source `rfone-selection-source.zip` of 2026-10-03, chain head `d8e2f5a9c3b7`) runs `alembic upgrade head` at import; RDS is at a revision that chain does not contain (`7b1d4f9a2c6e` since 2026-10-12, now `84354dc654ce`), so Alembic stops with "Can't locate revision" and the app does not boot. The instance started on 2026-10-03 keeps serving; a restart, scale-out or redeploy of the same image would fail | Pre-existing since BANK_AWS_001 (2026-10-12); not caused by the removal, which only moved RDS from one unknown revision to another. Fixing it means a new Selection deploy, not authorized in this step | Rebuild `rfone-selection` from a branch whose chain contains `84354dc654ce` (this one, or an aligned `main`), with the usual backup of `rfone-selection-source.zip`; this also closes R1 for Selection. Do it before anything restarts the service |
| R1 | Dormant Bank code in the `rfone-tips` and `rfone-selection` images (`bank_reconciliation/`, PayPal connector, Bank ORM classes in the shared Data Store) | Rebuilding them from a branch other than the one they were built from would also have published non-Bank changes that were not live. Not reachable: no route; the tables no longer exist | Rebuild both from a branch whose chain contains `84354dc654ce` and that has no Bank code, once `main` is aligned; usual backup of `source.zip` / `rfone-selection-source.zip`; no migration needed |
| R2 | Verification of the other Domains after login | Done: public routes, database fingerprints of all 224 tables, service logs. Not done: pages opened by a signed-in account — it needs a technical account to be activated temporarily (an account change) | With Product Owner authorization: activate `release-smoke-20260925` temporarily with the needed accesses, open Home, Tips, Training, Compensation, Projects, Wines, Organization, Selection, Clover Acquisition; restore it INACTIVE, with its previous accesses and a rotated password |

## 7. References

- Branch `release/remove-bank-aws`: `617e867` (code + migration), `754ae2e` (Infrastructure README), this file.
- CodeBuild `rfone-web-build:862f40e7-1b84-4229-8102-a02cd3a15ec8`; ECR `rfone-web` `sha256:222ec5e4288be646905b77055ff3672d1afe2d5f043941f5296c4cea0cdbe40f`.
- App Runner `rfone-web`: `UPDATE_SERVICE` `6b6ba24a218a4653a081ed840a43dba1`, `START_DEPLOYMENT` `5564abe753844e81b3744fc969cf7ee0`.
- Previous release: `07 Tasks/Reports/BANK_AWS_001_RELEASE_HANDOVER.md` (on `release/bank-aws` / `origin/main`).

## 8. R0, R1, R2 closed (2026-10-14, ~03:00 UTC)

**R0 + R1 — `rfone-selection` and `rfone-tips` rebuilt from this branch @ `53ddf4a`.** Their application folders
(Selection, Tips, Training, Clover Data Explorer, Shared UI) are identical to what was live (only two `.md` files
differ); the Data Store is the one already live in `rfone-web` (Bank removed, chain up to `84354dc654ce`, Projects /
Wines / item access already released). Compensation `f63bf66` is not included. No `bank_reconciliation/`, no PayPal
connector in either image.

| Step | Result |
|---|---|
| Boot check before deploy | Both apps imported in the image layout (from the zips uploaded below) against a disposable `rfone_pgval_bootcheck_*` at `84354dc654ce`, requests through the official-entry header: Selection 302 to login, Tips 302 to login, Tips dish guide 200; Alembic, schema and every row unchanged by boot and requests; database dropped |
| Source backups | `backups/rfone-selection-source-pre-bank-removal-20261014t025601z.zip`, `backups/rfone-tips-source-pre-bank-removal-20261014t025601z.zip` |
| Builds | `rfone-selection-build:01783370-a0f0-4742-bb85-891cd1d67802` SUCCEEDED → `sha256:386fa2ef…0c95`; `rfone-tips-build:acaa8f67-b10c-4a2f-b38b-af56874538d1` SUCCEEDED → `sha256:7f53fe79…4258` |
| Deploys | `start-deployment` Selection `0e84f7cba0cc4f7a908cdead62258091`, Tips `4deaa51875f1431b913cdeb050544833`: SUCCEEDED, both RUNNING. Logs: clean boot 02:58 UTC; Selection's boot-time Alembic ran no revision; RDS still `84354dc654ce`, 224 tables |

**R2 — signed-in check.** Technical account `release-smoke-20260925` made ACTIVE for the check only, with access to
TRAINING, TIPS, COMPENSATION, SELECTION, CLOVER_ACQUISITION, WINES, PROJECTS, ORGANIZATION (no admin). 200 on Home,
Tips, Compensation, Selection, Clover Acquisition, Wines, Projects, Organization; `/training` returns to Home with a
message because this account has no Training identity (expected behavior of `training_integration.py`); no Bank
link on any page; `/bank`, `/bank/review`, `/bank/ai-rules`, `/bank/export` → 404. Afterwards: logout; account
restored identical (INACTIVE, previous password hash, only the previous TIPS row, disabled) except
`session_version` 22 → 24, so the test cookie is revoked (verified: it now redirects to login). No other table
changed during the check.
