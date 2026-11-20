"""add purchased field corrections table

Revision ID: 879dbf90de9b
Revises: baf1fe9ef53a
Create Date: 2026-09-15 09:17:48.925453

"Purchased Human Review + Supplier Format Training UI": adds
`purchased_field_corrections`, the Human Review Model's own audit trail —
one row per field a human confirmed (CORRECT) or corrected
(INCORRECT/UNREAD/AMBIGUOUS -> a `corrected_value`). Purely additive — a
brand new table, no existing column changed, no existing row touched.
`PurchaseDocument`/`PurchaseLine`'s own columns are never written by this
migration or by anything built on top of this table (Task requirement 5:
"La source evidence resta immutabile") — see `models.PurchasedFieldCorrection`'s
own docstring.

Autogenerate also detected pre-existing, unrelated drift on Selection
tables (`applications`, `in_person_interview_plans`,
`phone_interview_plans`) — those are intentionally NOT included here (same
convention as `2747004fc651_add_legal_entities_table_and_.py` and
`baf1fe9ef53a_add_supplier_aliases_table.py`).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '879dbf90de9b'
down_revision: Union[str, Sequence[str], None] = 'baf1fe9ef53a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'purchased_field_corrections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('purchase_document_id', sa.Integer(), nullable=False),
        sa.Column('purchase_line_id', sa.Integer(), nullable=True),
        sa.Column('field_name', sa.String(length=64), nullable=False),
        sa.Column('classification', sa.String(length=16), nullable=False),
        sa.Column('original_value', sa.Text(), nullable=True),
        sa.Column('corrected_value', sa.Text(), nullable=True),
        sa.Column('reviewed_by', sa.String(length=255), nullable=False),
        sa.Column(
            'reviewed_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.CheckConstraint(
            "classification IN ('CORRECT', 'INCORRECT', 'UNREAD', 'AMBIGUOUS')",
            name='ck_purchased_field_corrections_classification',
        ),
        sa.ForeignKeyConstraint(['purchase_document_id'], ['purchase_documents.id'], name='fk_purchased_field_corrections_purchase_document_id'),
        sa.ForeignKeyConstraint(['purchase_line_id'], ['purchase_lines.id'], name='fk_purchased_field_corrections_purchase_line_id'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_purchased_field_corrections_purchase_document_id'), 'purchased_field_corrections',
        ['purchase_document_id'], unique=False,
    )
    op.create_index(
        op.f('ix_purchased_field_corrections_purchase_line_id'), 'purchased_field_corrections',
        ['purchase_line_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_purchased_field_corrections_purchase_line_id'), table_name='purchased_field_corrections')
    op.drop_index(op.f('ix_purchased_field_corrections_purchase_document_id'), table_name='purchased_field_corrections')
    op.drop_table('purchased_field_corrections')
