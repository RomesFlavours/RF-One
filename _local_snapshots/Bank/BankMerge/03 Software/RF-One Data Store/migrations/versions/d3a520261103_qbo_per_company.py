"""BANK_UPLOAD_AND_RECONCILE_001 (2026-11-03): QuickBooks Online chart, correspondences and exports per company.

Each company (LEGAL ReportingEntity) is its own QBO company: its own chart of accounts, its own correspondences, its
own export files. Nothing is assumed to be shared between two companies.

* `bank_qbo_accounts.reporting_entity_id` — the company whose Account List the account was imported from. The
  account name is unique per company, no longer globally.
* `bank_qbo_account_maps.reporting_entity_id` + `status` + `qbo_account_row_id` + `proposed_from`:
  - VERIFIED  — set for a company and checked against THAT company's chart (`qbo_account_row_id`);
  - PROPOSED  — copied from another company's configuration; used for nothing until a person verifies it in the
                destination company's chart;
  - GLOBAL_LEGACY — a correspondence made before this revision, for no company. It is NOT attributed to any company
                (the existing rows keep `reporting_entity_id` NULL): it is only offered as a proposal.
  Unique per (company, kind, local id).
* `bank_qbo_export_batches` — one generated file of one company: its content (kept, so a new download is the same
  file, never a new batch), the movements in it, and its states kept apart: GENERATED -> (downloads counted) ->
  IMPORT_CONFIRMED by a person, or WITHDRAWN by a person before any import (its movements become exportable again).
* `bank_qbo_exports.reporting_entity_id` + `batch_id` — the company and the file of each exported movement.

Additive: no existing row is deleted or reinterpreted; nothing is seeded.
"""
from alembic import op
import sqlalchemy as sa

revision = "d3a520261103"
down_revision = "c8f420261103"
branch_labels = depends_on = None


def upgrade():
    with op.batch_alter_table("bank_qbo_accounts") as batch:
        batch.add_column(sa.Column("reporting_entity_id", sa.Integer))
        batch.create_foreign_key("fk_bank_qbo_accounts_entity", "reporting_entities", ["reporting_entity_id"], ["id"])
        batch.drop_constraint("uq_bank_qbo_account_name", type_="unique")
        batch.create_unique_constraint("uq_bank_qbo_account_entity_name", ["reporting_entity_id", "name"])
    with op.batch_alter_table("bank_qbo_account_maps") as batch:
        batch.add_column(sa.Column("reporting_entity_id", sa.Integer))
        batch.add_column(sa.Column("status", sa.String(16), nullable=False, server_default="GLOBAL_LEGACY"))
        batch.add_column(sa.Column("qbo_account_row_id", sa.Integer))
        batch.add_column(sa.Column("proposed_from", sa.String(255)))
        batch.create_foreign_key("fk_bank_qbo_account_maps_entity", "reporting_entities", ["reporting_entity_id"], ["id"])
        batch.create_foreign_key("fk_bank_qbo_account_maps_account", "bank_qbo_accounts", ["qbo_account_row_id"], ["id"])
        batch.drop_constraint("uq_bank_qbo_account_map", type_="unique")
        batch.create_unique_constraint("uq_bank_qbo_account_map_entity", ["reporting_entity_id", "kind", "local_id"])
        batch.create_check_constraint("ck_bank_qbo_account_map_status",
                                      "status IN ('VERIFIED', 'PROPOSED', 'GLOBAL_LEGACY')")
    op.create_table(
        "bank_qbo_export_batches",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("reporting_entity_id", sa.Integer, sa.ForeignKey("reporting_entities.id"), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_format", sa.String(32), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("movements_json", sa.Text, nullable=False),
        sa.Column("journal_count", sa.Integer, nullable=False),
        sa.Column("line_count", sa.Integer, nullable=False),
        sa.Column("total_minor", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("download_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("first_downloaded_at", sa.DateTime(timezone=True)),
        sa.Column("last_downloaded_at", sa.DateTime(timezone=True)),
        sa.Column("import_confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("import_confirmed_by_account_id", sa.Integer, sa.ForeignKey("rfone_accounts.id")),
        sa.Column("import_note", sa.Text),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True)),
        sa.Column("withdrawn_by_account_id", sa.Integer, sa.ForeignKey("rfone_accounts.id")),
        sa.Column("withdraw_reason", sa.Text),
        sa.Column("created_by_account_id", sa.Integer, sa.ForeignKey("rfone_accounts.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("file_name", name="uq_bank_qbo_export_batch_file"),
        sa.CheckConstraint("status IN ('GENERATED', 'IMPORT_CONFIRMED', 'WITHDRAWN')", name="ck_bank_qbo_export_batch_status"))
    with op.batch_alter_table("bank_qbo_exports") as batch:
        batch.add_column(sa.Column("reporting_entity_id", sa.Integer))
        batch.add_column(sa.Column("batch_id", sa.Integer))
        batch.create_foreign_key("fk_bank_qbo_exports_entity", "reporting_entities", ["reporting_entity_id"], ["id"])
        batch.create_foreign_key("fk_bank_qbo_exports_batch", "bank_qbo_export_batches", ["batch_id"], ["id"])


def downgrade():
    with op.batch_alter_table("bank_qbo_exports") as batch:
        batch.drop_constraint("fk_bank_qbo_exports_batch", type_="foreignkey")
        batch.drop_constraint("fk_bank_qbo_exports_entity", type_="foreignkey")
        batch.drop_column("batch_id")
        batch.drop_column("reporting_entity_id")
    op.drop_table("bank_qbo_export_batches")
    with op.batch_alter_table("bank_qbo_account_maps") as batch:
        batch.drop_constraint("ck_bank_qbo_account_map_status", type_="check")
        batch.drop_constraint("uq_bank_qbo_account_map_entity", type_="unique")
        batch.create_unique_constraint("uq_bank_qbo_account_map", ["kind", "local_id"])
        batch.drop_constraint("fk_bank_qbo_account_maps_account", type_="foreignkey")
        batch.drop_constraint("fk_bank_qbo_account_maps_entity", type_="foreignkey")
        batch.drop_column("proposed_from")
        batch.drop_column("qbo_account_row_id")
        batch.drop_column("status")
        batch.drop_column("reporting_entity_id")
    with op.batch_alter_table("bank_qbo_accounts") as batch:
        batch.drop_constraint("uq_bank_qbo_account_entity_name", type_="unique")
        batch.create_unique_constraint("uq_bank_qbo_account_name", ["name"])
        batch.drop_constraint("fk_bank_qbo_accounts_entity", type_="foreignkey")
        batch.drop_column("reporting_entity_id")
