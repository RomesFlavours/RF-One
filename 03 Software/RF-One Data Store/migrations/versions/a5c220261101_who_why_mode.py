"""BANK_WHO_WHY_MODE_001: WHO WHY mode (UNIQUE / MULTIPLE) in its own table.

Additive only: no existing row is changed or reinterpreted. Every WHO without a row stays UNIQUE, so the
existing WHO + Source classifications keep deciding exactly as before; no WHO is marked MULTIPLE here.
"""
from alembic import op
import sqlalchemy as sa

revision = "a5c220261101"
down_revision = "f4b120261026"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "bank_who_why_modes",
        sa.Column("occurrence_id", sa.Integer, sa.ForeignKey("bank_occurrences.id"), primary_key=True),
        sa.Column("why_mode", sa.String(16), nullable=False),
        sa.Column("note", sa.Text),
        sa.Column("updated_by_account_id", sa.Integer, sa.ForeignKey("rfone_accounts.id")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("why_mode IN ('UNIQUE', 'MULTIPLE')", name="ck_bank_who_why_mode"))


def downgrade():
    op.drop_table("bank_who_why_modes")
