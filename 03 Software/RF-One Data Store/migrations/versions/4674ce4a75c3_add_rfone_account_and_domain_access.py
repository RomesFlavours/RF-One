"""add rfone_account and rfone_account_domain_access

Revision ID: 4674ce4a75c3
Revises: 8f933b662969
Create Date: 2026-09-10 19:00:00.000000

Adds the general RF-One Web shell's own login identity (RF-ONE GENERAL WEB
APP V1 task): `rfone_accounts` (the ONE account an operator uses to enter
the RF-One shell — `03 Software/RF-One Web/` — deliberately independent of
any Domain-specific account such as `training_accounts`) and
`rfone_account_domain_access` (which RF-One Domains, and optionally which
Domain-interpreted role, each account may enter — `domain_code` matches
`RF-One Web/domain_registry.py`'s canonical codes, never validated against
a DB-side enum here since that registry is the single source of truth for
which Domains currently exist).

Purely additive — no existing table (Training, Tips, Compensation, or any
other) is altered.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4674ce4a75c3'
down_revision: Union[str, Sequence[str], None] = '8f933b662969'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'rfone_accounts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False, server_default='ACTIVE'),
        sa.Column('is_admin', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name='ck_rfone_account_status'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
    )
    op.create_index(op.f('ix_rfone_accounts_username'), 'rfone_accounts', ['username'], unique=True)

    op.create_table(
        'rfone_account_domain_access',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('domain_code', sa.String(length=32), nullable=False),
        sa.Column('role_code', sa.String(length=64), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['account_id'], ['rfone_accounts.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account_id', 'domain_code', name='uq_rfone_account_domain_access_account_domain'),
    )
    op.create_index(
        op.f('ix_rfone_account_domain_access_account_id'), 'rfone_account_domain_access',
        ['account_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_rfone_account_domain_access_account_id'), table_name='rfone_account_domain_access')
    op.drop_table('rfone_account_domain_access')
    op.drop_index(op.f('ix_rfone_accounts_username'), table_name='rfone_accounts')
    op.drop_table('rfone_accounts')
