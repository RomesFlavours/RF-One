# Selection — Applications CV Delete release (2026-11-02)

Status: App Runner operation `35d1d95a2035418a9664ee2b76bc2b0e` SUCCEEDED; service RUNNING.

## What changed

Only SELECTION_CV_DELETE_001 (commit `ef8f324`) on top of the image that was running
(`sel-fa35e6131032`, branch `release/selection-shared-migrations`): Delete of a CV in the
Applications CV list before its AI analysis starts (rule enforced on the server, inside a row lock
shared with the analysis queue), NEW of the page session across successive uploads, and the
Applications section of "How Selection works". No migration was applied; no schema change.

## Release identity

- Branch `release/selection-cv-delete`, commit `ef8f32439f0bcfe87fdca75a243cb6974db2b37a`.
- Image `418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-selection:sel-ef8f32439f0b`.
- Build `rfone-selection-build:ed80b9c8-bb1a-427b-8823-2021b52fdc3a`.
- RDS `alembic_version` = `e0a120261101` before and after (= head of the release commit).

## Rollback

- Image `rfone-selection:pre-cv-delete-001-20261102t143000z` (= `sel-fa35e6131032`).
- Source backup `s3://rfone-tips-deploy-418674484214/backups/rfone-selection-source-pre-cv-delete-001-20261102t143000z.zip`.
- RDS snapshot `rfone-dev-pre-selection-cv-delete-001-20261102t143000z`.

## Verified

- Health `/selection/candidate/bridge/health` 200 (`rmaed-selection-bridge-3`); unsigned relay call
  403; candidate entry redirects to RMAED.it with a signed state; staff pages redirect anonymous
  visitors to the RF-One login.
- One-off ECS task (released image, production database, queue workers disabled in that process,
  task definition `rfone-selection-cv-delete-verify` deregistered afterwards): 21/21 checks.
  Real Job 2 (42 analyzed CVs) read only: Applications ranking and CV list, Evaluation, Interviews,
  Decisions and a dossier render; analyzed CVs show Delete dimmed. Synthetic Draft Job (id 4) with a
  synthetic CV: Delete shown while waiting; refused without login and with a wrong CSRF token;
  refused by the server while the analysis is queued, running or done; when allowed it removes the
  Job link, application, résumé snapshot, document record, identity and stored file and is logged.
  The synthetic Job and all its rows were removed. No real CV was deleted.
- The verification task used a container-local document store (no IAM role was created for it), so
  S3 deletion on AWS was not exercised there; the S3 path is `S3DocumentStore.discard`, already in
  use, and the local suite covers it.
- Release-tree tests: all 14 Selection test files pass. The HTTP race scenario of
  `test_cv_delete_http.py` fails intermittently on SQLite under load ("database is locked"), in this
  tree and in the original one alike; production runs PostgreSQL with `FOR UPDATE`.
