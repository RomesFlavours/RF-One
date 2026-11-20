"""add canonical financial transaction

Revision ID: ee2cabebf2c3
Revises: 45cd9d349bf0
Create Date: 2026-09-16 15:31:14.887977

Canonical Financial Model Convergence — Phase 2 only
(FINANCIAL_MODEL_CONVERGENCE_001). Adds ONE new, additive table,
`financial_transactions` — the future single normalized transaction
ledger for every financial-movement source. SCHEMA ONLY: nothing writes
to this table yet, no existing transaction data is migrated, and neither
`normalized_financial_transactions` nor `payment_instrument_transactions`
(the two pre-convergence ledgers this table eventually replaces) is
created here.

`explanation_id` is omitted (no `bank_transaction_explanations` table
exists on this branch yet — deferred to the phase that ports Recognition/
Explanation). `import_batch_id` is a plain nullable column with no FK (no
`bank_import_batches` table exists on this branch yet — deferred to the
phase that ports CSV source acquisition).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ee2cabebf2c3'
down_revision: Union[str, Sequence[str], None] = '45cd9d349bf0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'financial_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('payment_instrument_id', sa.Integer(), nullable=False),
        sa.Column('source_system_id', sa.Integer(), nullable=True),
        sa.Column('external_transaction_id', sa.String(length=128), nullable=True),
        sa.Column('bank_source', sa.String(length=32), nullable=True),
        sa.Column('posting_date', sa.Date(), nullable=True),
        sa.Column('transaction_date', sa.Date(), nullable=True),
        sa.Column('transaction_datetime', sa.DateTime(timezone=True), nullable=True),
        sa.Column('description_original', sa.Text(), nullable=True),
        sa.Column('description_normalized', sa.Text(), nullable=True),
        sa.Column('amount_minor', sa.Integer(), nullable=False),
        sa.Column('native_transaction_type', sa.String(length=64), nullable=True),
        sa.Column('reference', sa.String(length=128), nullable=True),
        sa.Column('balance_minor', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('import_batch_id', sa.Integer(), nullable=True),
        sa.Column('source_row_number', sa.Integer(), nullable=True),
        sa.Column('fingerprint', sa.String(length=128), nullable=True),
        sa.Column('occurrence_index_in_batch', sa.Integer(), nullable=True),
        sa.Column('occurrence_count_in_batch', sa.Integer(), nullable=True),
        sa.Column('duplicate_status', sa.String(length=24), nullable=True),
        sa.Column('duplicate_of_transaction_id', sa.Integer(), nullable=True),
        sa.Column('review_status', sa.String(length=24), nullable=True),
        sa.Column('gross_amount_minor', sa.Integer(), nullable=True),
        sa.Column('fee_amount_minor', sa.Integer(), nullable=True),
        sa.Column('net_amount_minor', sa.Integer(), nullable=True),
        sa.Column('counterparty_name', sa.String(length=255), nullable=True),
        sa.Column('counterparty_identifier', sa.String(length=255), nullable=True),
        sa.Column('related_external_transaction_id', sa.String(length=128), nullable=True),
        sa.Column('classification', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['payment_instrument_id'], ['payment_instruments.id']),
        sa.ForeignKeyConstraint(['source_system_id'], ['source_systems.id']),
        sa.ForeignKeyConstraint(['duplicate_of_transaction_id'], ['financial_transactions.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'payment_instrument_id', 'external_transaction_id', name='uq_ft_instrument_external_id',
        ),
        sa.CheckConstraint(
            "classification IN ('REVENUE', 'EXPENSE', 'INTERNAL_TRANSFER', 'FEE', 'UNKNOWN')",
            name='ck_ft_classification',
        ),
        sa.CheckConstraint(
            "status IN ('COMPLETED', 'PENDING', 'REVERSED', 'FAILED', 'UNKNOWN')",
            name='ck_ft_status',
        ),
        sa.CheckConstraint(
            "duplicate_status IS NULL OR duplicate_status IN "
            "('NONE', 'CANDIDATE_DUPLICATE', 'CONFIRMED_DUPLICATE', 'CONFIRMED_DISTINCT')",
            name='ck_ft_duplicate_status',
        ),
        sa.CheckConstraint(
            "review_status IS NULL OR review_status IN ('REQUIRES_REVIEW', 'REVIEWED', 'ACCEPTED')",
            name='ck_ft_review_status',
        ),
    )
    op.create_index(
        'ix_ft_instrument_posting_date_amount', 'financial_transactions',
        ['payment_instrument_id', 'posting_date', 'amount_minor'],
    )
    op.create_index(
        'ix_ft_instrument_datetime', 'financial_transactions',
        ['payment_instrument_id', 'transaction_datetime'],
    )
    op.create_index('ix_ft_source_system_id', 'financial_transactions', ['source_system_id'])
    op.create_index('ix_ft_fingerprint', 'financial_transactions', ['fingerprint'])
    op.create_index(
        'ix_financial_transactions_payment_instrument_id', 'financial_transactions', ['payment_instrument_id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_financial_transactions_payment_instrument_id', table_name='financial_transactions')
    op.drop_index('ix_ft_fingerprint', table_name='financial_transactions')
    op.drop_index('ix_ft_source_system_id', table_name='financial_transactions')
    op.drop_index('ix_ft_instrument_datetime', table_name='financial_transactions')
    op.drop_index('ix_ft_instrument_posting_date_amount', table_name='financial_transactions')
    op.drop_table('financial_transactions')
