"""add Selection 5D-MICRO-FIX session-level scheduling windows (Task 5D-MICRO-FIX)

Revision ID: e8b2d5f1a9c3
Revises: d4a7c1e9f3b6
Create Date: 2026-09-04 00:00:00.000000

Widens `interview_scheduling_windows.application_id` to nullable (a
Session-scoped shared window has no single owning Application), indexes
`session_id`, and adds a check constraint requiring at least one of
`session_id`/`application_id`. Adds `interview_appointments.slot_ordinal`
plus a partial unique index (`status = 'CONFIRMED'` only) enforcing, at the
database level, at most `capacity_per_slot` CONFIRMED appointments per
(window, slot start time) — the shared-capacity concurrency guard. No
existing row is altered; no existing column's meaning changes for rows that
keep `application_id` set (the pre-existing Application-scoped windows
continue to work unchanged as the "override" case).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8b2d5f1a9c3'
down_revision: Union[str, Sequence[str], None] = 'd4a7c1e9f3b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    with op.batch_alter_table('interview_scheduling_windows', schema=None) as batch_op:
        batch_op.alter_column('application_id', existing_type=sa.Integer(), nullable=True)
        batch_op.create_check_constraint(
            'ck_scheduling_window_session_or_application',
            'session_id IS NOT NULL OR application_id IS NOT NULL',
        )
    op.create_index(
        op.f('ix_interview_scheduling_windows_session_id'), 'interview_scheduling_windows', ['session_id'],
        unique=False,
    )

    with op.batch_alter_table('interview_appointments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('slot_ordinal', sa.Integer(), nullable=False, server_default='0'))
    op.create_index(
        'ux_interview_appointment_slot_ordinal_confirmed', 'interview_appointments',
        ['scheduling_window_id', 'slot_start_at', 'slot_ordinal'], unique=True,
        sqlite_where=sa.text("status = 'CONFIRMED'"),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index('ux_interview_appointment_slot_ordinal_confirmed', table_name='interview_appointments')
    with op.batch_alter_table('interview_appointments', schema=None) as batch_op:
        batch_op.drop_column('slot_ordinal')

    op.drop_index(op.f('ix_interview_scheduling_windows_session_id'), table_name='interview_scheduling_windows')
    with op.batch_alter_table('interview_scheduling_windows', schema=None) as batch_op:
        batch_op.drop_constraint('ck_scheduling_window_session_or_application', type_='check')
        batch_op.alter_column('application_id', existing_type=sa.Integer(), nullable=False)
