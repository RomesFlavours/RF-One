"""Counterparty card display names and durable removal."""
from alembic import op
import sqlalchemy as sa
revision="e7d420261019"
down_revision="d6c320261019"
branch_labels=depends_on=None
def upgrade():
    op.add_column("bank_who_knowledge",sa.Column("display_name",sa.String(200),nullable=True))
    op.add_column("bank_who_knowledge",sa.Column("deleted_at",sa.DateTime(timezone=True),nullable=True))
def downgrade():
    op.drop_column("bank_who_knowledge","deleted_at")
    op.drop_column("bank_who_knowledge","display_name")
