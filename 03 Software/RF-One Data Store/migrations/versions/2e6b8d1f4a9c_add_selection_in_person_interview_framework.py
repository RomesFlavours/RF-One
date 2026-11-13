"""add Selection In-Person Interview + Practical Assessment + Consistency Engine (Task 4B)

Revision ID: 2e6b8d1f4a9c
Revises: 1d4f7a9b2c6e
Create Date: 2026-09-02 00:00:00.000000

Additive, non-destructive changes implementing the RF-One Selection Task 4B
In-Person Interview / Practical Assessment / Consistency Engine framework:

- `in_person_interview_section_definitions` / `assessment_item_definitions`
  — restaurant-configurable interview structure (task §2/§3/§24), mirroring
  `requirements`/`phone_interview_question_definitions`' shape.
- `in_person_interview_plans` — one Application's In-Person Interview
  (task §1), pinned to the same immutable `requirement_set_snapshot_id`/
  `fit_assessment_id` already used, optionally linked to a
  `phone_interview_plan_id`.
- `assessment_item_instances` — one unified table for every item type
  actually placed into a plan (task §3/§9), copy-by-value at entry time.
- `consistency_threads` / `consistency_statements` — the Consistency Engine
  (task §8-§14): one topic compared across multiple sources, append-only
  source statements, a neutral comparison status (never a dishonesty
  label).

No existing table, row or column is altered in a way that loses data.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2e6b8d1f4a9c'
down_revision: Union[str, Sequence[str], None] = '1d4f7a9b2c6e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'in_person_interview_section_definitions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('target_role', sa.String(length=64), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('section_kind', sa.String(length=32), nullable=False, server_default='OTHER'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_in_person_interview_section_definitions_restaurant_id'),
        'in_person_interview_section_definitions', ['restaurant_id'], unique=False,
    )
    op.create_index(
        op.f('ix_in_person_interview_section_definitions_target_role'),
        'in_person_interview_section_definitions', ['target_role'], unique=False,
    )

    op.create_table(
        'assessment_item_definitions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('section_id', sa.Integer(), nullable=False),
        sa.Column('item_type', sa.String(length=24), nullable=False),
        sa.Column('title_or_question', sa.Text(), nullable=False),
        sa.Column('instruction', sa.Text(), nullable=True),
        sa.Column('scenario', sa.Text(), nullable=True),
        sa.Column('objective', sa.Text(), nullable=True),
        sa.Column('linked_requirement_ids', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('linked_signal_definition_ids', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('importance', sa.String(length=16), nullable=False, server_default='MEDIUM'),
        sa.Column('mandatory_within_selection_process', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('evidence_expected', sa.Text(), nullable=True),
        sa.Column('evidence_positive', sa.Text(), nullable=True),
        sa.Column('evidence_contrary', sa.Text(), nullable=True),
        sa.Column('evidence_insufficient', sa.Text(), nullable=True),
        sa.Column('selezionatore_instructions', sa.Text(), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['section_id'], ['in_person_interview_section_definitions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_assessment_item_definitions_section_id'), 'assessment_item_definitions', ['section_id'],
        unique=False,
    )

    op.create_table(
        'consistency_threads',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('topic', sa.String(length=255), nullable=False),
        sa.Column('importance', sa.String(length=16), nullable=False, server_default='MEDIUM'),
        sa.Column('comparison_status', sa.String(length=24), nullable=False, server_default='UNRESOLVED'),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('confidence', sa.String(length=16), nullable=True),
        sa.Column('selezionatore_resolution', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_consistency_threads_application_id'), 'consistency_threads', ['application_id'], unique=False,
    )

    op.create_table(
        'consistency_statements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('thread_id', sa.Integer(), nullable=False),
        sa.Column('source_stage', sa.String(length=24), nullable=False),
        sa.Column('source_reference', sa.String(length=255), nullable=True),
        sa.Column('source_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('raw_statement', sa.Text(), nullable=False),
        sa.Column('normalized_interpretation', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['thread_id'], ['consistency_threads.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_consistency_statements_thread_id'), 'consistency_statements', ['thread_id'], unique=False,
    )

    op.create_table(
        'in_person_interview_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('person_id', sa.Integer(), nullable=False),
        sa.Column('candidate_id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('requirement_set_snapshot_id', sa.Integer(), nullable=False),
        sa.Column('fit_assessment_id', sa.Integer(), nullable=False),
        sa.Column('phone_interview_plan_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=24), nullable=False, server_default='NOT_STARTED'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.ForeignKeyConstraint(['person_id'], ['candidate_persons.id'], ),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.ForeignKeyConstraint(['requirement_set_snapshot_id'], ['requirement_set_snapshots.id'], ),
        sa.ForeignKeyConstraint(['fit_assessment_id'], ['fit_assessments.id'], ),
        sa.ForeignKeyConstraint(['phone_interview_plan_id'], ['phone_interview_plans.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('application_id', name='uq_in_person_interview_plans_application_id'),
    )
    op.create_index(
        op.f('ix_in_person_interview_plans_application_id'), 'in_person_interview_plans', ['application_id'],
        unique=True,
    )
    op.create_index(
        op.f('ix_in_person_interview_plans_person_id'), 'in_person_interview_plans', ['person_id'], unique=False,
    )
    op.create_index(
        op.f('ix_in_person_interview_plans_candidate_id'), 'in_person_interview_plans', ['candidate_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_in_person_interview_plans_restaurant_id'), 'in_person_interview_plans', ['restaurant_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_in_person_interview_plans_requirement_set_snapshot_id'), 'in_person_interview_plans',
        ['requirement_set_snapshot_id'], unique=False,
    )
    op.create_index(
        op.f('ix_in_person_interview_plans_fit_assessment_id'), 'in_person_interview_plans', ['fit_assessment_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_in_person_interview_plans_phone_interview_plan_id'), 'in_person_interview_plans',
        ['phone_interview_plan_id'], unique=False,
    )

    op.create_table(
        'assessment_item_instances',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('source_type', sa.String(length=24), nullable=False),
        sa.Column('source_item_definition_id', sa.Integer(), nullable=True),
        sa.Column('source_phone_question_instance_id', sa.Integer(), nullable=True),
        sa.Column('consistency_thread_id', sa.Integer(), nullable=True),
        sa.Column('section_name', sa.String(length=255), nullable=False),
        sa.Column('section_kind', sa.String(length=32), nullable=False, server_default='OTHER'),
        sa.Column('section_display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('title_or_question', sa.Text(), nullable=False),
        sa.Column('instruction', sa.Text(), nullable=True),
        sa.Column('scenario', sa.Text(), nullable=True),
        sa.Column('objective', sa.Text(), nullable=True),
        sa.Column('linked_requirement_ids', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('linked_signal_definition_ids', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('importance', sa.String(length=16), nullable=False, server_default='MEDIUM'),
        sa.Column('mandatory_within_selection_process', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('selezionatore_instructions', sa.Text(), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reason_for_inclusion', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=24), nullable=False, server_default='NOT_DONE'),
        sa.Column('raw_response', sa.Text(), nullable=True),
        sa.Column('selezionatore_note', sa.Text(), nullable=True),
        sa.Column('confidence', sa.String(length=16), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['plan_id'], ['in_person_interview_plans.id'], ),
        sa.ForeignKeyConstraint(['consistency_thread_id'], ['consistency_threads.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_assessment_item_instances_plan_id'), 'assessment_item_instances', ['plan_id'], unique=False,
    )
    op.create_index(
        op.f('ix_assessment_item_instances_consistency_thread_id'), 'assessment_item_instances',
        ['consistency_thread_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_assessment_item_instances_consistency_thread_id'), table_name='assessment_item_instances')
    op.drop_index(op.f('ix_assessment_item_instances_plan_id'), table_name='assessment_item_instances')
    op.drop_table('assessment_item_instances')

    op.drop_index(op.f('ix_in_person_interview_plans_phone_interview_plan_id'), table_name='in_person_interview_plans')
    op.drop_index(op.f('ix_in_person_interview_plans_fit_assessment_id'), table_name='in_person_interview_plans')
    op.drop_index(op.f('ix_in_person_interview_plans_requirement_set_snapshot_id'), table_name='in_person_interview_plans')
    op.drop_index(op.f('ix_in_person_interview_plans_restaurant_id'), table_name='in_person_interview_plans')
    op.drop_index(op.f('ix_in_person_interview_plans_candidate_id'), table_name='in_person_interview_plans')
    op.drop_index(op.f('ix_in_person_interview_plans_person_id'), table_name='in_person_interview_plans')
    op.drop_index(op.f('ix_in_person_interview_plans_application_id'), table_name='in_person_interview_plans')
    op.drop_table('in_person_interview_plans')

    op.drop_index(op.f('ix_consistency_statements_thread_id'), table_name='consistency_statements')
    op.drop_table('consistency_statements')

    op.drop_index(op.f('ix_consistency_threads_application_id'), table_name='consistency_threads')
    op.drop_table('consistency_threads')

    op.drop_index(op.f('ix_assessment_item_definitions_section_id'), table_name='assessment_item_definitions')
    op.drop_table('assessment_item_definitions')

    op.drop_index(
        op.f('ix_in_person_interview_section_definitions_target_role'),
        table_name='in_person_interview_section_definitions',
    )
    op.drop_index(
        op.f('ix_in_person_interview_section_definitions_restaurant_id'),
        table_name='in_person_interview_section_definitions',
    )
    op.drop_table('in_person_interview_section_definitions')
