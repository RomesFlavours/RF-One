"""BANK_SPLIT_ALLOCATION_001: split lines of one bank movement (QuickBooks Online "Split") and QBO export.

Additive only. Two nullable columns on `bank_transaction_allocations` (line description, documents/items
behind the line) and two new empty tables (QBO account correspondences, QBO export duplicate protection).
No existing allocation, decision or movement is changed or reinterpreted; nothing is seeded.
"""
from alembic import op
import sqlalchemy as sa

revision = "b7e320261101"
down_revision = "a5c220261101"
branch_labels = depends_on = None


def upgrade():
    with op.batch_alter_table("bank_transaction_allocations") as batch:
        batch.add_column(sa.Column("description", sa.Text, nullable=True))
        batch.add_column(sa.Column("evidence_detail", sa.Text, nullable=True))
    op.create_table(
        "bank_qbo_account_maps",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("local_id", sa.Integer, nullable=False),
        sa.Column("qbo_account_id", sa.String(64), nullable=False),
        sa.Column("qbo_account_name", sa.String(255)),
        sa.Column("updated_by_account_id", sa.Integer, sa.ForeignKey("rfone_accounts.id")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("kind", "local_id", name="uq_bank_qbo_account_map"),
        sa.CheckConstraint("kind IN ('CATEGORY', 'PAYMENT_ACCOUNT')", name="ck_bank_qbo_account_map_kind"))
    op.create_table(
        "bank_qbo_exports",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("financial_transaction_id", sa.Integer, sa.ForeignKey("financial_transactions.id"), nullable=False),
        sa.Column("request_id", sa.String(50), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("qbo_purchase_id", sa.String(64)),
        sa.Column("created_by_account_id", sa.Integer, sa.ForeignKey("rfone_accounts.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("financial_transaction_id", name="uq_bank_qbo_export_transaction"),
        sa.UniqueConstraint("request_id", name="uq_bank_qbo_export_request"),
        sa.CheckConstraint("status IN ('PREPARED', 'SENT')", name="ck_bank_qbo_export_status"))


def downgrade():
    op.drop_table("bank_qbo_exports")
    op.drop_table("bank_qbo_account_maps")
    with op.batch_alter_table("bank_transaction_allocations") as batch:
        batch.drop_column("evidence_detail")
        batch.drop_column("description")
