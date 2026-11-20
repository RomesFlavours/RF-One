"""add ingestion_runs.lock_key (TIPS_IMPORT_CONCURRENCY_GUARD_001)

Revision ID: c4e8a1f6b3d9
Revises: a7b3e9c1f5d2
Create Date: 2026-09-05 00:00:00.000000

One additive, non-destructive change: a nullable `lock_key` column on
`ingestion_runs`, plus a UNIQUE index on it. Existing rows get
`lock_key = NULL` (SQLite/ANSI SQL treat multiple NULLs in a UNIQUE index as
distinct, so this never conflicts with historical rows).

`lock_key` is the execution guard's token (task §5): an import execution
sets it to a non-NULL value for as long as (and only as long as) it is
RUNNING, and clears it back to NULL on COMPLETE/PARTIAL/FAILED. The UNIQUE
index turns "is another same-scope import already running" into a
DB-enforced constraint instead of an application-level check-then-act race.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e8a1f6b3d9'
down_revision: Union[str, Sequence[str], None] = 'a7b3e9c1f5d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('ingestion_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('lock_key', sa.String(length=128), nullable=True))
        batch_op.create_index('ix_ingestion_runs_lock_key', ['lock_key'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('ingestion_runs', schema=None) as batch_op:
        batch_op.drop_index('ix_ingestion_runs_lock_key')
        batch_op.drop_column('lock_key')
