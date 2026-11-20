"""Bank AI Rules: Personal = the Source's classification; branches; invalidate Personal = Person

Revision ID: b2f8d4a6c1e9
Revises: a8e4c2f6d0b3
Create Date: 2026-10-11

BANK_AI_RULES_007 — AI Rules tables only.

  * bank_ai_rule_preview_items.to_verify — the fields a rule leaves "Da verificare" for a movement.
  * DATA: a saved interpretation that read "Personal" as "the Source owner is a Person"
    (`source_owner_kind` in its structure) is invalidated: its structure is cleared and the reason
    recorded, so it is never executed again. The rule text, the raw AI answer, the drafts and the
    operative rules are NOT changed and nothing is activated. (Interpretations are also keyed by a
    new engine version, so none of the previous ones is reused anyway.)

Downgrade drops the column; invalidated structures are not restored.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b2f8d4a6c1e9'
down_revision: Union[str, Sequence[str], None] = 'a8e4c2f6d0b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REASON = ("invalidated (BANK_AI_RULES_007): this interpretation read “Personal” as “the Source owner is a Person”; "
          "“Personal” is the Source's Personal classification in Bank")


def upgrade() -> None:
    with op.batch_alter_table("bank_ai_rule_preview_items") as batch:
        batch.add_column(sa.Column("to_verify", sa.String(16), nullable=True))
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "UPDATE bank_ai_rule_interpretations SET spec = NULL, rejection_reason = :reason "
        "WHERE spec LIKE '%source_owner_kind%'"), {"reason": REASON})
    print(f"[b2f8d4a6c1e9] interpretations invalidated (Personal = Person): {result.rowcount}")


def downgrade() -> None:
    with op.batch_alter_table("bank_ai_rule_preview_items") as batch:
        batch.drop_column("to_verify")
