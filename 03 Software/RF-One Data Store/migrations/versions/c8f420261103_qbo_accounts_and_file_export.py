"""BANK_UPLOAD_AND_RECONCILE_001 (2026-11-03): QBO account list, verifiable mappings and the exported file.

Additive only; no existing row is changed or reinterpreted, nothing is seeded.

* `bank_qbo_accounts` — the QuickBooks Online chart of accounts as the person imported it (the Account List
  exported from QBO) or, later, as read through the QBO API. A QBO internal Id is stored only when it comes from
  QBO itself: the Account List export carries names and types, never Ids.
* `bank_qbo_account_maps` — `qbo_account_id` becomes nullable (a correspondence verified by name against the
  imported list has no Id until a QBO connection exists); `qbo_account_type` and `verified_by` record what the
  correspondence was verified against.
* `bank_qbo_exports` — `qbo_entity` (Purchase / Deposit / Transfer), `counterpart_transaction_id` (the other leg
  of a transfer, so neither leg is exported twice), `export_file` (the file the movement went out in) and the
  status FILE_EXPORTED (in a QBO import file; not sent through the API).
"""
from alembic import op
import sqlalchemy as sa

revision = "c8f420261103"
down_revision = "b7e320261101"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "bank_qbo_accounts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("account_type", sa.String(64)),
        sa.Column("detail_type", sa.String(128)),
        sa.Column("qbo_account_id", sa.String(64)),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("imported_by_account_id", sa.Integer, sa.ForeignKey("rfone_accounts.id")),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_bank_qbo_account_name"),
        sa.CheckConstraint("source IN ('ACCOUNT_LIST_FILE', 'QBO_API')", name="ck_bank_qbo_account_source"))
    with op.batch_alter_table("bank_qbo_account_maps") as batch:
        batch.alter_column("qbo_account_id", existing_type=sa.String(64), nullable=True)
        batch.add_column(sa.Column("qbo_account_type", sa.String(64)))
        batch.add_column(sa.Column("verified_by", sa.String(24)))
    with op.batch_alter_table("bank_qbo_exports") as batch:
        batch.add_column(sa.Column("qbo_entity", sa.String(16)))
        batch.add_column(sa.Column("counterpart_transaction_id", sa.Integer))
        batch.create_foreign_key("fk_bank_qbo_exports_counterpart", "financial_transactions",
                                 ["counterpart_transaction_id"], ["id"])
        batch.add_column(sa.Column("export_file", sa.String(255)))
        batch.drop_constraint("ck_bank_qbo_export_status", type_="check")
        batch.create_check_constraint("ck_bank_qbo_export_status", "status IN ('PREPARED', 'FILE_EXPORTED', 'SENT')")


def downgrade():
    with op.batch_alter_table("bank_qbo_exports") as batch:
        batch.drop_constraint("ck_bank_qbo_export_status", type_="check")
        batch.create_check_constraint("ck_bank_qbo_export_status", "status IN ('PREPARED', 'SENT')")
        batch.drop_column("export_file")
        batch.drop_constraint("fk_bank_qbo_exports_counterpart", type_="foreignkey")
        batch.drop_column("counterpart_transaction_id")
        batch.drop_column("qbo_entity")
    with op.batch_alter_table("bank_qbo_account_maps") as batch:
        batch.drop_column("verified_by")
        batch.drop_column("qbo_account_type")
        batch.alter_column("qbo_account_id", existing_type=sa.String(64), nullable=False)
    op.drop_table("bank_qbo_accounts")
