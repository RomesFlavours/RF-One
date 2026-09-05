"""add Selection 3D-FIX automatic screening evidence + note context

Revision ID: b3d7f2a9c5e1
Revises: 4f9a1c7e3b6d
Create Date: 2026-09-02 00:00:00.000000

Two additive, non-destructive columns implementing the RF-One Selection
Task 3D-FIX (Automatic Primary Screening Evaluation from Application
Evidence):

- `primary_screening_criterion_evaluations.evidence_items` — the
  structured evidence list (source_type/source_reference/evidence_text/
  interpretation) a generic/AI-assisted evaluation is grounded in. The
  existing `evidence_source`/`evidence_text` columns (Task 3D) are kept
  unchanged for the deterministic Signal-mapping path.
- `application_notes.context_type` / `.context_id` — an optional source/
  context tag (e.g. "PRIMARY_SCREENING_RUN"/run id) so notes stay
  queryable by WHERE in the Selection journey they were entered, not just
  by Application (task §16). Both nullable; existing rows (general
  Application-level notes, Task 3C-FIX) are unaffected.

No existing table, row or column is altered in a way that loses data.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3d7f2a9c5e1'
down_revision: Union[str, Sequence[str], None] = '4f9a1c7e3b6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'primary_screening_criterion_evaluations',
        sa.Column('evidence_items', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )

    op.add_column('application_notes', sa.Column('context_type', sa.String(length=48), nullable=True))
    op.add_column('application_notes', sa.Column('context_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_application_notes_context_type'), 'application_notes', ['context_type'], unique=False)
    op.create_index(op.f('ix_application_notes_context_id'), 'application_notes', ['context_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_application_notes_context_id'), table_name='application_notes')
    op.drop_index(op.f('ix_application_notes_context_type'), table_name='application_notes')
    op.drop_column('application_notes', 'context_id')
    op.drop_column('application_notes', 'context_type')

    op.drop_column('primary_screening_criterion_evaluations', 'evidence_items')
