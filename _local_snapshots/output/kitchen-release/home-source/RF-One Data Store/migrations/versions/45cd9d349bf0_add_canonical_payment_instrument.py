"""add canonical payment instrument

Revision ID: 45cd9d349bf0
Revises: a1f4c7e9b2d5
Create Date: 2026-09-16 15:23:28.412824

Canonical Financial Model Convergence — Phase 1 only
(FINANCIAL_MODEL_CONVERGENCE_001). Adds ONE new, additive table,
`payment_instruments` — the single canonical identity model for a
financial/payment instrument (Bank Account, Credit Card, or PayPal
account), absorbing the source-resolution fields
(`institution`/`last_four`/`external_account_identifier`) an earlier
`FinancialAccount` model used for the same purpose on a sibling branch.

This migration does NOT touch `financial_accounts`, does NOT migrate any
existing data, and does NOT create or modify any transaction table
(`normalized_financial_transactions`, `payment_instrument_transactions`,
or any canonical FinancialTransaction). Those belong to later,
not-yet-authorized phases.

Rechained from its original source-branch down_revision (09ed62634a09)
to main's actual current head (a1f4c7e9b2d5) at Financial Model
Convergence main-integration time — main independently gained the
Purchased Domain's supplier-aliases/field-corrections/line-additions
migrations (chained through the same 09ed62634a09 parent) after this
branch diverged; keeping the original down_revision would have created a
second Alembic head instead of extending the existing one linearly. Pure
rechain only — no schema effect of this or any downstream Phase 1-6B
migration was altered.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '45cd9d349bf0'
down_revision: Union[str, Sequence[str], None] = 'a1f4c7e9b2d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'payment_instruments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('legal_entity_id', sa.Integer(), nullable=True),
        sa.Column('instrument_type', sa.String(length=16), nullable=False),
        sa.Column('provider', sa.String(length=255), nullable=True),
        sa.Column('display_name', sa.String(length=255), nullable=False),
        sa.Column('institution', sa.String(length=64), nullable=True),
        sa.Column('last_four', sa.String(length=4), nullable=True),
        sa.Column('external_account_identifier', sa.String(length=128), nullable=True),
        sa.Column('currency', sa.String(length=8), nullable=True),
        sa.Column('linked_instrument_id', sa.Integer(), nullable=True),
        sa.Column('source_system_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['legal_entity_id'], ['legal_entities.id']),
        sa.ForeignKeyConstraint(['linked_instrument_id'], ['payment_instruments.id']),
        sa.ForeignKeyConstraint(['source_system_id'], ['source_systems.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "instrument_type IN ('BANK_ACCOUNT', 'CREDIT_CARD', 'PAYPAL')",
            name='ck_pi_instrument_type',
        ),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name='ck_pi_status'),
    )
    op.create_index('ix_pi_legal_entity_id', 'payment_instruments', ['legal_entity_id'])
    op.create_index('ix_pi_linked_instrument_id', 'payment_instruments', ['linked_instrument_id'])
    op.create_index('ix_pi_source_system_id', 'payment_instruments', ['source_system_id'])
    op.create_index(
        'ix_payment_instruments_external_account_identifier',
        'payment_instruments', ['external_account_identifier'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_payment_instruments_external_account_identifier', table_name='payment_instruments')
    op.drop_index('ix_pi_source_system_id', table_name='payment_instruments')
    op.drop_index('ix_pi_linked_instrument_id', table_name='payment_instruments')
    op.drop_index('ix_pi_legal_entity_id', table_name='payment_instruments')
    op.drop_table('payment_instruments')
