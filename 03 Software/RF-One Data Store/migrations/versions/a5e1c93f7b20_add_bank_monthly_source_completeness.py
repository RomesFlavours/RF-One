"""add Bank monthly source completeness and Payment Instrument lifecycle

Revision ID: a5e1c93f7b20
Revises: f3c92a5e81d7
Create Date: 2026-09-22

BANK_MONTHLY_SOURCE_COMPLETENESS_001.

Purely ADDITIVE. Nothing is dropped, nothing is rewritten, no existing row
is touched, and no data file is read: this migration creates structure and
stops there. `down_revision` is the actual single Alembic head observed at
the time of writing (`f3c92a5e81d7`, the Tips hypothetical-amount drop),
not an assumed one.

What it adds
------------
1. Four nullable columns on `payment_instruments`, giving the instrument a
   HISTORICAL EFFECTIVE life alongside the CURRENT `status` it already had:

       effective_start_date      NULL means UNKNOWN
       effective_end_date        NULL means UNKNOWN
       lifecycle_end_reason      CLOSED / LOST / REPLACED / OTHER
       replaced_by_instrument_id FK to the SUCCESSOR instrument

   Every existing row keeps NULL in all four, which is the truthful answer:
   RF-One does not know when those real accounts and cards were opened.
   `created_at` is emphatically NOT copied into `effective_start_date` — it
   records when the row was written, a fact about RF-One, not about the
   bank. Backfilling it would manufacture certainty the business does not
   have, which §6 forbids.

2. `bank_monthly_source_periods` — one row per controlled month.

3. `bank_monthly_instrument_coverages` — one row per (month, instrument),
   carrying the expectation verdict, the accepted source file if any, the
   human resolution if any, and the small snapshot that keeps a COMPLETED
   month reconstructable.

Runs unchanged on an empty disposable database, on the current local QA
database, and on AWS RDS through an ordinary `alembic upgrade head`.
SQLite gets `batch_alter_table` for the column additions because it has no
native ALTER for constrained columns.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a5e1c93f7b20"
down_revision: Union[str, Sequence[str], None] = "f3c92a5e81d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- 1. Payment Instrument historical lifecycle --------------------
    with op.batch_alter_table("payment_instruments") as batch:
        batch.add_column(sa.Column("effective_start_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("effective_end_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("lifecycle_end_reason", sa.String(length=16), nullable=True))
        batch.add_column(sa.Column("replaced_by_instrument_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_pi_replaced_by_instrument_id", "payment_instruments",
            ["replaced_by_instrument_id"], ["id"],
        )

    # --- 2. Monthly source-control period ------------------------------
    op.create_table(
        "bank_monthly_source_periods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("period_month", sa.String(length=7), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="OPEN"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_account_id", sa.Integer(), nullable=True),
        sa.Column("audit_log", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("period_month", name="uq_bmsp_period_month"),
        sa.CheckConstraint("status IN ('OPEN', 'INCOMPLETE', 'COMPLETE')", name="ck_bmsp_status"),
        sa.ForeignKeyConstraint(["completed_by_account_id"], ["rfone_accounts.id"]),
    )

    # --- 3. Per-instrument coverage within a month ---------------------
    op.create_table(
        "bank_monthly_instrument_coverages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("period_id", sa.Integer(), nullable=False),
        sa.Column("payment_instrument_id", sa.Integer(), nullable=False),
        sa.Column("expectation", sa.String(length=32), nullable=False),
        sa.Column("expectation_basis", sa.Text(), nullable=True),
        sa.Column("import_batch_id", sa.Integer(), nullable=True),
        sa.Column("resolution", sa.String(length=32), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolution_effective_date", sa.Date(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_account_id", sa.Integer(), nullable=True),
        sa.Column("instrument_display_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("institution_snapshot", sa.String(length=64), nullable=True),
        sa.Column("last_four_snapshot", sa.String(length=4), nullable=True),
        sa.Column("instrument_status_snapshot", sa.String(length=16), nullable=True),
        sa.Column("lifecycle_label_snapshot", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("period_id", "payment_instrument_id", name="uq_bmic_period_instrument"),
        sa.CheckConstraint(
            "expectation IN ('EXPECTED', 'NOT_EXPECTED', 'NEEDS_HUMAN_CONFIRMATION')",
            name="ck_bmic_expectation",
        ),
        sa.CheckConstraint(
            "resolution IS NULL OR resolution IN ("
            "'NO_ACTIVITY', 'CLOSED', 'LOST', 'REPLACED', 'OTHER', "
            "'SOURCE_FILE_MISSING', 'NOT_EXPECTED_CONFIRMED')",
            name="ck_bmic_resolution",
        ),
        sa.ForeignKeyConstraint(["period_id"], ["bank_monthly_source_periods.id"]),
        sa.ForeignKeyConstraint(["payment_instrument_id"], ["payment_instruments.id"]),
        sa.ForeignKeyConstraint(["import_batch_id"], ["bank_import_batches.id"]),
        sa.ForeignKeyConstraint(["resolved_by_account_id"], ["rfone_accounts.id"]),
    )
    op.create_index("ix_bmic_period_id", "bank_monthly_instrument_coverages", ["period_id"])
    op.create_index(
        "ix_bmic_payment_instrument_id", "bank_monthly_instrument_coverages",
        ["payment_instrument_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_bmic_payment_instrument_id", table_name="bank_monthly_instrument_coverages")
    op.drop_index("ix_bmic_period_id", table_name="bank_monthly_instrument_coverages")
    op.drop_table("bank_monthly_instrument_coverages")
    op.drop_table("bank_monthly_source_periods")
    with op.batch_alter_table("payment_instruments") as batch:
        batch.drop_constraint("fk_pi_replaced_by_instrument_id", type_="foreignkey")
        batch.drop_column("replaced_by_instrument_id")
        batch.drop_column("lifecycle_end_reason")
        batch.drop_column("effective_end_date")
        batch.drop_column("effective_start_date")
