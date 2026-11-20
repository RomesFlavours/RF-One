"""Organize reasoning and signatures; retain sourced WHO knowledge separately."""
from alembic import op
import sqlalchemy as sa
revision = "c5b220261019"
down_revision = "b4a120261019"
branch_labels = depends_on = None

def upgrade():
    op.add_column("bank_ai_rules", sa.Column("organization_kind", sa.String(20), nullable=False, server_default="AUTO"))
    op.create_table("bank_who_knowledge",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("occurrence_id", sa.Integer(), sa.ForeignKey("bank_occurrences.id"), nullable=False, unique=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("sources_json", sa.Text(), nullable=False),
        sa.Column("suggested_reason_id", sa.Integer(), sa.ForeignKey("bank_transaction_reasons.id"), nullable=True),
        sa.Column("researched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))

def downgrade():
    op.drop_table("bank_who_knowledge")
    op.drop_column("bank_ai_rules", "organization_kind")
