"""add Selection Feedback Intelligence Foundation (Pattern Definition/
Signature/Observation, Stage Pattern Snapshot/Delta, Learning Trace,
Selection Effort, Case Memory, Downstream Outcome Feedback, Authority
governance foundation)

Revision ID: 33c870767fef
Revises: a3f8e1c6d9b4
Create Date: 2026-09-03 00:00:00.000000

Twelve new, additive tables only. No existing table, column, or row is
altered. THE PAST IS IMMUTABLE (task's own core principle): every table
below is either append-only (no service function in this codebase ever
UPDATEs or DELETEs a row) or an explicit live/immutable-snapshot pair
mirroring `selection_outcome_definitions`/`selection_outcome_definition_
snapshots`' own exact discipline.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '33c870767fef'
down_revision: Union[str, Sequence[str], None] = 'a3f8e1c6d9b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # -- Authority governance foundation (created first: Pattern Definition
    # -- references it) -----------------------------------------------------
    op.create_table(
        'selection_authority_levels',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('level_key', sa.String(length=64), nullable=False),
        sa.Column('level_order', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=True),
        sa.Column('assigned_holders', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_selection_authority_levels_restaurant_id'), 'selection_authority_levels', ['restaurant_id'], unique=False)

    op.create_table(
        'selection_governance_requirements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('action_type', sa.String(length=64), nullable=False),
        sa.Column('required_authority_level_id', sa.Integer(), nullable=True),
        sa.Column('requires_higher_approval', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.ForeignKeyConstraint(['required_authority_level_id'], ['selection_authority_levels.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_selection_governance_requirements_restaurant_id'), 'selection_governance_requirements', ['restaurant_id'], unique=False)
    op.create_index(op.f('ix_selection_governance_requirements_required_authority_level_id'), 'selection_governance_requirements', ['required_authority_level_id'], unique=False)

    # -- Pattern Definition + Signature + Snapshot + Examples ---------------
    op.create_table(
        'selection_pattern_definitions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('scope', sa.String(length=24), nullable=False, server_default='GENERAL'),
        sa.Column('applicability_context', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='PROPOSED'),
        sa.Column('maturity', sa.String(length=16), nullable=False, server_default='EMERGING'),
        sa.Column('persistence_type', sa.String(length=24), nullable=False, server_default='STRUCTURAL'),
        sa.Column('signature', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('creation_provenance', sa.String(length=32), nullable=False, server_default='HUMAN_AUTHORED'),
        sa.Column('created_by', sa.String(length=255), nullable=True),
        sa.Column('required_authority_level_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.ForeignKeyConstraint(['required_authority_level_id'], ['selection_authority_levels.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_selection_pattern_definitions_restaurant_id'), 'selection_pattern_definitions', ['restaurant_id'], unique=False)
    op.create_index(op.f('ix_selection_pattern_definitions_required_authority_level_id'), 'selection_pattern_definitions', ['required_authority_level_id'], unique=False)

    op.create_table(
        'selection_pattern_definition_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('definition_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('scope', sa.String(length=24), nullable=False),
        sa.Column('applicability_context', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('maturity', sa.String(length=16), nullable=False),
        sa.Column('persistence_type', sa.String(length=24), nullable=False),
        sa.Column('signature', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('creation_provenance', sa.String(length=32), nullable=False),
        sa.Column('was_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['definition_id'], ['selection_pattern_definitions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('definition_id', 'version', name='uq_pattern_definition_snapshot_version'),
    )
    op.create_index(op.f('ix_selection_pattern_definition_snapshots_definition_id'), 'selection_pattern_definition_snapshots', ['definition_id'], unique=False)

    op.create_table(
        'selection_pattern_examples',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pattern_definition_id', sa.Integer(), nullable=False),
        sa.Column('definition_version_at_capture', sa.Integer(), nullable=False),
        sa.Column('example_type', sa.String(length=24), nullable=False, server_default='ORIGINAL'),
        sa.Column('case_reference', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('provenance', sa.String(length=32), nullable=False, server_default='HUMAN_AUTHORED'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['pattern_definition_id'], ['selection_pattern_definitions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_selection_pattern_examples_pattern_definition_id'), 'selection_pattern_examples', ['pattern_definition_id'], unique=False)

    # -- Pattern Case Comparison (task §7/§24) --------------------------------
    op.create_table(
        'selection_pattern_case_comparisons',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pattern_definition_id', sa.Integer(), nullable=False),
        sa.Column('pattern_definition_snapshot_id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('classification', sa.String(length=24), nullable=False),
        sa.Column('dimensions_compared', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('supporting_evidence_references', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('internal_numeric_value', sa.Float(), nullable=True),
        sa.Column('provenance', sa.String(length=32), nullable=False, server_default='SYSTEM_GENERATED'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['pattern_definition_id'], ['selection_pattern_definitions.id'], ),
        sa.ForeignKeyConstraint(['pattern_definition_snapshot_id'], ['selection_pattern_definition_snapshots.id'], ),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_selection_pattern_case_comparisons_pattern_definition_id'), 'selection_pattern_case_comparisons', ['pattern_definition_id'], unique=False)
    op.create_index(op.f('ix_selection_pattern_case_comparisons_pattern_definition_snapshot_id'), 'selection_pattern_case_comparisons', ['pattern_definition_snapshot_id'], unique=False)
    op.create_index(op.f('ix_selection_pattern_case_comparisons_application_id'), 'selection_pattern_case_comparisons', ['application_id'], unique=False)

    # -- Pattern Observation --------------------------------------------------
    op.create_table(
        'selection_pattern_observations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pattern_definition_id', sa.Integer(), nullable=False),
        sa.Column('pattern_definition_snapshot_id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('person_id', sa.Integer(), nullable=True),
        sa.Column('stage', sa.String(length=32), nullable=False),
        sa.Column('stage_occurrence_index', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('observation_status', sa.String(length=16), nullable=False, server_default='ACTIVE'),
        sa.Column('superseded_by_id', sa.Integer(), nullable=True),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('relevance', sa.String(length=16), nullable=False, server_default='MEDIUM'),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('evidence_references', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('rule_references', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('provenance', sa.String(length=32), nullable=False, server_default='SYSTEM_GENERATED'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['pattern_definition_id'], ['selection_pattern_definitions.id'], ),
        sa.ForeignKeyConstraint(['pattern_definition_snapshot_id'], ['selection_pattern_definition_snapshots.id'], ),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.ForeignKeyConstraint(['person_id'], ['candidate_persons.id'], ),
        sa.ForeignKeyConstraint(['superseded_by_id'], ['selection_pattern_observations.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_selection_pattern_observations_pattern_definition_id'), 'selection_pattern_observations', ['pattern_definition_id'], unique=False)
    op.create_index(op.f('ix_selection_pattern_observations_pattern_definition_snapshot_id'), 'selection_pattern_observations', ['pattern_definition_snapshot_id'], unique=False)
    op.create_index(op.f('ix_selection_pattern_observations_application_id'), 'selection_pattern_observations', ['application_id'], unique=False)
    op.create_index(op.f('ix_selection_pattern_observations_person_id'), 'selection_pattern_observations', ['person_id'], unique=False)

    # -- Stage Pattern Snapshot + Delta ---------------------------------------
    op.create_table(
        'selection_stage_pattern_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('stage', sa.String(length=32), nullable=False),
        sa.Column('stage_occurrence_index', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('observation_ids', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('pattern_definition_versions', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('rule_versions', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('evidence_references', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('resulting_priority_interpretation', sa.String(length=64), nullable=True),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('rf_one_judgment', sa.Text(), nullable=True),
        sa.Column('selector_action', sa.Text(), nullable=True),
        sa.Column('divergence_occurred', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('divergence_category', sa.String(length=32), nullable=True),
        sa.Column('note_required', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('selector_note', sa.Text(), nullable=True),
        sa.Column('previous_snapshot_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.ForeignKeyConstraint(['previous_snapshot_id'], ['selection_stage_pattern_snapshots.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_selection_stage_pattern_snapshots_application_id'), 'selection_stage_pattern_snapshots', ['application_id'], unique=False)

    op.create_table(
        'selection_stage_pattern_deltas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('stage_snapshot_id', sa.Integer(), nullable=False),
        sa.Column('pattern_definition_id', sa.Integer(), nullable=False),
        sa.Column('delta_type', sa.String(length=24), nullable=False),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['stage_snapshot_id'], ['selection_stage_pattern_snapshots.id'], ),
        sa.ForeignKeyConstraint(['pattern_definition_id'], ['selection_pattern_definitions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_selection_stage_pattern_deltas_stage_snapshot_id'), 'selection_stage_pattern_deltas', ['stage_snapshot_id'], unique=False)
    op.create_index(op.f('ix_selection_stage_pattern_deltas_pattern_definition_id'), 'selection_stage_pattern_deltas', ['pattern_definition_id'], unique=False)

    # -- Learning Trace (append-only) -----------------------------------------
    op.create_table(
        'selection_learning_traces',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=True),
        sa.Column('person_id', sa.Integer(), nullable=True),
        sa.Column('stage', sa.String(length=32), nullable=True),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('event_data', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('source_reference', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('provenance', sa.String(length=32), nullable=False, server_default='SYSTEM_GENERATED'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.ForeignKeyConstraint(['person_id'], ['candidate_persons.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_selection_learning_traces_application_id'), 'selection_learning_traces', ['application_id'], unique=False)
    op.create_index(op.f('ix_selection_learning_traces_person_id'), 'selection_learning_traces', ['person_id'], unique=False)
    op.create_index(op.f('ix_selection_learning_traces_event_type'), 'selection_learning_traces', ['event_type'], unique=False)

    # -- Selection Effort -------------------------------------------------------
    op.create_table(
        'selection_efforts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('stages_traversed_count', sa.Integer(), nullable=True),
        sa.Column('repeated_stages_count', sa.Integer(), nullable=True),
        sa.Column('interviewer_time_minutes', sa.Integer(), nullable=True),
        sa.Column('tests_administered_count', sa.Integer(), nullable=True),
        sa.Column('followups_count', sa.Integer(), nullable=True),
        sa.Column('preparation_notes', sa.Text(), nullable=True),
        sa.Column('interactions_count', sa.Integer(), nullable=True),
        sa.Column('point_of_exit', sa.String(length=64), nullable=True),
        sa.Column('final_outcome', sa.String(length=255), nullable=True),
        sa.Column('effort_elements', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_selection_efforts_application_id'), 'selection_efforts', ['application_id'], unique=False)

    # -- Case Memory (references Outcome Decision + Stage Snapshot + Effort) -
    op.create_table(
        'selection_case_memories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('person_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_current', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('previous_case_memory_id', sa.Integer(), nullable=True),
        sa.Column('reopening_event_reference', sa.JSON(), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('outcome_decision_id', sa.Integer(), nullable=False),
        sa.Column('lifecycle_state_at_closure', sa.String(length=16), nullable=False),
        sa.Column('essential_facts', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('selection_signals_summary', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('final_stage_snapshot_id', sa.Integer(), nullable=True),
        sa.Column('stage_snapshot_ids', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('materially_impactful_pattern_versions', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('materially_impactful_rules', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('rf_one_final_judgment', sa.Text(), nullable=True),
        sa.Column('selezionatore_final_decision', sa.Text(), nullable=True),
        sa.Column('skill_findings', sa.JSON(), nullable=True),
        sa.Column('training_burden_estimate', sa.JSON(), nullable=True),
        sa.Column('trainable_gaps', sa.JSON(), nullable=True),
        sa.Column('selection_effort_id', sa.Integer(), nullable=True),
        sa.Column('notes_reference', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('learning_trace_reference', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('evidence_reference', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.ForeignKeyConstraint(['person_id'], ['candidate_persons.id'], ),
        sa.ForeignKeyConstraint(['previous_case_memory_id'], ['selection_case_memories.id'], ),
        sa.ForeignKeyConstraint(['outcome_decision_id'], ['selection_outcome_decisions.id'], ),
        sa.ForeignKeyConstraint(['final_stage_snapshot_id'], ['selection_stage_pattern_snapshots.id'], ),
        sa.ForeignKeyConstraint(['selection_effort_id'], ['selection_efforts.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('application_id', 'version', name='uq_case_memory_application_version'),
    )
    op.create_index(op.f('ix_selection_case_memories_application_id'), 'selection_case_memories', ['application_id'], unique=False)
    op.create_index(op.f('ix_selection_case_memories_person_id'), 'selection_case_memories', ['person_id'], unique=False)
    op.create_index(op.f('ix_selection_case_memories_outcome_decision_id'), 'selection_case_memories', ['outcome_decision_id'], unique=False)

    # -- Downstream Outcome Feedback (foundation only) ------------------------
    op.create_table(
        'selection_downstream_outcome_feedback',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('case_memory_id', sa.Integer(), nullable=True),
        sa.Column('source_domain', sa.String(length=64), nullable=False),
        sa.Column('source_record_reference', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('feedback_type', sa.String(length=64), nullable=False),
        sa.Column('observed_fact', sa.Text(), nullable=False),
        sa.Column('evidence_reference', sa.JSON(), nullable=True),
        sa.Column('classification', sa.String(length=32), nullable=True),
        sa.Column('provenance', sa.String(length=32), nullable=False, server_default='SYSTEM_GENERATED'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.ForeignKeyConstraint(['case_memory_id'], ['selection_case_memories.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_selection_downstream_outcome_feedback_application_id'), 'selection_downstream_outcome_feedback', ['application_id'], unique=False)
    op.create_index(op.f('ix_selection_downstream_outcome_feedback_case_memory_id'), 'selection_downstream_outcome_feedback', ['case_memory_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('selection_downstream_outcome_feedback')
    op.drop_table('selection_case_memories')
    op.drop_table('selection_efforts')
    op.drop_table('selection_learning_traces')
    op.drop_table('selection_stage_pattern_deltas')
    op.drop_table('selection_stage_pattern_snapshots')
    op.drop_table('selection_pattern_observations')
    op.drop_table('selection_pattern_case_comparisons')
    op.drop_table('selection_pattern_examples')
    op.drop_table('selection_pattern_definition_snapshots')
    op.drop_table('selection_pattern_definitions')
    op.drop_table('selection_governance_requirements')
    op.drop_table('selection_authority_levels')
