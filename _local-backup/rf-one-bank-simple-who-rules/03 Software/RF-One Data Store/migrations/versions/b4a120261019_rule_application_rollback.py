"""Two rule modes and guarded application rollback (additive)."""
from alembic import op
import sqlalchemy as sa
revision = "b4a120261019"
down_revision = "a6e2c8f4b0d9"
branch_labels = depends_on = None
COLUMNS = {
    "bank_ai_rule_previews": [("application_mode", sa.String(24)), ("state_fingerprint", sa.String(64))],
    "bank_ai_rule_applications": [("application_mode", sa.String(24)), ("rolled_back_at", sa.DateTime(timezone=True)), ("rolled_back_by_account_id", sa.Integer())],
    "bank_ai_rule_application_items": [("before_state", sa.Text()), ("after_state", sa.Text()), ("rollback_outcome", sa.String(24))],
}
def upgrade():
    for table, cols in COLUMNS.items():
        for name, kind in cols:
            op.add_column(table, sa.Column(name, kind, nullable=True))
def downgrade():
    for table, cols in reversed(list(COLUMNS.items())):
        for name, _ in reversed(cols):
            op.drop_column(table, name)
