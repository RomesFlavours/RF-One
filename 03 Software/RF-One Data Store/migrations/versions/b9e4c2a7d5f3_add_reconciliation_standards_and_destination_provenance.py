"""add Reconciliation Standards and accounting-destination provenance
(BANK_RECONCILIATION_STANDARDS_001, Product Owner approved schema)

Revision ID: b9e4c2a7d5f3
Revises: f6c2e8a4b1d7
Create Date: 2026-09-30 12:00:00.000000

Three approved changes, one coherent revision. No existing row is
reinterpreted and no lineage is fabricated.

1. `bank_reconciliation_standards` — HUMAN-APPROVED reconciliation
   knowledge: a recognition signature (the same dimensions a
   `BankRecognitionRule` uses) and its complete approved result — WHO, WHY,
   accounting destination, For Whom — with state and audit. Deliberately a
   separate table: `BankRecognitionRule` stays WHO-only and its
   purpose-scope CHECK (BANK_WHO_WHY_INVARIANT_001) is untouched.

2. `reconciliation_standard_id` on `bank_transaction_explanations` and
   `bank_transaction_allocations`: the exact Standard that produced an
   Automatic decision/allocation. Existing rows: NULL.

3. `accounting_destination_source` on the same two tables: WHY (derived from
   the WHY's mapping), TRANSACTION (chosen by a human for this transaction
   only) or STANDARD (supplied by a Standard). Existing rows: WHY — every
   destination recorded so far was derived from the WHY under the previous
   invariant.

A CHECK ties the two new columns together on each table: STANDARD exactly
when a Standard is named, so provenance and lineage can never contradict.

Runs on SQLite (batch rebuild, which keeps every named CHECK) and PostgreSQL.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9e4c2a7d5f3'
down_revision: Union[str, Sequence[str], None] = 'f6c2e8a4b1d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STANDARDS = "bank_reconciliation_standards"
TARGETS = (
    ("bank_transaction_explanations", "bte"),
    ("bank_transaction_allocations", "bta"),
)
SOURCE_CHECK = "accounting_destination_source IN ('WHY', 'TRANSACTION', 'STANDARD')"
LINEAGE_CHECK = (
    "(accounting_destination_source = 'STANDARD' AND reconciliation_standard_id IS NOT NULL) OR "
    "(accounting_destination_source <> 'STANDARD' AND reconciliation_standard_id IS NULL)"
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        STANDARDS,
        sa.Column("id", sa.Integer(), nullable=False),
        # --- recognition signature
        sa.Column("match_type", sa.String(length=32), nullable=False),
        sa.Column("normalized_pattern", sa.Text(), nullable=False),
        sa.Column("match_field", sa.String(length=16), server_default="DESCRIPTION", nullable=False),
        sa.Column("payment_instrument_id", sa.Integer(), nullable=True),
        sa.Column("direction", sa.String(length=8), nullable=True),
        # --- approved result
        sa.Column("occurrence_id", sa.Integer(), nullable=False),
        sa.Column("transaction_reason_id", sa.Integer(), nullable=False),
        sa.Column("accounting_classification_id", sa.Integer(), nullable=False),
        sa.Column("reporting_entity_id", sa.Integer(), nullable=False),
        # --- state and audit
        sa.Column("status", sa.String(length=16), server_default="ACTIVE", nullable=False),
        sa.Column("approved_by_account_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_from_transaction_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "match_type IN ('EXACT_NORMALIZED_DESCRIPTION', 'CONTAINS_TEXT', 'PREFIX')",
            name="ck_brs_match_type",
        ),
        sa.CheckConstraint("match_field IN ('DESCRIPTION', 'MEMO')", name="ck_brs_match_field"),
        sa.CheckConstraint("direction IS NULL OR direction IN ('DEBIT', 'CREDIT')", name="ck_brs_direction"),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_brs_status"),
        sa.ForeignKeyConstraint(["payment_instrument_id"], ["payment_instruments.id"], name="fk_brs_payment_instrument_id"),
        sa.ForeignKeyConstraint(["occurrence_id"], ["bank_occurrences.id"], name="fk_brs_occurrence_id"),
        sa.ForeignKeyConstraint(["transaction_reason_id"], ["bank_transaction_reasons.id"], name="fk_brs_transaction_reason_id"),
        sa.ForeignKeyConstraint(["accounting_classification_id"], ["bank_accounting_classifications.id"],
                                name="fk_brs_accounting_classification_id"),
        sa.ForeignKeyConstraint(["reporting_entity_id"], ["reporting_entities.id"], name="fk_brs_reporting_entity_id"),
        sa.ForeignKeyConstraint(["approved_by_account_id"], ["rfone_accounts.id"], name="fk_brs_approved_by_account_id"),
        sa.ForeignKeyConstraint(["created_from_transaction_id"], ["financial_transactions.id"],
                                name="fk_brs_created_from_transaction_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_brs_pattern", STANDARDS, ["normalized_pattern"])
    op.create_index("ix_brs_occurrence_id", STANDARDS, ["occurrence_id"])
    # One ACTIVE Standard per canonical signature: two indistinguishable
    # Standards can never both be active.
    op.create_index(
        "ux_brs_active_signature", STANDARDS,
        ["match_type", "normalized_pattern", "match_field", "payment_instrument_id", "direction"],
        unique=True,
        sqlite_where=sa.text("status = 'ACTIVE'"),
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    is_sqlite = op.get_context().dialect.name == "sqlite"
    for table, short in TARGETS:
        if is_sqlite:
            with op.batch_alter_table(table, schema=None, recreate="always") as batch_op:
                batch_op.add_column(sa.Column(
                    "accounting_destination_source", sa.String(length=16),
                    server_default="WHY", nullable=False))
                batch_op.add_column(sa.Column("reconciliation_standard_id", sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    f"fk_{short}_reconciliation_standard_id", STANDARDS,
                    ["reconciliation_standard_id"], ["id"])
                batch_op.create_check_constraint(f"ck_{short}_destination_source", SOURCE_CHECK)
                batch_op.create_check_constraint(f"ck_{short}_standard_lineage", LINEAGE_CHECK)
        else:
            op.add_column(table, sa.Column(
                "accounting_destination_source", sa.String(length=16),
                server_default="WHY", nullable=False))
            op.add_column(table, sa.Column("reconciliation_standard_id", sa.Integer(), nullable=True))
            op.create_foreign_key(
                f"fk_{short}_reconciliation_standard_id", table, STANDARDS,
                ["reconciliation_standard_id"], ["id"])
            op.create_check_constraint(f"ck_{short}_destination_source", table, SOURCE_CHECK)
            op.create_check_constraint(f"ck_{short}_standard_lineage", table, LINEAGE_CHECK)
        op.create_index(f"ix_{short}_reconciliation_standard_id", table, ["reconciliation_standard_id"])


def downgrade() -> None:
    """Downgrade schema."""
    is_sqlite = op.get_context().dialect.name == "sqlite"
    for table, short in TARGETS:
        op.drop_index(f"ix_{short}_reconciliation_standard_id", table_name=table)
        if is_sqlite:
            with op.batch_alter_table(table, schema=None, recreate="always") as batch_op:
                batch_op.drop_constraint(f"ck_{short}_standard_lineage", type_="check")
                batch_op.drop_constraint(f"ck_{short}_destination_source", type_="check")
                batch_op.drop_constraint(f"fk_{short}_reconciliation_standard_id", type_="foreignkey")
                batch_op.drop_column("reconciliation_standard_id")
                batch_op.drop_column("accounting_destination_source")
        else:
            op.drop_constraint(f"ck_{short}_standard_lineage", table, type_="check")
            op.drop_constraint(f"ck_{short}_destination_source", table, type_="check")
            op.drop_constraint(f"fk_{short}_reconciliation_standard_id", table, type_="foreignkey")
            op.drop_column(table, "reconciliation_standard_id")
            op.drop_column(table, "accounting_destination_source")
    op.drop_index("ux_brs_active_signature", table_name=STANDARDS)
    op.drop_index("ix_brs_occurrence_id", table_name=STANDARDS)
    op.drop_index("ix_brs_pattern", table_name=STANDARDS)
    op.drop_table(STANDARDS)
