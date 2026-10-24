"""Durable import reconciliation and research queue; no historical jobs."""
from alembic import op
import sqlalchemy as sa
revision="d6c320261019"
down_revision="c5b220261019"
branch_labels=depends_on=None

def upgrade():
    op.create_table("bank_import_reconciliations",
        sa.Column("id",sa.Integer(),primary_key=True),
        sa.Column("financial_transaction_id",sa.Integer(),sa.ForeignKey("financial_transactions.id"),nullable=False,unique=True),
        sa.Column("status",sa.String(24),nullable=False),sa.Column("stage",sa.String(24),nullable=False),
        sa.Column("context_json",sa.Text(),nullable=False),sa.Column("proposal_json",sa.Text(),nullable=True),
        sa.Column("eligible_versions_json",sa.Text(),nullable=False,server_default="[]"),
        sa.Column("input_state",sa.Text(),nullable=False),sa.Column("attempts",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("lease_until",sa.DateTime(timezone=True),nullable=True),sa.Column("last_error",sa.Text(),nullable=True),
        sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
    op.create_index("ix_bank_import_reconciliations_status","bank_import_reconciliations",["status"])

def downgrade():
    op.drop_table("bank_import_reconciliations")
