"""add Selection Candidate Fit Assessment (TASK 3B)

Revision ID: e5a1c8d3f6b2
Revises: c2b6e8a4f1d7
Create Date: 2026-09-04 00:00:00.000000

Three additive, non-destructive tables implementing evidence-based
Candidate Fit Assessment (01 Domains/Cross Domain/Selection/FitAssessment.md):

- `fit_assessments` — one evaluation run of one candidate against one
  immutable `RequirementSetSnapshot` (never a live `RequirementSet`).
- `requirement_assessments` — the fundamental Candidate x
  RequirementSnapshotItem unit; unique per (fit_assessment, snapshot item).
- `evidence_items` — append-only evidence attached to one
  RequirementAssessment; multiple/conflicting items always coexist.

No existing table, row or column (Task 2A/2B/3A/3A-FIX) is altered or
dropped.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5a1c8d3f6b2'
down_revision: Union[str, Sequence[str], None] = 'c2b6e8a4f1d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'fit_assessments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('candidate_id', sa.Integer(), nullable=False),
        sa.Column('requirement_set_snapshot_id', sa.Integer(), nullable=False),
        sa.Column('requirement_set_id', sa.Integer(), nullable=True),
        sa.Column('current_stage', sa.String(length=24), nullable=False, server_default='RESUME'),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='ACTIVE'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ),
        sa.ForeignKeyConstraint(['requirement_set_snapshot_id'], ['requirement_set_snapshots.id'], ),
        sa.ForeignKeyConstraint(['requirement_set_id'], ['requirement_sets.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fit_assessments_candidate_id'), 'fit_assessments', ['candidate_id'], unique=False)
    op.create_index(
        op.f('ix_fit_assessments_requirement_set_snapshot_id'), 'fit_assessments',
        ['requirement_set_snapshot_id'], unique=False,
    )
    op.create_index(
        op.f('ix_fit_assessments_requirement_set_id'), 'fit_assessments', ['requirement_set_id'], unique=False
    )

    op.create_table(
        'requirement_assessments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fit_assessment_id', sa.Integer(), nullable=False),
        sa.Column('requirement_snapshot_item_id', sa.Integer(), nullable=False),
        sa.Column('stage', sa.String(length=24), nullable=False, server_default='RESUME'),
        sa.Column('system_status', sa.String(length=32), nullable=False),
        sa.Column('effective_status', sa.String(length=32), nullable=False),
        sa.Column('confidence', sa.String(length=16), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('origin', sa.String(length=24), nullable=False, server_default='SYSTEM_GENERATED'),
        sa.Column('override_reason', sa.Text(), nullable=True),
        sa.Column('overridden_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['fit_assessment_id'], ['fit_assessments.id'], ),
        sa.ForeignKeyConstraint(['requirement_snapshot_item_id'], ['requirement_snapshot_items.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'fit_assessment_id', 'requirement_snapshot_item_id', name='uq_requirement_assessment_fit_item'
        ),
    )
    op.create_index(
        op.f('ix_requirement_assessments_fit_assessment_id'), 'requirement_assessments', ['fit_assessment_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_requirement_assessments_requirement_snapshot_item_id'), 'requirement_assessments',
        ['requirement_snapshot_item_id'], unique=False,
    )

    op.create_table(
        'evidence_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('requirement_assessment_id', sa.Integer(), nullable=False),
        sa.Column('source_type', sa.String(length=32), nullable=False),
        sa.Column('source_stage', sa.String(length=24), nullable=True),
        sa.Column('source_reference', sa.String(length=255), nullable=True),
        sa.Column('evidence_text', sa.Text(), nullable=True),
        sa.Column('evidence_classification', sa.String(length=24), nullable=False),
        sa.Column('evidence_relationship', sa.String(length=16), nullable=False),
        sa.Column('confidence', sa.String(length=16), nullable=False, server_default='UNKNOWN'),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('is_system_generated', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['requirement_assessment_id'], ['requirement_assessments.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_evidence_items_requirement_assessment_id'), 'evidence_items', ['requirement_assessment_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_evidence_items_requirement_assessment_id'), table_name='evidence_items')
    op.drop_table('evidence_items')

    op.drop_index(
        op.f('ix_requirement_assessments_requirement_snapshot_item_id'), table_name='requirement_assessments'
    )
    op.drop_index(op.f('ix_requirement_assessments_fit_assessment_id'), table_name='requirement_assessments')
    op.drop_table('requirement_assessments')

    op.drop_index(op.f('ix_fit_assessments_requirement_set_id'), table_name='fit_assessments')
    op.drop_index(op.f('ix_fit_assessments_requirement_set_snapshot_id'), table_name='fit_assessments')
    op.drop_index(op.f('ix_fit_assessments_candidate_id'), table_name='fit_assessments')
    op.drop_table('fit_assessments')
