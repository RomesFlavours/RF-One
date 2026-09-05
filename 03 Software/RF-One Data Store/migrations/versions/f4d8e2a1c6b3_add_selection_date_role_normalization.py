"""add Selection date + role normalization fields (TASK 2B)

Revision ID: f4d8e2a1c6b3
Revises: 9c4a2f7b1e3d
Create Date: 2026-09-01 00:00:00.000000

Additive, non-destructive change supporting Task 2B's date and role
normalization layer:

- `candidate_education` / `candidate_work_history`: `start_date_text`,
  `end_date_text` (the résumé's own date text, exactly as extracted),
  `start_date_precision`, `end_date_precision`, `date_normalization_confidence`.
  The existing `start_date`/`end_date` columns are UNCHANGED in meaning and
  UNTOUCHED by this migration — they now hold the value re-derived from the
  new `*_text` columns, but every already-persisted value survives exactly
  as Task 2A left it (Task 2B's normalizer only ever recomputes a date when
  `start_date_text`/`end_date_text` is present, and this migration never
  backfills those from anything, so no existing row's dates are altered by
  running this migration).
- `candidate_work_history`: `normalized_title`, `role_family`,
  `seniority_level`, `multi_role` (default false), `title_normalization_confidence`.

No existing table, row or column is altered or dropped.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4d8e2a1c6b3'
down_revision: Union[str, Sequence[str], None] = '9c4a2f7b1e3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('candidate_education', sa.Column('start_date_text', sa.String(length=64), nullable=True))
    op.add_column('candidate_education', sa.Column('end_date_text', sa.String(length=64), nullable=True))
    op.add_column('candidate_education', sa.Column('start_date_precision', sa.String(length=16), nullable=True))
    op.add_column('candidate_education', sa.Column('end_date_precision', sa.String(length=16), nullable=True))
    op.add_column(
        'candidate_education', sa.Column('date_normalization_confidence', sa.String(length=16), nullable=True)
    )

    op.add_column('candidate_work_history', sa.Column('start_date_text', sa.String(length=64), nullable=True))
    op.add_column('candidate_work_history', sa.Column('end_date_text', sa.String(length=64), nullable=True))
    op.add_column('candidate_work_history', sa.Column('start_date_precision', sa.String(length=16), nullable=True))
    op.add_column('candidate_work_history', sa.Column('end_date_precision', sa.String(length=16), nullable=True))
    op.add_column(
        'candidate_work_history', sa.Column('date_normalization_confidence', sa.String(length=16), nullable=True)
    )
    op.add_column('candidate_work_history', sa.Column('normalized_title', sa.String(length=255), nullable=True))
    op.add_column('candidate_work_history', sa.Column('role_family', sa.String(length=64), nullable=True))
    op.add_column('candidate_work_history', sa.Column('seniority_level', sa.String(length=32), nullable=True))
    op.add_column(
        'candidate_work_history',
        sa.Column('multi_role', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'candidate_work_history', sa.Column('title_normalization_confidence', sa.String(length=16), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('candidate_work_history', 'title_normalization_confidence')
    op.drop_column('candidate_work_history', 'multi_role')
    op.drop_column('candidate_work_history', 'seniority_level')
    op.drop_column('candidate_work_history', 'role_family')
    op.drop_column('candidate_work_history', 'normalized_title')
    op.drop_column('candidate_work_history', 'date_normalization_confidence')
    op.drop_column('candidate_work_history', 'end_date_precision')
    op.drop_column('candidate_work_history', 'start_date_precision')
    op.drop_column('candidate_work_history', 'end_date_text')
    op.drop_column('candidate_work_history', 'start_date_text')

    op.drop_column('candidate_education', 'date_normalization_confidence')
    op.drop_column('candidate_education', 'end_date_precision')
    op.drop_column('candidate_education', 'start_date_precision')
    op.drop_column('candidate_education', 'end_date_text')
    op.drop_column('candidate_education', 'start_date_text')
