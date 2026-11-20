"""add order_fees.note_raw (CLOVER_TIPS_INGESTION_001)

Revision ID: f4c9a2e7b1d3
Revises: e1a4c8f2b6d9
Create Date: 2026-09-05 00:00:00.000000

One additive, non-destructive change: a nullable `note_raw` column on
`order_fees`, preserving the exact Clover `note` string (e.g. "Service
Charge") a gratuity/service-charge line item carried, alongside the
already-existing derived `fee_type` classification
(`07 Tasks/Reports/CLOVER_TIPS_DATA_PROBE_001.md` / `CLOVER_TIPS_INGESTION_001`
task §5 — "persist enough provenance to know ... note").

No existing row is modified: every existing `order_fees` row gets
`note_raw = NULL`. The full-history rows already ingested by
`ingest_clover.py` are not backfilled by this migration (their classification
via `fee_type` remains exactly as ingested) — a future re-run of the full
Clover ingestion will populate `note_raw` for them going forward, per
`mapping.map_order_fee`'s own updated behavior.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4c9a2e7b1d3'
down_revision: Union[str, Sequence[str], None] = 'e1a4c8f2b6d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('order_fees', schema=None) as batch_op:
        batch_op.add_column(sa.Column('note_raw', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('order_fees', schema=None) as batch_op:
        batch_op.drop_column('note_raw')
