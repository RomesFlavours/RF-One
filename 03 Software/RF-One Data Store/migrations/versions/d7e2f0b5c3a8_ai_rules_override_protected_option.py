"""Bank AI Rules: the per-rule option "Sostituisci anche WHO/WHY manuali, Standard o confermati"

Revision ID: d7e2f0b5c3a8
Revises: c6d1e9a4f2b7
Create Date: 2026-10-11

BANK_AI_RULES_011 — AI Rules tables only, additive.

  * bank_ai_rule_drafts.override_protected, bank_ai_rule_previews.override_protected,
    bank_ai_rule_versions.override_protected — an explicit option of ONE rule, off (0) by default and for every
    existing row. With it on, that rule may replace WHO / WHY also when manual, Standard or confirmed (For Whom
    kept, the decision written "Da confermare", the override named in its notes). The protections of every
    other rule are unchanged.

No data is changed. Downgrade drops the columns.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd7e2f0b5c3a8'
down_revision: Union[str, Sequence[str], None] = 'c6d1e9a4f2b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("bank_ai_rule_drafts", "bank_ai_rule_previews", "bank_ai_rule_versions")


def upgrade() -> None:
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("override_protected", sa.Boolean(), nullable=False,
                                       server_default=sa.text("0")))


def downgrade() -> None:
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            batch.drop_column("override_protected")
