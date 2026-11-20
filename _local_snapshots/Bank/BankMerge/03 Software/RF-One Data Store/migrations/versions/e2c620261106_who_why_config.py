"""BANK_WHO_WHY_CONFIG_001 (BANK-2026-11-04, 2026-11-06): one WHY configuration per WHO, with company exceptions.

Additive only: two new tables. No existing row is changed, moved or deleted — the WHO + Source classifications
stay as they are and keep deciding for every WHO without a configuration row. The conversion of the coherent
pairs is a separate, explicit step (`who_why_config.convert_pairs`).
"""
from alembic import op
import sqlalchemy as sa

revision = "e2c620261106"
down_revision = "d3a520261103"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "bank_who_why_configs",
        sa.Column("occurrence_id", sa.Integer, sa.ForeignKey("bank_occurrences.id"), primary_key=True),
        sa.Column("behaviour", sa.String(16), nullable=False),
        sa.Column("why_id", sa.Integer, sa.ForeignKey("bank_transaction_reasons.id")),
        sa.Column("personal_why_id", sa.Integer, sa.ForeignKey("bank_transaction_reasons.id")),
        sa.Column("company_why_id", sa.Integer, sa.ForeignKey("bank_transaction_reasons.id")),
        sa.Column("origin", sa.String(32)),
        sa.Column("updated_by_account_id", sa.Integer, sa.ForeignKey("rfone_accounts.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("behaviour IN ('SINGLE', 'BY_SUBJECT')", name="ck_bank_who_why_config_behaviour"))
    op.create_table(
        "bank_who_why_exceptions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("occurrence_id", sa.Integer, sa.ForeignKey("bank_occurrences.id"), nullable=False, index=True),
        sa.Column("reporting_entity_id", sa.Integer, sa.ForeignKey("reporting_entities.id"), nullable=False),
        sa.Column("replaces", sa.String(16), nullable=False),
        sa.Column("why_id", sa.Integer, sa.ForeignKey("bank_transaction_reasons.id"), nullable=False),
        sa.Column("whom_entity_id", sa.Integer, sa.ForeignKey("reporting_entities.id")),
        sa.Column("approved_by_account_id", sa.Integer, sa.ForeignKey("rfone_accounts.id")),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("occurrence_id", "reporting_entity_id", name="uq_bank_who_why_exception"),
        sa.CheckConstraint("replaces IN ('SINGLE', 'COMPANY', 'RULE')", name="ck_bank_who_why_exception_replaces"))


def downgrade():
    op.drop_table("bank_who_why_exceptions")
    op.drop_table("bank_who_why_configs")
