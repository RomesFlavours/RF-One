"""Bank AI Rules: For Whom assignment — current and proposed For Whom on preview and application items

Revision ID: c6d1e9a4f2b7
Revises: b2f8d4a6c1e9
Create Date: 2026-10-11

BANK_AI_RULES_010 — AI Rules tables only, additive.

  * bank_ai_rule_preview_items.current_for_whom_name / proposed_for_whom_name / proposed_for_whom_id
    — the movement's current For Whom and the entity the rule proposes.
  * bank_ai_rule_application_items.for_whom_before / for_whom_after.

No data is changed: no interpretation, rule, preview, decision or allocation. (Interpretations are keyed
by a new engine version; a VALID previous one stays reusable, a blocked one is interpreted again — in
code, `ai_rules.saved_interpretation`.)

Downgrade drops the columns.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c6d1e9a4f2b7'
down_revision: Union[str, Sequence[str], None] = 'b2f8d4a6c1e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bank_ai_rule_preview_items") as batch:
        batch.add_column(sa.Column("current_for_whom_name", sa.String(255), nullable=True))
        batch.add_column(sa.Column("proposed_for_whom_name", sa.String(255), nullable=True))
        batch.add_column(sa.Column("proposed_for_whom_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_bank_ai_rule_preview_item_for_whom", "reporting_entities",
                                 ["proposed_for_whom_id"], ["id"])
    with op.batch_alter_table("bank_ai_rule_application_items") as batch:
        batch.add_column(sa.Column("for_whom_before", sa.String(255), nullable=True))
        batch.add_column(sa.Column("for_whom_after", sa.String(255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("bank_ai_rule_application_items") as batch:
        batch.drop_column("for_whom_after")
        batch.drop_column("for_whom_before")
    with op.batch_alter_table("bank_ai_rule_preview_items") as batch:
        batch.drop_constraint("fk_bank_ai_rule_preview_item_for_whom", type_="foreignkey")
        batch.drop_column("proposed_for_whom_id")
        batch.drop_column("proposed_for_whom_name")
        batch.drop_column("current_for_whom_name")
