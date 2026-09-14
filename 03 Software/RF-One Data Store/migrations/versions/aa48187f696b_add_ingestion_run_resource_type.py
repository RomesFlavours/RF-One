"""add ingestion_runs.resource_type (CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE §4)

Revision ID: aa48187f696b
Revises: 09ed62634a09
Create Date: 2026-09-13 00:00:00.000000

One additive, non-destructive change: a nullable `resource_type` column on
`ingestion_runs`, the Modification Cursor's Location × Resource granularity
(CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md §4). Every existing row
(every Historical Backfill and Live Sync run ever recorded) gets
`resource_type = NULL`, preserving its exact current meaning — one
whole-Location run per cycle. Only the new Correction/Reconciliation Poller
(`technical/connectors/clover/correction_sync.py`) ever sets it (e.g.
"orders", "payments", "refunds"), one new row per resource per correction
cycle, reusing this existing table rather than introducing a new one.

`live_sync.compute_next_sync_window` and `freshness._is_range_covered` are
both updated (same change) to filter `resource_type IS NULL`, so this
addition cannot silently change the meaning of the existing Live Cursor or
freshness-coverage checks for any row already in the table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aa48187f696b'
down_revision: Union[str, Sequence[str], None] = '09ed62634a09'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('ingestion_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('resource_type', sa.String(length=32), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('ingestion_runs', schema=None) as batch_op:
        batch_op.drop_column('resource_type')
