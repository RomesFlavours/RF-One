"""add ingestion_runs.requested_by_account_id (CLOVER_ACQUISITION_IDENTITY_001)

Revision ID: c9e5a3b7d2f1
Revises: b8d4e2f7a1c9
Create Date: 2026-09-26 18:00:00.000000

Additive, non-destructive. A manual Clover acquisition (Sync Now,
Historical Backfill) may now be started only by a signed-in RF-One account
holding the CLOVER_ACQUISITION access; the job records WHICH account, as a
reference to the existing `rfone_accounts` row — never a typed name.

NULL means "no person requested it": every run recorded before this change,
and any automatic acquisition (Live Sync, once enabled) — kept distinct from
a manual request without inventing today how an automatic system identity
will eventually be represented.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9e5a3b7d2f1'
down_revision: Union[str, Sequence[str], None] = 'b8d4e2f7a1c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('ingestion_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('requested_by_account_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_ingestion_runs_requested_by_account_id', 'rfone_accounts', ['requested_by_account_id'], ['id'],
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('ingestion_runs', schema=None) as batch_op:
        batch_op.drop_constraint('fk_ingestion_runs_requested_by_account_id', type_='foreignkey')
        batch_op.drop_column('requested_by_account_id')
