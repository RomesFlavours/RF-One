# Selection migration preparation

These tools compare the verified AWS backups with a consistent snapshot of the current local database. They do not use AWS credentials, call AWS APIs, or import data into a live database.

- `prepare.py --archive <private-backup-folder> --local-database <existing-local-sqlite>` reads both restored PostgreSQL databases on loopback port 55479 and produces a private review package. It snapshots SQLite using a read-only source connection. The package contains schema comparisons, checksummed document matches, decision CSVs and draft additive SQL ending in `ROLLBACK`.
- `rehearse_schema.py --review <review-package>` creates a **new local clone** of `rfone_current_verify`, checks that it is running in the archive's isolated PostgreSQL cluster, rehearses the additive schema changes and verifies compatibility with the local application's ORM. It preserves and compares all existing table counts and the AWS Alembic revision. No business data merge is performed.
- `validate_choices.py --review <review-package>` validates the edited mapping decisions. An incomplete package exits with status 2. Completing choices does not import data or authorize deployment; the next gate remains a separate data-import rehearsal.

The review package contains candidate information and a local database snapshot. Keep it outside Git. Do not point the tools at cloud addresses, substitute production connection URLs, reset the shared Alembic revision to the local one, or restore the SQLite database over PostgreSQL.

Preserve existing AWS identifiers, users and domain permissions. Namespace identifiers from each source, map organization/role/site/position ownership explicitly, and allocate fresh target identifiers for local records. Exact CV bytes can identify the same document; names alone never authorize merging people. Keep legacy judgments and completed interviews as history, preserve successful action executions, and never dispatch mail, rerun AI or retry old jobs during migration.

The observed document buckets are also used by Trainer, Kitchen Call and the development journal. Their names do not establish exclusive Selection ownership. Never delete a whole shared bucket as part of retiring an old Selection service.
