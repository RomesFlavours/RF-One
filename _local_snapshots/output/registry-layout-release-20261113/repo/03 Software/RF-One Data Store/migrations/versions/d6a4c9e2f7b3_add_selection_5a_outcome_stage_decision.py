"""add Selection 5A Outcome + Stage + Decision History engine

Revision ID: d6a4c9e2f7b3
Revises: b3d7f2a9c5e1
Create Date: 2026-09-02 00:00:00.000000

Additive, non-destructive changes implementing the RF-One Selection Task 5A
Outcome + Stage + Decision History Engine:

- `application_stage_transitions` — append-only Stage movement history
  (task §3); `applications.current_stage` (new column, default
  APPLICATION_RECEIVED) is a convenience pointer only.
- `selection_outcome_definitions` / `selection_outcome_definition_snapshots`
  — restaurant-configurable Outcome Definitions (task §4/§5) and their
  immutable, point-in-time snapshots (task §28), mirroring
  `primary_screening_criteria`/`primary_screening_criterion_snapshots`'
  exact shape.
- `selection_outcome_decisions` — append-only Outcome Decision History
  (task §8/§9/§26); `applications.lifecycle_state` (new column, default
  ACTIVE) is a convenience pointer only — the current effective Outcome is
  always derivable as the most recent decision.
- `selection_reminders` — the minimal follow-up record an Outcome's
  "creates reminder" configuration may generate (task §5/§11).
- `candidate_flags` — persistent, person-level markers an Outcome may
  create (task §16-19), never causing automatic rejection.

`applications.workflow_status` (Task 3C-FIX/4A) is entirely UNCHANGED by
this migration — no existing table, row or column is altered in a way that
loses data.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd6a4c9e2f7b3'
down_revision: Union[str, Sequence[str], None] = 'b3d7f2a9c5e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'applications',
        sa.Column('current_stage', sa.String(length=32), nullable=False, server_default='APPLICATION_RECEIVED'),
    )
    op.add_column(
        'applications', sa.Column('lifecycle_state', sa.String(length=16), nullable=False, server_default='ACTIVE'),
    )

    op.create_table(
        'application_stage_transitions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('previous_stage', sa.String(length=32), nullable=True),
        sa.Column('new_stage', sa.String(length=32), nullable=False),
        sa.Column('performed_by', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_application_stage_transitions_application_id'), 'application_stage_transitions', ['application_id'],
        unique=False,
    )

    op.create_table(
        'selection_outcome_definitions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('lifecycle_effect', sa.String(length=16), nullable=False, server_default='ACTIVE'),
        sa.Column('is_reopenable', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('requires_note', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('requires_reason', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('reason_choices', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('target_queue_label', sa.String(length=255), nullable=True),
        sa.Column('creates_reminder', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('reminder_days', sa.Integer(), nullable=True),
        sa.Column('future_contact_policy', sa.String(length=16), nullable=False, server_default='ALLOWED'),
        sa.Column('creates_candidate_flag', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('candidate_flag_name', sa.String(length=255), nullable=True),
        sa.Column('candidate_flag_scope', sa.String(length=32), nullable=True),
        sa.Column('candidate_flag_operational_effect', sa.String(length=24), nullable=True),
        sa.Column('candidate_flag_default_reason', sa.Text(), nullable=True),
        sa.Column('candidate_flag_expires_after_days', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_selection_outcome_definitions_restaurant_id'), 'selection_outcome_definitions', ['restaurant_id'],
        unique=False,
    )

    op.create_table(
        'selection_outcome_definition_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('definition_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('lifecycle_effect', sa.String(length=16), nullable=False),
        sa.Column('is_reopenable', sa.Boolean(), nullable=False),
        sa.Column('requires_note', sa.Boolean(), nullable=False),
        sa.Column('requires_reason', sa.Boolean(), nullable=False),
        sa.Column('reason_choices', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('target_queue_label', sa.String(length=255), nullable=True),
        sa.Column('creates_reminder', sa.Boolean(), nullable=False),
        sa.Column('reminder_days', sa.Integer(), nullable=True),
        sa.Column('future_contact_policy', sa.String(length=16), nullable=False),
        sa.Column('creates_candidate_flag', sa.Boolean(), nullable=False),
        sa.Column('candidate_flag_name', sa.String(length=255), nullable=True),
        sa.Column('candidate_flag_scope', sa.String(length=32), nullable=True),
        sa.Column('candidate_flag_operational_effect', sa.String(length=24), nullable=True),
        sa.Column('candidate_flag_default_reason', sa.Text(), nullable=True),
        sa.Column('candidate_flag_expires_after_days', sa.Integer(), nullable=True),
        sa.Column('was_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['definition_id'], ['selection_outcome_definitions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('definition_id', 'version', name='uq_outcome_definition_snapshot_version'),
    )
    op.create_index(
        op.f('ix_selection_outcome_definition_snapshots_definition_id'), 'selection_outcome_definition_snapshots',
        ['definition_id'], unique=False,
    )

    op.create_table(
        'selection_outcome_decisions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('outcome_definition_snapshot_id', sa.Integer(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('is_reopen_event', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('performed_by', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.ForeignKeyConstraint(['outcome_definition_snapshot_id'], ['selection_outcome_definition_snapshots.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_selection_outcome_decisions_application_id'), 'selection_outcome_decisions', ['application_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_selection_outcome_decisions_outcome_definition_snapshot_id'), 'selection_outcome_decisions',
        ['outcome_definition_snapshot_id'], unique=False,
    )

    op.create_table(
        'selection_reminders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('outcome_decision_id', sa.Integer(), nullable=True),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('note_text', sa.Text(), nullable=True),
        sa.Column('is_resolved', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.ForeignKeyConstraint(['outcome_decision_id'], ['selection_outcome_decisions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_selection_reminders_application_id'), 'selection_reminders', ['application_id'], unique=False,
    )
    op.create_index(
        op.f('ix_selection_reminders_outcome_decision_id'), 'selection_reminders', ['outcome_decision_id'],
        unique=False,
    )

    op.create_table(
        'candidate_flags',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('person_id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('originating_application_id', sa.Integer(), nullable=True),
        sa.Column('originating_outcome_decision_id', sa.Integer(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('scope', sa.String(length=32), nullable=False, server_default='INFORMATIONAL'),
        sa.Column('role_scope', sa.String(length=64), nullable=True),
        sa.Column('location_scope', sa.String(length=255), nullable=True),
        sa.Column('operational_effect', sa.String(length=24), nullable=False, server_default='INFORMATION_ONLY'),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('start_date', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('created_by', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['person_id'], ['candidate_persons.id'], ),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.ForeignKeyConstraint(['originating_application_id'], ['applications.id'], ),
        sa.ForeignKeyConstraint(['originating_outcome_decision_id'], ['selection_outcome_decisions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_candidate_flags_person_id'), 'candidate_flags', ['person_id'], unique=False)
    op.create_index(op.f('ix_candidate_flags_restaurant_id'), 'candidate_flags', ['restaurant_id'], unique=False)
    op.create_index(
        op.f('ix_candidate_flags_originating_application_id'), 'candidate_flags', ['originating_application_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_candidate_flags_originating_outcome_decision_id'), 'candidate_flags',
        ['originating_outcome_decision_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_candidate_flags_originating_outcome_decision_id'), table_name='candidate_flags')
    op.drop_index(op.f('ix_candidate_flags_originating_application_id'), table_name='candidate_flags')
    op.drop_index(op.f('ix_candidate_flags_restaurant_id'), table_name='candidate_flags')
    op.drop_index(op.f('ix_candidate_flags_person_id'), table_name='candidate_flags')
    op.drop_table('candidate_flags')

    op.drop_index(op.f('ix_selection_reminders_outcome_decision_id'), table_name='selection_reminders')
    op.drop_index(op.f('ix_selection_reminders_application_id'), table_name='selection_reminders')
    op.drop_table('selection_reminders')

    op.drop_index(
        op.f('ix_selection_outcome_decisions_outcome_definition_snapshot_id'), table_name='selection_outcome_decisions',
    )
    op.drop_index(op.f('ix_selection_outcome_decisions_application_id'), table_name='selection_outcome_decisions')
    op.drop_table('selection_outcome_decisions')

    op.drop_index(
        op.f('ix_selection_outcome_definition_snapshots_definition_id'),
        table_name='selection_outcome_definition_snapshots',
    )
    op.drop_table('selection_outcome_definition_snapshots')

    op.drop_index(op.f('ix_selection_outcome_definitions_restaurant_id'), table_name='selection_outcome_definitions')
    op.drop_table('selection_outcome_definitions')

    op.drop_index(
        op.f('ix_application_stage_transitions_application_id'), table_name='application_stage_transitions',
    )
    op.drop_table('application_stage_transitions')

    op.drop_column('applications', 'lifecycle_state')
    op.drop_column('applications', 'current_stage')
