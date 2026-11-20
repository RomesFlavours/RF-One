# Selection production preparation

No AWS changes are performed by preparation or local tests. The approved frozen baseline is the only supported source; rebuild the plan after source changes. Never restore the complete local database over the shared production database.

## Runtime
Use the server OpenAI provider and an explicit model. The example runtime file must be merged into the existing service configuration, preserving database, authentication, mail and shared-module settings. Inject an application API key through Secrets Manager; never copy a desktop login or .env into the image. gpt-5-mini was tested with synthetic data through the real API. Errors do not generate substitute judgments or silently use Bank. Stored historical provider labels remain unchanged.

Build the Linux image from an immutable reviewed source release and run container smoke tests before deployment. Docker/WSL was unavailable on the local machine, so this image has not been built or verified here. Native OCR libraries are included in the Dockerfile. Runtime startup must not apply database migrations.

## Import
Use production_import.py --help and the subcommand help for exact arguments. Keep plans, receipts, backup exports and candidate data in the private archive, outside Git. The plan checksum seals 1,030 insertions and the reviewed role/context changes. Import uses returned database IDs and rebases candidate/rule references. It preserves existing accounts, other modules, legacy events and original CV objects.

Before the maintenance window: take a fresh complete database backup and document-version inventory; compare Selection changes since the archived baseline and reconcile them into a new reviewed plan. Any count/anchor drift stops this importer. Upload only the 52 new originals to their planned unique keys, then verify actual S3 bytes and SHA256. Existing buckets contain other modules and must never be cleared.

Pause Selection writes, explicitly apply the five application tables, four nullable columns and import audit ledger using the schema command. Do not change the global Alembic revision or run local full-schema migrations. Check the plan and objects read-only first. Production writes require the exact production target, matching plan checksum approval file and explicit maintenance flags. The example approval remains false.

The apply transaction locks only Selection import tables and reviewed position anchors. Repeating the same batch inserts zero rows. Rollback removes only unchanged imported rows and restores only changed position fields; it refuses if subsequent user data depends on the imported records. It never deletes S3 objects, accounts, added schema or other-module rows. Keep backup-based recovery available for a later rollback requiring reconciliation.

The current adapter supports the approved baseline natural-language results. It refuses incremental-version caches rather than guessing their reference format. New baseline formats require an explicit adapter and another local rehearsal.

## Evidence
The private production-preparation directory contains actual PostgreSQL import/rollback, S3 staging and PDF/DOCX/TXT/OCR ingestion reports. Ingestion runs without CV evaluation. Cross-process advisory-lock tests prove exclusive ownership and crash release; browser polling resumes persisted running jobs. No live AWS writes or operational-local-database writes were used for these tests.
