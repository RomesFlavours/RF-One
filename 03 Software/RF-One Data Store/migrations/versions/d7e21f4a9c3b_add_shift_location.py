"""add shifts.location_id (TASK_TIPS_003)

Revision ID: d7e21f4a9c3b
Revises: b4f3c8a1d6e2
Create Date: 2026-08-30 00:00:00.000000

One additive, non-destructive change: a nullable `location_id` FK on
`shifts` (`01 Domains/Restaurant/Organization/Employee Assignment.md`,
`01 Domains/Restaurant/Tips/Tip Allocation.md`).

Closes the residual half of TASK_TIPS_001 Scenario 9 (documented as a Future
Enhancement, not a blocker, in `07 Tasks/Reports/TASK_TIPS_001_REPORT.md`
§O): before this migration, `Shift` carried no Location field at all, so an
Employee who genuinely works more than one Location could only be
represented by a single, fixed `Employee.location_id` — insufficient to
distinguish which specific Shift occurred at which Location. This column
gives a Shift the capability to carry its own, deterministic Location
evidence, used by `rfone_data_store/tips/engine.py`'s
`_shift_active_employee_ids` in preference to the `Employee.location_id`
proxy whenever it is actually populated.

No existing row is modified by this migration — every existing `shifts` row
gets `location_id = NULL` (unknown), which is correct: RF-One never
backfills or guesses a historical Shift's Location from `Employee.location_id`
or any other source. The real production database (single Location today)
is unaffected in behavior — see `07 Tasks/Reports/TASK_TIPS_003_REPORT.md`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7e21f4a9c3b'
down_revision: Union[str, Sequence[str], None] = 'b4f3c8a1d6e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('shifts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('location_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_shifts_location_id', 'locations', ['location_id'], ['id']
        )
        batch_op.create_index('ix_shifts_location_id', ['location_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('shifts', schema=None) as batch_op:
        batch_op.drop_index('ix_shifts_location_id')
        batch_op.drop_constraint('fk_shifts_location_id', type_='foreignkey')
        batch_op.drop_column('location_id')
