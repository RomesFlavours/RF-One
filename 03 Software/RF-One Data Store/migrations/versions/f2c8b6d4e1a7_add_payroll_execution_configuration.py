"""add payroll_execution_configurations (TASK_PAYROLL_003)

Revision ID: f2c8b6d4e1a7
Revises: d7e21f4a9c3b
Create Date: 2026-08-30 00:00:00.000000

One additive, non-destructive change: a new table,
`payroll_execution_configurations` — a Restaurant-scoped, temporally valid
statement of which Payment Execution Provider is approved for new
PayrollRuns during a window (`01 Domains/Administration/Payroll/Payment
Execution.md`).

Closes a real production gap identified by TASK_PAYROLL_003: TASK_PAYROLL_002
had the ADP importer silently default every newly created PayrollRun's
`payment_execution_provider` to `ADP_DIRECT_DEPOSIT` merely because the
source data came from ADP — conflating "who calculated/supplied this result"
with "who executes payment," which this task corrects. This table is the
explicit, auditable configuration a Run's provider may now be DERIVED from
when not explicitly selected at import/acquisition time; when neither an
explicit selection nor a configuration row covers the Run's `pay_date`, the
Run's `payment_execution_provider` is left NULL rather than guessed.

No existing row is affected by this migration — it only creates a new,
empty table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2c8b6d4e1a7'
down_revision: Union[str, Sequence[str], None] = 'd7e21f4a9c3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'payroll_execution_configurations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint(
            "provider IN ('ADP_DIRECT_DEPOSIT', 'MERCURY_ACH')",
            name='ck_payroll_execution_configurations_provider',
        ),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_payroll_execution_configurations_restaurant_id'),
        'payroll_execution_configurations', ['restaurant_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_payroll_execution_configurations_restaurant_id'),
        table_name='payroll_execution_configurations',
    )
    op.drop_table('payroll_execution_configurations')
