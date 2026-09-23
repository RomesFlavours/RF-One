"""widen import batch source formats for American Express

Revision ID: a9e6d3c71f24
Revises: f7c4a21e98b3
Create Date: 2026-09-23

BANK_HISTORICAL_CLEAN_CONSOLIDATE_AND_IMPORT_001 §7.

One widened CHECK constraint on `bank_import_batches.detected_format`. No
table is added, no column is added, removed, renamed or retyped, no row is
touched and nothing is inserted. `down_revision` is the actual single
Alembic head observed at the time of writing (`f7c4a21e98b3`), confirmed
through `alembic heads`. No earlier migration is edited.

Why
---
`detected_format` was constrained to the four CSV layouts RF-One could
parse when the table was created. American Express publishes the same
account in three further shapes — QBO/OFX, XLSX and CSV — and all three are
genuine structured financial sources that RF-One now parses:

    AMEX_QBO    carries FITID, the provider's own stable transaction id
    AMEX_XLSX   carries `Reference`, an id in the same namespace
    AMEX_CSV    carries neither, and falls back to canonical evidence

Refusing to record the batch would mean either importing Amex activity with
no provenance at all, or leaving real money out of the historical dataset.
Neither is acceptable, so the vocabulary is widened to match what RF-One can
actually read. The four original values are kept exactly as they were, so no
existing row could become invalid.

How, and why it is done this way
--------------------------------
SQLite cannot drop a CHECK constraint, so the table has to be recreated. The
obvious approach — re-declaring the table from a hand-written column list —
was tried and rejected: it silently dropped `uploaded_at`'s
`DEFAULT CURRENT_TIMESTAMP`, `row_count`'s and `status`'s defaults, narrowed
`detected_format` from VARCHAR(48) to VARCHAR(32), and lost
`uq_bank_import_batches_sha256` entirely. Every one of those is invisible in
a passing migration and every one breaks something later.

So this migration does not re-declare anything. It reads the table's OWN
`CREATE TABLE` statement out of `sqlite_master`, replaces the one CHECK
expression textually, and rebuilds from that. Everything the migration is
not deliberately changing is copied verbatim, because it is literally the
same SQL. The replacement is asserted to match exactly once, and the
migration refuses to run if the table does not look the way it expects.

On PostgreSQL none of this applies: the constraint is dropped and recreated
in place, with no rebuild at all.

Fenced the same way as the previous constraint widening in this repository:
the upgrade COUNTS THE ROWS FIRST and refuses to rebuild a table that
contains data.

Runs unchanged on an empty disposable database, on the local golden
database, and on AWS RDS through an ordinary `alembic upgrade head`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a9e6d3c71f24"
down_revision: str | None = "f7c4a21e98b3"
branch_labels: str | None = None
depends_on: str | None = None

TABLE = "bank_import_batches"

OLD_CHECK = (
    "CHECK (detected_format IN ('CHASE_BANK_ACCOUNT', 'CHASE_CREDIT_CARD_WITH_CARD', "
    "'CHASE_CREDIT_CARD_NO_CARD', 'FIRST_CITIZENS'))"
)
NEW_CHECK = (
    "CHECK (detected_format IN ('CHASE_BANK_ACCOUNT', 'CHASE_CREDIT_CARD_WITH_CARD', "
    "'CHASE_CREDIT_CARD_NO_CARD', 'FIRST_CITIZENS', 'AMEX_QBO', 'AMEX_XLSX', 'AMEX_CSV'))"
)
CONSTRAINT = "ck_bank_import_batch_detected_format"


def _rewrite(old_check: str, new_check: str) -> None:
    bind = op.get_bind()

    existing = bind.execute(sa.text(f"SELECT COUNT(*) FROM {TABLE}")).scalar() or 0
    if existing:
        raise RuntimeError(
            f"{TABLE} holds {existing} row(s). This migration widens a CHECK constraint and will "
            "not rebuild a table that contains data. Migrate those rows deliberately, then re-run."
        )

    if bind.dialect.name != "sqlite":
        op.drop_constraint(CONSTRAINT, TABLE, type_="check")
        op.create_check_constraint(CONSTRAINT, TABLE, new_check[len("CHECK ("):-1])
        return

    create_sql = bind.execute(
        sa.text("SELECT sql FROM sqlite_master WHERE type='table' AND name = :name"),
        {"name": TABLE},
    ).scalar()
    if not create_sql:
        raise RuntimeError(f"{TABLE} does not exist; nothing to widen.")

    # Whitespace in the stored DDL is not guaranteed, so compare on a
    # normalized form and operate on the original text.
    normalized = " ".join(create_sql.split())
    if normalized.count(" ".join(old_check.split())) != 1:
        raise RuntimeError(
            f"{TABLE} does not carry the expected format CHECK exactly once. Its current "
            f"definition is:\n{create_sql}\nRefusing to rebuild a table this migration does not "
            "recognise."
        )

    # Rebuild from the table's OWN definition with only the CHECK swapped,
    # so every default, type, foreign key and unique constraint survives
    # because it is the same SQL text.
    temporary = f"{TABLE}__rebuild"
    rebuilt = normalized.replace(
        " ".join(old_check.split()), " ".join(new_check.split()), 1,
    )
    # SQLite quotes the table name in the stored DDL after an
    # `ALTER TABLE ... RENAME TO`, so the statement may read either
    # `CREATE TABLE name (` or `CREATE TABLE "name" (`. Both spellings are
    # handled: matching only one of them would work on the first rebuild
    # and fail on the next, which is exactly how a downgrade path rots
    # unnoticed.
    for spelling in (f'CREATE TABLE {TABLE} ', f'CREATE TABLE "{TABLE}" '):
        if spelling in rebuilt:
            rebuilt = rebuilt.replace(spelling, f'CREATE TABLE "{temporary}" ', 1)
            break
    else:
        raise RuntimeError(
            f"Could not find {TABLE} in its own CREATE statement: {create_sql}"
        )

    columns = [
        row[1] for row in bind.execute(sa.text(f"PRAGMA table_info({TABLE})")).all()
    ]
    column_list = ", ".join(f'"{name}"' for name in columns)

    op.execute(rebuilt)
    op.execute(f'INSERT INTO "{temporary}" ({column_list}) SELECT {column_list} FROM "{TABLE}"')
    op.execute(f'DROP TABLE "{TABLE}"')
    op.execute(f'ALTER TABLE "{temporary}" RENAME TO "{TABLE}"')


def upgrade() -> None:
    _rewrite(OLD_CHECK, NEW_CHECK)


def downgrade() -> None:
    _rewrite(NEW_CHECK, OLD_CHECK)
