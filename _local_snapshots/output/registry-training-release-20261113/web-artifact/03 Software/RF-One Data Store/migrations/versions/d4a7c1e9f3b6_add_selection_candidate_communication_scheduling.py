"""add Selection Candidate Communication + Interview Scheduling (Task 5D)

Revision ID: d4a7c1e9f3b6
Revises: a1c4e7b9d2f5
Create Date: 2026-09-04 00:00:00.000000

Nine new, additive tables (acquisition_source_definitions,
communication_templates, communication_template_snapshots,
communication_reminder_policies, candidate_communications,
interview_scheduling_windows, interview_appointments,
candidate_scheduling_tokens, inbound_communications) plus two nullable
columns on `applications` (`acquisition_source_id`,
`acquisition_source_other_text`). No existing row is altered; no existing
column's meaning changes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4a7c1e9f3b6'
down_revision: Union[str, Sequence[str], None] = 'a1c4e7b9d2f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # -- acquisition_source_definitions --------------------------------------
    op.create_table(
        'acquisition_source_definitions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('restaurant_id', 'name', name='uq_acquisition_source_restaurant_name'),
    )
    op.create_index(op.f('ix_acquisition_source_definitions_restaurant_id'), 'acquisition_source_definitions', ['restaurant_id'], unique=False)

    # -- communication_templates ----------------------------------------------
    op.create_table(
        'communication_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('location_label', sa.String(length=255), nullable=True),
        sa.Column('role', sa.String(length=64), nullable=True),
        sa.Column('stage', sa.String(length=32), nullable=True),
        sa.Column('trigger_event', sa.String(length=48), nullable=False),
        sa.Column('outcome_definition_id', sa.Integer(), nullable=True),
        sa.Column('purpose', sa.String(length=255), nullable=True),
        sa.Column('language', sa.String(length=16), nullable=False, server_default='en'),
        sa.Column('sms_text', sa.Text(), nullable=True),
        sa.Column('email_subject', sa.String(length=500), nullable=True),
        sa.Column('email_body', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.ForeignKeyConstraint(['outcome_definition_id'], ['selection_outcome_definitions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_communication_templates_restaurant_id'), 'communication_templates', ['restaurant_id'], unique=False)
    op.create_index(op.f('ix_communication_templates_trigger_event'), 'communication_templates', ['trigger_event'], unique=False)

    # -- communication_template_snapshots --------------------------------------
    op.create_table(
        'communication_template_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('location_label', sa.String(length=255), nullable=True),
        sa.Column('role', sa.String(length=64), nullable=True),
        sa.Column('stage', sa.String(length=32), nullable=True),
        sa.Column('trigger_event', sa.String(length=48), nullable=False),
        sa.Column('outcome_definition_id', sa.Integer(), nullable=True),
        sa.Column('purpose', sa.String(length=255), nullable=True),
        sa.Column('language', sa.String(length=16), nullable=False),
        sa.Column('sms_text', sa.Text(), nullable=True),
        sa.Column('email_subject', sa.String(length=500), nullable=True),
        sa.Column('email_body', sa.Text(), nullable=True),
        sa.Column('was_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['template_id'], ['communication_templates.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('template_id', 'version', name='uq_communication_template_snapshot_version'),
    )
    op.create_index(op.f('ix_communication_template_snapshots_template_id'), 'communication_template_snapshots', ['template_id'], unique=False)

    # -- communication_reminder_policies ----------------------------------------
    op.create_table(
        'communication_reminder_policies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('location_label', sa.String(length=255), nullable=True),
        sa.Column('role', sa.String(length=64), nullable=True),
        sa.Column('stage', sa.String(length=32), nullable=True),
        sa.Column('trigger_event', sa.String(length=48), nullable=False),
        sa.Column('reminder_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('first_reminder_delay_hours', sa.Integer(), nullable=True),
        sa.Column('reminder_interval_hours', sa.Integer(), nullable=True),
        sa.Column('final_deadline_hours', sa.Integer(), nullable=True),
        sa.Column('auto_stop_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('auto_stop_outcome_definition_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.ForeignKeyConstraint(['auto_stop_outcome_definition_id'], ['selection_outcome_definitions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_communication_reminder_policies_restaurant_id'), 'communication_reminder_policies', ['restaurant_id'], unique=False)
    op.create_index(op.f('ix_communication_reminder_policies_trigger_event'), 'communication_reminder_policies', ['trigger_event'], unique=False)

    # -- interview_scheduling_windows -------------------------------------------
    op.create_table(
        'interview_scheduling_windows',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=True),
        sa.Column('interview_stage', sa.String(length=32), nullable=False),
        sa.Column('window_date', sa.Date(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.Column('slot_duration_minutes', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('capacity_per_slot', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('timezone', sa.String(length=64), nullable=False, server_default='America/New_York'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_by', sa.String(length=255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.ForeignKeyConstraint(['session_id'], ['selection_sessions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_interview_scheduling_windows_application_id'), 'interview_scheduling_windows', ['application_id'], unique=False)

    # -- interview_appointments ---------------------------------------------------
    op.create_table(
        'interview_appointments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('interview_stage', sa.String(length=32), nullable=False),
        sa.Column('scheduling_window_id', sa.Integer(), nullable=False),
        sa.Column('slot_start_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('slot_end_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='CONFIRMED'),
        sa.Column('candidate_selected_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('previous_appointment_id', sa.Integer(), nullable=True),
        sa.Column('cancellation_reason', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.ForeignKeyConstraint(['scheduling_window_id'], ['interview_scheduling_windows.id'], ),
        sa.ForeignKeyConstraint(['previous_appointment_id'], ['interview_appointments.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_interview_appointments_application_id'), 'interview_appointments', ['application_id'], unique=False)
    op.create_index(op.f('ix_interview_appointments_scheduling_window_id'), 'interview_appointments', ['scheduling_window_id'], unique=False)

    # -- candidate_scheduling_tokens -----------------------------------------------
    op.create_table(
        'candidate_scheduling_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('interview_stage', sa.String(length=32), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_candidate_scheduling_tokens_token'), 'candidate_scheduling_tokens', ['token'], unique=True)
    op.create_index(op.f('ix_candidate_scheduling_tokens_application_id'), 'candidate_scheduling_tokens', ['application_id'], unique=False)

    # -- inbound_communications -------------------------------------------------
    op.create_table(
        'inbound_communications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('channel', sa.String(length=16), nullable=False),
        sa.Column('raw_text', sa.Text(), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=True),
        sa.Column('classification_system', sa.String(length=48), nullable=True),
        sa.Column('classification_confidence', sa.Float(), nullable=True),
        sa.Column('classification_effective', sa.String(length=48), nullable=True),
        sa.Column('classification_corrected_by', sa.String(length=255), nullable=True),
        sa.Column('classification_corrected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('classification_correction_reason', sa.Text(), nullable=True),
        sa.Column('related_outgoing_communication_id', sa.Integer(), nullable=True),
        sa.Column('alert_required', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('alert_reason', sa.String(length=64), nullable=True),
        sa.Column('alert_acknowledged_by', sa.String(length=255), nullable=True),
        sa.Column('alert_acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_inbound_communications_application_id'), 'inbound_communications', ['application_id'], unique=False)

    # -- candidate_communications (references inbound_communications) -----------
    op.create_table(
        'candidate_communications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('template_snapshot_id', sa.Integer(), nullable=False),
        sa.Column('trigger_event', sa.String(length=48), nullable=False),
        sa.Column('channel_sms_used', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('channel_email_used', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('recipient_phone', sa.String(length=64), nullable=True),
        sa.Column('recipient_email', sa.String(length=255), nullable=True),
        sa.Column('rendered_sms_text', sa.Text(), nullable=True),
        sa.Column('rendered_email_subject', sa.String(length=500), nullable=True),
        sa.Column('rendered_email_body', sa.Text(), nullable=True),
        sa.Column('language_used', sa.String(length=16), nullable=False, server_default='en'),
        sa.Column('sms_status', sa.String(length=16), nullable=True),
        sa.Column('sms_provider_ref', sa.String(length=128), nullable=True),
        sa.Column('email_status', sa.String(length=16), nullable=True),
        sa.Column('email_provider_ref', sa.String(length=128), nullable=True),
        sa.Column('is_reminder', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('reminder_sequence_number', sa.Integer(), nullable=True),
        sa.Column('parent_communication_id', sa.Integer(), nullable=True),
        sa.Column('awaiting_response', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('response_received_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('response_inbound_id', sa.Integer(), nullable=True),
        sa.Column('reminder_policy_id', sa.Integer(), nullable=True),
        sa.Column('final_deadline_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reminders_sent_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('no_response_stop_applied', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('no_response_stop_outcome_decision_id', sa.Integer(), nullable=True),
        sa.Column('related_outcome_decision_id', sa.Integer(), nullable=True),
        sa.Column('related_stage_transition_id', sa.Integer(), nullable=True),
        sa.Column('performed_by', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.ForeignKeyConstraint(['template_snapshot_id'], ['communication_template_snapshots.id'], ),
        sa.ForeignKeyConstraint(['parent_communication_id'], ['candidate_communications.id'], ),
        sa.ForeignKeyConstraint(['response_inbound_id'], ['inbound_communications.id'], ),
        sa.ForeignKeyConstraint(['reminder_policy_id'], ['communication_reminder_policies.id'], ),
        sa.ForeignKeyConstraint(['no_response_stop_outcome_decision_id'], ['selection_outcome_decisions.id'], ),
        sa.ForeignKeyConstraint(['related_outcome_decision_id'], ['selection_outcome_decisions.id'], ),
        sa.ForeignKeyConstraint(['related_stage_transition_id'], ['application_stage_transitions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_candidate_communications_application_id'), 'candidate_communications', ['application_id'], unique=False)
    op.create_index(op.f('ix_candidate_communications_template_snapshot_id'), 'candidate_communications', ['template_snapshot_id'], unique=False)
    op.create_index(op.f('ix_candidate_communications_trigger_event'), 'candidate_communications', ['trigger_event'], unique=False)
    op.create_index(op.f('ix_candidate_communications_parent_communication_id'), 'candidate_communications', ['parent_communication_id'], unique=False)

    # -- inbound_communications.related_outgoing_communication_id (FK now resolvable) --
    with op.batch_alter_table('inbound_communications', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_inbound_communications_related_outgoing', 'candidate_communications',
            ['related_outgoing_communication_id'], ['id'],
        )

    # -- applications.acquisition_source_id / acquisition_source_other_text -----
    with op.batch_alter_table('applications', schema=None) as batch_op:
        batch_op.add_column(sa.Column('acquisition_source_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('acquisition_source_other_text', sa.String(length=255), nullable=True))
        batch_op.create_foreign_key(
            'fk_applications_acquisition_source_id', 'acquisition_source_definitions',
            ['acquisition_source_id'], ['id'],
        )
    op.create_index(op.f('ix_applications_acquisition_source_id'), 'applications', ['acquisition_source_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(op.f('ix_applications_acquisition_source_id'), table_name='applications')
    with op.batch_alter_table('applications', schema=None) as batch_op:
        batch_op.drop_constraint('fk_applications_acquisition_source_id', type_='foreignkey')
        batch_op.drop_column('acquisition_source_other_text')
        batch_op.drop_column('acquisition_source_id')

    with op.batch_alter_table('inbound_communications', schema=None) as batch_op:
        batch_op.drop_constraint('fk_inbound_communications_related_outgoing', type_='foreignkey')

    op.drop_index(op.f('ix_candidate_communications_parent_communication_id'), table_name='candidate_communications')
    op.drop_index(op.f('ix_candidate_communications_trigger_event'), table_name='candidate_communications')
    op.drop_index(op.f('ix_candidate_communications_template_snapshot_id'), table_name='candidate_communications')
    op.drop_index(op.f('ix_candidate_communications_application_id'), table_name='candidate_communications')
    op.drop_table('candidate_communications')

    op.drop_index(op.f('ix_inbound_communications_application_id'), table_name='inbound_communications')
    op.drop_table('inbound_communications')

    op.drop_index(op.f('ix_candidate_scheduling_tokens_application_id'), table_name='candidate_scheduling_tokens')
    op.drop_index(op.f('ix_candidate_scheduling_tokens_token'), table_name='candidate_scheduling_tokens')
    op.drop_table('candidate_scheduling_tokens')

    op.drop_index(op.f('ix_interview_appointments_scheduling_window_id'), table_name='interview_appointments')
    op.drop_index(op.f('ix_interview_appointments_application_id'), table_name='interview_appointments')
    op.drop_table('interview_appointments')

    op.drop_index(op.f('ix_interview_scheduling_windows_application_id'), table_name='interview_scheduling_windows')
    op.drop_table('interview_scheduling_windows')

    op.drop_index(op.f('ix_communication_reminder_policies_trigger_event'), table_name='communication_reminder_policies')
    op.drop_index(op.f('ix_communication_reminder_policies_restaurant_id'), table_name='communication_reminder_policies')
    op.drop_table('communication_reminder_policies')

    op.drop_index(op.f('ix_communication_template_snapshots_template_id'), table_name='communication_template_snapshots')
    op.drop_table('communication_template_snapshots')

    op.drop_index(op.f('ix_communication_templates_trigger_event'), table_name='communication_templates')
    op.drop_index(op.f('ix_communication_templates_restaurant_id'), table_name='communication_templates')
    op.drop_table('communication_templates')

    op.drop_index(op.f('ix_acquisition_source_definitions_restaurant_id'), table_name='acquisition_source_definitions')
    op.drop_table('acquisition_source_definitions')
