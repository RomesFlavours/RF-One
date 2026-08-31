"""add payroll_runs.payment_execution_provider (TASK_PAYROLL_002)

Revision ID: b4f3c8a1d6e2
Revises: 09631adaed4d
Create Date: 2026-08-30 00:00:00.000000

One additive, non-destructive change: a nullable `payment_execution_provider`
column on `payroll_runs`, constrained to `ADP_DIRECT_DEPOSIT`/`MERCURY_ACH`
(`01 Domains/Administration/Payroll/Payment Execution.md`).

Closes a real production gap: before this migration, nothing on `PayrollRun`
recorded who is responsible for actually moving money to Employees, so
nothing prevented an already-ADP-executed Run from later being reassigned to
a different (future) executor. This column, together with
`rfone_data_store/payroll/payment_execution.py`'s
`assign_payment_execution_provider` guard, makes that reassignment
architecturally rejected once a Run's provider is set.

No existing row is modified by this migration — every existing `payroll_runs`
row gets `payment_execution_provider = NULL` (not yet assigned), which is
correct: RF-One never guesses a historical Run's payment executor.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4f3c8a1d6e2'
down_revision: Union[str, Sequence[str], None] = '09631adaed4d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('payroll_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('payment_execution_provider', sa.String(length=32), nullable=True))
        batch_op.create_check_constraint(
            'ck_payroll_runs_payment_execution_provider',
            "payment_execution_provider IS NULL OR payment_execution_provider IN "
            "('ADP_DIRECT_DEPOSIT', 'MERCURY_ACH')",
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('payroll_runs', schema=None) as batch_op:
        batch_op.drop_constraint('ck_payroll_runs_payment_execution_provider', type_='check')
        batch_op.drop_column('payment_execution_provider')
