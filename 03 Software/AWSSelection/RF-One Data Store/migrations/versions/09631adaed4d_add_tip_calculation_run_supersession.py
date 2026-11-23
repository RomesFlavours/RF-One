"""add tip_calculation_runs.superseded_by_calculation_run_id (TASK_TIPS_001
multi-location/production-readiness closure)

Revision ID: 09631adaed4d
Revises: c1a9f0d3e7b2
Create Date: 2026-08-30 00:00:00.000000

One additive, non-destructive change: a nullable, self-referential
`superseded_by_calculation_run_id` FK on `tip_calculation_runs`, mirroring
the existing `payroll_runs.superseded_by_payroll_run_id` convention
(migration 2ae7e5a3d715) rather than inventing a new mechanism.

Closes a real idempotency/double-payment gap: before this migration, nothing
prevented two independent PERSIST calculation runs from producing two full,
independently payable sets of `TipAllocation` rows for the same Restaurant
and overlapping period (e.g. an operator accidentally re-running the same
`calculate_tips.py --persist` command). `rfone_data_store/tips/engine.py`'s
`run_tip_calculation` now refuses a second PERSIST run over an overlapping,
not-yet-superseded period unless the caller explicitly names the run it
supersedes (`supersedes_run_id=...`), at which point this column records
that fact on the prior run. No existing row is modified by this migration —
every existing `tip_calculation_runs` row gets `superseded_by_calculation_run_id
= NULL` (unsuperseded, i.e. today's status quo), which is correct: the real
runtime database currently has zero rows in this table (no TipPolicy has
ever been configured for the real Restaurant — see `DATABASE_SCHEMA.md`
§4b "Managed-history boundary").
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '09631adaed4d'
down_revision: Union[str, Sequence[str], None] = 'c1a9f0d3e7b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('tip_calculation_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('superseded_by_calculation_run_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_tip_calculation_runs_superseded_by_calculation_run_id',
            'tip_calculation_runs',
            ['superseded_by_calculation_run_id'],
            ['id'],
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('tip_calculation_runs', schema=None) as batch_op:
        batch_op.drop_constraint(
            'fk_tip_calculation_runs_superseded_by_calculation_run_id', type_='foreignkey'
        )
        batch_op.drop_column('superseded_by_calculation_run_id')
