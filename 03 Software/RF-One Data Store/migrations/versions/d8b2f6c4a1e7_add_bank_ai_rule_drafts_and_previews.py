"""Bank AI Rules: natural-language rule drafts and their period previews

Revision ID: d8b2f6c4a1e7
Revises: c5e1a7d3b9f2
Create Date: 2026-10-11

BANK_AI_RULES_002 — three NEW tables, separate from every traditional rule.
Nothing existing is altered; the BANK_AI_RULES_001 tables stay as they are.

  * bank_ai_rule_drafts         — a natural-language AI rule saved as a draft,
                                  with its origin transaction (link + snapshot).
  * bank_ai_rule_previews       — one Preview over every movement of a period.
  * bank_ai_rule_preview_items  — the movements it matched or doubted.

Downgrade drops the three tables (and the drafts and previews they hold).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd8b2f6c4a1e7'
down_revision: Union[str, Sequence[str], None] = 'c5e1a7d3b9f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bank_ai_rule_drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rule_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("origin_transaction_id", sa.Integer(),
                  sa.ForeignKey("financial_transactions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("origin_posting_date", sa.Date(), nullable=True),
        sa.Column("origin_description", sa.Text(), nullable=True),
        sa.Column("origin_amount_minor", sa.Integer(), nullable=True),
        sa.Column("created_by_account_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('DRAFT')", name="ck_bank_ai_rule_draft_status"),
    )
    op.create_index("ix_bank_ai_rule_drafts_origin_transaction_id", "bank_ai_rule_drafts",
                    ["origin_transaction_id"])
    op.create_table(
        "bank_ai_rule_previews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("draft_id", sa.Integer(), sa.ForeignKey("bank_ai_rule_drafts.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("rule_text", sa.Text(), nullable=False),
        sa.Column("origin_transaction_id", sa.Integer(),
                  sa.ForeignKey("financial_transactions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
        sa.Column("examined_count", sa.Integer(), nullable=False),
        sa.Column("match_count", sa.Integer(), nullable=False),
        sa.Column("doubt_count", sa.Integer(), nullable=False),
        sa.Column("ai_calls", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by_account_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('COMPLETED', 'FAILED')", name="ck_bank_ai_rule_preview_status"),
    )
    op.create_index("ix_bank_ai_rule_previews_draft_id", "bank_ai_rule_previews", ["draft_id"])
    op.create_table(
        "bank_ai_rule_preview_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("preview_id", sa.Integer(), sa.ForeignKey("bank_ai_rule_previews.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("financial_transaction_id", sa.Integer(),
                  sa.ForeignKey("financial_transactions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("verdict", sa.String(8), nullable=False),
        sa.Column("is_origin", sa.Boolean(), nullable=False),
        sa.Column("posting_date", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("source_label", sa.String(255), nullable=True),
        sa.Column("current_who_name", sa.String(255), nullable=True),
        sa.Column("current_why_name", sa.String(255), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("proposed_who_name", sa.String(255), nullable=True),
        sa.Column("proposed_who_id", sa.Integer(), sa.ForeignKey("bank_occurrences.id"), nullable=True),
        sa.Column("proposed_who_is_new", sa.Boolean(), nullable=False),
        sa.Column("proposed_why_name", sa.String(255), nullable=True),
        sa.Column("proposed_why_id", sa.Integer(), sa.ForeignKey("bank_transaction_reasons.id"), nullable=True),
        sa.Column("proposed_why_is_new", sa.Boolean(), nullable=False),
        sa.CheckConstraint("verdict IN ('MATCH', 'DOUBT')", name="ck_bank_ai_rule_preview_item_verdict"),
    )
    op.create_index("ix_bank_ai_rule_preview_items_preview_id", "bank_ai_rule_preview_items", ["preview_id"])
    op.create_index("ix_bank_ai_rule_preview_items_financial_transaction_id", "bank_ai_rule_preview_items",
                    ["financial_transaction_id"])


def downgrade() -> None:
    op.drop_index("ix_bank_ai_rule_preview_items_financial_transaction_id", table_name="bank_ai_rule_preview_items")
    op.drop_index("ix_bank_ai_rule_preview_items_preview_id", table_name="bank_ai_rule_preview_items")
    op.drop_table("bank_ai_rule_preview_items")
    op.drop_index("ix_bank_ai_rule_previews_draft_id", table_name="bank_ai_rule_previews")
    op.drop_table("bank_ai_rule_previews")
    op.drop_index("ix_bank_ai_rule_drafts_origin_transaction_id", table_name="bank_ai_rule_drafts")
    op.drop_table("bank_ai_rule_drafts")
