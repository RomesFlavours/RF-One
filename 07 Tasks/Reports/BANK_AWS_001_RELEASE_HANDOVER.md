# BANK_AWS_001 — Release handover (Bank on AWS)

Living handover document for the Bank AWS release. A new session reads this first and does **not** ask the
Product Owner again for what is recorded under "Authorizations".

## 1. Authorizations granted by the Product Owner (2026-10-12)

Granted in writing in the session of 2026-10-12, valid for this release (`release/bank-aws`):

| # | Authorized | Conditions |
|---|---|---|
| A1 | Read RDS `rfone-dev` / `rfone` | — |
| A2 | Recreate the release worktree | — |
| A3 | Verify the release, push it | Start from `release/bank-aws` @ `a450505`; first check that `main` has not advanced; preserve every function already online, Responsible included |
| A4 | Apply the necessary migrations to RDS | Check the real RDS state first, take a backup, verify that the updates preserve existing data **and** that tables have the expected structure (not merely exist) |
| A5 | Publish Bank on AWS (`rfone-web`) | Never publish code older than `main` @ `d3632a8` |
| A6 | Complete the AI Preview check on AWS | Deploying the pages alone does not conclude the work |
| A7 | Prepare and verify the initial Bank data transfer | Separate from the software deploy; never overwrite existing AWS data; if Bank data on AWS would be replaced, show the comparison first; say when local changes must stop for the final transfer; preserve other Domains' data and the "Solo WHO" phase |

**Not covered by these authorizations (still need an explicit Product Owner decision):** see §4.

## 2. State of the work

_Updated during the session; the latest state is at the bottom of each subsection._

### 2.1 Code

- `origin/main` = `d3632a8` (MyRF Project Management: a Responsible per Task), checked 2026-10-12 ~22:00 UTC. `release/bank-aws` contains it (merge-base = `d3632a8`).
- Worktree: `C:/Users/servi/rfone-wt/bank-aws` (recreated 2026-10-12).
- Fix found by the migration rehearsal: six Bank-line migrations used `server_default=sa.text("0"/"1")` on
  Boolean columns, which PostgreSQL rejects (`BOOLEAN DEFAULT 0`). Changed to `sa.false()` / `sa.true()`
  (renders `0`/`1` on SQLite, so already-migrated local databases are unaffected):
  `a5d9e3f7b2c4`, `b7f1c3e5a9d2`, `c3d9e1f5a7b2`, `d7e2f0b5c3a8`, `e4a9c1f7d3b5`, `e8f3a1c6d2b9`.

### 2.2 RDS (read-only checks)

- Alembic on RDS: `e8c4a2f6b1d3` (single head of `main`); 260 tables; 326,176 rows.
- Structure of RDS vs. the schema produced by `main`'s migration chain up to `e8c4a2f6b1d3`, compared on a
  disposable `rfone_pgval_*` database: **0 differences** (columns, types, nullability, defaults, PK, FK,
  unique, indexes, checks).
- Pending on RDS for this release: 25 revisions ending at the merge `7b1d4f9a2c6e`.

### 2.3 AI Preview on AWS

- `rfone-web` today has no AI configuration (no `RFONE_AI_PROVIDER`, no key); egress is through the VPC
  connector `rfone-tips-vpc-connector` (no NAT). A `bedrock-runtime` interface endpoint
  (`vpce-0010040e932d4ab8f`, private DNS, SG allows 443 from the connector SG) exists, created 2026-10-12
  for BANK_AWS_001.
- Bedrock model access on account 418674484214 (Converse probe, 2026-10-12): **accessible** Opus 4.6,
  Opus 4.5, Sonnet 4.6, Sonnet 4.5, Haiku 4.5; **denied** Opus 4.7/4.8/5/5.5, Sonnet 5/5.5, Haiku 5.5,
  Fable 5.1 ("not available for this account").
- Real rule texts of the local Bank (8 rules, current general instructions): Opus 4.6 → 7/8 valid, avg 12.9 s,
  max 19.8 s; Sonnet 4.6 → 7/8, avg 10.6 s; Haiku 4.5 → invalid on the two tried. Locally the rules are
  interpreted by `claude-opus-5-5` (Claude Code CLI/session).
