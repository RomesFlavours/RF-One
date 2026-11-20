"""Reusable WHY decisions for bank-originated statement narratives."""
from alembic import op
import sqlalchemy as sa

revision = "f1b820261108"
down_revision = "e2c620261106"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "bank_statement_purposes",
        sa.Column("bank", sa.Text, primary_key=True),
        sa.Column("direction", sa.String(3), primary_key=True),
        sa.Column("narrative", sa.Text, primary_key=True),
        sa.Column("why_id", sa.Integer, sa.ForeignKey("bank_transaction_reasons.id"), nullable=False),
        sa.CheckConstraint("direction IN ('IN', 'OUT')", name="ck_statement_purpose_direction"),
    )


def downgrade():
    op.drop_table("bank_statement_purposes")
