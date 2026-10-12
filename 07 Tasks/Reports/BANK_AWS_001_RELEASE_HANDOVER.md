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

## 3. Procedures used

- Release of `rfone-web`: `03 Software/Infrastructure/README.md` § "Procedura di rilascio di `rfone-web`".
- Migration rehearsal: disposable `rfone_pgval_bankaws_<ts>` on the same RDS instance — schema from `main`'s
  chain, structural diff vs. live, full copy of live rows (hash-verified), `alembic upgrade heads`,
  per-table comparison, ORM-vs-schema comparison; dropped afterwards.

## 4. Decisions still open for the Product Owner

1. IAM grant `bedrock:InvokeModel` (Opus 4.6 only) to `rfone-web-apprunner-instance-role` — or ask AWS for
   Opus 5.5 access to align AWS with the local interpretations.
2. Bank data transfer: replace the AWS Bank dataset (2026-09-25) with the local one? (comparison in the report)
