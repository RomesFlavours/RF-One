"""Bank AI Rules: operative rules, their versions and applications

Revision ID: a8e4c2f6d0b3
Revises: f7c3a9e1b5d8
Create Date: 2026-10-11

BANK_AI_RULES_006 — AI Rules tables only; nothing outside them altered.

  * bank_ai_rules                   — operative AI rules (status, applied to new imports or not)
  * bank_ai_rule_versions           — their versions: text, option, validated interpretation
  * bank_ai_rule_applications       — each application, with its summary
  * bank_ai_rule_application_items  — each movement: outcome, WHO/WHY before and after
  * bank_ai_rule_drafts.ai_rule_id  — a draft of a change to an operative rule
  * bank_ai_rule_previews           — scope, scope key and the planned outcome counts
  * bank_ai_rule_preview_items      — the planned outcome per movement

No rule is created or activated by this migration. Downgrade removes it all.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a8e4c2f6d0b3'
down_revision: Union[str, Sequence[str], None] = 'f7c3a9e1b5d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bank_ai_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("apply_future", sa.Boolean(), nullable=False),
        sa.Column("origin_transaction_id", sa.Integer(),
                  sa.ForeignKey("financial_transactions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("origin_description", sa.Text(), nullable=True),
        sa.Column("last_applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_account_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_bank_ai_rule_status"),
    )
    op.create_table(
        "bank_ai_rule_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rule_id", sa.Integer(), sa.ForeignKey("bank_ai_rules.id"), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("rule_text", sa.Text(), nullable=False),
        sa.Column("create_missing_who", sa.Boolean(), nullable=False),
        sa.Column("method", sa.String(8), nullable=False),
        sa.Column("spec", sa.Text(), nullable=True),
        sa.Column("interpretation_id", sa.Integer(), sa.ForeignKey("bank_ai_rule_interpretations.id"), nullable=True),
        sa.Column("instructions_snapshot", sa.Text(), nullable=True),
        sa.Column("created_by_account_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("rule_id", "version_no", name="uq_bank_ai_rule_version"),
        sa.CheckConstraint("method IN ('CODE', 'AI')", name="ck_bank_ai_rule_version_method"),
    )
    op.create_index("ix_bank_ai_rule_versions_rule_id", "bank_ai_rule_versions", ["rule_id"])
    op.create_table(
        "bank_ai_rule_applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rule_id", sa.Integer(), sa.ForeignKey("bank_ai_rules.id"), nullable=False),
        sa.Column("version_id", sa.Integer(), sa.ForeignKey("bank_ai_rule_versions.id"), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("preview_id", sa.Integer(), sa.ForeignKey("bank_ai_rule_previews.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("import_batch_id", sa.Integer(), sa.ForeignKey("bank_import_batches.id"), nullable=True),
        sa.Column("examined", sa.Integer(), nullable=False),
        sa.Column("updated", sa.Integer(), nullable=False),
        sa.Column("unchanged", sa.Integer(), nullable=False),
        sa.Column("protected", sa.Integer(), nullable=False),
        sa.Column("conflicts", sa.Integer(), nullable=False),
        sa.Column("unresolved", sa.Integer(), nullable=False),
        sa.Column("errors", sa.Integer(), nullable=False),
        sa.Column("who_created", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by_account_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("mode IN ('EXISTING_ALL', 'SELECTED', 'IMPORT')", name="ck_bank_ai_rule_application_mode"),
        sa.CheckConstraint("status IN ('COMPLETED', 'FAILED')", name="ck_bank_ai_rule_application_status"),
    )
    op.create_index("ix_bank_ai_rule_applications_rule_id", "bank_ai_rule_applications", ["rule_id"])
    op.create_table(
        "bank_ai_rule_application_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("application_id", sa.Integer(),
                  sa.ForeignKey("bank_ai_rule_applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("financial_transaction_id", sa.Integer(),
                  sa.ForeignKey("financial_transactions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("outcome", sa.String(12), nullable=False),
        sa.Column("who_before", sa.String(255), nullable=True),
        sa.Column("why_before", sa.String(255), nullable=True),
        sa.Column("who_after", sa.String(255), nullable=True),
        sa.Column("why_after", sa.String(255), nullable=True),
        sa.Column("explanation_id", sa.Integer(), sa.ForeignKey("bank_transaction_explanations.id"), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint("outcome IN ('UPDATED', 'UNCHANGED', 'PROTECTED', 'CONFLICT', 'UNRESOLVED', 'ERROR')",
                           name="ck_bank_ai_rule_application_item_outcome"),
    )
    op.create_index("ix_bank_ai_rule_application_items_application_id", "bank_ai_rule_application_items",
                    ["application_id"])
    op.create_index("ix_bank_ai_rule_application_items_financial_transaction_id", "bank_ai_rule_application_items",
                    ["financial_transaction_id"])
    with op.batch_alter_table("bank_ai_rule_drafts") as batch:
        batch.add_column(sa.Column("ai_rule_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_bank_ai_rule_drafts_ai_rule_id", "bank_ai_rules", ["ai_rule_id"], ["id"])
    with op.batch_alter_table("bank_ai_rule_previews") as batch:
        batch.add_column(sa.Column("scope", sa.String(16), nullable=True))
        batch.add_column(sa.Column("scope_key", sa.String(64), nullable=True))
        for name in ("planned_updates", "unchanged_count", "protected_count", "conflict_count", "unresolved_count"):
            batch.add_column(sa.Column(name, sa.Integer(), nullable=False, server_default=sa.text("0")))
    with op.batch_alter_table("bank_ai_rule_preview_items") as batch:
        batch.add_column(sa.Column("plan", sa.String(12), nullable=True))
        batch.add_column(sa.Column("plan_note", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("bank_ai_rule_preview_items") as batch:
        batch.drop_column("plan_note")
        batch.drop_column("plan")
    with op.batch_alter_table("bank_ai_rule_previews") as batch:
        for name in ("unresolved_count", "conflict_count", "protected_count", "unchanged_count", "planned_updates",
                     "scope_key", "scope"):
            batch.drop_column(name)
    with op.batch_alter_table("bank_ai_rule_drafts") as batch:
        batch.drop_constraint("fk_bank_ai_rule_drafts_ai_rule_id", type_="foreignkey")
        batch.drop_column("ai_rule_id")
    op.drop_index("ix_bank_ai_rule_application_items_financial_transaction_id", table_name="bank_ai_rule_application_items")
    op.drop_index("ix_bank_ai_rule_application_items_application_id", table_name="bank_ai_rule_application_items")
    op.drop_table("bank_ai_rule_application_items")
    op.drop_index("ix_bank_ai_rule_applications_rule_id", table_name="bank_ai_rule_applications")
    op.drop_table("bank_ai_rule_applications")
    op.drop_index("ix_bank_ai_rule_versions_rule_id", table_name="bank_ai_rule_versions")
    op.drop_table("bank_ai_rule_versions")
    op.drop_table("bank_ai_rules")
