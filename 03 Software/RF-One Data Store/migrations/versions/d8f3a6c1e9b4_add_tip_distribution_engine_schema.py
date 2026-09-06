"""add Tip Distribution Engine schema (TIP_DISTRIBUTION_ENGINE_001)

Revision ID: d8f3a6c1e9b4
Revises: c4e8a1f6b3d9
Create Date: 2026-09-05 00:00:00.000000

Two additive changes:

1. Four new columns on `tip_distribution_rule_versions` (eligibility_mode,
   distribution_method, no_eligible_recipient_behavior, transaction_scope) —
   the rule structure task §6 requires. Backfilled via `server_default` to
   the only values the engine currently implements (ACTIVE_AT_SETTLEMENT /
   EQUAL / SOURCE_RETAINS / ALL) so any row already seeded before this
   migration (e.g. by `seed_tip_distribution_rules.py`) remains valid and
   consistent with what it actually configured.

2. Two new tables — `tip_distribution_calculation_runs` and
   `tip_distribution_allocations` — the Tip Distribution Engine's own
   calculation-run and atomic-allocation tables. Deliberately separate from
   the pre-existing `tip_calculation_runs`/`tip_allocations`/
   `tip_calculation_issues` (the still-operational legacy per-Payment
   TipPolicy engine, untouched by this migration).

No existing table is altered beyond the four additive columns above; no
existing row's meaning changes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8f3a6c1e9b4'
down_revision: Union[str, Sequence[str], None] = 'c4e8a1f6b3d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('tip_distribution_rule_versions', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'eligibility_mode', sa.String(length=32), nullable=False,
                server_default='ACTIVE_AT_SETTLEMENT',
            )
        )
        batch_op.add_column(
            sa.Column('distribution_method', sa.String(length=32), nullable=False, server_default='EQUAL')
        )
        batch_op.add_column(
            sa.Column(
                'no_eligible_recipient_behavior', sa.String(length=32), nullable=False,
                server_default='SOURCE_RETAINS',
            )
        )
        batch_op.add_column(
            sa.Column('transaction_scope', sa.String(length=32), nullable=False, server_default='ALL')
        )

    op.create_table(
        'tip_distribution_calculation_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('superseded_by_calculation_run_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.ForeignKeyConstraint(
            ['superseded_by_calculation_run_id'], ['tip_distribution_calculation_runs.id'],
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_tip_distribution_calculation_runs_restaurant_id'),
        'tip_distribution_calculation_runs', ['restaurant_id'], unique=False,
    )

    op.create_table(
        'tip_distribution_allocations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('calculation_run_id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('source_employee_id', sa.Integer(), nullable=True),
        sa.Column('rule_version_id', sa.Integer(), nullable=False),
        sa.Column('calculation_base', sa.String(length=32), nullable=False),
        sa.Column('rate', sa.Numeric(precision=7, scale=4), nullable=False),
        sa.Column('base_amount_minor', sa.Integer(), nullable=False),
        sa.Column('pool_amount_minor', sa.Integer(), nullable=False),
        sa.Column('recipient_employee_id', sa.Integer(), nullable=True),
        sa.Column('recipient_eligibility_basis', sa.Text(), nullable=False),
        sa.Column('no_eligible_recipient', sa.Boolean(), nullable=False),
        sa.Column('allocated_amount_minor', sa.Integer(), nullable=False),
        sa.Column('settlement_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['calculation_run_id'], ['tip_distribution_calculation_runs.id'], ),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.ForeignKeyConstraint(['source_employee_id'], ['employees.id'], ),
        sa.ForeignKeyConstraint(['rule_version_id'], ['tip_distribution_rule_versions.id'], ),
        sa.ForeignKeyConstraint(['recipient_employee_id'], ['employees.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'calculation_run_id', 'order_id', 'rule_version_id', 'recipient_employee_id',
            name='uq_tip_distribution_allocation_recipient',
        ),
    )
    op.create_index(
        op.f('ix_tip_distribution_allocations_calculation_run_id'),
        'tip_distribution_allocations', ['calculation_run_id'], unique=False,
    )
    op.create_index(
        op.f('ix_tip_distribution_allocations_order_id'), 'tip_distribution_allocations', ['order_id'], unique=False,
    )
    op.create_index(
        op.f('ix_tip_distribution_allocations_source_employee_id'),
        'tip_distribution_allocations', ['source_employee_id'], unique=False,
    )
    op.create_index(
        op.f('ix_tip_distribution_allocations_rule_version_id'),
        'tip_distribution_allocations', ['rule_version_id'], unique=False,
    )
    op.create_index(
        op.f('ix_tip_distribution_allocations_recipient_employee_id'),
        'tip_distribution_allocations', ['recipient_employee_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_tip_distribution_allocations_recipient_employee_id'), table_name='tip_distribution_allocations',
    )
    op.drop_index(
        op.f('ix_tip_distribution_allocations_rule_version_id'), table_name='tip_distribution_allocations',
    )
    op.drop_index(
        op.f('ix_tip_distribution_allocations_source_employee_id'), table_name='tip_distribution_allocations',
    )
    op.drop_index(op.f('ix_tip_distribution_allocations_order_id'), table_name='tip_distribution_allocations')
    op.drop_index(
        op.f('ix_tip_distribution_allocations_calculation_run_id'), table_name='tip_distribution_allocations',
    )
    op.drop_table('tip_distribution_allocations')

    op.drop_index(
        op.f('ix_tip_distribution_calculation_runs_restaurant_id'), table_name='tip_distribution_calculation_runs',
    )
    op.drop_table('tip_distribution_calculation_runs')

    with op.batch_alter_table('tip_distribution_rule_versions', schema=None) as batch_op:
        batch_op.drop_column('transaction_scope')
        batch_op.drop_column('no_eligible_recipient_behavior')
        batch_op.drop_column('distribution_method')
        batch_op.drop_column('eligibility_mode')
