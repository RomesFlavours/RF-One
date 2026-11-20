"""Bank AI Rules: "Solo movimenti non ancora sistemati da regole AI"

Revision ID: e8f3a1c6d2b9
Revises: d7e2f0b5c3a8
Create Date: 2026-10-11

BANK_AI_RULES_013 — AI Rules tables only, additive.

  * bank_ai_rule_drafts.only_unsettled (1 by default: the option is selected unless the operator clears it);
  * bank_ai_rule_previews.only_unsettled, .excluded_ai_settled and bank_ai_rule_applications.only_unsettled,
    .excluded_ai_settled — whether a preview / application left out the movements already settled by an AI rule,
    and how many. Existing previews and applications considered every movement: 0 / NULL for them.

"Settled by an AI rule" is NOT stored on movements: it is the recorded provenance already there (the movement's
current decision is one an AI rule application wrote — an UPDATED application item with that decision).
No data is changed. Downgrade drops the columns.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e8f3a1c6d2b9'
down_revision: Union[str, Sequence[str], None] = 'd7e2f0b5c3a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bank_ai_rule_drafts") as batch:
        batch.add_column(sa.Column("only_unsettled", sa.Boolean(), nullable=False, server_default=sa.true()))
    for table in ("bank_ai_rule_previews", "bank_ai_rule_applications"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("only_unsettled", sa.Boolean(), nullable=False, server_default=sa.false()))
            batch.add_column(sa.Column("excluded_ai_settled", sa.Integer(), nullable=True))


def downgrade() -> None:
    for table in ("bank_ai_rule_applications", "bank_ai_rule_previews"):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("excluded_ai_settled")
            batch.drop_column("only_unsettled")
    with op.batch_alter_table("bank_ai_rule_drafts") as batch:
        batch.drop_column("only_unsettled")