- Chosen model for AWS: `us.anthropic.claude-opus-4-6-v1` (the most capable accessible). Needed:
  IAM `bedrock:InvokeModel` on that profile for `rfone-web-apprunner-instance-role`, and env vars
  `RFONE_AI_PROVIDER=BEDROCK`, `RFONE_BEDROCK_MODEL_ID=us.anthropic.claude-opus-4-6-v1` on `rfone-web`.
  **The IAM grant needs an explicit Product Owner confirmation** (see §4).

### 2.4 Bank data transfer

- The local Bank in use on MINIPC-KSYR1 (port 5080) is served from
  `rf-one-bank-simple-who-rules/03 Software/RF-One Data Store/data/rfone.db` (inside OneDrive: the Bank Local
  Environment has not yet adopted a working database on this PC — `run.ps1 status` reports no local
  database, no manifest, no lease).
- AWS already holds the Bank dataset migrated on 2026-09-25 (BANK_AWS_LIVE_DATA_MIGRATION_001). The local
  dataset is a different one. The transfer therefore **replaces** Bank data on AWS — comparison in the
  session report; awaiting the Product Owner's decision.

### 2.5 Deployed 2026-10-12 (software only)

| Step | Result |
|---|---|
| Release commit | `1a35771` on `origin/release/bank-aws` (contains `main` @ `d3632a8`) |
| Online source before (backup) | `s3://rfone-tips-deploy-418674484214/backups/rfone-web-source-pre-bank-aws-001-20261012t224445z.zip` — identical, file by file, to `main` @ `d3632a8` |
| New source | `rfone-web-source.zip` from committed files of `1a35771` (786 files, sha256 `5a943880…65de91`) |
| RDS snapshot (recovery point) | `rfone-dev-pre-bank-aws-001-20261012t224514z` (available 22:45 UTC) |
| CodeBuild | `rfone-web-build:ba9569be-4cc6-4d62-a994-9c55d260466e` SUCCEEDED; ECR `rfone-web:latest` `sha256:c6fa933e3250cbaebc17507e747f128336e3f1e7e219a7ceb2f886d8e3e4f8ea` |
| Migrations on RDS | `e8c4a2f6b1d3` → `7b1d4f9a2c6e` (25 revisions). Data effects, identical to the rehearsal: 117 WHO names upper-cased (0 collisions), WHY groups reorganized (6 new, 5 deactivated, 39 WHY moved), 1 ORGANIZATION access row; no row deleted anywhere; 252 of 260 existing tables unchanged |
| App Runner | `start-deployment` `22abc07369e0477aaebb1d3939e4ad76` SUCCEEDED 22:55 UTC; clean worker boot |
| Smoke (official host, technical account `release-smoke-20260925`, restored to INACTIVE + previous access + rotated password) | 200 on Home, `/bank` (4.4 s), review, export, AI Rules, configuration, Projects (Responsible field present), Wines, Organization |

Removed by the Bank line on purpose (were online): `bank_classification.html`, `bank_instruments.html`,
`bank_instrument_edit.html`, `bank_monthly.html` (`/bank/monthly` now redirects to `/bank#step-sources`).

**Not done yet:** AI configuration of `rfone-web` (§2.3, waiting for decision 1) and the Bank data transfer (§2.4,
waiting for decision 2). The AI Rules header on AWS still reads the unconfigured default "ANTHROPIC · claude-sonnet-5":
a Preview of a new rule text there ends FAILED ("No ANTHROPIC_API_KEY configured") until decision 1.

**Rollback:** code — restore the backup zip above to `rfone-web-source.zip`, rebuild, redeploy; database — the
snapshot above (the migrations are additive except the three data effects listed).

### 2.6 Session 2026-10-12 (evening): main, AI, data transfer preparation

**Main.** `origin/main` had no commit after the release (`d3632a8`), so aligning it is a pure fast-forward to
`930c641`; RDS (`7b1d4f9a2c6e`) equals the release's single Alembic head. The push to `main` was refused by the
session's automatic permission check; it has to be run by the Product Owner (or after allowing it):
`git push origin 930c641:refs/heads/main`. The working folder of `main` (`RF One/`) holds someone's uncommitted
Invoice Intake work: its migrations `b3f9d2c6e4a1` / `540ee75caa65` hang off old revisions and, once committed,
must be re-chained after `7b1d4f9a2c6e` (otherwise a second head).

