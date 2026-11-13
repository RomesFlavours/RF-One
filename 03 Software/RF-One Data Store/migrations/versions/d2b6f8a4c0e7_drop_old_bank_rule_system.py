"""Drop the old (non-AI) Bank rule system (BANK_OLD_RULES_REMOVAL_001)

Revision ID: d2b6f8a4c0e7
Revises: a3c7e5b9d1f4
Create Date: 2026-10-14

Since BANK_RULES_RESET_001 (2026-10-12) Bank classifies only through AI Rules and by a person. The old rule
system's tables were emptied by that reset and nothing writes them any more; this revision removes them:

  * bank_recognition_rules        — learned / WHO Rule recognition rules
  * bank_who_recognitions         — structural WHO recognition (who-v1)
  * bank_reconciliation_standards — Reconciliation Standards
  * bank_general_rules            — General Rules
  * bank_why_rules                — WHY rules
  * bank_pattern_suggestions      — Classification Learning suggestions
  * bank_learning_runs            — Classification Learning runs

and, with them, the columns of the live tables that could only point at them:

  * bank_transaction_explanations.recognition_rule_id
  * bank_transaction_explanations.reconciliation_standard_id
  * bank_transaction_allocations.reconciliation_standard_id

`accounting_destination_source` loses its STANDARD value (WHY | TRANSACTION remain) and the Standard lineage
CHECK goes with the column it tied.

It also drops `bank_occurrences.manual_only` (BANK_WHO_MANUAL_ONLY_001): the flag only kept a WHO out of the old
WHO Rules and Classification Learning; neither the AI rules nor manual reconciliation read it (Product Owner
decision, 2026-10-14).

The one row a migration itself installed in these tables — the General Rule seeded by `f4a8c2d6e9b3`
("Chase ACH — ORIG CO NAME"), present on every fresh database — is removed first, but only while it is exactly
as seeded (same markers, never applied, created by no one); BANK_RULES_RESET_001 already removed it from the
working database. Downgrade does not seed it back: the tables return empty, as after BANK_RULES_RESET_001.

Destroys nothing else: the upgrade REFUSES, before changing anything, while any of the seven tables holds a row, while
any of the three columns holds a value, while any row says STANDARD, or while any WHO is Manual Only. Every other row of the two live tables is
copied unchanged (SQLite batch rebuild, which keeps every named CHECK; PostgreSQL alters in place).

Downgrade recreates the seven tables EMPTY, the three columns NULL and `manual_only` false, with the constraints and indexes they had
at a3c7e5b9d1f4. What the tables held before BANK_RULES_RESET_001 is not part of this revision.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd2b6f8a4c0e7'
down_revision: Union[str, Sequence[str], None] = 'a3c7e5b9d1f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EXPLANATIONS = "bank_transaction_explanations"
ALLOCATIONS = "bank_transaction_allocations"
TARGETS = ((EXPLANATIONS, "bte"), (ALLOCATIONS, "bta"))

# Children before parents, so every drop is free of foreign keys.
OLD_TABLES = (
    "bank_pattern_suggestions",
    "bank_learning_runs",
    "bank_why_rules",
    "bank_general_rules",
    "bank_who_recognitions",
    "bank_reconciliation_standards",
    "bank_recognition_rules",
)

OLD_SOURCE_CHECK = "accounting_destination_source IN ('WHY', 'TRANSACTION', 'STANDARD')"
NEW_SOURCE_CHECK = "accounting_destination_source IN ('WHY', 'TRANSACTION')"
LINEAGE_CHECK = (
    "(accounting_destination_source = 'STANDARD' AND reconciliation_standard_id IS NOT NULL) OR "
    "(accounting_destination_source <> 'STANDARD' AND reconciliation_standard_id IS NULL)"
)


# The General Rule `f4a8c2d6e9b3` seeds (its CHASE_RULE, copied here: a migration never imports another).
SEEDED_GENERAL_RULE = {"name": "Chase ACH — ORIG CO NAME", "source_field": "DESCRIPTION",
                       "start_marker": "ORIG CO NAME:", "end_marker": "ORIG ID:", "status": "ACTIVE"}


def _remove_untouched_seed(bind) -> None:
    bind.execute(sa.text(
        "DELETE FROM bank_general_rules WHERE name = :name AND source_field = :source_field "
        "AND start_marker = :start_marker AND end_marker = :end_marker AND status = :status "
        "AND last_applied_at IS NULL AND created_by_account_id IS NULL"), SEEDED_GENERAL_RULE)


def _refuse_if_not_empty(bind) -> None:
    """Every fact this revision would remove must already be absent."""
    problems = []
    for table in OLD_TABLES:
        rows = bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar()
        if rows:
            problems.append(f"{table} holds {rows} row(s)")
    for table, column in ((EXPLANATIONS, "recognition_rule_id"), (EXPLANATIONS, "reconciliation_standard_id"),
                          (ALLOCATIONS, "reconciliation_standard_id")):
        rows = bind.execute(sa.text(f"SELECT COUNT(*) FROM {table} WHERE {column} IS NOT NULL")).scalar()
        if rows:
            problems.append(f"{table}.{column} is set on {rows} row(s)")
    for table, _short in TARGETS:
        rows = bind.execute(sa.text(
            f"SELECT COUNT(*) FROM {table} WHERE accounting_destination_source = 'STANDARD'")).scalar()
        if rows:
            problems.append(f"{table} has {rows} row(s) whose destination came from a Standard")
    manual = bind.execute(sa.text("SELECT COUNT(*) FROM bank_occurrences WHERE manual_only")).scalar()
    if manual:
        problems.append(f"{manual} WHO are Manual Only")
    if problems:
        raise RuntimeError(
            "The old Bank rule system still holds data, so nothing was changed: " + "; ".join(problems)
            + ". Its tables are dropped only once BANK_RULES_RESET_001 has emptied them."
        )


def upgrade() -> None:
    # BANK_REINSTALL_001 — on a database where Bank was removed (84354dc654ce, RDS on 2026-10-14) there is nothing
    # to change: the reinstall revision c8e4b2a6f0d1 creates the current Bank schema there.
    if "bank_transaction_explanations" not in sa.inspect(op.get_bind()).get_table_names():
        return
    bind = op.get_bind()
    _remove_untouched_seed(bind)
    _refuse_if_not_empty(bind)
    is_sqlite = op.get_context().dialect.name == "sqlite"

    for table, short in TARGETS:
        op.drop_index(f"ix_{short}_reconciliation_standard_id", table_name=table)
        if is_sqlite:
            with op.batch_alter_table(table, schema=None, recreate="always") as batch_op:
                batch_op.drop_constraint(f"ck_{short}_standard_lineage", type_="check")
                batch_op.drop_constraint(f"ck_{short}_destination_source", type_="check")
                batch_op.drop_constraint(f"fk_{short}_reconciliation_standard_id", type_="foreignkey")
                batch_op.drop_column("reconciliation_standard_id")
                if table == EXPLANATIONS:
                    # Its foreign key is unnamed: the rebuild leaves out every
                    # constraint on a column that no longer exists.
                    batch_op.drop_column("recognition_rule_id")
                batch_op.create_check_constraint(f"ck_{short}_destination_source", NEW_SOURCE_CHECK)
        else:
            op.drop_constraint(f"ck_{short}_standard_lineage", table, type_="check")
            op.drop_constraint(f"ck_{short}_destination_source", table, type_="check")
            op.drop_constraint(f"fk_{short}_reconciliation_standard_id", table, type_="foreignkey")
            op.drop_column(table, "reconciliation_standard_id")
            if table == EXPLANATIONS:
                op.drop_column(table, "recognition_rule_id")  # drops its foreign key with it
            op.create_check_constraint(f"ck_{short}_destination_source", table, NEW_SOURCE_CHECK)

    for table in OLD_TABLES:
        op.drop_table(table)

    with op.batch_alter_table("bank_occurrences", schema=None) as batch_op:
        batch_op.drop_column("manual_only")


def downgrade() -> None:
    with op.batch_alter_table("bank_occurrences", schema=None) as batch_op:
        batch_op.add_column(sa.Column("manual_only", sa.Boolean(), nullable=False, server_default=sa.text("0")))
    _create_old_tables()
    is_sqlite = op.get_context().dialect.name == "sqlite"
    for table, short in TARGETS:
        if is_sqlite:
            with op.batch_alter_table(table, schema=None, recreate="always") as batch_op:
                batch_op.drop_constraint(f"ck_{short}_destination_source", type_="check")
                if table == EXPLANATIONS:
                    batch_op.add_column(sa.Column("recognition_rule_id", sa.Integer(), nullable=True))
                    batch_op.create_foreign_key(
                        "fk_bte_recognition_rule_id", "bank_recognition_rules", ["recognition_rule_id"], ["id"])
                batch_op.add_column(sa.Column("reconciliation_standard_id", sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    f"fk_{short}_reconciliation_standard_id", "bank_reconciliation_standards",
                    ["reconciliation_standard_id"], ["id"])
                batch_op.create_check_constraint(f"ck_{short}_destination_source", OLD_SOURCE_CHECK)
                batch_op.create_check_constraint(f"ck_{short}_standard_lineage", LINEAGE_CHECK)
        else:
            op.drop_constraint(f"ck_{short}_destination_source", table, type_="check")
            if table == EXPLANATIONS:
                op.add_column(table, sa.Column("recognition_rule_id", sa.Integer(), nullable=True))
                op.create_foreign_key(
                    "fk_bte_recognition_rule_id", table, "bank_recognition_rules", ["recognition_rule_id"], ["id"])
            op.add_column(table, sa.Column("reconciliation_standard_id", sa.Integer(), nullable=True))
            op.create_foreign_key(
                f"fk_{short}_reconciliation_standard_id", table, "bank_reconciliation_standards",
                ["reconciliation_standard_id"], ["id"])
            op.create_check_constraint(f"ck_{short}_destination_source", table, OLD_SOURCE_CHECK)
            op.create_check_constraint(f"ck_{short}_standard_lineage", table, LINEAGE_CHECK)
        op.create_index(f"ix_{short}_reconciliation_standard_id", table, ["reconciliation_standard_id"])


def _timestamps(*, updated: bool = True) -> list[sa.Column]:
    columns = [sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]
    if updated:
        columns.append(sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                                 nullable=False))
    return columns


def _create_old_tables() -> None:
    """The seven tables as they were at a3c7e5b9d1f4, empty."""
    op.create_table(
        "bank_recognition_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("match_type", sa.String(32), nullable=False),
        sa.Column("normalized_pattern", sa.Text(), nullable=False),
        sa.Column("payment_instrument_id", sa.Integer(), sa.ForeignKey("payment_instruments.id"), nullable=True),
        sa.Column("direction", sa.String(8), nullable=True),
        sa.Column("occurrence_id", sa.Integer(), sa.ForeignKey("bank_occurrences.id"), nullable=False),
        sa.Column("transaction_reason_id", sa.Integer(), sa.ForeignKey("bank_transaction_reasons.id"),
                  nullable=True),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(16), server_default="ACTIVE", nullable=False),
        sa.Column("auto_apply_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("human_confirmations", sa.Integer(), server_default="0", nullable=False),
        sa.Column("human_contradictions", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_from_transaction_id", sa.Integer(), sa.ForeignKey("financial_transactions.id"),
                  nullable=True),
        *_timestamps(),
        sa.Column("match_field", sa.String(16), server_default="DESCRIPTION", nullable=False),
        sa.Column("determines_purpose", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("literal_pattern", sa.Text(), nullable=True),
        sa.CheckConstraint("NOT determines_purpose OR match_field = 'MEMO'",
                           name="ck_bank_recognition_rule_purpose_scope"),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE', 'NEEDS_REVIEW')", name="ck_bank_recognition_rule_status"),
        sa.CheckConstraint("match_field IN ('DESCRIPTION', 'MEMO')", name="ck_bank_recognition_rule_match_field"),
        sa.CheckConstraint("match_type IN ('EXACT_NORMALIZED_DESCRIPTION', 'CONTAINS_TEXT', 'PREFIX')",
                           name="ck_bank_recognition_rule_match_type"),
        sa.CheckConstraint("direction IS NULL OR direction IN ('DEBIT', 'CREDIT')",
                           name="ck_bank_recognition_rule_direction"),
    )
    op.create_index("ix_bank_recognition_rule_pattern", "bank_recognition_rules", ["normalized_pattern"])
    op.create_index("ix_bank_recognition_rules_occurrence_id", "bank_recognition_rules", ["occurrence_id"])

    op.create_table(
        "bank_reconciliation_standards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("match_type", sa.String(32), nullable=False),
        sa.Column("normalized_pattern", sa.Text(), nullable=False),
        sa.Column("match_field", sa.String(16), server_default="DESCRIPTION", nullable=False),
        sa.Column("payment_instrument_id", sa.Integer(), nullable=True),
        sa.Column("direction", sa.String(8), nullable=True),
        sa.Column("occurrence_id", sa.Integer(), nullable=False),
        sa.Column("transaction_reason_id", sa.Integer(), nullable=False),
        sa.Column("accounting_classification_id", sa.Integer(), nullable=False),
        sa.Column("reporting_entity_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), server_default="ACTIVE", nullable=False),
        sa.Column("approved_by_account_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_from_transaction_id", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("match_type IN ('EXACT_NORMALIZED_DESCRIPTION', 'CONTAINS_TEXT', 'PREFIX')",
                           name="ck_brs_match_type"),
        sa.CheckConstraint("match_field IN ('DESCRIPTION', 'MEMO')", name="ck_brs_match_field"),
        sa.CheckConstraint("direction IS NULL OR direction IN ('DEBIT', 'CREDIT')", name="ck_brs_direction"),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_brs_status"),
        sa.ForeignKeyConstraint(["payment_instrument_id"], ["payment_instruments.id"],
                                name="fk_brs_payment_instrument_id"),
        sa.ForeignKeyConstraint(["occurrence_id"], ["bank_occurrences.id"], name="fk_brs_occurrence_id"),
        sa.ForeignKeyConstraint(["transaction_reason_id"], ["bank_transaction_reasons.id"],
                                name="fk_brs_transaction_reason_id"),
        sa.ForeignKeyConstraint(["accounting_classification_id"], ["bank_accounting_classifications.id"],
                                name="fk_brs_accounting_classification_id"),
        sa.ForeignKeyConstraint(["reporting_entity_id"], ["reporting_entities.id"],
                                name="fk_brs_reporting_entity_id"),
        sa.ForeignKeyConstraint(["approved_by_account_id"], ["rfone_accounts.id"],
                                name="fk_brs_approved_by_account_id"),
        sa.ForeignKeyConstraint(["created_from_transaction_id"], ["financial_transactions.id"],
                                name="fk_brs_created_from_transaction_id"),
    )
    op.create_index("ix_brs_pattern", "bank_reconciliation_standards", ["normalized_pattern"])
    op.create_index("ix_brs_occurrence_id", "bank_reconciliation_standards", ["occurrence_id"])
    op.create_index(
        "ux_brs_active_signature", "bank_reconciliation_standards",
        ["match_type", "normalized_pattern", "match_field", "payment_instrument_id", "direction"],
        unique=True, sqlite_where=sa.text("status = 'ACTIVE'"), postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        "bank_who_recognitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("financial_transaction_id", sa.Integer(), sa.ForeignKey("financial_transactions.id"),
                  nullable=False),
        sa.Column("recognizer_version", sa.String(32), nullable=False),
        sa.Column("tier", sa.String(16), nullable=False),
        sa.Column("family", sa.String(48), nullable=False),
        sa.Column("parser_code", sa.String(64), nullable=False),
        sa.Column("extracted_name", sa.String(255), nullable=True),
        sa.Column("proposed_name", sa.String(255), nullable=True),
        sa.Column("occurrence_id", sa.Integer(), sa.ForeignKey("bank_occurrences.id"), nullable=True),
        sa.Column("internal_payment_instrument_id", sa.Integer(), sa.ForeignKey("payment_instruments.id"),
                  nullable=True),
        sa.Column("internal_legal_entity_id", sa.Integer(), sa.ForeignKey("legal_entities.id"), nullable=True),
        sa.Column("referenced_last_four", sa.String(4), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("financial_transaction_id", "recognizer_version", name="uq_bank_who_recognition_version"),
        sa.CheckConstraint("tier IN ('DETERMINISTIC', 'PROPOSED', 'UNRESOLVED', 'STRUCTURAL')",
                           name="ck_bank_who_recognition_tier"),
        sa.CheckConstraint("(tier = 'DETERMINISTIC') = (occurrence_id IS NOT NULL)",
                           name="ck_bank_who_recognition_occurrence"),
    )
    op.create_index("ix_bank_who_recognitions_financial_transaction_id", "bank_who_recognitions",
                    ["financial_transaction_id"])
    op.create_index("ix_bank_who_recognitions_occurrence_id", "bank_who_recognitions", ["occurrence_id"])

    op.create_table(
        "bank_general_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("source_field", sa.String(16), nullable=False),
        sa.Column("start_marker", sa.String(80), nullable=False),
        sa.Column("end_marker", sa.String(80), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_by_account_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=True),
        sa.Column("last_applied_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("name", name="uq_bank_general_rule_name"),
        sa.CheckConstraint("source_field IN ('DESCRIPTION')", name="ck_bank_general_rule_source_field"),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_bank_general_rule_status"),
    )

    op.create_table(
        "bank_why_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("occurrence_id", sa.Integer(), sa.ForeignKey("bank_occurrences.id"), nullable=False),
        sa.Column("description_contains", sa.String(120), nullable=True),
        sa.Column("direction", sa.String(8), nullable=True),
        sa.Column("instrument_type", sa.String(32), nullable=True),
        sa.Column("transaction_reason_id", sa.Integer(), sa.ForeignKey("bank_transaction_reasons.id"),
                  nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("origin", sa.String(32), nullable=False),
        sa.Column("approved_by_account_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_summary", sa.Text(), nullable=True),
        *_timestamps(updated=False),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_bank_why_rule_status"),
        sa.CheckConstraint("direction IS NULL OR direction IN ('DEBIT', 'CREDIT')", name="ck_bank_why_rule_direction"),
    )
    op.create_index("ix_bank_why_rules_occurrence_id", "bank_why_rules", ["occurrence_id"])

    op.create_table(
        "bank_learning_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("created_by_account_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        *_timestamps(updated=False),
        sa.CheckConstraint("kind IN ('DISCOVERY', 'BACKTEST')", name="ck_bank_learning_run_kind"),
    )

    op.create_table(
        "bank_pattern_suggestions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("pattern_type", sa.String(16), nullable=False),
        sa.Column("determinism", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("proposal", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("evidence_level", sa.String(24), nullable=False),
        sa.Column("previously_rejected", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("rejected_evidence_size", sa.Integer(), nullable=True),
        sa.Column("discovery_run_id", sa.Integer(), sa.ForeignKey("bank_learning_runs.id"), nullable=True),
        sa.Column("decided_by_account_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("routed_to", sa.String(64), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("fingerprint", name="uq_bank_pattern_suggestion_fingerprint"),
        sa.CheckConstraint("pattern_type IN ('STRUCTURAL', 'WHO', 'WHY')", name="ck_bank_pattern_suggestion_type"),
        sa.CheckConstraint("status IN ('SUGGESTED', 'APPROVED', 'REJECTED', 'COVERED')",
                           name="ck_bank_pattern_suggestion_status"),
        sa.CheckConstraint("determinism IN ('DETERMINISTIC', 'PROBABILISTIC')",
                           name="ck_bank_pattern_suggestion_determinism"),
    )
