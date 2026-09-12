"""add backup position, organizational fallback policy, position.backup_required, attention_items.resolution_path (TASK_ORG_CHART_ADMIN_PAGE)

Revision ID: 4afdc598f407
Revises: a6aed1d9d2ed
Create Date: 2026-09-12 00:00:00.000000

Additive, non-destructive changes supporting the Organizational Chart Admin
Page's Backup Position and Organizational Fallback Policy concepts
(`10 System/Organizational Responsibility and Attention Management/README.md`):

- `position_backups` — an ordered Backup Position chain per Position,
  distinct from `position_temporary_coverages`.
- `organizational_fallback_policies` — company-configured fallback
  ("Unowned Attention -> CEO" for Rome's Flavours, never a Core rule).
- `positions.backup_required` — opt-in policy flag (default False) so the
  Organizational Coverage Check only flags a missing backup where an admin
  has actually required one.
- `attention_items.resolution_path` — records which resolution step
  actually produced the recipient (direct occupant / temporary coverage /
  backup / organizational fallback).

No existing row is affected — the two new columns are added with safe
defaults/nullable, and the two new tables start empty.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4afdc598f407'
down_revision: Union[str, Sequence[str], None] = 'a6aed1d9d2ed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POSITION_SCOPE_KINDS = (
    'CORPORATE', 'BRAND', 'LEGAL_ENTITY', 'OPERATIONAL_UNIT', 'RESTAURANT', 'OPERATIONAL_AREA',
    'DOMAIN', 'MODULE', 'PROCESS', 'PROCESS_PHASE', 'GLOBAL',
)


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('positions') as batch_op:
        batch_op.add_column(sa.Column('backup_required', sa.Boolean(), nullable=False, server_default=sa.text('0')))

    with op.batch_alter_table('attention_items') as batch_op:
        batch_op.add_column(sa.Column('resolution_path', sa.String(length=32), nullable=True))

    op.create_table(
        'position_backups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('covered_position_id', sa.Integer(), nullable=False),
        sa.Column('backup_position_id', sa.Integer(), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint('covered_position_id != backup_position_id', name='ck_position_backup_not_self'),
        sa.ForeignKeyConstraint(['covered_position_id'], ['positions.id'], ),
        sa.ForeignKeyConstraint(['backup_position_id'], ['positions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('covered_position_id', 'sequence', name='uq_position_backup_sequence'),
    )
    op.create_index(op.f('ix_position_backups_covered_position_id'), 'position_backups', ['covered_position_id'], unique=False)

    op.create_table(
        'organizational_fallback_policies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scope_type', sa.String(length=32), nullable=False),
        sa.Column('scope_id', sa.Integer(), nullable=True),
        sa.Column('scope_key', sa.String(length=128), nullable=True),
        sa.Column('fallback_position_id', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint(f"scope_type IN {POSITION_SCOPE_KINDS!r}", name='ck_organizational_fallback_scope_type'),
        sa.ForeignKeyConstraint(['fallback_position_id'], ['positions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('organizational_fallback_policies')
    op.drop_index(op.f('ix_position_backups_covered_position_id'), table_name='position_backups')
    op.drop_table('position_backups')
    with op.batch_alter_table('attention_items') as batch_op:
        batch_op.drop_column('resolution_path')
    with op.batch_alter_table('positions') as batch_op:
        batch_op.drop_column('backup_required')
