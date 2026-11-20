"""add Selection Primary Screening Engine (Task 3D)

Revision ID: 4f9a1c7e3b6d
Revises: 2e6b8d1f4a9c
Create Date: 2026-09-02 00:00:00.000000

Additive, non-destructive changes implementing the RF-One Selection Task 3D
Primary Screening Engine (restaurant-configurable Criteria on a fixed 0-4
level scale, an internal-only Priority Index, Hard Disqualifiers, and
snapshot-safe historical traceability):

- `primary_screening_criteria` — restaurant-configurable Screening
  Criteria (task §1/§10), never a fixed universal list.
- `primary_screening_criterion_snapshots` — immutable, point-in-time
  copies of a Criterion (task §16), mirroring
  `requirement_snapshot_items`' own discipline at single-Criterion
  granularity.
- `primary_screening_runs` — one Primary Screening pass over one
  Application (task §17), holding the INTERNAL `priority_index` (never
  exposed to the Selezionatore) and Hard Disqualifier state.
- `primary_screening_criterion_evaluations` — one (Run, Criterion
  Snapshot) unit (task §13), with explicit uncertainty states (task §14)
  and full system-vs-effective / Hard-Disqualifier-override traceability
  (task §8/§15).

No existing table, row or column is altered in a way that loses data.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f9a1c7e3b6d'
down_revision: Union[str, Sequence[str], None] = '2e6b8d1f4a9c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'primary_screening_criteria',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=64), nullable=True),
        sa.Column('target_role', sa.String(length=64), nullable=True),
        sa.Column('location_label', sa.String(length=255), nullable=True),
        sa.Column('coefficient', sa.Float(), nullable=False, server_default='1.0'),
        sa.Column('direction', sa.String(length=16), nullable=False, server_default='POSITIVE'),
        sa.Column('is_hard_disqualifier', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('hard_disqualifier_trigger_level', sa.Integer(), nullable=True),
        sa.Column('level_descriptions', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('evidence_sources_allowed', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('evaluation_guidance', sa.Text(), nullable=True),
        sa.Column('evidence_positive', sa.Text(), nullable=True),
        sa.Column('evidence_contrary', sa.Text(), nullable=True),
        sa.Column('evidence_insufficient', sa.Text(), nullable=True),
        sa.Column('auto_evaluation_signal_definition_id', sa.Integer(), nullable=True),
        sa.Column('auto_evaluation_level_map', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.ForeignKeyConstraint(['auto_evaluation_signal_definition_id'], ['signal_definitions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_primary_screening_criteria_restaurant_id'), 'primary_screening_criteria', ['restaurant_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_primary_screening_criteria_target_role'), 'primary_screening_criteria', ['target_role'],
        unique=False,
    )

    op.create_table(
        'primary_screening_criterion_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('criterion_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=64), nullable=True),
        sa.Column('target_role', sa.String(length=64), nullable=True),
        sa.Column('location_label', sa.String(length=255), nullable=True),
        sa.Column('coefficient', sa.Float(), nullable=False),
        sa.Column('direction', sa.String(length=16), nullable=False),
        sa.Column('is_hard_disqualifier', sa.Boolean(), nullable=False),
        sa.Column('hard_disqualifier_trigger_level', sa.Integer(), nullable=True),
        sa.Column('level_descriptions', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('evidence_sources_allowed', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('evaluation_guidance', sa.Text(), nullable=True),
        sa.Column('evidence_positive', sa.Text(), nullable=True),
        sa.Column('evidence_contrary', sa.Text(), nullable=True),
        sa.Column('evidence_insufficient', sa.Text(), nullable=True),
        sa.Column('auto_evaluation_signal_definition_id', sa.Integer(), nullable=True),
        sa.Column('auto_evaluation_level_map', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('was_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['criterion_id'], ['primary_screening_criteria.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('criterion_id', 'version', name='uq_primary_screening_criterion_snapshot_version'),
    )
    op.create_index(
        op.f('ix_primary_screening_criterion_snapshots_criterion_id'), 'primary_screening_criterion_snapshots',
        ['criterion_id'], unique=False,
    )

    op.create_table(
        'primary_screening_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('priority_index', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('has_active_hard_disqualifier', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_primary_screening_runs_application_id'), 'primary_screening_runs', ['application_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_primary_screening_runs_restaurant_id'), 'primary_screening_runs', ['restaurant_id'], unique=False,
    )

    op.create_table(
        'primary_screening_criterion_evaluations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.Integer(), nullable=False),
        sa.Column('criterion_snapshot_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False, server_default='NOT_EVALUATED'),
        sa.Column('system_level', sa.Integer(), nullable=True),
        sa.Column('effective_level', sa.Integer(), nullable=True),
        sa.Column('confidence', sa.String(length=16), nullable=True),
        sa.Column('evidence_source', sa.String(length=32), nullable=True),
        sa.Column('evidence_text', sa.Text(), nullable=True),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('origin', sa.String(length=24), nullable=False, server_default='SYSTEM_GENERATED'),
        sa.Column('override_reason', sa.Text(), nullable=True),
        sa.Column('overridden_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('contribution', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('is_active_hard_disqualifier', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('hard_disqualifier_overridden', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('hard_disqualifier_override_reason', sa.Text(), nullable=True),
        sa.Column('hard_disqualifier_overridden_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['primary_screening_runs.id'], ),
        sa.ForeignKeyConstraint(['criterion_snapshot_id'], ['primary_screening_criterion_snapshots.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id', 'criterion_snapshot_id', name='uq_primary_screening_evaluation_run_snapshot'),
    )
    op.create_index(
        op.f('ix_primary_screening_criterion_evaluations_run_id'), 'primary_screening_criterion_evaluations',
        ['run_id'], unique=False,
    )
    op.create_index(
        op.f('ix_primary_screening_criterion_evaluations_criterion_snapshot_id'),
        'primary_screening_criterion_evaluations', ['criterion_snapshot_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_primary_screening_criterion_evaluations_criterion_snapshot_id'),
        table_name='primary_screening_criterion_evaluations',
    )
    op.drop_index(
        op.f('ix_primary_screening_criterion_evaluations_run_id'), table_name='primary_screening_criterion_evaluations',
    )
    op.drop_table('primary_screening_criterion_evaluations')

    op.drop_index(op.f('ix_primary_screening_runs_restaurant_id'), table_name='primary_screening_runs')
    op.drop_index(op.f('ix_primary_screening_runs_application_id'), table_name='primary_screening_runs')
    op.drop_table('primary_screening_runs')

    op.drop_index(
        op.f('ix_primary_screening_criterion_snapshots_criterion_id'), table_name='primary_screening_criterion_snapshots',
    )
    op.drop_table('primary_screening_criterion_snapshots')

    op.drop_index(op.f('ix_primary_screening_criteria_target_role'), table_name='primary_screening_criteria')
    op.drop_index(op.f('ix_primary_screening_criteria_restaurant_id'), table_name='primary_screening_criteria')
    op.drop_table('primary_screening_criteria')
