"""add Selection batch-import metadata (TASK_SELECTION_002)

Revision ID: 2e9125cf954b
Revises: b8f1c4a2e6d9
Create Date: 2026-08-31 00:00:00.000000

Two additive, non-destructive columns supporting multi-résumé batch import:

- `raw_resumes.content_hash` — a best-effort duplicate-detection signal
  (see `rfone_data_store/selection/parsing/dedup.py`), indexed so a batch
  import can cheaply check "have we already imported this exact résumé for
  this restaurant?" before creating a second Candidate for it.
- `candidates.source_provider` — which acquirer produced this résumé within
  its `source` (ResumeSource) — "manual" for today's LOCAL_UPLOAD; keeps the
  schema ready for a future API-based ResumeSource without another
  migration touching this shape again.

No existing table, row or column is altered or dropped.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2e9125cf954b'
down_revision: Union[str, Sequence[str], None] = 'b8f1c4a2e6d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('raw_resumes', sa.Column('content_hash', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_raw_resumes_content_hash'), 'raw_resumes', ['content_hash'], unique=False)

    op.add_column('candidates', sa.Column('source_provider', sa.String(length=64), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('candidates', 'source_provider')

    op.drop_index(op.f('ix_raw_resumes_content_hash'), table_name='raw_resumes')
    op.drop_column('raw_resumes', 'content_hash')
