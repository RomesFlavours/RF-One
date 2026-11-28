"""allow the Mercury transactions export as a Bank import format

Revision ID: m1e120261120
Revises: w3c120261127
Create Date: 2026-11-20

BANK_MERCURY_CSV_001.

One widened CHECK constraint on `bank_import_batches.detected_format`: the
seven existing values stay exactly as they are and 'MERCURY' is added. No
table or column is added, removed or changed, and no row is touched.

`down_revision` is the revision the AWS database is stamped with on
27 Nov 2026 (`w3c120261127`, the drink card beers, read from `alembic_version`).
Written 20 Nov after `e9a120261117`; moved to the current head so it goes in
after every migration already on main. No other migration is edited.

PostgreSQL: the constraint is dropped and re-created in place inside the
migration's transaction. SQLite (local test databases): the same textual
rebuild approach as a9e6d3c71f24, refused if the table holds rows.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "m1e120261120"
down_revision: str | None = "w3c120261127"
branch_labels: str | None = None
depends_on: str | None = None

TABLE = "bank_import_batches"
CONSTRAINT = "ck_bank_import_batch_detected_format"
OLD_VALUES = ("'CHASE_BANK_ACCOUNT', 'CHASE_CREDIT_CARD_WITH_CARD', 'CHASE_CREDIT_CARD_NO_CARD', "
              "'FIRST_CITIZENS', 'AMEX_QBO', 'AMEX_XLSX', 'AMEX_CSV'")
NEW_VALUES = OLD_VALUES + ", 'MERCURY'"


def _rewrite(old_values: str, new_values: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint(CONSTRAINT, TABLE, type_="check")
        op.create_check_constraint(CONSTRAINT, TABLE, f"detected_format IN ({new_values})")
        return
    if bind.execute(sa.text(f"SELECT COUNT(*) FROM {TABLE}")).scalar():
        raise RuntimeError(f"{TABLE} holds rows; this migration will not rebuild it on SQLite.")
    create_sql = bind.execute(sa.text("SELECT sql FROM sqlite_master WHERE type='table' AND name=:n"),
                              {"n": TABLE}).scalar()
    old_check = f"detected_format IN ({old_values})"
    normalized = " ".join(create_sql.split())
    if normalized.count(" ".join(old_check.split())) != 1:
        raise RuntimeError(f"{TABLE} does not carry the expected format CHECK exactly once.")
    new_sql = normalized.replace(" ".join(old_check.split()), f"detected_format IN ({new_values})")
    op.execute(f"ALTER TABLE {TABLE} RENAME TO {TABLE}__old")
    op.execute(new_sql)
    op.execute(f"INSERT INTO {TABLE} SELECT * FROM {TABLE}__old")
    op.execute(f"DROP TABLE {TABLE}__old")


def upgrade() -> None:
    _rewrite(OLD_VALUES, NEW_VALUES)


def downgrade() -> None:
    # PostgreSQL refuses this by itself if a MERCURY batch exists.
    _rewrite(NEW_VALUES, OLD_VALUES)
