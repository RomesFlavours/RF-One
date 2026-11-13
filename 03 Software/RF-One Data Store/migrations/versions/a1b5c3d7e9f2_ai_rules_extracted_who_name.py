"""Bank AI Rules: the extracted WHO text on preview items

Revision ID: a1b5c3d7e9f2
Revises: f9a4b2d7e1c3
Create Date: 2026-10-11

BANK_AI_RULES_016 — AI Rules tables only, additive.

  * bank_ai_rule_preview_items.extracted_who_name — the WHO text a rule extracted (cleaned: line breaks and tabs as
    spaces, spaces collapsed, trimmed, upper case), shown next to the final WHO when an existing WHO was reused for it.

No data is changed. Downgrade drops the column.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b5c3d7e9f2'
down_revision: Union[str, Sequence[str], None] = 'f9a4b2d7e1c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bank_ai_rule_preview_items") as batch:
        batch.add_column(sa.Column("extracted_who_name", sa.String(255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("bank_ai_rule_preview_items") as batch:
        batch.drop_column("extracted_who_name")
