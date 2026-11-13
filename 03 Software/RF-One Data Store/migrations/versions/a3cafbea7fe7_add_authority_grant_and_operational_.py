"""add authority grant and operational signature schema
(RFONE_SHARED_IDENTITY_AUTHORITY_SIGNATURE_001)

Revision ID: a3cafbea7fe7
Revises: c7f2b9e4a6d1
Create Date: 2026-09-07 17:31:56.458793

Minimum shared persistence for the RF-One Identity/Authority/Operational
Signature foundation (00 Core/ConceptualArchitecture/
09_Identity_Authority_and_Accountability.md; 03 Software/Identity Authority
and Security Architecture.md §5, §9-10). Adds exactly two tables, both
reusable by every future Domain — no Domain-specific permission or signature
data is created here:

- `authority_grants` — a bounded Authority grant to an existing
  `acting_identities` row, scoped by domain/module/action and an explicit
  Corporate/Brand/Operational Unit/Operational Area/GLOBAL context chain
  (`scope_type`/`scope_id` — no FK to those tables since none exist yet;
  see the model's own docstring).
- `operational_signatures` — the append-only RF-One Operational Signature
  evidence record (actor, action, context, object, before/after, applicable
  version, authority used, reason, actor kind, authentication assurance
  level). `corrects_signature_id` is the only way a correction is expressed
  — a new row, never an update to an existing one.

No existing table is altered. See `authority_service.py` and
`operational_signature_service.py` for the shared entry points that write
and read these tables — no other code should query them directly.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3cafbea7fe7'
down_revision: Union[str, Sequence[str], None] = 'c7f2b9e4a6d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('authority_grants',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('acting_identity_id', sa.Integer(), nullable=False),
    sa.Column('domain', sa.String(length=64), nullable=False),
    sa.Column('module', sa.String(length=64), nullable=False),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('scope_type', sa.String(length=32), nullable=False),
    sa.Column('scope_id', sa.Integer(), nullable=True),
    sa.Column('granted_by_identity_id', sa.Integer(), nullable=True),
    sa.Column('granted_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("scope_type = 'GLOBAL' OR scope_id IS NOT NULL", name='ck_authority_grant_scope_id_required'),
    sa.CheckConstraint("scope_type IN ('CORPORATE', 'BRAND', 'OPERATIONAL_UNIT', 'OPERATIONAL_AREA', 'GLOBAL')", name='ck_authority_grant_scope_type'),
    sa.ForeignKeyConstraint(['acting_identity_id'], ['acting_identities.id'], ),
    sa.ForeignKeyConstraint(['granted_by_identity_id'], ['acting_identities.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_authority_grants_acting_identity_id'), 'authority_grants', ['acting_identity_id'], unique=False)
    op.create_index('ix_authority_grants_lookup', 'authority_grants', ['acting_identity_id', 'domain', 'action'], unique=False)
    op.create_table('operational_signatures',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('acting_identity_id', sa.Integer(), nullable=False),
    sa.Column('actor_kind', sa.String(length=24), nullable=False),
    sa.Column('action', sa.String(length=128), nullable=False),
    sa.Column('domain', sa.String(length=64), nullable=False),
    sa.Column('module', sa.String(length=64), nullable=True),
    sa.Column('scope_type', sa.String(length=32), nullable=True),
    sa.Column('scope_id', sa.Integer(), nullable=True),
    sa.Column('object_type', sa.String(length=128), nullable=True),
    sa.Column('object_id', sa.String(length=128), nullable=True),
    sa.Column('before_state', sa.JSON(), nullable=True),
    sa.Column('after_state', sa.JSON(), nullable=True),
    sa.Column('applicable_version', sa.String(length=64), nullable=True),
    sa.Column('authority_used', sa.Text(), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('assurance_level', sa.String(length=40), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('recorded_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('corrects_signature_id', sa.Integer(), nullable=True),
    sa.CheckConstraint("actor_kind IN ('HUMAN_USER', 'SYSTEM', 'AI_AGENT', 'EXTERNAL_SERVICE')", name='ck_operational_signature_actor_kind'),
    sa.CheckConstraint("assurance_level IN ('NORMAL_AUTHENTICATED_ACTION', 'EXPLICIT_CONFIRMATION', 'STEP_UP_AUTHENTICATION')", name='ck_operational_signature_assurance_level'),
    sa.ForeignKeyConstraint(['acting_identity_id'], ['acting_identities.id'], ),
    sa.ForeignKeyConstraint(['corrects_signature_id'], ['operational_signatures.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_operational_signatures_acting_identity_id'), 'operational_signatures', ['acting_identity_id'], unique=False)
    op.create_index('ix_operational_signatures_lookup', 'operational_signatures', ['domain', 'object_type', 'object_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_operational_signatures_lookup', table_name='operational_signatures')
    op.drop_index(op.f('ix_operational_signatures_acting_identity_id'), table_name='operational_signatures')
    op.drop_table('operational_signatures')
    op.drop_index('ix_authority_grants_lookup', table_name='authority_grants')
    op.drop_index(op.f('ix_authority_grants_acting_identity_id'), table_name='authority_grants')
    op.drop_table('authority_grants')
