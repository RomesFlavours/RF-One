"""Bank AI Rules: "Crea WHO mancanti" and the evaluation method of a preview

Revision ID: e4a9c1f7d3b5
Revises: d8b2f6c4a1e7
Create Date: 2026-10-11

BANK_AI_RULES_003 — columns added to the AI Rules tables only:

  * bank_ai_rule_drafts.create_missing_who      (default false)
  * bank_ai_rule_previews.create_missing_who    (default false)
  * bank_ai_rule_previews.method                ('AI' for every existing preview)
  * bank_ai_rule_previews.interpretation        (JSON, nullable)

No other table changes. Downgrade drops the four columns.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e4a9c1f7d3b5'
down_revision: Union[str, Sequence[str], None] = 'd8b2f6c4a1e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bank_ai_rule_drafts") as batch:
        batch.add_column(sa.Column("create_missing_who", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    with op.batch_alter_table("bank_ai_rule_previews") as batch:
        batch.add_column(sa.Column("method", sa.String(8), nullable=False, server_default="AI"))
        batch.add_column(sa.Column("interpretation", sa.Text(), nullable=True))
        batch.add_column(sa.Column("create_missing_who", sa.Boolean(), nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    with op.batch_alter_table("bank_ai_rule_previews") as batch:
        batch.drop_column("create_missing_who")
        batch.drop_column("interpretation")
        batch.drop_column("method")
    with op.batch_alter_table("bank_ai_rule_drafts") as batch:
        batch.drop_column("create_missing_who")
