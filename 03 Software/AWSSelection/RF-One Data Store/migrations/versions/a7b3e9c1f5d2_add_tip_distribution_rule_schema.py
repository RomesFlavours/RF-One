"""add Tip Distribution Rule schema (TIPS_DISTRIBUTION_RULES_001)

Revision ID: a7b3e9c1f5d2
Revises: f4c9a2e7b1d3
Create Date: 2026-09-05 00:00:00.000000

New, additive-only schema: `tip_distribution_rules` (the stable, restaurant-
scoped rule identity, plus its `is_active` toggle) and
`tip_distribution_rule_versions` (append-only, effective-dated configuration
snapshots — never updated/deleted once created). Deliberately separate from
the pre-existing `tip_policies`/`tip_policy_components` tables; no existing
table is altered by this migration.

See `01 Domains/Business Domain/Restaurant/Functional Specifications/
TIP_DISTRIBUTION_ENGINE_FUNCTIONAL_SPEC_001.md` §7-§9/§16 and
`07 Tasks/Reports/TIPS_DISTRIBUTION_RULES_001_REPORT.md`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b3e9c1f5d2'
down_revision: Union[str, Sequence[str], None] = 'f4c9a2e7b1d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'tip_distribution_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_tip_distribution_rules_restaurant_id'), 'tip_distribution_rules', ['restaurant_id'], unique=False,
    )

    op.create_table(
        'tip_distribution_rule_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('rule_id', sa.Integer(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('source_role_id', sa.Integer(), nullable=False),
        sa.Column('recipient_role_id', sa.Integer(), nullable=False),
        sa.Column('calculation_base', sa.String(length=32), nullable=False),
        sa.Column('rate', sa.Numeric(precision=7, scale=4), nullable=False),
        sa.Column('effective_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('effective_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint(
            "calculation_base IN ('VOLUNTARY_TIP','GRATUITY','TIP_PLUS_GRATUITY','TOTAL_SALES','FOOD_SALES',"
            "'BEVERAGE_SALES')",
            name='ck_tip_distribution_rule_version_calculation_base',
        ),
        sa.ForeignKeyConstraint(['recipient_role_id'], ['restaurant_roles.id'], ),
        sa.ForeignKeyConstraint(['rule_id'], ['tip_distribution_rules.id'], ),
        sa.ForeignKeyConstraint(['source_role_id'], ['restaurant_roles.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rule_id', 'version_number', name='uq_tip_distribution_rule_version_number'),
    )
    op.create_index(
        op.f('ix_tip_distribution_rule_versions_rule_id'), 'tip_distribution_rule_versions', ['rule_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_tip_distribution_rule_versions_rule_id'), table_name='tip_distribution_rule_versions')
    op.drop_table('tip_distribution_rule_versions')
    op.drop_index(op.f('ix_tip_distribution_rules_restaurant_id'), table_name='tip_distribution_rules')
    op.drop_table('tip_distribution_rules')
