"""Selection candidates verified on the careers page hosted on Aruba
(SELECTION_ARUBA_IDENTITY_001).

Additive only: first and last name on the candidate identity, its password
becomes optional (an identity verified by email on Aruba has none), and one
row per accepted identity token so that a token is used only once. Existing
identities and their passwords are unchanged.

Revision ID: c2b720261025
Revises: b8e620261021
"""

from alembic import op
import sqlalchemy as sa

revision = "c2b720261025"
down_revision = "b8e620261021"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("selection_candidate_accounts") as batch:
        batch.add_column(sa.Column("first_name", sa.String(120), nullable=True))
        batch.add_column(sa.Column("last_name", sa.String(120), nullable=True))
        batch.alter_column("password_hash", existing_type=sa.String(255), nullable=True)
    op.create_table(
        "selection_candidate_identity_handoffs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_id", sa.String(64), nullable=False),
        sa.Column("position_id", sa.Integer(), sa.ForeignKey("selection_workspace_positions.id"), nullable=False),
        sa.Column("candidate_account_id", sa.Integer(), sa.ForeignKey("selection_candidate_accounts.id"),
                  nullable=False),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=False),
        sa.Column("request_ip", sa.String(64), nullable=True),
        sa.UniqueConstraint("token_id", name="uq_selection_candidate_identity_handoffs_token_id"),
    )
    op.create_index("ix_selection_candidate_identity_handoffs_candidate_account_id",
                    "selection_candidate_identity_handoffs", ["candidate_account_id"])


def downgrade():
    op.drop_index("ix_selection_candidate_identity_handoffs_candidate_account_id",
                  table_name="selection_candidate_identity_handoffs")
    op.drop_table("selection_candidate_identity_handoffs")
    # Deliberately fails while email-only identities (no password) exist: no candidate is deleted here.
    with op.batch_alter_table("selection_candidate_accounts") as batch:
        batch.alter_column("password_hash", existing_type=sa.String(255), nullable=False)
        batch.drop_column("last_name")
        batch.drop_column("first_name")
