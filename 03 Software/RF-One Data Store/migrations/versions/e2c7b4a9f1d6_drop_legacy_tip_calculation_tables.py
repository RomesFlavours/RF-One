"""drop legacy Tip calculation tables (TIPS_LEGACY_ENGINE_RETIREMENT_001)

Revision ID: e2c7b4a9f1d6
Revises: d8f3a6c1e9b4
Create Date: 2026-09-05 00:00:00.000000

Retires the legacy Payment-level `tips/engine.py` calculation engine's own
RESULT tables — `tip_calculation_runs`, `tip_allocations`,
`tip_calculation_issues` — now that the canonical, Order-level Tip
Distribution Engine (`tips/distribution_engine.py`,
`tip_distribution_calculation_runs`/`tip_distribution_allocations`) is the
only active calculation path.

Confirmed EMPTY (0 rows each) in the operational database at retirement
time — unlike `tip_policies`/`tip_policy_components` (which hold Rome's
Flavours' real historical configuration and are deliberately NOT touched by
this migration; they remain as read-only legacy history, per
`07 Tasks/Reports/TIPS_LEGACY_ENGINE_RETIREMENT_001.md`). Dropping empty
tables loses no data.

Drop order respects FK dependencies: `tip_allocations` and
`tip_calculation_issues` both reference `tip_calculation_runs`, so both are
dropped before their parent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2c7b4a9f1d6'
down_revision: Union[str, Sequence[str], None] = 'd8f3a6c1e9b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index(op.f('ix_tip_allocations_policy_component_id'), table_name='tip_allocations')
    op.drop_index(op.f('ix_tip_allocations_payment_tip_id'), table_name='tip_allocations')
    op.drop_index(op.f('ix_tip_allocations_payment_id'), table_name='tip_allocations')
    op.drop_index(op.f('ix_tip_allocations_order_id'), table_name='tip_allocations')
    op.drop_index(op.f('ix_tip_allocations_employee_id'), table_name='tip_allocations')
    op.drop_index(op.f('ix_tip_allocations_calculation_run_id'), table_name='tip_allocations')
    op.drop_table('tip_allocations')

    op.drop_index(op.f('ix_tip_calculation_issues_payment_tip_id'), table_name='tip_calculation_issues')
    op.drop_index(op.f('ix_tip_calculation_issues_payment_id'), table_name='tip_calculation_issues')
    op.drop_index(op.f('ix_tip_calculation_issues_order_id'), table_name='tip_calculation_issues')
    op.drop_index(op.f('ix_tip_calculation_issues_calculation_run_id'), table_name='tip_calculation_issues')
    op.drop_table('tip_calculation_issues')

    with op.batch_alter_table('tip_calculation_runs', schema=None) as batch_op:
        batch_op.drop_constraint(
            'fk_tip_calculation_runs_superseded_by_calculation_run_id', type_='foreignkey'
        )
    op.drop_index(op.f('ix_tip_calculation_runs_restaurant_id'), table_name='tip_calculation_runs')
    op.drop_table('tip_calculation_runs')


def downgrade() -> None:
    """Downgrade schema — recreates the exact shape these tables had
    immediately before this migration (base schema from `dc31a1741fd8` plus
    the `superseded_by_calculation_run_id` column from `09631adaed4d`)."""
    op.create_table(
        'tip_calculation_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('mode', sa.String(length=16), nullable=False),
        sa.Column('calculation_version', sa.String(length=64), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('superseded_by_calculation_run_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.ForeignKeyConstraint(
            ['superseded_by_calculation_run_id'], ['tip_calculation_runs.id'],
            name='fk_tip_calculation_runs_superseded_by_calculation_run_id',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tip_calculation_runs_restaurant_id'), 'tip_calculation_runs', ['restaurant_id'], unique=False)

    op.create_table(
        'tip_calculation_issues',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('calculation_run_id', sa.Integer(), nullable=False),
        sa.Column('payment_tip_id', sa.Integer(), nullable=True),
        sa.Column('payment_id', sa.Integer(), nullable=True),
        sa.Column('order_id', sa.Integer(), nullable=True),
        sa.Column('issue_type', sa.String(length=64), nullable=False),
        sa.Column('severity', sa.String(length=16), nullable=False),
        sa.Column('details', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['calculation_run_id'], ['tip_calculation_runs.id'], ),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], ),
        sa.ForeignKeyConstraint(['payment_tip_id'], ['payment_tips.payment_id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tip_calculation_issues_calculation_run_id'), 'tip_calculation_issues', ['calculation_run_id'], unique=False)
    op.create_index(op.f('ix_tip_calculation_issues_order_id'), 'tip_calculation_issues', ['order_id'], unique=False)
    op.create_index(op.f('ix_tip_calculation_issues_payment_id'), 'tip_calculation_issues', ['payment_id'], unique=False)
    op.create_index(op.f('ix_tip_calculation_issues_payment_tip_id'), 'tip_calculation_issues', ['payment_tip_id'], unique=False)

    op.create_table(
        'tip_allocations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('calculation_run_id', sa.Integer(), nullable=False),
        sa.Column('payment_tip_id', sa.Integer(), nullable=False),
        sa.Column('payment_id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('policy_component_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('allocated_amount_minor', sa.Integer(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['calculation_run_id'], ['tip_calculation_runs.id'], ),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], ),
        sa.ForeignKeyConstraint(['payment_tip_id'], ['payment_tips.payment_id'], ),
        sa.ForeignKeyConstraint(['policy_component_id'], ['tip_policy_components.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('calculation_run_id', 'payment_tip_id', 'policy_component_id', 'employee_id'),
    )
    op.create_index(op.f('ix_tip_allocations_calculation_run_id'), 'tip_allocations', ['calculation_run_id'], unique=False)
    op.create_index(op.f('ix_tip_allocations_employee_id'), 'tip_allocations', ['employee_id'], unique=False)
    op.create_index(op.f('ix_tip_allocations_order_id'), 'tip_allocations', ['order_id'], unique=False)
    op.create_index(op.f('ix_tip_allocations_payment_id'), 'tip_allocations', ['payment_id'], unique=False)
    op.create_index(op.f('ix_tip_allocations_payment_tip_id'), 'tip_allocations', ['payment_tip_id'], unique=False)
    op.create_index(op.f('ix_tip_allocations_policy_component_id'), 'tip_allocations', ['policy_component_id'], unique=False)
