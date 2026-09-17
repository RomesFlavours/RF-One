"""add purchased line additions table

Revision ID: a1f4c7e9b2d5
Revises: 879dbf90de9b
Create Date: 2026-09-16 09:00:00.000000

"Close Purchased Human Review Reliability Gaps" §3: adds
`purchased_line_additions`, the audit trail for a `PurchaseLine` added
during Purchased Human Review when the original OCR/parser extraction
never created one at all. Purely additive — a brand new table, no
existing column changed, no existing row touched. `PurchaseLine` itself
gains no new column: whether a given `PurchaseLine` row is original
source evidence or a later human addition is derived by checking for a
matching row here (same "Persist Facts — Derive Calculations" convention
`get_document_functional_status()` already uses for NORMALIZED/HUMAN) —
see `models.PurchasedLineAddition`'s own docstring.

Autogenerate also detected pre-existing, unrelated drift on Selection
tables (`applications`, `in_person_interview_plans`,
`phone_interview_plans`) — those are intentionally NOT included here (same
convention as `879dbf90de9b_add_purchased_field_corrections_table.py` and
earlier migrations).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f4c7e9b2d5'
down_revision: Union[str, Sequence[str], None] = '879dbf90de9b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'purchased_line_additions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('purchase_document_id', sa.Integer(), nullable=False),
        sa.Column('purchase_line_id', sa.Integer(), nullable=False),
        sa.Column('added_by', sa.String(length=255), nullable=False),
        sa.Column(
            'added_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['purchase_document_id'], ['purchase_documents.id'], name='fk_purchased_line_additions_purchase_document_id'),
        sa.ForeignKeyConstraint(['purchase_line_id'], ['purchase_lines.id'], name='fk_purchased_line_additions_purchase_line_id'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('purchase_line_id', name='uq_purchased_line_additions_purchase_line_id'),
    )
    op.create_index(
        op.f('ix_purchased_line_additions_purchase_document_id'), 'purchased_line_additions',
        ['purchase_document_id'], unique=False,
    )
    op.create_index(
        op.f('ix_purchased_line_additions_purchase_line_id'), 'purchased_line_additions',
        ['purchase_line_id'], unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_purchased_line_additions_purchase_line_id'), table_name='purchased_line_additions')
    op.drop_index(op.f('ix_purchased_line_additions_purchase_document_id'), table_name='purchased_line_additions')
    op.drop_table('purchased_line_additions')
