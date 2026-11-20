"""add Selection 5E job posting + application intake + pre-screening (Task 5E)

Revision ID: f7c3a9d1e6b4
Revises: e8b2d5f1a9c3
Create Date: 2026-09-05 00:00:00.000000

Twelve new, additive tables (job_postings, job_posting_versions,
channel_definitions, job_posting_channel_variants,
job_posting_channel_variant_versions, channel_publications,
channel_tracking_links, application_question_definitions,
application_question_answers, missing_evidence_questionnaires,
missing_evidence_questions, missing_evidence_answers); three additive
nullable/defaulted columns on primary_screening_criteria and
primary_screening_criterion_snapshots
(required_for_phone_review/missing_evidence_question_text/
missing_evidence_answer_level_map); one additive nullable column on
applications (channel_publication_id). No existing row is altered; no
existing column's meaning changes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7c3a9d1e6b4'
down_revision: Union[str, Sequence[str], None] = 'e8b2d5f1a9c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # -- primary_screening_criteria / snapshots: additive fields ----------------
    with op.batch_alter_table('primary_screening_criteria', schema=None) as batch_op:
        batch_op.add_column(sa.Column('required_for_phone_review', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('missing_evidence_question_text', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('missing_evidence_answer_level_map', sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    with op.batch_alter_table('primary_screening_criterion_snapshots', schema=None) as batch_op:
        batch_op.add_column(sa.Column('required_for_phone_review', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('missing_evidence_question_text', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('missing_evidence_answer_level_map', sa.JSON(), nullable=False, server_default=sa.text("'{}'")))

    # -- job_postings (current_rule_set-style circular FK to versions avoided: -
    # -- job_posting_versions references job_postings; approved_version_id is --
    # -- added to job_postings AFTER job_posting_versions exists) --------------
    op.create_table(
        'job_postings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('location_label', sa.String(length=255), nullable=True),
        sa.Column('role', sa.String(length=64), nullable=False),
        sa.Column('rule_set_version_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='DRAFT'),
        sa.Column('current_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('approved_version_id', sa.Integer(), nullable=True),
        sa.Column('created_by', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['selection_sessions.id'], ),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.ForeignKeyConstraint(['rule_set_version_id'], ['selection_rule_set_versions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_job_postings_session_id'), 'job_postings', ['session_id'], unique=False)
    op.create_index(op.f('ix_job_postings_restaurant_id'), 'job_postings', ['restaurant_id'], unique=False)

    op.create_table(
        'job_posting_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_posting_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=True),
        sa.Column('company_description', sa.Text(), nullable=True),
        sa.Column('branch_description', sa.Text(), nullable=True),
        sa.Column('role_summary', sa.Text(), nullable=True),
        sa.Column('responsibilities', sa.Text(), nullable=True),
        sa.Column('minimum_requirements', sa.Text(), nullable=True),
        sa.Column('preferred_experience', sa.Text(), nullable=True),
        sa.Column('availability_expectations', sa.Text(), nullable=True),
        sa.Column('schedule_description', sa.Text(), nullable=True),
        sa.Column('compensation_description', sa.Text(), nullable=True),
        sa.Column('benefits_description', sa.Text(), nullable=True),
        sa.Column('location_context', sa.Text(), nullable=True),
        sa.Column('application_instructions', sa.Text(), nullable=True),
        sa.Column('other_info', sa.Text(), nullable=True),
        sa.Column('source', sa.String(length=16), nullable=False, server_default='SYSTEM_GENERATED'),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('author', sa.String(length=255), nullable=True),
        sa.Column('approved_by', sa.String(length=255), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['job_posting_id'], ['job_postings.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_posting_id', 'version', name='uq_job_posting_version'),
    )
    op.create_index(op.f('ix_job_posting_versions_job_posting_id'), 'job_posting_versions', ['job_posting_id'], unique=False)

    with op.batch_alter_table('job_postings', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_job_postings_approved_version_id', 'job_posting_versions', ['approved_version_id'], ['id'],
        )

    # -- channel_definitions ------------------------------------------------------
    op.create_table(
        'channel_definitions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('is_connected', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('supports_publish', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('supports_update', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('supports_pause', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('supports_stop', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('supports_metrics', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('supports_cost_tracking', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_paid', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('default_acquisition_source_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.ForeignKeyConstraint(['default_acquisition_source_id'], ['acquisition_source_definitions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('restaurant_id', 'name', name='uq_channel_definition_restaurant_name'),
    )
    op.create_index(op.f('ix_channel_definitions_restaurant_id'), 'channel_definitions', ['restaurant_id'], unique=False)

    # -- job_posting_channel_variants / versions ------------------------------------
    op.create_table(
        'job_posting_channel_variants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_posting_id', sa.Integer(), nullable=False),
        sa.Column('channel_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='DRAFT'),
        sa.Column('current_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('approved_version_id', sa.Integer(), nullable=True),
        sa.Column('created_by', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['job_posting_id'], ['job_postings.id'], ),
        sa.ForeignKeyConstraint(['channel_id'], ['channel_definitions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_job_posting_channel_variants_job_posting_id'), 'job_posting_channel_variants', ['job_posting_id'], unique=False)
    op.create_index(op.f('ix_job_posting_channel_variants_channel_id'), 'job_posting_channel_variants', ['channel_id'], unique=False)

    op.create_table(
        'job_posting_channel_variant_versions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('variant_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('title_override', sa.String(length=500), nullable=True),
        sa.Column('variant_text', sa.Text(), nullable=False),
        sa.Column('source', sa.String(length=16), nullable=False, server_default='SYSTEM_GENERATED'),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('author', sa.String(length=255), nullable=True),
        sa.Column('approved_by', sa.String(length=255), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['variant_id'], ['job_posting_channel_variants.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('variant_id', 'version', name='uq_job_posting_channel_variant_version'),
    )
    op.create_index(op.f('ix_job_posting_channel_variant_versions_variant_id'), 'job_posting_channel_variant_versions', ['variant_id'], unique=False)

    with op.batch_alter_table('job_posting_channel_variants', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_job_posting_channel_variants_approved_version_id', 'job_posting_channel_variant_versions',
            ['approved_version_id'], ['id'],
        )

    # -- channel_publications / tracking links -------------------------------------
    op.create_table(
        'channel_publications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('variant_version_id', sa.Integer(), nullable=False),
        sa.Column('channel_id', sa.Integer(), nullable=False),
        sa.Column('placement_label', sa.String(length=255), nullable=False),
        sa.Column('is_connected', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='DRAFT'),
        sa.Column('publish_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('external_link', sa.String(length=1000), nullable=True),
        sa.Column('cost_amount_cents', sa.Integer(), nullable=True),
        sa.Column('cost_currency', sa.String(length=8), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['variant_version_id'], ['job_posting_channel_variant_versions.id'], ),
        sa.ForeignKeyConstraint(['channel_id'], ['channel_definitions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_channel_publications_variant_version_id'), 'channel_publications', ['variant_version_id'], unique=False)
    op.create_index(op.f('ix_channel_publications_channel_id'), 'channel_publications', ['channel_id'], unique=False)

    op.create_table(
        'channel_tracking_links',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('channel_publication_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['channel_publication_id'], ['channel_publications.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_channel_tracking_links_token'), 'channel_tracking_links', ['token'], unique=True)
    op.create_index(op.f('ix_channel_tracking_links_channel_publication_id'), 'channel_tracking_links', ['channel_publication_id'], unique=False)

    # -- applications.channel_publication_id ---------------------------------------
    with op.batch_alter_table('applications', schema=None) as batch_op:
        batch_op.add_column(sa.Column('channel_publication_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_applications_channel_publication_id', 'channel_publications', ['channel_publication_id'], ['id'],
        )
    op.create_index(op.f('ix_applications_channel_publication_id'), 'applications', ['channel_publication_id'], unique=False)

    # -- application_question_definitions / answers --------------------------------
    op.create_table(
        'application_question_definitions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('session_id', sa.Integer(), nullable=True),
        sa.Column('target_role', sa.String(length=64), nullable=True),
        sa.Column('question_text', sa.Text(), nullable=False),
        sa.Column('response_type', sa.String(length=16), nullable=False, server_default='TEXT'),
        sa.Column('is_required', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('related_criterion_id', sa.Integer(), nullable=True),
        sa.Column('answer_level_map', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.ForeignKeyConstraint(['session_id'], ['selection_sessions.id'], ),
        sa.ForeignKeyConstraint(['related_criterion_id'], ['primary_screening_criteria.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_application_question_definitions_restaurant_id'), 'application_question_definitions', ['restaurant_id'], unique=False)
    op.create_index(op.f('ix_application_question_definitions_session_id'), 'application_question_definitions', ['session_id'], unique=False)

    op.create_table(
        'application_question_answers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('question_definition_id', sa.Integer(), nullable=False),
        sa.Column('question_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('raw_answer', sa.Text(), nullable=False),
        sa.Column('answered_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.ForeignKeyConstraint(['question_definition_id'], ['application_question_definitions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_application_question_answers_application_id'), 'application_question_answers', ['application_id'], unique=False)
    op.create_index(op.f('ix_application_question_answers_question_definition_id'), 'application_question_answers', ['question_definition_id'], unique=False)

    # -- missing_evidence_questionnaires / questions / answers ----------------------
    op.create_table(
        'missing_evidence_questionnaires',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('primary_screening_run_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='PENDING'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.ForeignKeyConstraint(['primary_screening_run_id'], ['primary_screening_runs.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_missing_evidence_questionnaires_token'), 'missing_evidence_questionnaires', ['token'], unique=True)
    op.create_index(op.f('ix_missing_evidence_questionnaires_application_id'), 'missing_evidence_questionnaires', ['application_id'], unique=False)
    op.create_index(op.f('ix_missing_evidence_questionnaires_primary_screening_run_id'), 'missing_evidence_questionnaires', ['primary_screening_run_id'], unique=False)

    op.create_table(
        'missing_evidence_questions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('questionnaire_id', sa.Integer(), nullable=False),
        sa.Column('criterion_id', sa.Integer(), nullable=False),
        sa.Column('question_text', sa.Text(), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['questionnaire_id'], ['missing_evidence_questionnaires.id'], ),
        sa.ForeignKeyConstraint(['criterion_id'], ['primary_screening_criteria.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_missing_evidence_questions_questionnaire_id'), 'missing_evidence_questions', ['questionnaire_id'], unique=False)
    op.create_index(op.f('ix_missing_evidence_questions_criterion_id'), 'missing_evidence_questions', ['criterion_id'], unique=False)

    op.create_table(
        'missing_evidence_answers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('question_id', sa.Integer(), nullable=False),
        sa.Column('raw_answer', sa.Text(), nullable=False),
        sa.Column('answered_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['question_id'], ['missing_evidence_questions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_missing_evidence_answers_question_id'), 'missing_evidence_answers', ['question_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(op.f('ix_missing_evidence_answers_question_id'), table_name='missing_evidence_answers')
    op.drop_table('missing_evidence_answers')

    op.drop_index(op.f('ix_missing_evidence_questions_criterion_id'), table_name='missing_evidence_questions')
    op.drop_index(op.f('ix_missing_evidence_questions_questionnaire_id'), table_name='missing_evidence_questions')
    op.drop_table('missing_evidence_questions')

    op.drop_index(op.f('ix_missing_evidence_questionnaires_primary_screening_run_id'), table_name='missing_evidence_questionnaires')
    op.drop_index(op.f('ix_missing_evidence_questionnaires_application_id'), table_name='missing_evidence_questionnaires')
    op.drop_index(op.f('ix_missing_evidence_questionnaires_token'), table_name='missing_evidence_questionnaires')
    op.drop_table('missing_evidence_questionnaires')

    op.drop_index(op.f('ix_application_question_answers_question_definition_id'), table_name='application_question_answers')
    op.drop_index(op.f('ix_application_question_answers_application_id'), table_name='application_question_answers')
    op.drop_table('application_question_answers')

    op.drop_index(op.f('ix_application_question_definitions_session_id'), table_name='application_question_definitions')
    op.drop_index(op.f('ix_application_question_definitions_restaurant_id'), table_name='application_question_definitions')
    op.drop_table('application_question_definitions')

    op.drop_index(op.f('ix_applications_channel_publication_id'), table_name='applications')
    with op.batch_alter_table('applications', schema=None) as batch_op:
        batch_op.drop_constraint('fk_applications_channel_publication_id', type_='foreignkey')
        batch_op.drop_column('channel_publication_id')

    op.drop_index(op.f('ix_channel_tracking_links_channel_publication_id'), table_name='channel_tracking_links')
    op.drop_index(op.f('ix_channel_tracking_links_token'), table_name='channel_tracking_links')
    op.drop_table('channel_tracking_links')

    op.drop_index(op.f('ix_channel_publications_channel_id'), table_name='channel_publications')
    op.drop_index(op.f('ix_channel_publications_variant_version_id'), table_name='channel_publications')
    op.drop_table('channel_publications')

    with op.batch_alter_table('job_posting_channel_variants', schema=None) as batch_op:
        batch_op.drop_constraint('fk_job_posting_channel_variants_approved_version_id', type_='foreignkey')

    op.drop_index(op.f('ix_job_posting_channel_variant_versions_variant_id'), table_name='job_posting_channel_variant_versions')
    op.drop_table('job_posting_channel_variant_versions')

    op.drop_index(op.f('ix_job_posting_channel_variants_channel_id'), table_name='job_posting_channel_variants')
    op.drop_index(op.f('ix_job_posting_channel_variants_job_posting_id'), table_name='job_posting_channel_variants')
    op.drop_table('job_posting_channel_variants')

    op.drop_index(op.f('ix_channel_definitions_restaurant_id'), table_name='channel_definitions')
    op.drop_table('channel_definitions')

    with op.batch_alter_table('job_postings', schema=None) as batch_op:
        batch_op.drop_constraint('fk_job_postings_approved_version_id', type_='foreignkey')

    op.drop_index(op.f('ix_job_posting_versions_job_posting_id'), table_name='job_posting_versions')
    op.drop_table('job_posting_versions')

    op.drop_index(op.f('ix_job_postings_restaurant_id'), table_name='job_postings')
    op.drop_index(op.f('ix_job_postings_session_id'), table_name='job_postings')
    op.drop_table('job_postings')

    with op.batch_alter_table('primary_screening_criterion_snapshots', schema=None) as batch_op:
        batch_op.drop_column('missing_evidence_answer_level_map')
        batch_op.drop_column('missing_evidence_question_text')
        batch_op.drop_column('required_for_phone_review')
    with op.batch_alter_table('primary_screening_criteria', schema=None) as batch_op:
        batch_op.drop_column('missing_evidence_answer_level_map')
        batch_op.drop_column('missing_evidence_question_text')
        batch_op.drop_column('required_for_phone_review')
