"""add Tips configurable schedule/entitlement/payment-cycle schema (TASK_TIPS_COMPLETE_001)

Revision ID: b4e7c1a9f3d6
Revises: 09ed62634a09
Create Date: 2026-09-13 00:00:00.000000

Completes Tips as a configurable end-to-end process (Calculation Schedule
!= Payment Schedule != Distribution Rules — see CLOVER_CONTINUOUS_
SYNCHRONIZATION_ARCHITECTURE.md's own Cognito-vs-Tips distinction for the
parallel principle this mirrors on the timing side).

Four NEW, additive tables:
- `tips_calculation_schedule_configs` — Restaurant-scoped, effective-dated
  MANUAL/AUTOMATIC calculation cadence ("every N days", execution time,
  anchor date).
- `tips_payment_schedule_configs` — the same shape for WHEN Tips are PAID
  OUT, deliberately independent of the above, plus the Restaurant's Mercury
  sandbox source account (TASK_TIPS_CORE2_PILOT_REPORT.md §8's own flagged
  gap).
- `tip_entitlements` — the persisted per-Employee, per-calculation-run net
  payable result (previously only ever derived on the fly by
  `distribution_engine.build_employee_review`), so a Payment Cycle can
  aggregate MANY calculation runs'/Business Dates' worth of unpaid
  entitlements into one payout.
- `tip_payment_cycles` — one payout batch, replacing the pilot's original
  "exactly one calculation run per payout" assumption.

One BREAKING, but pre-production-safe change: `tip_payment_instructions`
(TASK_TIPS_CORE2_PILOT, zero real rows — "PILOT... nothing here is deployed
or authorized for production", `Tips Payment Execution.md` v0.1) is dropped
and recreated: `calculation_run_id` (1:1 with a single run) is replaced by
`payment_cycle_id` (1:1 with a Payment Cycle, which may aggregate many
runs), and a new nullable `attention_item_id` links a failed instruction to
the AttentionItem it raised (task §12). Recreated rather than
`batch_alter_table`-migrated in place because there is no data to preserve
and a straight recreate is simpler/safer than an in-place FK-column swap on
SQLite.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4e7c1a9f3d6'
down_revision: Union[str, Sequence[str], None] = '09ed62634a09'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'tips_calculation_schedule_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=False),
        sa.Column('mode', sa.String(length=16), nullable=False),
        sa.Column('interval_days', sa.Integer(), nullable=True),
        sa.Column('execution_time', sa.Time(), nullable=True),
        sa.Column('anchor_date', sa.Date(), nullable=True),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint("mode IN ('MANUAL','AUTOMATIC')", name='ck_tips_calculation_schedule_mode'),
        sa.CheckConstraint(
            "mode = 'MANUAL' OR interval_days IS NOT NULL",
            name='ck_tips_calculation_schedule_interval_required_if_automatic',
        ),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_tips_calculation_schedule_configs_restaurant_id'),
        'tips_calculation_schedule_configs', ['restaurant_id'], unique=False,
    )
    op.create_index(
        'ix_tips_calculation_schedule_restaurant_valid_from',
        'tips_calculation_schedule_configs', ['restaurant_id', 'valid_from'], unique=False,
    )

    op.create_table(
        'tips_payment_schedule_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=False),
        sa.Column('mode', sa.String(length=16), nullable=False),
        sa.Column('interval_days', sa.Integer(), nullable=True),
        sa.Column('execution_time', sa.Time(), nullable=True),
        sa.Column('anchor_date', sa.Date(), nullable=True),
        sa.Column('mercury_source_account_id', sa.String(length=64), nullable=True),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint("mode IN ('MANUAL','AUTOMATIC')", name='ck_tips_payment_schedule_mode'),
        sa.CheckConstraint(
            "mode = 'MANUAL' OR interval_days IS NOT NULL",
            name='ck_tips_payment_schedule_interval_required_if_automatic',
        ),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_tips_payment_schedule_configs_restaurant_id'),
        'tips_payment_schedule_configs', ['restaurant_id'], unique=False,
    )
    op.create_index(
        'ix_tips_payment_schedule_restaurant_valid_from',
        'tips_payment_schedule_configs', ['restaurant_id', 'valid_from'], unique=False,
    )

    op.create_table(
        'tip_payment_cycles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('triggered_by', sa.String(length=16), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('approved_by_identity_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.CheckConstraint("status IN ('OPEN','APPROVED')", name='ck_tip_payment_cycle_status'),
        sa.CheckConstraint("triggered_by IN ('MANUAL','AUTOMATIC')", name='ck_tip_payment_cycle_triggered_by'),
        sa.ForeignKeyConstraint(['approved_by_identity_id'], ['acting_identities.id'], ),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_tip_payment_cycles_restaurant_id'), 'tip_payment_cycles', ['restaurant_id'], unique=False,
    )

    # --- Recreate tip_payment_instructions (Run-scoped -> Cycle-scoped) ---
    op.drop_table('tip_payment_instructions')
    op.create_table(
        'tip_payment_instructions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('payment_cycle_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('amount_minor', sa.Integer(), nullable=False),
        sa.Column('idempotency_key', sa.String(length=128), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('provider', sa.String(length=16), nullable=False),
        sa.Column('provider_account_id', sa.String(length=64), nullable=True),
        sa.Column('provider_recipient_id', sa.String(length=64), nullable=True),
        sa.Column('provider_transaction_id', sa.String(length=64), nullable=True),
        sa.Column('provider_status', sa.String(length=32), nullable=True),
        sa.Column('posted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failure_class', sa.String(length=32), nullable=True),
        sa.Column('reason_for_failure', sa.Text(), nullable=True),
        sa.Column('priority', sa.String(length=16), nullable=True),
        sa.Column('attention_item_id', sa.Integer(), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['attention_item_id'], ['attention_items.id'], ),
        sa.ForeignKeyConstraint(['payment_cycle_id'], ['tip_payment_cycles.id'], ),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('payment_cycle_id', 'employee_id', name='uq_tip_payment_instruction_cycle_employee'),
        sa.UniqueConstraint('idempotency_key'),
    )
    op.create_index(
        op.f('ix_tip_payment_instructions_payment_cycle_id'),
        'tip_payment_instructions', ['payment_cycle_id'], unique=False,
    )
    op.create_index(
        op.f('ix_tip_payment_instructions_employee_id'),
        'tip_payment_instructions', ['employee_id'], unique=False,
    )

    op.create_table(
        'tip_entitlements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('calculation_run_id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=False),
        sa.Column('business_date', sa.Date(), nullable=True),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('gross_amount_minor', sa.Integer(), nullable=False),
        sa.Column('outbound_amount_minor', sa.Integer(), nullable=False),
        sa.Column('inbound_amount_minor', sa.Integer(), nullable=False),
        sa.Column('payable_amount_minor', sa.Integer(), nullable=False),
        sa.Column('tip_payment_instruction_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['calculation_run_id'], ['tip_distribution_calculation_runs.id'], ),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
        sa.ForeignKeyConstraint(['tip_payment_instruction_id'], ['tip_payment_instructions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('calculation_run_id', 'employee_id', name='uq_tip_entitlement_run_employee'),
    )
    op.create_index(
        op.f('ix_tip_entitlements_calculation_run_id'), 'tip_entitlements', ['calculation_run_id'], unique=False,
    )
    op.create_index(
        op.f('ix_tip_entitlements_restaurant_id'), 'tip_entitlements', ['restaurant_id'], unique=False,
    )
    op.create_index(
        op.f('ix_tip_entitlements_business_date'), 'tip_entitlements', ['business_date'], unique=False,
    )
    op.create_index(
        op.f('ix_tip_entitlements_employee_id'), 'tip_entitlements', ['employee_id'], unique=False,
    )
    op.create_index(
        op.f('ix_tip_entitlements_tip_payment_instruction_id'),
        'tip_entitlements', ['tip_payment_instruction_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_tip_entitlements_tip_payment_instruction_id'), table_name='tip_entitlements')
    op.drop_index(op.f('ix_tip_entitlements_employee_id'), table_name='tip_entitlements')
    op.drop_index(op.f('ix_tip_entitlements_business_date'), table_name='tip_entitlements')
    op.drop_index(op.f('ix_tip_entitlements_restaurant_id'), table_name='tip_entitlements')
    op.drop_index(op.f('ix_tip_entitlements_calculation_run_id'), table_name='tip_entitlements')
    op.drop_table('tip_entitlements')

    op.drop_index(op.f('ix_tip_payment_instructions_employee_id'), table_name='tip_payment_instructions')
    op.drop_index(op.f('ix_tip_payment_instructions_payment_cycle_id'), table_name='tip_payment_instructions')
    op.drop_table('tip_payment_instructions')
    op.create_table(
        'tip_payment_instructions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('calculation_run_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('amount_minor', sa.Integer(), nullable=False),
        sa.Column('idempotency_key', sa.String(length=128), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('provider', sa.String(length=16), nullable=False),
        sa.Column('provider_account_id', sa.String(length=64), nullable=True),
        sa.Column('provider_recipient_id', sa.String(length=64), nullable=True),
        sa.Column('provider_transaction_id', sa.String(length=64), nullable=True),
        sa.Column('provider_status', sa.String(length=32), nullable=True),
        sa.Column('posted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failure_class', sa.String(length=32), nullable=True),
        sa.Column('reason_for_failure', sa.Text(), nullable=True),
        sa.Column('priority', sa.String(length=16), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['calculation_run_id'], ['tip_distribution_calculation_runs.id'], ),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('calculation_run_id', 'employee_id', name='uq_tip_payment_instruction_run_employee'),
        sa.UniqueConstraint('idempotency_key'),
    )
    op.create_index(
        op.f('ix_tip_payment_instructions_employee_id'), 'tip_payment_instructions', ['employee_id'], unique=False,
    )
    op.create_index(
        op.f('ix_tip_payment_instructions_calculation_run_id'),
        'tip_payment_instructions', ['calculation_run_id'], unique=False,
    )

    op.drop_index(op.f('ix_tip_payment_cycles_restaurant_id'), table_name='tip_payment_cycles')
    op.drop_table('tip_payment_cycles')

    op.drop_index('ix_tips_payment_schedule_restaurant_valid_from', table_name='tips_payment_schedule_configs')
    op.drop_index(
        op.f('ix_tips_payment_schedule_configs_restaurant_id'), table_name='tips_payment_schedule_configs',
    )
    op.drop_table('tips_payment_schedule_configs')

    op.drop_index('ix_tips_calculation_schedule_restaurant_valid_from', table_name='tips_calculation_schedule_configs')
    op.drop_index(
        op.f('ix_tips_calculation_schedule_configs_restaurant_id'), table_name='tips_calculation_schedule_configs',
    )
    op.drop_table('tips_calculation_schedule_configs')
