"""converge cross-ledger transfer matching

FINANCIAL_MODEL_CONVERGENCE_001 Phase 6. Adds the canonical cross-ledger
internal-transfer match table, `financial_transaction_matches`
(`FinancialTransactionMatch`, `models.py`) — a confirmed link between two
`financial_transactions` rows on different `payment_instruments`,
representing the two sides of the same internal movement of funds (e.g. a
PayPal "transfer to bank" row and the corresponding bank deposit row).

Ported and adapted from `feature/purchased-invoice-intake-alignment`'s
`payment_instrument_transaction_matches` (that branch's migration
`b3e7d1a9c4f6`) — retargeted from the retired `payment_instrument_
transactions` ledger (not present on this branch) to `financial_
transactions`, and renamed from `PaymentInstrumentTransactionMatch` since
the old name incorrectly implied that ledger.

Purely additive — no existing table or column is touched. No other Phase
1-5 schema (PaymentInstrument, FinancialTransaction, Recognition, Kermali,
PayPal provenance, CSV provenance) is modified; the canonical fields
Phase 6's matching engine needs already existed there.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c7e9a2f5d81'
down_revision: Union[str, Sequence[str], None] = '8ddfe6f314be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'financial_transaction_matches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('transaction_a_id', sa.Integer(), nullable=False),
        sa.Column('transaction_b_id', sa.Integer(), nullable=False),
        sa.Column('match_type', sa.String(length=24), nullable=False, server_default='INTERNAL_TRANSFER'),
        sa.Column('match_method', sa.String(length=8), nullable=False),
        sa.Column('match_basis', sa.Text(), nullable=True),
        sa.Column('matched_amount_minor', sa.Integer(), nullable=False),
        sa.Column('confirmed_by', sa.String(length=255), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.CheckConstraint("match_type IN ('INTERNAL_TRANSFER')", name='ck_ftm_match_type'),
        sa.CheckConstraint("match_method IN ('AUTO', 'HUMAN')", name='ck_ftm_match_method'),
        sa.CheckConstraint('transaction_a_id < transaction_b_id', name='ck_ftm_ordered_pair'),
        sa.ForeignKeyConstraint(['transaction_a_id'], ['financial_transactions.id'], ),
        sa.ForeignKeyConstraint(['transaction_b_id'], ['financial_transactions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('transaction_a_id', 'transaction_b_id', name='uq_ftm_pair'),
    )
    op.create_index(
        'ix_ftm_transaction_a_id', 'financial_transaction_matches', ['transaction_a_id'],
        unique=False,
    )
    op.create_index(
        'ix_ftm_transaction_b_id', 'financial_transaction_matches', ['transaction_b_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_ftm_transaction_b_id', table_name='financial_transaction_matches')
    op.drop_index('ix_ftm_transaction_a_id', table_name='financial_transaction_matches')
    op.drop_table('financial_transaction_matches')
