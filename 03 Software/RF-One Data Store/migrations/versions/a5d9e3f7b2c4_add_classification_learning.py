"""add Classification Learning: pattern suggestions, learning runs, WHY rules

Revision ID: a5d9e3f7b2c4
Revises: f4a8c2d6e9b3
Create Date: 2026-10-05

BANK_CLASSIFICATION_LEARNING_001 — Product Owner approved. ADDITIVE, no data.

  * `bank_learning_runs`     — each explicit Discover / Backtest action and its summary.
  * `bank_pattern_suggestions` — proposed patterns (STRUCTURAL / WHO / WHY), with a
    fingerprint so a rejected pattern is not proposed again without new evidence.
    A suggestion is never a rule: approval creates the rule in its own store.
  * `bank_why_rules`         — deterministic WHY rules of WHO Classification: WHO
    scope (required) + simple conditions -> WHY. Human-approved only; a WHY rule
    never chooses a WHO.

Downgrade drops the three tables.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a5d9e3f7b2c4'
down_revision: Union[str, Sequence[str], None] = 'f4a8c2d6e9b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bank_learning_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("created_by_account_id", sa.Integer(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_account_id"], ["rfone_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("kind IN ('DISCOVERY', 'BACKTEST')", name="ck_bank_learning_run_kind"),
    )
    op.create_table(
        "bank_pattern_suggestions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("pattern_type", sa.String(length=16), nullable=False),
        sa.Column("determinism", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("proposal", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("evidence_level", sa.String(length=24), nullable=False),
        sa.Column("previously_rejected", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("rejected_evidence_size", sa.Integer(), nullable=True),
        sa.Column("discovery_run_id", sa.Integer(), nullable=True),
        sa.Column("decided_by_account_id", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("routed_to", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["discovery_run_id"], ["bank_learning_runs.id"]),
        sa.ForeignKeyConstraint(["decided_by_account_id"], ["rfone_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint", name="uq_bank_pattern_suggestion_fingerprint"),
        sa.CheckConstraint("pattern_type IN ('STRUCTURAL', 'WHO', 'WHY')", name="ck_bank_pattern_suggestion_type"),
        sa.CheckConstraint("status IN ('SUGGESTED', 'APPROVED', 'REJECTED', 'COVERED')",
                           name="ck_bank_pattern_suggestion_status"),
        sa.CheckConstraint("determinism IN ('DETERMINISTIC', 'PROBABILISTIC')",
                           name="ck_bank_pattern_suggestion_determinism"),
    )
    op.create_table(
        "bank_why_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("occurrence_id", sa.Integer(), nullable=False),
        sa.Column("description_contains", sa.String(length=120), nullable=True),
        sa.Column("direction", sa.String(length=8), nullable=True),
        sa.Column("instrument_type", sa.String(length=32), nullable=True),
        sa.Column("transaction_reason_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("origin", sa.String(length=32), nullable=False),
        sa.Column("approved_by_account_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["occurrence_id"], ["bank_occurrences.id"]),
        sa.ForeignKeyConstraint(["transaction_reason_id"], ["bank_transaction_reasons.id"]),
        sa.ForeignKeyConstraint(["approved_by_account_id"], ["rfone_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_bank_why_rule_status"),
        sa.CheckConstraint("direction IS NULL OR direction IN ('DEBIT', 'CREDIT')", name="ck_bank_why_rule_direction"),
    )
    op.create_index("ix_bank_why_rules_occurrence_id", "bank_why_rules", ["occurrence_id"])


def downgrade() -> None:
    op.drop_index("ix_bank_why_rules_occurrence_id", table_name="bank_why_rules")
    op.drop_table("bank_why_rules")
    op.drop_table("bank_pattern_suggestions")
    op.drop_table("bank_learning_runs")
