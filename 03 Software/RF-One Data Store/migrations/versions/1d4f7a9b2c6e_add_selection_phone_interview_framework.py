"""add Selection Phone Interview framework (Task 4A)

Revision ID: 1d4f7a9b2c6e
Revises: c8e4a1f7d2b9
Create Date: 2026-09-02 00:00:00.000000

Additive, non-destructive changes implementing the RF-One Selection Task 4A
Phone Interview framework:

- `phone_interview_question_definitions` — restaurant-configurable Core
  (and Courtesy) Question library (task §3/§18), mirroring `requirements`/
  `signal_definitions`' shape (restaurant/role scoping, active/version,
  display order).
- `phone_interview_plans` — one Application's Phone Interview (task §1),
  pinned to the same immutable `requirement_set_snapshot_id`/
  `fit_assessment_id` already used at résumé stage.
- `phone_interview_question_instances` — questions actually placed into one
  plan (task §9) — CORE/DYNAMIC/COURTESY/FOLLOW_UP, each a copy-by-value of
  its text/objective/importance at the moment it entered the plan.

No existing table, row or column is altered in a way that loses data. The
post-Phone-Interview ADVANCE_TO_IN_PERSON/HOLD/STOP decision (task §22)
reuses the existing `applications.workflow_status` column (no schema
change needed — `ADVANCE_TO_IN_PERSON` is simply a new allowed value of an
already-unconstrained String column, validated in Python by
`core/application_model.WORKFLOW_STATUSES`).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1d4f7a9b2c6e'
down_revision: Union[str, Sequence[str], None] = 'c8e4a1f7d2b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'phone_interview_question_definitions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('target_role', sa.String(length=64), nullable=True),
        sa.Column('question_text', sa.Text(), nullable=False),
        sa.Column('objective', sa.Text(), nullable=True),
        sa.Column('linked_requirement_ids', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('linked_signal_definition_ids', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('importance', sa.String(length=16), nullable=False, server_default='MEDIUM'),
        sa.Column('is_sine_qua_non', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('mandatory_within_selection_process', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('assessment_stages', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('follow_up_guidance', sa.Text(), nullable=True),
        sa.Column('is_courtesy', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_phone_interview_question_definitions_restaurant_id'),
        'phone_interview_question_definitions', ['restaurant_id'], unique=False,
    )
    op.create_index(
        op.f('ix_phone_interview_question_definitions_target_role'),
        'phone_interview_question_definitions', ['target_role'], unique=False,
    )

    op.create_table(
        'phone_interview_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('person_id', sa.Integer(), nullable=False),
        sa.Column('candidate_id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('requirement_set_snapshot_id', sa.Integer(), nullable=False),
        sa.Column('fit_assessment_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False, server_default='NOT_STARTED'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('escape_route_activated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('escape_route_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.ForeignKeyConstraint(['person_id'], ['candidate_persons.id'], ),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.ForeignKeyConstraint(['requirement_set_snapshot_id'], ['requirement_set_snapshots.id'], ),
        sa.ForeignKeyConstraint(['fit_assessment_id'], ['fit_assessments.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('application_id', name='uq_phone_interview_plans_application_id'),
    )
    op.create_index(
        op.f('ix_phone_interview_plans_application_id'), 'phone_interview_plans', ['application_id'], unique=True,
    )
    op.create_index(
        op.f('ix_phone_interview_plans_person_id'), 'phone_interview_plans', ['person_id'], unique=False,
    )
    op.create_index(
        op.f('ix_phone_interview_plans_candidate_id'), 'phone_interview_plans', ['candidate_id'], unique=False,
    )
    op.create_index(
        op.f('ix_phone_interview_plans_restaurant_id'), 'phone_interview_plans', ['restaurant_id'], unique=False,
    )
    op.create_index(
        op.f('ix_phone_interview_plans_requirement_set_snapshot_id'),
        'phone_interview_plans', ['requirement_set_snapshot_id'], unique=False,
    )
    op.create_index(
        op.f('ix_phone_interview_plans_fit_assessment_id'),
        'phone_interview_plans', ['fit_assessment_id'], unique=False,
    )

    op.create_table(
        'phone_interview_question_instances',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('source_type', sa.String(length=16), nullable=False),
        sa.Column('source_question_definition_id', sa.Integer(), nullable=True),
        sa.Column('parent_question_instance_id', sa.Integer(), nullable=True),
        sa.Column('question_text', sa.Text(), nullable=False),
        sa.Column('objective', sa.Text(), nullable=True),
        sa.Column('linked_requirement_ids', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('linked_signal_definition_ids', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('importance', sa.String(length=16), nullable=False, server_default='MEDIUM'),
        sa.Column('is_sine_qua_non', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('mandatory_within_selection_process', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reason_for_inclusion', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=24), nullable=False, server_default='NOT_ASKED'),
        sa.Column('gate_evaluation', sa.String(length=16), nullable=True),
        sa.Column('answer_text', sa.Text(), nullable=True),
        sa.Column('selezionatore_note', sa.Text(), nullable=True),
        sa.Column('carried_forward_reason', sa.Text(), nullable=True),
        sa.Column('asked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('answered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['plan_id'], ['phone_interview_plans.id'], ),
        sa.ForeignKeyConstraint(['parent_question_instance_id'], ['phone_interview_question_instances.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_phone_interview_question_instances_plan_id'),
        'phone_interview_question_instances', ['plan_id'], unique=False,
    )
    op.create_index(
        op.f('ix_phone_interview_question_instances_parent_question_instance_id'),
        'phone_interview_question_instances', ['parent_question_instance_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_phone_interview_question_instances_parent_question_instance_id'),
        table_name='phone_interview_question_instances',
    )
    op.drop_index(
        op.f('ix_phone_interview_question_instances_plan_id'), table_name='phone_interview_question_instances',
    )
    op.drop_table('phone_interview_question_instances')

    op.drop_index(op.f('ix_phone_interview_plans_fit_assessment_id'), table_name='phone_interview_plans')
    op.drop_index(op.f('ix_phone_interview_plans_requirement_set_snapshot_id'), table_name='phone_interview_plans')
    op.drop_index(op.f('ix_phone_interview_plans_restaurant_id'), table_name='phone_interview_plans')
    op.drop_index(op.f('ix_phone_interview_plans_candidate_id'), table_name='phone_interview_plans')
    op.drop_index(op.f('ix_phone_interview_plans_person_id'), table_name='phone_interview_plans')
    op.drop_index(op.f('ix_phone_interview_plans_application_id'), table_name='phone_interview_plans')
    op.drop_table('phone_interview_plans')

    op.drop_index(
        op.f('ix_phone_interview_question_definitions_target_role'),
        table_name='phone_interview_question_definitions',
    )
    op.drop_index(
        op.f('ix_phone_interview_question_definitions_restaurant_id'),
        table_name='phone_interview_question_definitions',
    )
    op.drop_table('phone_interview_question_definitions')
