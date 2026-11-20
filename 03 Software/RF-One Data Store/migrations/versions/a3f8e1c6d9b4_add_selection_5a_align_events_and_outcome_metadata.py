"""add Selection 5A-ALIGN information/event log fields + Outcome metadata

Revision ID: a3f8e1c6d9b4
Revises: e7c2a9f4d1b6
Create Date: 2026-09-03 00:00:00.000000

Additive, non-destructive changes closing genuine gaps found during the
Task 5A / 5A-FIX conceptual alignment check against the current
authoritative product decisions:

- `application_notes.event_type` / `.reported_by` / `.original_source` /
  `.stage_at_time` — support a distinct INFORMATION/EVENT LOG entry
  (context_type="INFORMATION_EVENT") on the SAME append-only table, so a
  staff-reported fact stays clearly distinguishable from a Selezionatore
  note/decision without a parallel notes system.
- `selection_outcome_definitions.authority_label` / `.driven_by` (+ the
  same two columns on `selection_outcome_definition_snapshots`) — the
  remaining custom-Outcome wizard metadata (who has authority to apply it;
  candidate- vs restaurant-driven). Purely informational/descriptive, like
  the existing `performed_by` field — no RBAC enforcement system exists in
  Selection to act on them.

Deliberately NOT added: a new engine-level "changing a decision always
requires a reason" gate. The existing, restaurant-configurable
`requires_reason` flag on `SelectionOutcomeDefinition` already lets a
restaurant mandate a reason for any Outcome it considers substantive
(Hold/Stop/etc.), while HIRABLE simply ships with `requires_reason=False` —
exactly the behavior the task's own §8/§9 describe. A universal, non-
configurable rule would itself be the kind of RF-One-imposed judgment this
codebase's whole architecture deliberately avoids, and would silently
change already-relied-upon call sites (e.g. the legacy workflow-status
projection). See the Task 5A-ALIGN report for the full reasoning.

No existing table, row or column is altered in a way that loses data.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f8e1c6d9b4'
down_revision: Union[str, Sequence[str], None] = 'e7c2a9f4d1b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('application_notes', sa.Column('event_type', sa.String(length=64), nullable=True))
    op.add_column('application_notes', sa.Column('reported_by', sa.String(length=255), nullable=True))
    op.add_column('application_notes', sa.Column('original_source', sa.Text(), nullable=True))
    op.add_column('application_notes', sa.Column('stage_at_time', sa.String(length=32), nullable=True))

    op.add_column('selection_outcome_definitions', sa.Column('authority_label', sa.String(length=64), nullable=True))
    op.add_column('selection_outcome_definitions', sa.Column('driven_by', sa.String(length=24), nullable=True))

    op.add_column('selection_outcome_definition_snapshots', sa.Column('authority_label', sa.String(length=64), nullable=True))
    op.add_column('selection_outcome_definition_snapshots', sa.Column('driven_by', sa.String(length=24), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('selection_outcome_definition_snapshots', 'driven_by')
    op.drop_column('selection_outcome_definition_snapshots', 'authority_label')

    op.drop_column('selection_outcome_definitions', 'driven_by')
    op.drop_column('selection_outcome_definitions', 'authority_label')

    op.drop_column('application_notes', 'stage_at_time')
    op.drop_column('application_notes', 'original_source')
    op.drop_column('application_notes', 'reported_by')
    op.drop_column('application_notes', 'event_type')
