"""add Selection 5A-FIX operational queues/lists + Outcome target queue

Revision ID: e7c2a9f4d1b6
Revises: d6a4c9e2f7b3
Create Date: 2026-09-03 00:00:00.000000

Additive, non-destructive changes implementing the RF-One Selection Task
5A-FIX operational queue/list model (task §7-§14):

- `selection_queues` — restaurant-configurable, purely organizational
  queues/lists (e.g. "Active Review," "Call Later," "Hold").
- `application_queue_movements` — append-only queue-movement history
  (task §9), mirroring `application_stage_transitions`' exact shape.
- `applications.current_queue_id` — a convenience pointer only (mirrors
  `current_stage`/`lifecycle_state`); `NULL` means no queue assigned.
- `selection_outcome_definitions.target_queue_id` /
  `selection_outcome_definition_snapshots.target_queue_id` — the
  OPERATIONAL queue reference (the existing `target_queue_label` column on
  both tables is kept, unchanged, as legacy display-only text).

No existing table, row or column is altered in a way that loses data.
`applications.workflow_status` (Task 3C-FIX/4A) is untouched by this
migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7c2a9f4d1b6'
down_revision: Union[str, Sequence[str], None] = 'd6a4c9e2f7b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'selection_queues',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_selection_queues_restaurant_id'), 'selection_queues', ['restaurant_id'], unique=False)

    op.add_column(
        'selection_outcome_definitions',
        sa.Column('target_queue_id', sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f('ix_selection_outcome_definitions_target_queue_id'), 'selection_outcome_definitions',
        ['target_queue_id'], unique=False,
    )
    with op.batch_alter_table('selection_outcome_definitions') as batch_op:
        batch_op.create_foreign_key(
            'fk_selection_outcome_definitions_target_queue_id', 'selection_queues', ['target_queue_id'], ['id'],
        )

    op.add_column(
        'selection_outcome_definition_snapshots',
        sa.Column('target_queue_id', sa.Integer(), nullable=True),
    )

    op.add_column('applications', sa.Column('current_queue_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_applications_current_queue_id'), 'applications', ['current_queue_id'], unique=False)
    with op.batch_alter_table('applications') as batch_op:
        batch_op.create_foreign_key(
            'fk_applications_current_queue_id', 'selection_queues', ['current_queue_id'], ['id'],
        )

    op.create_table(
        'application_queue_movements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('previous_queue_id', sa.Integer(), nullable=True),
        sa.Column('new_queue_id', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(length=16), nullable=False, server_default='MANUAL'),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('originating_outcome_decision_id', sa.Integer(), nullable=True),
        sa.Column('performed_by', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ),
        sa.ForeignKeyConstraint(['previous_queue_id'], ['selection_queues.id'], ),
        sa.ForeignKeyConstraint(['new_queue_id'], ['selection_queues.id'], ),
        sa.ForeignKeyConstraint(['originating_outcome_decision_id'], ['selection_outcome_decisions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_application_queue_movements_application_id'), 'application_queue_movements', ['application_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_application_queue_movements_new_queue_id'), 'application_queue_movements', ['new_queue_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_application_queue_movements_originating_outcome_decision_id'), 'application_queue_movements',
        ['originating_outcome_decision_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_application_queue_movements_originating_outcome_decision_id'),
        table_name='application_queue_movements',
    )
    op.drop_index(op.f('ix_application_queue_movements_new_queue_id'), table_name='application_queue_movements')
    op.drop_index(op.f('ix_application_queue_movements_application_id'), table_name='application_queue_movements')
    op.drop_table('application_queue_movements')

    with op.batch_alter_table('applications') as batch_op:
        batch_op.drop_constraint('fk_applications_current_queue_id', type_='foreignkey')
    op.drop_index(op.f('ix_applications_current_queue_id'), table_name='applications')
    op.drop_column('applications', 'current_queue_id')

    op.drop_column('selection_outcome_definition_snapshots', 'target_queue_id')

    with op.batch_alter_table('selection_outcome_definitions') as batch_op:
        batch_op.drop_constraint('fk_selection_outcome_definitions_target_queue_id', type_='foreignkey')
    op.drop_index(op.f('ix_selection_outcome_definitions_target_queue_id'), table_name='selection_outcome_definitions')
    op.drop_column('selection_outcome_definitions', 'target_queue_id')

    op.drop_index(op.f('ix_selection_queues_restaurant_id'), table_name='selection_queues')
    op.drop_table('selection_queues')
