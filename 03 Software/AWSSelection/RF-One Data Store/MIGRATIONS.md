# Shared Database Migrations

RF-One services (rfone-web, rfone-selection, rfone-tips and the Clover
workers) share one database: RDS `rfone-dev` / `rfone` on AWS and, locally,
the canonical local working database. They also share one Alembic chain in
`migrations/versions/`. This document is the rule for keeping both coherent
without letting one Domain block another.

## The rule

**No service applies migrations to the shared database while it starts.**

A service starting, restarting or scaling never runs `alembic upgrade`. Schema
changes reach the shared database only through a deliberate release step (below).

## One chain

- The reference chain is what is applied on AWS. Its current revision is in
  [`migrations/aws_applied_revision.json`](migrations/aws_applied_revision.json).
- A revision applied on AWS is committed, byte-identical, to the shared chain the
  same day, together with the updated `aws_applied_revision.json`. Every release
  branch then takes that commit by cherry-pick (never by merging unrelated work).
- The chain has exactly one head. A branch that adds a migration sets its
  `down_revision` to the current AWS revision before release. A revision that was
  ever applied to a shared database is never edited, renamed or re-parented.
- A migration that must never run again moves to
  `90 Archive/Superseded Migrations/` with its origin and reason. It is not
  deleted and never moved back into `versions/`.

## How a migration is applied

1. RDS snapshot.
2. One short-lived task (ECS `rfone-jobs`) applies exactly the planned revisions
   from the expected starting revision, and refuses any other starting revision.
3. Record the result and update `aws_applied_revision.json`.

`run_migrations_to_head()` refuses any non-SQLite database unless
`RFONE_SCHEMA_MIGRATION_TARGET` names the tree's head revision. That variable
belongs only to the explicit migration step above, never to a service's
configuration.

A brand-new, empty, private SQLite file (tests, first local run) is still created
at head automatically (`prepare_new_private_database()`). An existing database
is never migrated by a service. Local databases are brought forward explicitly,
as a separate step, after a backup.

## What a service checks when it starts

Read-only, with `rfone_data_store/schema_compatibility.py`:

| Database state | Result |
|---|---|
| Every table and column the service's code maps is present, revision known | Starts |
| Same, but the revision is unknown to this code (another Domain applied a newer migration) | Starts, with a warning naming the revision |
| A mapped table or column is missing | Refuses to start (`IncompatibleSchemaError`) and applies nothing |

| Service | Required objects |
|---|---|
| Selection (`Selection/app.py`) | `Selection/workspace/schema.py`: the shared tables its code uses (`REQUIRED_TABLES`) plus its workspace tables |
| Clover workers (`clover_connector_release_check.py --database-readonly`) | Employee directory, context links and shifts (`CLOVER_REQUIRED_TABLES`) |
| Tips scheduler, Clover live sync, Clover correction sync | No migration at start (bootstrap of a new private SQLite file only) |

Tables of other Domains are not required, so a migration in Bank, Tips or
Interviews cannot stop Selection or Clover from starting.

## Build check

Every service Dockerfile runs `check_migration_chain.py`. The image is refused
when the tree has more than one head, a missing parent or a duplicate revision,
or when it does not contain the AWS revision. The buildspecs pass the
deployment bucket's `schema/aws_applied_revision.json` when it is published.
Otherwise the tree's own registry applies.

## Limits

- The start check verifies that tables and columns are present. It does not
  verify types, nullability or constraints.
- The rule assumes additive migrations. A change that code already running
  elsewhere cannot tolerate (a drop, a rename, a new NOT NULL column without a
  default) is a breaking release: every consuming service ships compatible code
  first, then the migration is applied.
