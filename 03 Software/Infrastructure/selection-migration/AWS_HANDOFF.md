# Selection AWS handoff — prepared, not executed

Scope: release the current `03 Software/AWSSelection/Selection` and its matching `RF-One Data Store` to the existing Selection service, retaining data and services belonging to other RF-One modules. This document does not authorize or perform an AWS change.

## Verified baseline

The private archive under `%LOCALAPPDATA%/RF-One/Selection-AWS-Archive/20261115T162302Z` contains the verified operational/prototype dumps, all available versions of the document buckets, source packages and dependency inventory. The data rehearsal `data-rehearsal/20261115T173619Z` verified 202 CVs, 206 candidate-position links, eight positions, 712 FK checks, zero orphans and zero new records on a second import. The 52 local AI results, configurations and completed action were read with the current application services.

Use those results as a rehearsal baseline, not as current production state. Capture and reconcile later AWS/local changes before cutover. The operational RDS database is shared; never restore the whole rehearsal database or SQLite file over it.

## Release blockers

| Gate | Evidence / required work |
|---|---|
| Server-side AI | `workspace/rule_ai.py` dynamically loads `RFBank/ai.py`, which invokes the PC's Codex executable and interactive session. The Dockerfile packages neither that transport nor its authentication. Implement and test a server transport preserving the conversation/rule contracts, with application credentials in Secrets Manager. Do not package the operator's Codex session or silently switch the model/provider. |
| PostgreSQL ingestion | The rehearsal adapter removed NUL characters from 11 text fields and preserved originals in its audit archive. The live CV extraction/import path still needs the same documented compatibility boundary, including JSON-bound text, with tests on actual PostgreSQL. Preserve original document bytes. Apply explicit UTC handling to timezone-aware import columns. |
| Container/OCR | Validate PDF/DOCX/TXT readers, scanned-PDF OCR models, Linux native libraries and resource use in the actual image. The current slim Dockerfile has no native-library installation; OCR and two Gunicorn workers require memory/concurrency validation. Fail clearly on missing readers. |
| AI job lifecycle | The AI reader uses process-local thread ownership (`_jobs` and a threading lock), while the Dockerfile starts two workers. Verify/rework cross-process ownership, retries and restart recovery. A single-worker initial setting can reduce risk but does not replace a restart/concurrency test or durable ownership. Do not restart completed mail actions or old failed screening jobs. |
| Production data runner | `rehearse_data.py` is intentionally guarded to a new local clone and uses local document paths. Prepare a separate reviewed, transaction-safe production runner with dynamic identifier maps, provenance, fresh-source checks and idempotency. Never remove its guard and point the rehearsal tool at RDS. Include reversible before-images and the confirmed role aliases. |
| Persistent originals | Stage 52 new originals under `selection/resumes/migrations/<batch>/...` in the existing private operational bucket, verify checksums, and bind new S3 URIs before committing DB links. Retain existing object URIs/versions; no Windows paths may remain active. Reconcile any CVs added since the snapshot. |
| Immutable artifact | The new `03 Software/AWSSelection` tree is not yet frozen in version control. Package this tree, not the older `03 Software/Selection` directory. Match Docker context names `Selection/` and `RF-One Data Store/`. Exclude local launchers, data/uploads, database copies, credentials and private migration outputs. Record commit, source hashes, dependency versions and image digest. |
| Runtime/security | Preserve shared RF-One authentication/session secret, existing staff grants and candidate verification flows. No automatic local sign-in in production. Preserve real URLs, private storage and mail transport acknowledgement. Select the conversational engine explicitly; do not enable the old screening engine. |
| Release checks | Run image-layout startup, actual PostgreSQL upload tests, multi-worker/restart tests, current UI flows, help checks and the mandated interface-language verification on the frozen artifact. Local SQL/model tests do not establish image or cloud readiness. |

The proven additive application delta is five new tables and four nullable columns. If the cloud-readiness work adds fields/tables, update this delta and repeat the schema/data rehearsal before release. Do not change the shared Alembic revision to the older local revision. Keep the two shared-table nullability differences already identified instead of tightening other modules' constraints.

## Confirmed data policy

- Merge local Server Mount Dora into operational position 3, and Server Winter Park into position 6.
- Canonicalize FOOD_RUNNER and BUSSER to the local Server Assistant role. Keep the two operational campaigns separate, with original history and state; put the 52 local CVs into active position 7. Position 8 remains draft.
- Create Line Cook Mount Dora with the existing Enzo manager. Keep existing managers and grants.
- Preserve current Selection organization ownership at restaurant 1, including Mount Dora. Do not infer a move to restaurant 4 from site labels.
- Preserve old judgments, completed interviews, online answers and audit events. Do not convert old scores into new rule definitions or execute AI/mail during migration.
- Preserve the succeeded action and local rule/model/action/procedure configurations. Keep the prototype TEST database archived rather than promoting its records.

## Cutover sequence, once blockers are closed

1. Re-read the actual service, image, configuration, database revision and object-store state. Record a recovery image and a fresh database/document checkpoint. Verify new data since the rehearsal and stop for semantic mapping conflicts.
2. Build and test an immutable release image before touching the live service. Rehearse the production-shaped runner against a fresh isolated copy with real S3-style URI mapping and fake transports. Confirm a second run is a no-op.
3. Arrange a short Selection-only write window. Drain/hold Selection uploads, public applications and its mail/AI producers as appropriate; keep other modules online. Do not make the entire shared database read-only or rotate shared session/database credentials.
4. Capture final Selection deltas, validate source fingerprints and stage new original files in a batch-specific private prefix. Existing bucket policies should be reused; verify the actual IAM prefix permission before upload.
5. Apply only reviewed additive schema DDL explicitly. Preserve the global revision and shared tables. Run the targeted data import with approved maps in a transaction and an atomic import ledger, not a database replacement. Verify CV hashes, FK integrity, exact preserved history, expected counts and ownership before opening writes.
6. Update only the existing `rfone-selection` service to the tested image/configuration. Keep the official `/selection` routing and shared web/session settings. Follow the deployment to a terminal state and verify health, access controls, CV originals, rule creation, filtering, interviews and action success reporting.
7. Reopen Selection writes after validation. Recheck other modules' startup and selected authorized read flows, and confirm no unauthorized schema/data/permission changes.

## Rollback without losing other modules' data

- Additive schema should remain backward compatible. Do not drop new columns/tables to roll back an image.
- Before opening Selection writes, use the import ledger and before-images to reverse only this batch's inserts and the modified Selection role/context fields if needed; then restore the prior Selection image. Role aliases must also be reversed if the older image does not understand the new catalog codes.
- After writes have reopened, freeze Selection again and preserve new submissions before deciding how to reverse the batch. Never delete imported IDs that acquired new dependent records.
- A whole-database snapshot is a recovery source, not a command to overwrite the shared operational RDS database. If necessary, restore it to an isolated recovery destination and extract only the required Selection records. Protect newer records from all other modules.

## Retirement of old Selection components

After successful validation and the agreed recovery period, retire only confirmed obsolete Selection components. Review App Runner, image/build references, prototype DB/secrets and the old web stub separately. Do not delete `rfone-web` to remove its legacy Selection route.

Both document buckets have live non-Selection dependencies: Trainer/Kitchen Call use the test bucket, and the development journal uses the operational bucket. No bucket-wide deletion or blanket policy change is permitted as Selection cleanup. Verify DB/secret dependencies as well before retiring any resource. Preserve recovery artifacts before removing old ECR images.
