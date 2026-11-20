"""Bank AI Rules: AI instructions, AI test runs and their proposals

Revision ID: c5e1a7d3b9f2
Revises: a9d3f5b7c1e2
Create Date: 2026-10-11

BANK_AI_RULES_001 — three NEW tables, separate from every traditional rule
(General Rules, WHO Rules, WHY Rules, Standards). Nothing existing is
altered: no column, no row of any other table changes.

  * bank_ai_instructions  — the AI classification instructions, append-only
                            (each Save is a version; the latest is current).
  * bank_ai_test_runs     — one "Run AI Test" on a small sample.
  * bank_ai_test_results  — the AI's proposal per movement, with snapshots.

Downgrade drops the three tables (and the test history they hold).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c5e1a7d3b9f2'
down_revision: Union[str, Sequence[str], None] = 'a9d3f5b7c1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bank_ai_instructions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("created_by_account_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "bank_ai_test_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instruction_id", sa.Integer(), sa.ForeignKey("bank_ai_instructions.id"), nullable=True),
        sa.Column("instructions_snapshot", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(255), nullable=True),
        sa.Column("date_from", sa.Date(), nullable=True),
        sa.Column("date_to", sa.Date(), nullable=True),
        sa.Column("only_unclassified", sa.Boolean(), nullable=False),
        sa.Column("requested_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by_account_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('COMPLETED', 'FAILED')", name="ck_bank_ai_test_run_status"),
    )
    op.create_table(
        "bank_ai_test_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("bank_ai_test_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("financial_transaction_id", sa.Integer(),
                  sa.ForeignKey("financial_transactions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("posting_date", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("source_label", sa.String(255), nullable=True),
        sa.Column("current_who_name", sa.String(255), nullable=True),
        sa.Column("current_why_name", sa.String(255), nullable=True),
        sa.Column("proposed_who_name", sa.String(255), nullable=True),
        sa.Column("proposed_who_id", sa.Integer(), sa.ForeignKey("bank_occurrences.id"), nullable=True),
        sa.Column("proposed_who_is_new", sa.Boolean(), nullable=False),
        sa.Column("proposed_why_name", sa.String(255), nullable=True),
        sa.Column("proposed_why_id", sa.Integer(), sa.ForeignKey("bank_transaction_reasons.id"), nullable=True),
        sa.Column("proposed_why_is_new", sa.Boolean(), nullable=False),
        sa.Column("to_verify", sa.Boolean(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("doubt", sa.Text(), nullable=True),
    )
    op.create_index("ix_bank_ai_test_results_run_id", "bank_ai_test_results", ["run_id"])
    op.create_index("ix_bank_ai_test_results_financial_transaction_id", "bank_ai_test_results",
                    ["financial_transaction_id"])


def downgrade() -> None:
    op.drop_index("ix_bank_ai_test_results_financial_transaction_id", table_name="bank_ai_test_results")
    op.drop_index("ix_bank_ai_test_results_run_id", table_name="bank_ai_test_results")
    op.drop_table("bank_ai_test_results")
    op.drop_table("bank_ai_test_runs")
    op.drop_table("bank_ai_instructions")
