"""Bank AI Rules: saved rule interpretations and completed AI batches

Revision ID: f7c3a9e1b5d8
Revises: e4a9c1f7d3b5
Create Date: 2026-10-11

BANK_AI_RULES_005 — two NEW tables, AI Rules only; nothing existing altered.

  * bank_ai_rule_interpretations — the AI's interpretation of a rule text under
    a set of general instructions (raw answer + validated structure), reused
    while both are unchanged.
  * bank_ai_rule_batch_results   — the answer to one batch of a movement-by-
    movement preview, keyed by the exact prompt, so a stopped preview resumes
    without asking again the batches already completed.

Downgrade drops the two tables.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f7c3a9e1b5d8'
down_revision: Union[str, Sequence[str], None] = 'e4a9c1f7d3b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bank_ai_rule_interpretations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cache_key", sa.String(64), nullable=False),
        sa.Column("rule_text", sa.Text(), nullable=False),
        sa.Column("instructions_snapshot", sa.Text(), nullable=True),
        sa.Column("raw_answer", sa.Text(), nullable=True),
        sa.Column("spec", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(32), nullable=True),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("cache_key", name="uq_bank_ai_rule_interpretation_key"),
    )
    op.create_table(
        "bank_ai_rule_batch_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("items_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("prompt_hash", name="uq_bank_ai_rule_batch_prompt"),
    )


def downgrade() -> None:
    op.drop_table("bank_ai_rule_batch_results")
    op.drop_table("bank_ai_rule_interpretations")
