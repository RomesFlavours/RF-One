"""add Selection Trainable Gap (Task 5B)

Revision ID: f2a7c4e9b1d6
Revises: 33c870767fef
Create Date: 2026-09-04 00:00:00.000000

One new, additive table only. No existing table, column, or row is
altered. Mirrors the system/effective/origin/override_reason/overridden_at
quadruple already used by `requirement_assessments`,
`primary_screening_criterion_evaluations`, and `applications`
(review_priority_*) — see `rfone_data_store/models.py`'s `TrainableGap`
class docstring for the full rationale.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2a7c4e9b1d6'
down_revision: Union[str, Sequence[str], None] = '33c870767fef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        'trainable_gaps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('candidate_id', sa.Integer(), nullable=False),
        sa.Column('fit_assessment_id', sa.Integer(), nullable=False),
        sa.Column('requirement_assessment_id', sa.Integer(), nullable=False),
        sa.Column('missing_capability', sa.Text(), nullable=False),
        sa.Column('trainability', sa.String(length=24), nullable=False),
        sa.Column('source_fit_status', sa.String(length=32), nullable=False),
        sa.Column('importance', sa.String(length=16), nullable=True),
        sa.Column('rf_one_initial_level', sa.Integer(), nullable=False),
        sa.Column('selezionatore_initial_level', sa.Integer(), nullable=True),
        sa.Column('effective_initial_level', sa.Integer(), nullable=False),
        sa.Column('confidence', sa.String(length=16), nullable=True),
        sa.Column('origin', sa.String(length=24), nullable=False, server_default='SYSTEM_GENERATED'),
        sa.Column('override_reason', sa.Text(), nullable=True),
        sa.Column('overridden_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('overridden_by', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='ACTIVE'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ),
        sa.ForeignKeyConstraint(['fit_assessment_id'], ['fit_assessments.id'], ),
        sa.ForeignKeyConstraint(['requirement_assessment_id'], ['requirement_assessments.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('requirement_assessment_id', name='uq_trainable_gap_requirement_assessment'),
    )
    op.create_index(op.f('ix_trainable_gaps_application_id'), 'trainable_gaps', ['application_id'], unique=False)
    op.create_index(op.f('ix_trainable_gaps_candidate_id'), 'trainable_gaps', ['candidate_id'], unique=False)
    op.create_index(op.f('ix_trainable_gaps_fit_assessment_id'), 'trainable_gaps', ['fit_assessment_id'], unique=False)
    op.create_index(op.f('ix_trainable_gaps_requirement_assessment_id'), 'trainable_gaps', ['requirement_assessment_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(op.f('ix_trainable_gaps_requirement_assessment_id'), table_name='trainable_gaps')
    op.drop_index(op.f('ix_trainable_gaps_fit_assessment_id'), table_name='trainable_gaps')
    op.drop_index(op.f('ix_trainable_gaps_candidate_id'), table_name='trainable_gaps')
    op.drop_index(op.f('ix_trainable_gaps_application_id'), table_name='trainable_gaps')
    op.drop_table('trainable_gaps')
