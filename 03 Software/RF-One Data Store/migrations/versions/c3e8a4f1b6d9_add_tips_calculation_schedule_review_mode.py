"""add tips_calculation_schedule_configs.review_mode (HOST_TIP_AUDIT_001)

Revision ID: c3e8a4f1b6d9
Revises: 96337baf293c
Create Date: 2026-09-19 00:00:00.000000

One additive, non-destructive change: a nullable `review_mode` column on
`tips_calculation_schedule_configs`, restricted by CHECK to `'AUDIT'` or
`'AUTOMATIC'` (or NULL). Introduced by the Host Tip Audit/Explain report
task (HOST_TIP_AUDIT_001) — a pure workflow/UI-emphasis toggle (whether the
Audit report is surfaced prominently right after a calculation), never a
calculation-affecting fact. NULL means "not yet configured" and always
resolves to AUDIT at read time (`tips/review_mode_service.get_review_mode`)
— the task-mandated safe default; never silently AUTOMATIC. Every existing
row gets `review_mode = NULL`, changing nothing about its current meaning.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3e8a4f1b6d9'
down_revision: Union[str, Sequence[str], None] = '96337baf293c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('tips_calculation_schedule_configs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('review_mode', sa.String(length=16), nullable=True))
        batch_op.create_check_constraint(
            'ck_tips_calculation_schedule_review_mode',
            "review_mode IS NULL OR review_mode IN ('AUDIT','AUTOMATIC')",
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('tips_calculation_schedule_configs', schema=None) as batch_op:
        batch_op.drop_constraint('ck_tips_calculation_schedule_review_mode', type_='check')
        batch_op.drop_column('review_mode')
