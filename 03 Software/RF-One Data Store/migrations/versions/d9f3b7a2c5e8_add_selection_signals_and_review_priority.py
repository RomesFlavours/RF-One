"""add Selection Signals + Review Priority (TASK 3C)

Revision ID: d9f3b7a2c5e8
Revises: e5a1c8d3f6b2
Create Date: 2026-09-05 00:00:00.000000

Seven additive, non-destructive tables implementing the RF-One Selection
3C Concept Note (Selection Signals + Review Priority):

- `candidate_persons` — the PERSON, across every Application (concept note
  §1); distinct from the existing `candidates` table, which keeps its
  Task 2A meaning unchanged (one résumé/CV dataset for one Application).
- `applications` — one specific application by one person, for a specific
  role/context/date; links a `candidate_persons` row, a `candidates` row
  (unique — one Application per CV snapshot), and carries Review Priority.
- `signal_definitions` — restaurant-configurable Selection Signal
  definitions (mirrors `requirements`' shape).
- `signal_observations` — one (Application, SignalDefinition) unit (mirrors
  `requirement_assessments`).
- `signal_evidence_items` — append-only evidence for a SignalObservation
  (mirrors `evidence_items`; a separate table, not shared/polymorphic, so
  that existing table's NOT NULL `requirement_assessment_id` is untouched).
- `review_priority_policies` / `review_priority_policy_rules` — the
  restaurant-owned policy layer deciding how much a detected Signal affects
  Review Priority, kept structurally separate from Signal detection itself.

No existing table, row or column (Task 2A/2B/3A/3A-FIX/3B) is altered or
dropped.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9f3b7a2c5e8'
down_revision: Union[str, Sequence[str], None] = 'e5a1c8d3f6b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'candidate_persons',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('full_name', sa.String(length=255), nullable=True),
        sa.Column('primary_email', sa.String(length=255), nullable=True),
        sa.Column('primary_phone', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_candidate_persons_restaurant_id'), 'candidate_persons', ['restaurant_id'], unique=False)
    op.create_index(op.f('ix_candidate_persons_primary_email'), 'candidate_persons', ['primary_email'], unique=False)

    op.create_table(
        'applications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('person_id', sa.Integer(), nullable=False),
        sa.Column('candidate_id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('requirement_set_id', sa.Integer(), nullable=True),
        sa.Column('target_role', sa.String(length=64), nullable=True),
        sa.Column('applied_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('outcome', sa.String(length=32), nullable=True),
        sa.Column('review_priority_system', sa.String(length=16), nullable=True),
        sa.Column('review_priority_effective', sa.String(length=16), nullable=True),
        sa.Column('review_priority_origin', sa.String(length=24), nullable=False, server_default='SYSTEM_GENERATED'),
        sa.Column('review_priority_override_reason', sa.Text(), nullable=True),
        sa.Column('review_priority_overridden_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['person_id'], ['candidate_persons.id'], ),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.ForeignKeyConstraint(['requirement_set_id'], ['requirement_sets.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('candidate_id', name='uq_applications_candidate_id'),
    )
    op.create_index(op.f('ix_applications_person_id'), 'applications', ['person_id'], unique=False)
    op.create_index(op.f('ix_applications_candidate_id'), 'applications', ['candidate_id'], unique=False)
    op.create_index(op.f('ix_applications_restaurant_id'), 'applications', ['restaurant_id'], unique=False)
    op.create_index(op.f('ix_applications_requirement_set_id'), 'applications', ['requirement_set_id'], unique=False)

    op.create_table(
        'signal_definitions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('signal_family', sa.String(length=24), nullable=False),
        sa.Column('signal_subtype', sa.String(length=64), nullable=True),
        sa.Column('assessment_stages', sa.JSON(), nullable=False),
        sa.Column('evidence_sources_allowed', sa.JSON(), nullable=False),
        sa.Column('detection_guidance', sa.Text(), nullable=True),
        sa.Column('evidence_positive', sa.Text(), nullable=True),
        sa.Column('evidence_contrary', sa.Text(), nullable=True),
        sa.Column('evidence_insufficient', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_signal_definitions_restaurant_id'), 'signal_definitions', ['restaurant_id'], unique=False)

    op.create_table(
        'signal_observations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('signal_definition_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='NOT_ASSESSED'),
        sa.Column('confidence', sa.String(length=16), nullable=True),
        sa.Column('rationale', sa.Text(), nullable=True),
        sa.Column('detected_pattern', sa.Text(), nullable=True),
        sa.Column('origin', sa.String(length=24), nullable=False, server_default='SYSTEM_GENERATED'),
        sa.Column('override_reason', sa.Text(), nullable=True),
        sa.Column('overridden_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.ForeignKeyConstraint(['signal_definition_id'], ['signal_definitions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('application_id', 'signal_definition_id', name='uq_signal_observation_app_def'),
    )
    op.create_index(op.f('ix_signal_observations_application_id'), 'signal_observations', ['application_id'], unique=False)
    op.create_index(
        op.f('ix_signal_observations_signal_definition_id'), 'signal_observations', ['signal_definition_id'],
        unique=False,
    )

    op.create_table(
        'signal_evidence_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('signal_observation_id', sa.Integer(), nullable=False),
        sa.Column('source_type', sa.String(length=32), nullable=False),
        sa.Column('source_stage', sa.String(length=24), nullable=True),
        sa.Column('source_reference', sa.String(length=255), nullable=True),
        sa.Column('evidence_text', sa.Text(), nullable=True),
        sa.Column('evidence_classification', sa.String(length=24), nullable=False),
        sa.Column('evidence_relationship', sa.String(length=16), nullable=False),
        sa.Column('confidence', sa.String(length=16), nullable=False, server_default='UNKNOWN'),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('is_system_generated', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['signal_observation_id'], ['signal_observations.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_signal_evidence_items_signal_observation_id'), 'signal_evidence_items', ['signal_observation_id'],
        unique=False,
    )

    op.create_table(
        'review_priority_policies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_review_priority_policies_restaurant_id'), 'review_priority_policies', ['restaurant_id'],
        unique=False,
    )

    op.create_table(
        'review_priority_policy_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('policy_id', sa.Integer(), nullable=False),
        sa.Column('signal_definition_id', sa.Integer(), nullable=False),
        sa.Column('observed_status', sa.String(length=16), nullable=False),
        sa.Column('contribution', sa.String(length=24), nullable=False),
        sa.ForeignKeyConstraint(['policy_id'], ['review_priority_policies.id'], ),
        sa.ForeignKeyConstraint(['signal_definition_id'], ['signal_definitions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'policy_id', 'signal_definition_id', 'observed_status', name='uq_priority_rule_policy_def_status'
        ),
    )
    op.create_index(
        op.f('ix_review_priority_policy_rules_policy_id'), 'review_priority_policy_rules', ['policy_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_review_priority_policy_rules_signal_definition_id'), 'review_priority_policy_rules',
        ['signal_definition_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_review_priority_policy_rules_signal_definition_id'), table_name='review_priority_policy_rules'
    )
    op.drop_index(op.f('ix_review_priority_policy_rules_policy_id'), table_name='review_priority_policy_rules')
    op.drop_table('review_priority_policy_rules')

    op.drop_index(op.f('ix_review_priority_policies_restaurant_id'), table_name='review_priority_policies')
    op.drop_table('review_priority_policies')

    op.drop_index(op.f('ix_signal_evidence_items_signal_observation_id'), table_name='signal_evidence_items')
    op.drop_table('signal_evidence_items')

    op.drop_index(op.f('ix_signal_observations_signal_definition_id'), table_name='signal_observations')
    op.drop_index(op.f('ix_signal_observations_application_id'), table_name='signal_observations')
    op.drop_table('signal_observations')

    op.drop_index(op.f('ix_signal_definitions_restaurant_id'), table_name='signal_definitions')
    op.drop_table('signal_definitions')

    op.drop_index(op.f('ix_applications_requirement_set_id'), table_name='applications')
    op.drop_index(op.f('ix_applications_restaurant_id'), table_name='applications')
    op.drop_index(op.f('ix_applications_candidate_id'), table_name='applications')
    op.drop_index(op.f('ix_applications_person_id'), table_name='applications')
    op.drop_table('applications')

    op.drop_index(op.f('ix_candidate_persons_primary_email'), table_name='candidate_persons')
    op.drop_index(op.f('ix_candidate_persons_restaurant_id'), table_name='candidate_persons')
    op.drop_table('candidate_persons')
