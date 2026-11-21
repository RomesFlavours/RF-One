"""Versioned tip aggregation scope; existing rules keep order semantics."""
from alembic import op
import sqlalchemy as sa
revision = "e2c320261109"
down_revision = "e1b220261102"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tip_distribution_rule_versions", sa.Column(
        "aggregation_scope", sa.String(32), nullable=False, server_default="ORDER"))


def downgrade():
    op.drop_column("tip_distribution_rule_versions", "aggregation_scope")
