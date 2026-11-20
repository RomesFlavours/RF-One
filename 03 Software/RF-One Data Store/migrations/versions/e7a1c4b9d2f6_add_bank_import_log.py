"""add the import log of a Bank import batch

Revision ID: e7a1c4b9d2f6
Revises: d4f2b8a6c1e3
Create Date: 2026-10-07

BANK_TWO_PASS_IMPORT_001. ADDITIVE, no data change.

  * `bank_import_batches.import_log` (TEXT, JSON): the person's decisions at
    import — rows excluded or authorized as distinct operations, each with
    the reason and the stored transaction or upload row it resembled.
    Existing batches have none.

Downgrade drops the column (natively, without rebuilding the table).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e7a1c4b9d2f6'
down_revision: Union[str, Sequence[str], None] = 'd4f2b8a6c1e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Native ADD / DROP COLUMN on both dialects — never a batch rebuild: a
# rebuild of this table rewrites its DDL (defaults, constraint order), which
# a9e6d3c71f24 documents and avoids. SQLite >= 3.35 drops a column natively.


def upgrade() -> None:
    op.add_column("bank_import_batches", sa.Column("import_log", sa.Text(), nullable=True))


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute("ALTER TABLE bank_import_batches DROP COLUMN import_log")
    else:
        op.drop_column("bank_import_batches", "import_log")
