"""add bank instrument assignment audit and source instrument profile

Revision ID: b2f6c4a8d713
Revises: a1b7d3e5c920
Create Date: 2026-09-20

BANK_RECONCILIATION_INSTRUMENT_ASSIGNMENT_001 — purely additive, two new
tables, no data migration and no change to any existing table:

  * `bank_instrument_assignment_audits` — append-only history of every
    human correction of a source→Payment Instrument assignment (a whole
    `BankImportBatch`, or one `FinancialTransaction` when a single file
    carries several cards). The CURRENT assignment is still, and only,
    `BankImportBatch.payment_instrument_id` /
    `FinancialTransaction.payment_instrument_id` — this table is evidence
    of the change, never a second source of truth and never a parallel
    transaction ledger.
  * `bank_source_instrument_profiles` — a reusable source-resolution rule
    a human taught once, for a source file whose own content does not
    identify its instrument unambiguously (First Citizens'
    `AccountHistory.csv`, whose name never changes). Deliberately separate
    from `bank_recognition_rules`, which resolves WHO/WHY for an already
    instrument-resolved transaction, not WHICH INSTRUMENT a file came
    from.

Nothing in the raw preservation layer (`bank_import_batches.raw_file_bytes`,
`raw_bank_transactions.raw_fields`) is touched by this migration or by the
behavior it enables — raw stays immutable.

Downgrade drops both tables; no other schema is affected.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2f6c4a8d713'
down_revision: Union[str, Sequence[str], None] = 'a1b7d3e5c920'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "bank_instrument_assignment_audits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("import_batch_id", sa.Integer(), nullable=True),
        sa.Column("financial_transaction_id", sa.Integer(), nullable=True),
        sa.Column("previous_payment_instrument_id", sa.Integer(), nullable=True),
        sa.Column("new_payment_instrument_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("affected_transaction_count", sa.Integer(), nullable=False),
        sa.Column("changed_by_account_id", sa.Integer(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("scope IN ('BATCH', 'TRANSACTION')", name="ck_biaa_scope"),
        sa.CheckConstraint(
            "(scope = 'BATCH' AND import_batch_id IS NOT NULL AND financial_transaction_id IS NULL) OR "
            "(scope = 'TRANSACTION' AND financial_transaction_id IS NOT NULL)",
            name="ck_biaa_scope_target",
        ),
        sa.ForeignKeyConstraint(["import_batch_id"], ["bank_import_batches.id"]),
        sa.ForeignKeyConstraint(["financial_transaction_id"], ["financial_transactions.id"]),
        sa.ForeignKeyConstraint(["previous_payment_instrument_id"], ["payment_instruments.id"]),
        sa.ForeignKeyConstraint(["new_payment_instrument_id"], ["payment_instruments.id"]),
        sa.ForeignKeyConstraint(["changed_by_account_id"], ["rfone_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_biaa_import_batch_id", "bank_instrument_assignment_audits", ["import_batch_id"], unique=False,
    )
    op.create_index(
        "ix_biaa_financial_transaction_id", "bank_instrument_assignment_audits",
        ["financial_transaction_id"], unique=False,
    )

    op.create_table(
        "bank_source_instrument_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("detected_format", sa.String(length=48), nullable=False),
        sa.Column("file_name_key", sa.String(length=255), nullable=True),
        sa.Column("account_hint", sa.String(length=128), nullable=True),
        sa.Column("payment_instrument_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="ACTIVE", nullable=False),
        sa.Column("created_from_batch_id", sa.Integer(), nullable=True),
        sa.Column("created_by_account_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_bsip_status"),
        sa.CheckConstraint(
            "file_name_key IS NOT NULL OR account_hint IS NOT NULL", name="ck_bsip_has_key",
        ),
        sa.ForeignKeyConstraint(["payment_instrument_id"], ["payment_instruments.id"]),
        sa.ForeignKeyConstraint(["created_from_batch_id"], ["bank_import_batches.id"]),
        sa.ForeignKeyConstraint(["created_by_account_id"], ["rfone_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "detected_format", "file_name_key", "account_hint", name="uq_bsip_format_name_hint",
        ),
    )
    op.create_index(
        "ix_bsip_payment_instrument_id", "bank_source_instrument_profiles",
        ["payment_instrument_id"], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_bsip_payment_instrument_id", table_name="bank_source_instrument_profiles")
    op.drop_table("bank_source_instrument_profiles")
    op.drop_index("ix_biaa_financial_transaction_id", table_name="bank_instrument_assignment_audits")
    op.drop_index("ix_biaa_import_batch_id", table_name="bank_instrument_assignment_audits")
    op.drop_table("bank_instrument_assignment_audits")
