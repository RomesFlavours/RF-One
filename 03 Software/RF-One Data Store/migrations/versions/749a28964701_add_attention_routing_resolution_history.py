"""add attention_routing_resolutions audit trail (TASK_ORG_RUNTIME_CONSISTENCY_FIXES)

Revision ID: 749a28964701
Revises: 4afdc598f407
Create Date: 2026-09-13 00:00:00.000000

One additive, non-destructive new table: `attention_routing_resolutions` —
an append-only history of every `route_attention()` evaluation for an
Attention Item, so a re-evaluation ("Re-evaluate routing now") never
destroys the record of a prior resolution. `AttentionItem`'s own
`resolved_*`/`resolution_path` columns are unchanged and continue to hold
only the latest snapshot.

No existing table or row is affected by this migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '749a28964701'
down_revision: Union[str, Sequence[str], None] = '4afdc598f407'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'attention_routing_resolutions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('attention_item_id', sa.Integer(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('owner_position_id', sa.Integer(), nullable=True),
        sa.Column('resolved_recipient_acting_identity_id', sa.Integer(), nullable=True),
        sa.Column('resolution_path', sa.String(length=32), nullable=True),
        sa.Column('unresolved_reason', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['attention_item_id'], ['attention_items.id'], ),
        sa.ForeignKeyConstraint(['owner_position_id'], ['positions.id'], ),
        sa.ForeignKeyConstraint(['resolved_recipient_acting_identity_id'], ['acting_identities.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_attention_routing_resolutions_attention_item_id'),
        'attention_routing_resolutions', ['attention_item_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_attention_routing_resolutions_attention_item_id'), table_name='attention_routing_resolutions')
    op.drop_table('attention_routing_resolutions')
