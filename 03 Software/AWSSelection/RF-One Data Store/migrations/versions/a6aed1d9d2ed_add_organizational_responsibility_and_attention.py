"""add organizational responsibility and attention management runtime (TASK_ATTENTION_ORG_RUNTIME)

Revision ID: a6aed1d9d2ed
Revises: f7174fa37e93
Create Date: 2026-09-12 00:00:00.000000

Six additive, non-destructive new tables implementing the minimum shared,
cross-Domain runtime for Core 2.0's already-approved Organizational
Responsibility (`00 Core/Organizational Responsibility.md`) and Attention
Management (`00 Core/ConceptualArchitecture/12_Attention_Management.md`):

- `positions` — Position, distinct from any person/occupant
- `position_scopes` — a Position's operating perimeter (Corporate/Brand/
  Legal Entity/Operational Unit/Restaurant/Operational Area/Domain/Module/
  Process/Process Phase/Global)
- `position_assignments` — Position -> Occupant (Acting Identity),
  effective-dated
- `position_temporary_coverages` — temporary coverage of one Position by
  another Position or by an Acting Identity directly (a Delegation, reusing
  the same concept `authority_grants` already implements for Authority)
- `process_ownerships` — Process/Phase -> responsible Position, with an
  optional scope override
- `attention_items` — a cross-Domain "something requires human attention"
  record, with routing outcome recorded on the row itself

No existing table or row is affected by this migration — it only creates
six new, empty tables. No Core file was modified.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a6aed1d9d2ed'
down_revision: Union[str, Sequence[str], None] = 'f7174fa37e93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POSITION_SCOPE_KINDS = (
    'CORPORATE', 'BRAND', 'LEGAL_ENTITY', 'OPERATIONAL_UNIT', 'RESTAURANT', 'OPERATIONAL_AREA',
    'DOMAIN', 'MODULE', 'PROCESS', 'PROCESS_PHASE', 'GLOBAL',
)
ATTENTION_PRIORITIES = ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')
ATTENTION_STATUSES = ('OPEN', 'ACKNOWLEDGED', 'RESOLVED', 'CANCELLED')


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'positions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('parent_position_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['parent_position_id'], ['positions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'position_scopes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('position_id', sa.Integer(), nullable=False),
        sa.Column('scope_type', sa.String(length=32), nullable=False),
        sa.Column('scope_id', sa.Integer(), nullable=True),
        sa.Column('scope_key', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint(f"scope_type IN {POSITION_SCOPE_KINDS!r}", name='ck_position_scope_type'),
        sa.CheckConstraint(
            "scope_type = 'GLOBAL' OR scope_id IS NOT NULL OR scope_key IS NOT NULL",
            name='ck_position_scope_value_required',
        ),
        sa.ForeignKeyConstraint(['position_id'], ['positions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_position_scopes_position_id'), 'position_scopes', ['position_id'], unique=False)

    op.create_table(
        'position_assignments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('position_id', sa.Integer(), nullable=False),
        sa.Column('acting_identity_id', sa.Integer(), nullable=False),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['position_id'], ['positions.id'], ),
        sa.ForeignKeyConstraint(['acting_identity_id'], ['acting_identities.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_position_assignments_position_id'), 'position_assignments', ['position_id'], unique=False)
    op.create_index(op.f('ix_position_assignments_acting_identity_id'), 'position_assignments', ['acting_identity_id'], unique=False)

    op.create_table(
        'position_temporary_coverages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('covered_position_id', sa.Integer(), nullable=False),
        sa.Column('delegate_position_id', sa.Integer(), nullable=True),
        sa.Column('delegate_acting_identity_id', sa.Integer(), nullable=True),
        sa.Column('granted_by_identity_id', sa.Integer(), nullable=True),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint(
            "(delegate_position_id IS NOT NULL) != (delegate_acting_identity_id IS NOT NULL)",
            name='ck_position_temporary_coverage_delegate_xor',
        ),
        sa.ForeignKeyConstraint(['covered_position_id'], ['positions.id'], ),
        sa.ForeignKeyConstraint(['delegate_position_id'], ['positions.id'], ),
        sa.ForeignKeyConstraint(['delegate_acting_identity_id'], ['acting_identities.id'], ),
        sa.ForeignKeyConstraint(['granted_by_identity_id'], ['acting_identities.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_position_temporary_coverages_covered_position_id'),
        'position_temporary_coverages', ['covered_position_id'], unique=False,
    )

    op.create_table(
        'process_ownerships',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('domain', sa.String(length=64), nullable=False),
        sa.Column('module', sa.String(length=64), nullable=True),
        sa.Column('process_name', sa.String(length=128), nullable=False),
        sa.Column('phase', sa.String(length=32), nullable=True),
        sa.Column('position_id', sa.Integer(), nullable=False),
        sa.Column('scope_type', sa.String(length=32), nullable=True),
        sa.Column('scope_id', sa.Integer(), nullable=True),
        sa.Column('scope_key', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint(f"scope_type IS NULL OR scope_type IN {POSITION_SCOPE_KINDS!r}", name='ck_process_ownership_scope_type'),
        sa.ForeignKeyConstraint(['position_id'], ['positions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_process_ownerships_domain'), 'process_ownerships', ['domain'], unique=False)
    op.create_index(op.f('ix_process_ownerships_process_name'), 'process_ownerships', ['process_name'], unique=False)
    op.create_index(op.f('ix_process_ownerships_position_id'), 'process_ownerships', ['position_id'], unique=False)

    op.create_table(
        'attention_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_domain', sa.String(length=64), nullable=False),
        sa.Column('source_module', sa.String(length=64), nullable=True),
        sa.Column('source_process_name', sa.String(length=128), nullable=True),
        sa.Column('source_phase', sa.String(length=32), nullable=True),
        sa.Column('source_reference', sa.String(length=255), nullable=True),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('proposed_action', sa.Text(), nullable=True),
        sa.Column('priority', sa.String(length=16), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('scope_type', sa.String(length=32), nullable=True),
        sa.Column('scope_id', sa.Integer(), nullable=True),
        sa.Column('scope_key', sa.String(length=128), nullable=True),
        sa.Column('resolved_process_owner_position_id', sa.Integer(), nullable=True),
        sa.Column('resolved_recipient_acting_identity_id', sa.Integer(), nullable=True),
        sa.Column('routing_unresolved_reason', sa.Text(), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_by_identity_id', sa.Integer(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by_identity_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint(f"priority IN {ATTENTION_PRIORITIES!r}", name='ck_attention_item_priority'),
        sa.CheckConstraint(f"status IN {ATTENTION_STATUSES!r}", name='ck_attention_item_status'),
        sa.ForeignKeyConstraint(['resolved_process_owner_position_id'], ['positions.id'], ),
        sa.ForeignKeyConstraint(['resolved_recipient_acting_identity_id'], ['acting_identities.id'], ),
        sa.ForeignKeyConstraint(['acknowledged_by_identity_id'], ['acting_identities.id'], ),
        sa.ForeignKeyConstraint(['resolved_by_identity_id'], ['acting_identities.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_attention_items_source_domain'), 'attention_items', ['source_domain'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_attention_items_source_domain'), table_name='attention_items')
    op.drop_table('attention_items')
    op.drop_index(op.f('ix_process_ownerships_position_id'), table_name='process_ownerships')
    op.drop_index(op.f('ix_process_ownerships_process_name'), table_name='process_ownerships')
    op.drop_index(op.f('ix_process_ownerships_domain'), table_name='process_ownerships')
    op.drop_table('process_ownerships')
    op.drop_index(op.f('ix_position_temporary_coverages_covered_position_id'), table_name='position_temporary_coverages')
    op.drop_table('position_temporary_coverages')
    op.drop_index(op.f('ix_position_assignments_acting_identity_id'), table_name='position_assignments')
    op.drop_index(op.f('ix_position_assignments_position_id'), table_name='position_assignments')
    op.drop_table('position_assignments')
    op.drop_index(op.f('ix_position_scopes_position_id'), table_name='position_scopes')
    op.drop_table('position_scopes')
    op.drop_table('positions')
