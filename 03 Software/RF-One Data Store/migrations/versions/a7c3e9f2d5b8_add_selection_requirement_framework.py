"""add Selection requirement framework (TASK 3A)

Revision ID: a7c3e9f2d5b8
Revises: f4d8e2a1c6b3
Create Date: 2026-09-02 00:00:00.000000

One additive, non-destructive change: four new tables for the Selection
Requirement Framework (01 Domains/Cross Domain/Selection/SelectionRequirement.md) —
`requirement_templates`, `requirement_template_items`, `requirement_sets`,
`requirements`. Defines WHAT a restaurant is looking for; no candidate or
Fit Assessment table is added (out of scope for Task 3A).

No existing table, row or column is affected by this migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c3e9f2d5b8'
down_revision: Union[str, Sequence[str], None] = 'f4d8e2a1c6b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'requirement_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('intended_role', sa.String(length=64), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_requirement_templates_intended_role'), 'requirement_templates', ['intended_role'], unique=False
    )

    op.create_table(
        'requirement_template_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=False),
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
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(['template_id'], ['requirement_templates.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_requirement_template_items_template_id'), 'requirement_template_items', ['template_id'],
        unique=False,
    )

    op.create_table(
        'requirement_sets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('source_template_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('location_label', sa.String(length=255), nullable=True),
        sa.Column('target_role', sa.String(length=64), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.ForeignKeyConstraint(['source_template_id'], ['requirement_templates.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_requirement_sets_restaurant_id'), 'requirement_sets', ['restaurant_id'], unique=False)
    op.create_index(
        op.f('ix_requirement_sets_source_template_id'), 'requirement_sets', ['source_template_id'], unique=False
    )
    op.create_index(op.f('ix_requirement_sets_target_role'), 'requirement_sets', ['target_role'], unique=False)

    op.create_table(
        'requirements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('requirement_set_id', sa.Integer(), nullable=False),
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
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['requirement_set_id'], ['requirement_sets.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_requirements_requirement_set_id'), 'requirements', ['requirement_set_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_requirements_requirement_set_id'), table_name='requirements')
    op.drop_table('requirements')

    op.drop_index(op.f('ix_requirement_sets_target_role'), table_name='requirement_sets')
    op.drop_index(op.f('ix_requirement_sets_source_template_id'), table_name='requirement_sets')
    op.drop_index(op.f('ix_requirement_sets_restaurant_id'), table_name='requirement_sets')
    op.drop_table('requirement_sets')

    op.drop_index(op.f('ix_requirement_template_items_template_id'), table_name='requirement_template_items')
    op.drop_table('requirement_template_items')

    op.drop_index(op.f('ix_requirement_templates_intended_role'), table_name='requirement_templates')
    op.drop_table('requirement_templates')
