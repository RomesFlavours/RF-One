# BANK_REINSTALL_001 — Bank reinstalled on AWS, software and data (2026-10-17)

Product Owner decision (2026-10-17): the cleaned local Bank is published on AWS; for this first release the local
database used on port 5080 (MINIPC-KSYR1) is the authoritative source. **After this initial load the local database
is never transferred to AWS again** (Infrastructure README, "Bank reinstallato su AWS").

## Code

| Item | Value |
|---|---|
| Release branch | `release/bank-reinstall` = `origin/main` + `feature/bank-simple-who-rules` (`a455f9f`) + `release/remove-bank-aws` (migration `84354dc654ce` and records only, not the code removal) |
| Commits | `a455f9f` (Bank AI Rules work), `f294eef` (merge Bank line), `fc7c71a` (merge removal records), `2632de2` (reinstall revision, guards, loader, docs) |
| Alembic head | `c8e4b2a6f0d1` (single) |
| Not included | Invoice Intake work, uncommitted in `RF One/` (left untouched); `data/cleanup_logs/` of the Bank worktree |
| Included from `origin/main`, not released before | Compensation `f63bf66` (no migration; tests green) |

Tests (release worktree): 60 + 6 test files green (Bank HTTP suite incl. the new conflicts test, other Domains touched by
the removal, migrations, Compensation, image layout start-up).

## Rehearsal (local PostgreSQL 18.3, same version as RDS)

RDS-like database built by the chain up to `84354dc654ce` (224 tables, as RDS) → `c8e4b2a6f0d1` creates 46 tables, model
and database identical for Bank. Copy of the local working database → upgraded to `c8e4b2a6f0d1`: 3234 movements,
3251 decisions, 106 rules kept. Found and fixed: `bank_ai_rule_interpretations.cache_key` 64 → 128 (11 invalidated keys
of 97 characters). Initial load: preview, apply, second run refused. Bank pages on PostgreSQL: all under 1.5 s,
`/bank/ai-rules` (one year) 572 queries; `/bank/classification` (the 2026-09-25 timeout) no longer exists.

## Live (RDS `rfone-dev` / `rfone`, account 418674484214)

| Step | Result |
|---|---|
| Snapshot | `rfone-dev-pre-bank-reinstall-20261017t154950z` (available) |
| Source backups | `backups/{rfone-web,rfone-selection,rfone-tips}-source-pre-bank-reinstall-20261017t155335z.zip` |
| Migrations | `84354dc654ce` → `c8e4b2a6f0d1`: 224 → 270 tables (`d2b6f8a4c0e7`, `a6e2c8f4b0d9` no-ops; nothing dropped) |
| Initial load | `load_bank_initial_to_aws.py`: preview then COMMIT — 21,335 rows in 46 Bank tables, 69 checks passed, 224 tables of the other Domains unchanged (count + hash) |
| Post-check | 46 tables equal in count; totals per Source equal (11 Sources); 3234 movements all decided, 300 WHO/WHY pairs; 101 active AI rules; 232 WHO; 107 WHY; 328 saved interpretations |
| Builds | `rfone-web-build:90f65e40-…`, `rfone-selection-build:9748428c-…`, `rfone-tips-build:6d131309-…` SUCCEEDED |
| Deploys | `rfone-web` UPDATE_SERVICE `fe3949c8…` (AI variables) + START_DEPLOYMENT `0c984416…`; `rfone-selection` `6c55f261…`; `rfone-tips` `74d60aeb…` — all RUNNING, clean boots, no error in the logs |
| AI | Bedrock `us.anthropic.claude-opus-4-6-v1` (Opus 5.5: "not available for this account"); policy `rfone-web-bedrock-invoke-bank-ai-rules` (versioned in `deploy/rfone-web/bedrock-invoke-policy.json`); endpoint `vpce-0150ede1898b9a0f5` (us-east-1a/b, private DNS), security group `sg-099f894d3b9e1942e` (443 from `sg-0a4d4d094ea0d0fc3` only) |
| Public checks | `/bank*`, `/selection/`, `/tips`, `/compensation`, `/projects`, `/restaurant/wines` → login redirect; `/login` 200 |
| BANK access history | Read from snapshot `rfone-dev-pre-bank-removal-20261014t021458z` on a temporary instance (deleted afterwards): `rfone` enabled, `swyfox` enabled (role admin), `enzo` disabled, `release-smoke-20260925` disabled; no item rows |

## Open (blocked by the session's automatic permission check)

1. Restore the four BANK rows above in `rfone_account_domain_access` (refused as "Permission Grant").
2. Fast-forward `main` to `2632de2` (`git push origin 2632de2:refs/heads/main`, refused).
3. Signed-in checks online, including AI interpretation, Rewrite with AI and rule execution through Bedrock — they
   need an account with BANK access (item 1).

**Rollback:** code — restore the backup zips, rebuild, redeploy; data and schema — snapshot
`rfone-dev-pre-bank-reinstall-20261017t154950z`; AI — delete the policy, the endpoint, the security group and the two
variables.
