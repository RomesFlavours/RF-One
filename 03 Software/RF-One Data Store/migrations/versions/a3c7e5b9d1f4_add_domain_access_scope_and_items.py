"""Account access per Domain item, and Organization as its own Domain (ACCOUNT_ITEM_ACCESS_001)

Revision ID: a3c7e5b9d1f4
Revises: f5b8d2a4c6e1
Create Date: 2026-10-12

  * rfone_account_domain_access.scope  — new, required, ALL | SELECTED, default ALL. Every existing row becomes ALL,
                                         so every account keeps exactly the Domains it had, whole.
  * rfone_account_domain_item_access   — new: the items an account may use in a Domain whose scope is SELECTED.
  * ORGANIZATION access                — every administrator (rfone_accounts.is_admin) that has no ORGANIZATION row
                                         yet gets one, enabled, scope ALL: the Organization pages, until now reached
                                         from Settings by administrators, become the ORGANIZATION Domain, and
                                         administrators keep reaching them. Nobody else is granted anything.

Chained after the current head of this worktree (f5b8d2a4c6e1, MyRF Project Management: Project level).
Downgrade drops the item table, the scope column and every ORGANIZATION row.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a3c7e5b9d1f4'
down_revision: Union[str, Sequence[str], None] = 'f5b8d2a4c6e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ORGANIZATION = "ORGANIZATION"


def upgrade() -> None:
    with op.batch_alter_table("rfone_account_domain_access") as batch:
        batch.add_column(sa.Column("scope", sa.String(16), nullable=False, server_default="ALL"))
        batch.create_check_constraint("ck_rfone_account_domain_access_scope", "scope IN ('ALL', 'SELECTED')")

    op.create_table(
        "rfone_account_domain_item_access",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=False),
        sa.Column("domain_code", sa.String(32), nullable=False),
        sa.Column("item_code", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "account_id", "domain_code", "item_code", name="uq_rfone_account_domain_item_access_account_domain_item",
        ),
    )
    op.create_index(
        "ix_rfone_account_domain_item_access_account_id", "rfone_account_domain_item_access", ["account_id"],
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO rfone_account_domain_access (account_id, domain_code, enabled, scope) "
            "SELECT a.id, :code, :enabled, 'ALL' FROM rfone_accounts a "
            "WHERE a.is_admin = :is_admin AND NOT EXISTS ("
            "  SELECT 1 FROM rfone_account_domain_access x WHERE x.account_id = a.id AND x.domain_code = :code)"
        ),
        {"code": ORGANIZATION, "enabled": True, "is_admin": True},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM rfone_account_domain_access WHERE domain_code = :code"), {"code": ORGANIZATION})
    op.drop_index("ix_rfone_account_domain_item_access_account_id", table_name="rfone_account_domain_item_access")
    op.drop_table("rfone_account_domain_item_access")
    with op.batch_alter_table("rfone_account_domain_access") as batch:
        batch.drop_constraint("ck_rfone_account_domain_access_scope", type_="check")
        batch.drop_column("scope")
