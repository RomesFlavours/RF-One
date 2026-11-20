"""add tip payment execution tables (TASK_TIPS_CORE2_PILOT)

Revision ID: efe49dbc7321
Revises: f7174fa37e93
Create Date: 2026-09-12 00:00:00.000000

Two additive, non-destructive new tables supporting the RF-One Tips Core 2.0
Process-First pilot (`01 Domains/Business Domain/Restaurant/Tips/Tips
Payment Execution.md`):

- `employee_external_payment_accounts` — a stable Employee <-> external
  Payment Executor recipient reference (Mercury's own opaque recipient id
  only; no routing/account number is ever stored here).
- `tip_payment_instructions` — one Payment Instruction per
  (TipDistributionCalculationRun, Employee), the primary RF-One-side
  duplicate-payment guard (`uq_tip_payment_instruction_run_employee`), plus
  a deterministic `idempotency_key` sent to Mercury on submission.

No existing table or row is affected by this migration — it only creates
two new, empty tables.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'efe49dbc7321'
down_revision: Union[str, Sequence[str], None] = 'f7174fa37e93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'employee_external_payment_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=16), nullable=False),
        sa.Column('provider_recipient_id', sa.String(length=64), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint("provider IN ('MERCURY')", name='ck_employee_external_payment_accounts_provider'),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_employee_external_payment_accounts_employee_id'),
        'employee_external_payment_accounts', ['employee_id'], unique=False,
    )

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
        op.f('ix_tip_payment_instructions_calculation_run_id'),
        'tip_payment_instructions', ['calculation_run_id'], unique=False,
    )
    op.create_index(
        op.f('ix_tip_payment_instructions_employee_id'),
        'tip_payment_instructions', ['employee_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_tip_payment_instructions_employee_id'), table_name='tip_payment_instructions')
    op.drop_index(op.f('ix_tip_payment_instructions_calculation_run_id'), table_name='tip_payment_instructions')
    op.drop_table('tip_payment_instructions')
    op.drop_index(
        op.f('ix_employee_external_payment_accounts_employee_id'),
        table_name='employee_external_payment_accounts',
    )
    op.drop_table('employee_external_payment_accounts')
