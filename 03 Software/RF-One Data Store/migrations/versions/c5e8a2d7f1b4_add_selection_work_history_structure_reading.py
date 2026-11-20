"""add Selection work-history structure reading fields

Revision ID: c5e8a2d7f1b4
Revises: a7c3e9d5f2b8
Create Date: 2026-10-03 00:00:00.000000

SELECTION_CV_STRUCTURE_READING_001 — additive, non-destructive.

- `candidate_work_history.structure_confidence` (HIGH | MEDIUM | LOW) and
  `structure_note`: how sure the rule-based résumé reader is that an
  experience's title, employer, dates and duties were grouped correctly,
  and why. They describe the reading, never the candidate.

Both columns are nullable and are NOT backfilled: every candidate imported
before this migration keeps exactly its current values, with NULL meaning
"not assessed". No existing table, row or column is altered or dropped.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5e8a2d7f1b4'
down_revision: Union[str, Sequence[str], None] = 'a7c3e9d5f2b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('candidate_work_history', sa.Column('structure_confidence', sa.String(length=16), nullable=True))
    op.add_column('candidate_work_history', sa.Column('structure_note', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('candidate_work_history') as batch_op:
        batch_op.drop_column('structure_note')
        batch_op.drop_column('structure_confidence')
