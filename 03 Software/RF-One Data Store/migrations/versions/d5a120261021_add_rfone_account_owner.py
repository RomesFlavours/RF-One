"""RF-One accounts: the installation owner, distinct from administrators
(ADMIN_PERMISSIONS_001).

Adds `rfone_accounts.is_owner` (default false), a check that the owner is
always an administrator, and a partial unique index allowing at most one
owner. Backfill: the owner is assigned explicitly to the `rfone` account
(Pino Miraglia) — never to whichever administrator happens to come first.
That account is also made an administrator (the owner always is one). If
no `rfone` account exists (e.g. a fresh database), no owner is set and the
owner stays unassigned until set explicitly. No other row or column
changes; `is_admin` keeps its meaning and any number of accounts may hold
it.

Revision ID: d5a120261021
Revises: c4e820261021
"""

from alembic import op
import sqlalchemy as sa

revision = "d5a120261021"
down_revision = "c4e820261021"
branch_labels = None
depends_on = None

OWNER_USERNAME = "rfone"


def upgrade() -> None:
    with op.batch_alter_table("rfone_accounts") as batch:
        batch.add_column(sa.Column("is_owner", sa.Boolean(), nullable=False, server_default=sa.text("false")))
        batch.create_check_constraint("ck_rfone_account_owner_is_admin", "NOT is_owner OR is_admin")
    op.get_bind().execute(
        sa.text("UPDATE rfone_accounts SET is_owner = true, is_admin = true WHERE username = :username"),
        {"username": OWNER_USERNAME},
    )
    op.create_index(
        "uq_rfone_accounts_single_owner", "rfone_accounts", ["is_owner"], unique=True,
        postgresql_where=sa.text("is_owner"), sqlite_where=sa.text("is_owner"),
    )


def downgrade() -> None:
    op.drop_index("uq_rfone_accounts_single_owner", table_name="rfone_accounts")
    with op.batch_alter_table("rfone_accounts") as batch:
        batch.drop_constraint("ck_rfone_account_owner_is_admin", type_="check")
        batch.drop_column("is_owner")
