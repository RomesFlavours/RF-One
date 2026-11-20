"""Bank AI Rules: Delete a rule (kept as history, never executed again)

Revision ID: f9a4b2d7e1c3
Revises: e8f3a1c6d2b9
Create Date: 2026-10-11

BANK_AI_RULES_014 — AI Rules tables only, additive.

  * bank_ai_rules.deleted_at, .deleted_by_account_id — a deleted rule leaves the page and is never executed again
    (its status is INACTIVE and it cannot be reactivated or saved). Its versions, previews, applications and
    application items stay: the provenance of the classifications it applied is kept, and those classifications are
    not touched.

No data is changed. Downgrade drops the columns.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f9a4b2d7e1c3'
down_revision: Union[str, Sequence[str], None] = 'e8f3a1c6d2b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bank_ai_rules") as batch:
        batch.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("deleted_by_account_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_bank_ai_rule_deleted_by", "rfone_accounts", ["deleted_by_account_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("bank_ai_rules") as batch:
        batch.drop_constraint("fk_bank_ai_rule_deleted_by", type_="foreignkey")
        batch.drop_column("deleted_by_account_id")
        batch.drop_column("deleted_at")
