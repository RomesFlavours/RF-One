"""Validated discovery, conversational drafts and exact preview evidence."""
from alembic import op
import sqlalchemy as sa
revision="f8e520261019"
down_revision="e7d420261019"
branch_labels=depends_on=None
def upgrade():
    op.create_table("bank_flow_artifacts",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("kind",sa.String(24),nullable=False),sa.Column("payload",sa.Text(),nullable=False),sa.Column("account_id",sa.Integer(),sa.ForeignKey("rfone_accounts.id"),nullable=True),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
    op.create_index("ix_bank_flow_artifacts_kind","bank_flow_artifacts",["kind"])
def downgrade():
    op.drop_table("bank_flow_artifacts")
