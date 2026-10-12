"""Bank AI Rules: the "Solo WHO" run mode on previews and applications

Revision ID: c3d9e1f5a7b2
Revises: e3a7c5f9b1d4
Create Date: 2026-10-12

BANK_AI_RULES_018 — AI Rules tables only, additive.

  * bank_ai_rule_previews.who_only, bank_ai_rule_applications.who_only — whether only the WHO part of the rule was
    executed (WHY, the WHO's default WHY and For Whom left as they were). 0 for every existing row.

Chained after the current head of this worktree (e3a7c5f9b1d4, MyRF Project Management v1). No data is changed.
Downgrade drops the columns.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c3d9e1f5a7b2'
down_revision: Union[str, Sequence[str], None] = 'e3a7c5f9b1d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("bank_ai_rule_previews", "bank_ai_rule_applications"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("who_only", sa.Boolean(), nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    for table in ("bank_ai_rule_applications", "bank_ai_rule_previews"):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("who_only")
