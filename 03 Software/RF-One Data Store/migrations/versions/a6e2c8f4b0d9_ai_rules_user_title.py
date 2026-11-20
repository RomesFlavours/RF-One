"""Bank AI Rules: a Title the user writes for a rule (and for its drafts)

Revision ID: a6e2c8f4b0d9
Revises: d2b6f8a4c0e7
Create Date: 2026-10-14

BANK_AI_RULES_022 — AI Rules tables only, additive.

  * bank_ai_rules.user_title, bank_ai_rule_drafts.user_title — the Title typed by the user above the rule text: the
    rule's main identifier in the list. Optional, NULL for every existing row (it can be added later). Distinct from
    bank_ai_rules.title, which stays the automatic summary of the rule text, rewritten at each new version.

Chained after the current head of this worktree (d2b6f8a4c0e7, removal of the old rule system). No data is changed.
Downgrade drops the columns.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a6e2c8f4b0d9'
down_revision: Union[str, Sequence[str], None] = 'd2b6f8a4c0e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # BANK_REINSTALL_001 — on a database where Bank was removed (84354dc654ce, RDS on 2026-10-14) there is nothing
    # to change: the reinstall revision c8e4b2a6f0d1 creates the current Bank schema there.
    if "bank_transaction_explanations" not in sa.inspect(op.get_bind()).get_table_names():
        return
    for table in ("bank_ai_rules", "bank_ai_rule_drafts"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("user_title", sa.String(length=200), nullable=True))


def downgrade() -> None:
    for table in ("bank_ai_rule_drafts", "bank_ai_rules"):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("user_title")