**Rule 6 (PayPal WHO) with Opus 4.6.** Rejected by the validator: "“only if the WHO differs” needs a WHO assigned
by the rule". Opus 4.6 represents "Se il WHO cambia, imposta “Da confermare”; altrimenti conserva lo stato" as
`only_if_who_differs: true` (= apply the rule only when the WHO differs — a different instruction), with the WHO
inside the two format branches; the validator correctly refuses it. Opus 4.6 also reads the "IND NAME:"
delimiter case-sensitively (`end_case: as_written`) although the rule says to ignore case. Opus 5.5's valid
interpretation (local #36, structured-v7) uses `status: to_confirm` (applied only when the WHO changes) and
`end_case: ignore`. Fix without touching the rule text: reuse the saved Opus 5.5 interpretation (below), and ask
for Opus 5.5 access on Bedrock for future rule texts. Not recommended: relaxing the validator (it would accept
the misreading).

**Reuse of local interpretations** (prepared, nothing written): 13 of 37 local interpretations are valid,
read by the release engine (v3–v7) and re-validated today against the AWS For Whom catalogue; they cover
current rules 1, 3, 4, 5, 6, 7, 8. Rule 2's valid interpretation (#37) names For Whom "RFWP", not an AWS entity
today. Prerequisite: the interpretation key includes the general AI instructions, and AWS has none yet — the
local instructions must be on AWS first (data transfer). Files: `%LOCALAPPDATA%\RF-One\Bank\transfer-review-20261012\`
(`interpretation_reuse.json`, `prepare_interpretation_reuse.py`).

**IAM for the AI Preview (not applied).** Writing the policy was refused by the session's automatic permission
check as a permission grant. Minimal inline policy for `rfone-web-apprunner-instance-role` (the Converse API
needs only `bedrock:InvokeModel`):

```json
{"Version": "2012-10-17", "Statement": [{"Sid": "InvokeBankAiRulesModel", "Effect": "Allow",
  "Action": "bedrock:InvokeModel",
  "Resource": ["arn:aws:bedrock:us-east-1:418674484214:inference-profile/us.anthropic.claude-opus-4-6-v1",
               "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-opus-4-6-v1",
               "arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-opus-4-6-v1",
               "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-opus-4-6-v1"]}]}
```

Then on `rfone-web`: `RFONE_AI_PROVIDER=BEDROCK`, `RFONE_BEDROCK_MODEL_ID=us.anthropic.claude-opus-4-6-v1`
(an `update-service` must resend every existing env var and secret), redeploy, real Preview check.

**Data transfer comparison** (read-only; files in the folder above):

| | Count |
|---|---|
| AWS movements before 2026 (kept by the plan) | 9,318 (2018-12-10 → 2025-12-31) |
| AWS 2026 / local 2026 | 3,360 / 3,234 |
| Matched (date + amount + description) | 3,104 |
| AWS 2026 absent locally | 256 — Amex 193 (no local Source), RFWP checking 42 (38 in Jan), RF Saving 14 (no local Source), Freedom 5, Business 1, Sapphire 1; 83 carry a WHO/WHY decision |
| Local 2026 absent on AWS | 130 — all September 2026 (imported after the 2026-09-25 AWS copy) |
| Duplicates (same Source, date, amount, text) | AWS 13 groups / 27 rows (11 groups: local holds one copy, AWS two); local 0 |

Source differences: local "Ink RFCO ··3144" holds the movements AWS splits between "Business Anthony ··2270"
(168) and "Ink Giovanna ··3144" (52); local "Ink RFCO ··2270" and "FirstCitizen Debit 0632" have no movements;
AWS "Amex ··1002", "RF Saving", "Chase-2915" (inactive) have no local counterpart. Legal Entity ids differ
(local 1 = Mount Dora, 2 = Angeli e Demoni/WP, 3 = Gelati; AWS 1 = Winter Park, 2 = Mount Dora, 3 = Gelati)
and Reporting Entities differ entirely (local RE_RFWP / RE_RFMD_LLC / RE_RFCO / RE_PINO_PERSONAL; AWS
RE_ANGELI_E_DEMONI_LLC / RE_RF_MOUNT_DORA_LLC / RE_RF_GELATI_LLC). Nothing deleted or replaced.

### 2.7 Session 2026-10-12 (night): transfer proposal, interpreter, blocks

- Transfer proposal: `07 Tasks/Reports/BANK_AWS_DATA_TRANSFER_PLAN_001.md` (entities, Sources incl. the 3144/2270
  split by the file's `Card` column, movements, repeated rows, decisions, AI). No data changed.
- Interpreter clarifications for Opus 4.6: branch `feature/bank-ai-interpreter-precision` @ `0db13e1` (8/8 valid
  twice on the real rules; AI Rules tests green). Not merged, not deployed.
- Invoice Intake (other session, not modified): `b3f9d2c6e4a1` is applied only to `RF One/.../data/rfone.db`;
  `540ee75caa65` nowhere; RDS has none. Integration when it is committed on the new main: one NEW merge revision
  with down_revision (`540ee75caa65`, `7b1d4f9a2c6e`), rehearsed on PostgreSQL before RDS.
- Blocked by the session's automatic permission check (authorized by the Product Owner, not bypassed) — manual path:
  1. main: `git push origin release/bank-aws:refs/heads/main` (fast-forward from `d3632a8`).
  2. IAM: `aws iam put-role-policy --profile rfone-dev-login --role-name rfone-web-apprunner-instance-role
     --policy-name rfone-web-bedrock-invoke-bank-ai-rules --policy-document file://<policy of §2.6>`.
  3. Then `python enable_bedrock_on_rfone_web.py --apply` (in the transfer-review folder; dry run without
     `--apply`, verified), then a real Preview check on AWS by a session.

### 2.8 Session 2026-10-13: possible duplicates, transfer rehearsal, second deploy

State checked first (nothing repeated blindly): RDS `7b1d4f9a2c6e`; no AI config on `rfone-web`; IAM policy absent.

- **main** fast-forwarded `d3632a8..57f2698` (allowed once). A second fast-forward to `0576ea1` was refused by the
  automatic permission check: main is 3 commits behind the release — manual: `git push origin release/bank-aws:refs/heads/main`.
- **Possible duplicates** (Product Owner, 2026-10-13, BANK_POSSIBLE_DUPLICATES_001): never block an import or the
  transfer; without a decision a possible duplicate is imported as CANDIDATE_DUPLICATE, linked to the movement it
  may repeat (also on another Source), shown "Da verificare" in the Review; never deleted, merged or confirmed
  automatically; a running balance or bank reference that differs proves distinct movements. Commit `ed0bc82`.
- **Interpreter clarifications** merged (`0576ea1`).
- **Second deploy** of `rfone-web` from `0576ea1`: source backup `backups/rfone-web-source-pre-bank-aws-001b-20261013t215144z.zip`,
  CodeBuild `rfone-web-build:26b807d3-…` SUCCEEDED, image `sha256:f5857090…49f7`, App Runner `c312126ac28149ab9e2d84d06bac4ab9`
  SUCCEEDED; authenticated smoke 200 on every page, no error in the log. No migration (none in this code).
- **Transfer tool** `03 Software/RF-One Data Store/transfer_bank_2026_to_aws.py`, rehearsed with `--apply` on a disposable
  clone of live (`rfone_pgval_transfer_20261013t210308`, dropped): 3,104 matched, 130 added; history before 2026, other
  Domains, every AWS movement and decision unchanged; every local current decision current on AWS; AI work carried
  (11 invalidated interpretations kept as history under a non-matching key); 147 WHY kept from AWS where the local
  decision had none (default `--fill-from-aws`); 1 WHY conflict, local kept; 7 possible duplicates marked Da verificare;
  8/8 rules reuse a valid Opus 5.5 interpretation with the AWS For Whom catalogue; app smoke 200 on the clone.
- **Not done:** the definitive transfer — waits for the local data freeze (Product Owner asked to be told first).
  Preview with a real AI call online — waits for the IAM policy (refused again by the automatic check; manual path §2.7).

### 2.9 Definitive Bank transfer — DONE (2026-10-13)

- Product Owner: local data frozen; on matched movements the LOCAL state prevails, empty WHO/WHY included (no
  `--fill-from-aws`); local wins the one WHY conflict; previous AWS decisions kept as history; AWS-only movements and
  classifications and all history before 2026 kept; the 7 possible duplicates stay "Da verificare"; other Domains unchanged.
- Frozen local copy: `%LOCALAPPDATA%\RF-One\Bank\transfer-final-20261013\rfone_local_final.db`, sha256 `c2839215cde1a746…`.
- Corrected rehearsal on a disposable clone (`rfone_pgval_final_20261013t222553`, dropped): 11/11 checks.
- RDS snapshot before the transfer: `rfone-dev-pre-bank-transfer-20261013t224939z`.
- Live run (`transfer_bank_2026_to_aws.py --target live --apply --confirm-live`, commit `8c26b65`, REPEATABLE READ):
  committed 2026-10-13 ~23:14 UTC, 11/11 checks — 3,104 matched + 130 added; 121 matched AWS decisions kept only as
  history; 403/403 previous AWS decisions kept; 256 AWS-only movements unchanged; 12 WHO, 17 WHY added; 7 possible
  duplicates Da verificare; history and other Domains unchanged.
- Live counts after: 12,808 movements (9,318 before 2026, 3,490 in 2026); 8 AI rules, 37 interpretations, 1 set of
  general instructions. Authenticated smoke on https://rfone.romesflavours.com: 200 on every page.
- **Local Bank:** the transfer has been taken — local changes made from now on do NOT reach AWS.
- Still open: Bedrock IAM policy (manual), then Bedrock settings on `rfone-web` and the real Preview check; main fast-forward (manual).
  Policy file ready: `%LOCALAPPDATA%\RF-One\Bank\transfer-final-20261013\rfone-web-bedrock-invoke-policy.json`.

### 2.10 AI on AWS — ACTIVE (2026-10-13)

- IAM inline policy `rfone-web-bedrock-invoke-bank-ai-rules` (bedrock:InvokeModel on Opus 4.6 only) applied by the
  Product Owner from a terminal (the `!` prefix does not run commands in the VS Code extension); verified on AWS.
- `rfone-web` settings `RFONE_AI_PROVIDER=BEDROCK`, `RFONE_BEDROCK_MODEL_ID=us.anthropic.claude-opus-4-6-v1`
  (every other env var and secret kept): App Runner `UPDATE_SERVICE` `6ce8070116a34ff1a2ea79d580c2e8de` SUCCEEDED.
  AI Rules header online: "BEDROCK · us.anthropic.claude-opus-4-6-v1".
- Real Preview through https://rfone.romesflavours.com (technical account, restored): a new rule text (PUBLIX, Solo WHO,
  September 2026) — 1st Preview HTTP 200 in 6.9 s, a real Claude call: new interpretation #38, provider BEDROCK,
  valid; 2nd Preview of the same text 0.6 s, interpretation reused, no new row. Both: 7 movements matched, nothing
  applied. Test previews #1–#2 remain on AWS as Preview history (no rule saved).
- Remaining manual step: main fast-forward.

## 3. Procedures used

- Release of `rfone-web`: `03 Software/Infrastructure/README.md` § "Procedura di rilascio di `rfone-web`".
- Migration rehearsal: disposable `rfone_pgval_bankaws_<ts>` on the same RDS instance — schema from `main`'s
  chain, structural diff vs. live, full copy of live rows (hash-verified), `alembic upgrade heads`,
  per-table comparison, ORM-vs-schema comparison; dropped afterwards.

## 4. Decisions still open for the Product Owner

1. IAM grant `bedrock:InvokeModel` (Opus 4.6 only) to `rfone-web-apprunner-instance-role` — or ask AWS for
   Opus 5.5 access to align AWS with the local interpretations.
2. Bank data transfer: replace the AWS Bank dataset (2026-09-25) with the local one? (comparison in the report)
