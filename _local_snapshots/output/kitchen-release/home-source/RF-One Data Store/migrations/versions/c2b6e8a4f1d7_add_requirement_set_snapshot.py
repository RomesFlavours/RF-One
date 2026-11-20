"""add Selection Requirement Set immutable snapshot (TASK 3A-FIX)

Revision ID: c2b6e8a4f1d7
Revises: a7c3e9f2d5b8
Create Date: 2026-09-03 00:00:00.000000

Two additive, non-destructive tables so a later Fit Assessment (Task 3B)
can bind to an immutable, point-in-time copy of a `RequirementSet` instead
of its mutable live rows:

- `requirement_set_snapshots` — one row per (RequirementSet, version)
  captured, copying the set's own fields by value. Unique on
  (requirement_set_id, version) so re-requesting a snapshot for a version
  already captured returns the existing row rather than duplicating it.
- `requirement_snapshot_items` — one row per Requirement the set held at
  capture time, copying every field by value. `source_requirement_id` is
  deliberately NOT a foreign key — a snapshot must stay valid even if the
  live Requirement it was copied from later changes or is removed.

No existing table, row or column (Task 2A/2B/3A) is altered or dropped.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2b6e8a4f1d7'
down_revision: Union[str, Sequence[str], None] = 'a7c3e9f2d5b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'requirement_set_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('requirement_set_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('source_template_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('location_label', sa.String(length=255), nullable=True),
        sa.Column('target_role', sa.String(length=64), nullable=True),
        sa.Column('was_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['requirement_set_id'], ['requirement_sets.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('requirement_set_id', 'version', name='uq_requirement_set_snapshots_set_version'),
    )
    op.create_index(
        op.f('ix_requirement_set_snapshots_requirement_set_id'), 'requirement_set_snapshots',
        ['requirement_set_id'], unique=False,
    )

    op.create_table(
        'requirement_snapshot_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('snapshot_id', sa.Integer(), nullable=False),
        sa.Column('source_requirement_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=64), nullable=True),
        sa.Column('criticality', sa.String(length=16), nullable=False),
        sa.Column('trainability', sa.String(length=24), nullable=False),
        sa.Column('assessment_stages', sa.JSON(), nullable=False),
        sa.Column('evidence_positive', sa.Text(), nullable=True),
        sa.Column('evidence_contrary', sa.Text(), nullable=True),
        sa.Column('evidence_insufficient', sa.Text(), nullable=True),
        sa.Column('guidance_notes', sa.Text(), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('was_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(['snapshot_id'], ['requirement_set_snapshots.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_requirement_snapshot_items_snapshot_id'), 'requirement_snapshot_items', ['snapshot_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_requirement_snapshot_items_snapshot_id'), table_name='requirement_snapshot_items')
    op.drop_table('requirement_snapshot_items')

    op.drop_index(op.f('ix_requirement_set_snapshots_requirement_set_id'), table_name='requirement_set_snapshots')
    op.drop_table('requirement_set_snapshots')
