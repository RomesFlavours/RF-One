"""Add common interview requests, transcripts and candidate results."""
from alembic import op
import sqlalchemy as sa

revision = "f8d120261101"
down_revision = "f7c320261027"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("interview_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("requester_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=False),
        sa.Column("recipient_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("specialization", sa.String(32), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("results", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('REQUESTED', 'IN_PROGRESS', 'COMPLETED')", name="ck_interview_status"))
    op.create_index("ix_interview_sessions_requester_id", "interview_sessions", ["requester_id"])
    op.create_index("ix_interview_sessions_recipient_id", "interview_sessions", ["recipient_id"])


def downgrade():
    op.drop_table("interview_sessions")
