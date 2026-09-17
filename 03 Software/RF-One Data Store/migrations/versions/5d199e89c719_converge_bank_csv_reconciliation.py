"""converge bank csv reconciliation

Revision ID: 5d199e89c719
Revises: ee2cabebf2c3
Create Date: 2026-09-16 15:42:37.014495

Canonical Financial Model Convergence — Phase 3 only
(FINANCIAL_MODEL_CONVERGENCE_001). Ports the proven Bank Reconciliation V1
CSV-specific provenance tables from `feature/bank-reconciliation-mvp`
(`bank_import_batches`, `raw_bank_transactions`), identical in shape to
that branch's `90993b569d61` migration except that their financial-
identity FK now points at the canonical `payment_instruments` (Phase 1)
instead of a `financial_accounts` table that does not exist on this
branch, and `raw_bank_transactions.normalized_transaction_id` points at
the canonical `financial_transactions` (Phase 2) instead of a
`normalized_financial_transactions` table that does not exist on this
branch. Also retargets `financial_transactions.import_batch_id` (added as
a plain nullable scalar with no FK in Phase 2, since this table did not
yet exist) to a proper FK now that `bank_import_batches` exists.

No `financial_accounts`, `normalized_financial_transactions`, or any
Recognition/Explanation table is created here. No data is migrated.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d199e89c719'
down_revision: Union[str, Sequence[str], None] = 'ee2cabebf2c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'bank_import_batches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('detected_format', sa.String(length=48), nullable=False),
        sa.Column('payment_instrument_id', sa.Integer(), nullable=True),
        sa.Column('original_file_name', sa.String(length=255), nullable=False),
        sa.Column('raw_file_bytes', sa.LargeBinary(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('uploaded_by_account_id', sa.Integer(), nullable=True),
        sa.Column('row_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('date_range_start', sa.Date(), nullable=True),
        sa.Column('date_range_end', sa.Date(), nullable=True),
        sa.Column('status', sa.String(length=24), nullable=False, server_default='RECEIVED'),
        sa.Column('error_summary', sa.Text(), nullable=True),
        sa.Column('overlap_warning', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['payment_instrument_id'], ['payment_instruments.id']),
        sa.ForeignKeyConstraint(['uploaded_by_account_id'], ['rfone_accounts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sha256', name='uq_bank_import_batches_sha256'),
        sa.CheckConstraint(
            "detected_format IN ("
            "'CHASE_BANK_ACCOUNT', 'CHASE_CREDIT_CARD_WITH_CARD', "
            "'CHASE_CREDIT_CARD_NO_CARD', 'FIRST_CITIZENS')",
            name='ck_bank_import_batch_detected_format',
        ),
        sa.CheckConstraint(
            "status IN ('RECEIVED', 'PARSED', 'NORMALIZED', 'REQUIRES_REVIEW', 'ACCEPTED', 'REJECTED')",
            name='ck_bank_import_batch_status',
        ),
    )

    op.create_table(
        'raw_bank_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('import_batch_id', sa.Integer(), nullable=False),
        sa.Column('row_number', sa.Integer(), nullable=False),
        sa.Column('raw_fields', sa.JSON(), nullable=False),
        sa.Column('row_fingerprint', sa.String(length=128), nullable=False),
        sa.Column('parse_status', sa.String(length=16), nullable=False),
        sa.Column('anomalies', sa.Text(), nullable=True),
        sa.Column('normalized_transaction_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['import_batch_id'], ['bank_import_batches.id']),
        sa.ForeignKeyConstraint(['normalized_transaction_id'], ['financial_transactions.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('import_batch_id', 'row_number', name='uq_raw_bank_transaction_batch_row'),
        sa.CheckConstraint(
            "parse_status IN ('PARSED', 'ANOMALOUS', 'UNREADABLE')", name='ck_raw_bank_transaction_parse_status',
        ),
    )
    op.create_index('ix_raw_bank_transactions_import_batch_id', 'raw_bank_transactions', ['import_batch_id'])
    op.create_index('ix_raw_bank_transactions_row_fingerprint', 'raw_bank_transactions', ['row_fingerprint'])

    with op.batch_alter_table('financial_transactions', schema=None) as batch_op:
        batch_op.create_foreign_key(
            'fk_financial_transactions_import_batch', 'bank_import_batches', ['import_batch_id'], ['id'],
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('financial_transactions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_financial_transactions_import_batch', type_='foreignkey')

    op.drop_index('ix_raw_bank_transactions_row_fingerprint', table_name='raw_bank_transactions')
    op.drop_index('ix_raw_bank_transactions_import_batch_id', table_name='raw_bank_transactions')
    op.drop_table('raw_bank_transactions')

    op.drop_table('bank_import_batches')
