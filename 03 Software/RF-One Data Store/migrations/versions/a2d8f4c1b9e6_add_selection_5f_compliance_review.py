"""add Selection 5F compliance review + explainability (Task 5F)

Revision ID: a2d8f4c1b9e6
Revises: f7c3a9d1e6b4
Create Date: 2026-09-05 00:00:00.000000

Three new, additive tables (compliance_reviews, compliance_warnings,
compliance_dispositions). No existing table/column is altered — the
Selection Audit/Explainability Report is a pure read-time aggregation over
already-existing data and requires no schema change of its own.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2d8f4c1b9e6'
down_revision: Union[str, Sequence[str], None] = 'f7c3a9d1e6b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        'compliance_reviews',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('object_type', sa.String(length=48), nullable=False),
        sa.Column('object_id', sa.Integer(), nullable=False),
        sa.Column('object_version', sa.Integer(), nullable=False),
        sa.Column('reviewed_text', sa.Text(), nullable=False),
        sa.Column('engine_version', sa.String(length=64), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_compliance_reviews_object_type'), 'compliance_reviews', ['object_type'], unique=False)
    op.create_index(op.f('ix_compliance_reviews_object_id'), 'compliance_reviews', ['object_id'], unique=False)

    op.create_table(
        'compliance_warnings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('review_id', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(length=48), nullable=False),
        sa.Column('severity', sa.String(length=16), nullable=False),
        sa.Column('explanation', sa.Text(), nullable=False),
        sa.Column('suggested_rewrite', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['review_id'], ['compliance_reviews.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_compliance_warnings_review_id'), 'compliance_warnings', ['review_id'], unique=False)

    op.create_table(
        'compliance_dispositions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('review_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=32), nullable=False),
        sa.Column('final_text', sa.Text(), nullable=True),
        sa.Column('performed_by', sa.String(length=255), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['review_id'], ['compliance_reviews.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_compliance_dispositions_review_id'), 'compliance_dispositions', ['review_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(op.f('ix_compliance_dispositions_review_id'), table_name='compliance_dispositions')
    op.drop_table('compliance_dispositions')

    op.drop_index(op.f('ix_compliance_warnings_review_id'), table_name='compliance_warnings')
    op.drop_table('compliance_warnings')

    op.drop_index(op.f('ix_compliance_reviews_object_id'), table_name='compliance_reviews')
    op.drop_index(op.f('ix_compliance_reviews_object_type'), table_name='compliance_reviews')
    op.drop_table('compliance_reviews')
