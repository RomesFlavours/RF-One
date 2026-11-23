"""add Selection Session + Application Ownership + Rule Governance (Task 5C)

Revision ID: a1c4e7b9d2f5
Revises: f2a7c4e9b1d6
Create Date: 2026-09-04 00:00:00.000000

Widens the existing `application_notes` table (application_id -> nullable,
adds session_id) so the same unified, append-only notes mechanism can also
carry a Session-level note — no new notes table. Adds `session_id`/
`rule_set_version_id` to `applications` (both nullable — every pre-5C
Application remains valid and unaffected). Six new, additive tables:
selection_sessions, selection_session_assignments, application_ownerships,
selection_rule_set_versions, selection_rule_changes,
selection_rule_change_impacts. No existing row is altered; no existing
column's meaning changes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c4e7b9d2f5'
down_revision: Union[str, Sequence[str], None] = 'f2a7c4e9b1d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # -- Widen application_notes: application_id -> nullable ----------------
    with op.batch_alter_table('application_notes', schema=None) as batch_op:
        batch_op.alter_column('application_id', existing_type=sa.Integer(), nullable=True)

    # -- selection_sessions (current_rule_set_version_id added after the ----
    # -- versions table exists, to resolve the circular FK) ------------------
    op.create_table(
        'selection_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('location_label', sa.String(length=255), nullable=True),
        sa.Column('target_role', sa.String(length=64), nullable=False),
        sa.Column('start_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('planned_end_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('actual_close_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=24), nullable=False, server_default='DRAFT'),
        sa.Column('created_by', sa.String(length=255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_selection_sessions_restaurant_id'), 'selection_sessions', ['restaurant_id'], unique=False)
    op.create_index(op.f('ix_selection_sessions_target_role'), 'selection_sessions', ['target_role'], unique=False)

    # -- selection_session_assignments ---------------------------------------
    op.create_table(
        'selection_session_assignments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('selezionatore_name', sa.String(length=255), nullable=False),
        sa.Column('authority_level_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('deactivated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['selection_sessions.id'], ),
        sa.ForeignKeyConstraint(['authority_level_id'], ['selection_authority_levels.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', 'selezionatore_name', name='uq_session_assignment_session_selezionatore'),
    )
    op.create_index(op.f('ix_selection_session_assignments_session_id'), 'selection_session_assignments', ['session_id'], unique=False)

    # -- selection_rule_set_versions ------------------------------------------
    op.create_table(
        'selection_rule_set_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('requirement_set_id', sa.Integer(), nullable=True),
        sa.Column('requirement_set_snapshot_id', sa.Integer(), nullable=True),
        sa.Column('primary_screening_criterion_snapshot_ids', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('signal_definition_ids', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('review_priority_policy_id', sa.Integer(), nullable=True),
        sa.Column('outcome_definition_ids', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('phone_interview_question_definition_ids', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('in_person_interview_section_definition_ids', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('change_summary', sa.Text(), nullable=True),
        sa.Column('created_from_version_id', sa.Integer(), nullable=True),
        sa.Column('created_by', sa.String(length=255), nullable=True),
        sa.Column('confirmed_by', sa.String(length=255), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('confirmation_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['selection_sessions.id'], ),
        sa.ForeignKeyConstraint(['requirement_set_id'], ['requirement_sets.id'], ),
        sa.ForeignKeyConstraint(['requirement_set_snapshot_id'], ['requirement_set_snapshots.id'], ),
        sa.ForeignKeyConstraint(['review_priority_policy_id'], ['review_priority_policies.id'], ),
        sa.ForeignKeyConstraint(['created_from_version_id'], ['selection_rule_set_versions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', 'version', name='uq_rule_set_version_session_version'),
    )
    op.create_index(op.f('ix_selection_rule_set_versions_session_id'), 'selection_rule_set_versions', ['session_id'], unique=False)

    # -- now the circular FK can be added to selection_sessions --------------
    with op.batch_alter_table('selection_sessions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('current_rule_set_version_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_selection_sessions_current_rule_set_version', 'selection_rule_set_versions',
            ['current_rule_set_version_id'], ['id'],
        )

    # -- application_notes.session_id (FK now resolvable) ---------------------
    with op.batch_alter_table('application_notes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('session_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_application_notes_session_id', 'selection_sessions', ['session_id'], ['id'])
    op.create_index(op.f('ix_application_notes_session_id'), 'application_notes', ['session_id'], unique=False)

    # -- applications.session_id / rule_set_version_id ------------------------
    with op.batch_alter_table('applications', schema=None) as batch_op:
        batch_op.add_column(sa.Column('session_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('rule_set_version_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_applications_session_id', 'selection_sessions', ['session_id'], ['id'])
        batch_op.create_foreign_key(
            'fk_applications_rule_set_version_id', 'selection_rule_set_versions', ['rule_set_version_id'], ['id'],
        )
    op.create_index(op.f('ix_applications_session_id'), 'applications', ['session_id'], unique=False)
    op.create_index(op.f('ix_applications_rule_set_version_id'), 'applications', ['rule_set_version_id'], unique=False)

    # -- application_ownerships ------------------------------------------------
    op.create_table(
        'application_ownerships',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=True),
        sa.Column('owner_name', sa.String(length=255), nullable=False),
        sa.Column('assigned_by', sa.String(length=255), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('stage_at_time', sa.String(length=32), nullable=True),
        sa.Column('previous_ownership_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.ForeignKeyConstraint(['session_id'], ['selection_sessions.id'], ),
        sa.ForeignKeyConstraint(['previous_ownership_id'], ['application_ownerships.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_application_ownerships_application_id'), 'application_ownerships', ['application_id'], unique=False)
    op.create_index(op.f('ix_application_ownerships_session_id'), 'application_ownerships', ['session_id'], unique=False)

    # -- selection_rule_changes -------------------------------------------------
    op.create_table(
        'selection_rule_changes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('previous_version_id', sa.Integer(), nullable=True),
        sa.Column('new_version_id', sa.Integer(), nullable=False),
        sa.Column('rules_changed_summary', sa.Text(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('scope', sa.String(length=24), nullable=False),
        sa.Column('performed_by', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['selection_sessions.id'], ),
        sa.ForeignKeyConstraint(['previous_version_id'], ['selection_rule_set_versions.id'], ),
        sa.ForeignKeyConstraint(['new_version_id'], ['selection_rule_set_versions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_selection_rule_changes_session_id'), 'selection_rule_changes', ['session_id'], unique=False)

    # -- selection_rule_change_impacts ------------------------------------------
    op.create_table(
        'selection_rule_change_impacts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('rule_change_id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('recalculation_status', sa.String(length=24), nullable=False, server_default='PENDING'),
        sa.Column('review_status', sa.String(length=24), nullable=False, server_default='NEEDS_REVIEW'),
        sa.Column('recalculated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['rule_change_id'], ['selection_rule_changes.id'], ),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_selection_rule_change_impacts_rule_change_id'), 'selection_rule_change_impacts', ['rule_change_id'], unique=False)
    op.create_index(op.f('ix_selection_rule_change_impacts_application_id'), 'selection_rule_change_impacts', ['application_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(op.f('ix_selection_rule_change_impacts_application_id'), table_name='selection_rule_change_impacts')
    op.drop_index(op.f('ix_selection_rule_change_impacts_rule_change_id'), table_name='selection_rule_change_impacts')
    op.drop_table('selection_rule_change_impacts')

    op.drop_index(op.f('ix_selection_rule_changes_session_id'), table_name='selection_rule_changes')
    op.drop_table('selection_rule_changes')

    op.drop_index(op.f('ix_application_ownerships_session_id'), table_name='application_ownerships')
    op.drop_index(op.f('ix_application_ownerships_application_id'), table_name='application_ownerships')
    op.drop_table('application_ownerships')

    op.drop_index(op.f('ix_applications_rule_set_version_id'), table_name='applications')
    op.drop_index(op.f('ix_applications_session_id'), table_name='applications')
    with op.batch_alter_table('applications', schema=None) as batch_op:
        batch_op.drop_constraint('fk_applications_rule_set_version_id', type_='foreignkey')
        batch_op.drop_constraint('fk_applications_session_id', type_='foreignkey')
        batch_op.drop_column('rule_set_version_id')
        batch_op.drop_column('session_id')

    op.drop_index(op.f('ix_application_notes_session_id'), table_name='application_notes')
    with op.batch_alter_table('application_notes', schema=None) as batch_op:
        batch_op.drop_constraint('fk_application_notes_session_id', type_='foreignkey')
        batch_op.drop_column('session_id')

    with op.batch_alter_table('selection_sessions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_selection_sessions_current_rule_set_version', type_='foreignkey')
        batch_op.drop_column('current_rule_set_version_id')

    op.drop_index(op.f('ix_selection_rule_set_versions_session_id'), table_name='selection_rule_set_versions')
    op.drop_table('selection_rule_set_versions')

    op.drop_index(op.f('ix_selection_session_assignments_session_id'), table_name='selection_session_assignments')
    op.drop_table('selection_session_assignments')

    op.drop_index(op.f('ix_selection_sessions_target_role'), table_name='selection_sessions')
    op.drop_index(op.f('ix_selection_sessions_restaurant_id'), table_name='selection_sessions')
    op.drop_table('selection_sessions')

    with op.batch_alter_table('application_notes', schema=None) as batch_op:
        batch_op.alter_column('application_id', existing_type=sa.Integer(), nullable=False)
