"""Selection candidate verification by text message as well as by email
(SELECTION_CANDIDATE_SMS_001).

Additive only: nullable phone columns on the candidate identity, and the
channel/target of each verification code (existing codes are EMAIL).

Revision ID: b8e620261021
Revises: a7d520261021
"""

from alembic import op
import sqlalchemy as sa

revision = "b8e620261021"
down_revision = "a7d520261021"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("selection_candidate_accounts", sa.Column("phone", sa.String(32), nullable=True))
    op.add_column("selection_candidate_accounts", sa.Column("phone_verified_at", sa.DateTime(), nullable=True))
    op.add_column("selection_candidate_email_codes",
                  sa.Column("channel", sa.String(8), nullable=False, server_default="EMAIL"))
    op.add_column("selection_candidate_email_codes", sa.Column("target", sa.String(320), nullable=True))


def downgrade():
    with op.batch_alter_table("selection_candidate_email_codes") as batch:
        batch.drop_column("target")
        batch.drop_column("channel")
    with op.batch_alter_table("selection_candidate_accounts") as batch:
        batch.drop_column("phone_verified_at")
        batch.drop_column("phone")
