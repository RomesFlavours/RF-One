# DEV_JOURNAL_RELEASE_001 — Development Journal released on AWS (2026-10-21)

Product Owner request (2026-10-21): English UI, author corrections with kept versions, stable local launcher, documents
on the private Selection bucket under `dev-journal/documents/`, deploy and push. Module documentation:
`10 System/Development Journal/README.md`.

## Code

| Item | Value |
|---|---|
| Branch | `feature/dev-journal`, from `origin/main` `47310ae` (the line deployed on AWS) |
| Release commit | `5b3f64d` — pushed to `origin/feature/dev-journal` and fast-forwarded to `origin/main` (no force) |
| Alembic | single head `c4e820261021` (revises `c8e4b2a6f0d1`) |
| Not included | all uncommitted work in `RF One/` (branch `handoff/2026-10-17`): Selection workspace (`a7d520261021`, `b8e620261021`), Clover employee/line presence (`b9e620261019`, `d120261019ee`), Tips historical payments, AI Organization |

Tests (release worktree): `test_dev_journal_http` 89/89; access/Home/navigation/start-up/image layout/local banner,
Projects, Bank configuration, canonical catalog, Projects service — all green. `test_projects_http` check 32 fails only
in a Windows checkout (the CSS file has CRLF line endings via `core.autocrlf`); unrelated and not deployed that way.

## Live (account 418674484214)

| Step | Result |
|---|---|
| Source check | deployed `rfone-web` and `rfone-selection` zips identical to `47310ae` before the release; new zips differ only by the Development Journal files |
| Source backups | `backups/{rfone-web,rfone-selection}-source-pre-dev-journal-20261021t192018z.zip` |
| RDS snapshot | `rfone-dev-pre-dev-journal-20261021t192018z` (available before the migration) |
| Migration | `c8e4b2a6f0d1` → `c4e820261021` on `rfone-dev` / `rfone`: 270 → 276 tables (the 6 `dev_journal_*`), nothing else |
| Builds | `rfone-web-build:8fa3d392-…`, `rfone-selection-build:564077d4-…` SUCCEEDED |
| Images | `rfone-web` `sha256:fa7d38c7be28…a123f113`; `rfone-selection` `sha256:6fa4f23d6d94…3f645b433b` |
| Deploys | `rfone-web`: UPDATE_SERVICE `4298bd65…` (adds `RFONE_DEV_JOURNAL_DOCUMENT_BUCKET`; other 9 variables and 2 secrets unchanged) + START_DEPLOYMENT `28c1f551…` (the update alone did not pull the new `:latest`); `rfone-selection`: START_DEPLOYMENT `0647d5c4…` (it runs `alembic upgrade head` at boot, so it had to know `c4e820261021`) |
| Not redeployed | `rfone-tips`: its deployed source zip is **not** a commit (it holds the uncommitted Clover/Tips work of 2026-10-19); it runs no migration, so it was left untouched |
| IAM | inline policy `rfone-web-dev-journal-documents` on `rfone-web-apprunner-instance-role` (Put/Get/Delete on `…/dev-journal/documents/*` only) |
| Network, bucket | unchanged |
| Access | `DEV_JOURNAL` enabled for account 4 (`rfone`) only; no account created, no password changed |
| Logs | no error in the application logs of both services after the deploy |

## Online checks (24/24)

Performed with the Product Owner's account through a session signed in memory with the service's own Flask secret
(no password used or changed; nothing stored):
- `/login` 200; anonymous `/dev-journal` and documents → login.
- **Before** the access was granted, the same account got 403 on `/dev-journal`, `/dev-journal/new` and a document URL, and Home had no link.
- After: access page shows "Development Journal access" ticked; Home → Services → Development Journal; list in English.
- Card created and edited (phase Ready for release → Released, next step); release entry; author correction; versions page shows version 2 (current) and version 1.
- Upload: object under `dev-journal/documents/<random id>`, SSE AES256, anonymous S3 GET 403; download through the app returns the same bytes.
- Events: `WORK_CREATED`, `PHASE_CHANGED`, `RELEASE_RECORDED`, `ENTRY_EDITED`, `DOCUMENT_UPLOADED`, all by account 4; no delivery state; nothing sent.

The card created by the checks ("Development Journal — first release on AWS", id 1) is kept: it documents this release.

## Rollback

Code: restore the two backup zips, rebuild, redeploy (or redeploy a previous ECR image). Schema: `c4e820261021` has a
`downgrade` (drops only the 6 tables); or the snapshot above. S3: delete the policy and the variable; objects only under
`dev-journal/documents/`.
