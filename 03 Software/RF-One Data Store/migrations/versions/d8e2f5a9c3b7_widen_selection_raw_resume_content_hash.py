"""widen raw_resumes.content_hash to 80 characters

Revision ID: d8e2f5a9c3b7
Revises: c5e8a2d7f1b4
Create Date: 2026-10-03 00:00:00.000000

SELECTION_AWS_PUBLISH_001 — found while verifying Selection on AWS.

`selection/parsing/dedup.compute_content_hash` has always returned
"text:" + 64 hex characters (69) or "filename:" + 64 (73), while the column
was VARCHAR(64). SQLite does not enforce the length, so it went unnoticed
locally; PostgreSQL refuses the value, so no résumé could be imported.

The column is only widened (64 -> 80): no value changes, nothing is
backfilled, no other table is touched. In PostgreSQL widening a VARCHAR is a
metadata-only change, compatible with every service already running.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8e2f5a9c3b7'
down_revision: Union[str, Sequence[str], None] = 'c5e8a2d7f1b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('raw_resumes') as batch_op:
        batch_op.alter_column('content_hash', existing_type=sa.String(length=64), type_=sa.String(length=80),
                              existing_nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('raw_resumes') as batch_op:
        batch_op.alter_column('content_hash', existing_type=sa.String(length=80), type_=sa.String(length=64),
                              existing_nullable=True)
