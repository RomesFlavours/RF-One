"""add the historical source control foundation

Revision ID: c8f1a3e04d97
Revises: b7d4e92a1c58
Create Date: 2026-09-23

BANK_HISTORICAL_SOURCE_CONTROL_FOUNDATION_001.

Purely ADDITIVE. Two new tables, nothing dropped, nothing rewritten, no
existing row touched, no data file read, and no row inserted.
`down_revision` is the actual single Alembic head observed at the time of
writing (`b7d4e92a1c58`), confirmed through `ScriptDirectory.get_heads()`.
Migration `b7d4e92a1c58` itself is NOT edited.

Why two tables, and why the existing ones could not carry these facts
---------------------------------------------------------------------

1. `bank_instrument_identity_audits`

   RF-One already audits instrument decisions in
   `bank_instrument_assignment_audits`, but that table answers a different
   question and its own CHECK constraint says so:

       scope IN ('BATCH', 'TRANSACTION')
       AND the matching import_batch_id / financial_transaction_id
           IS NOT NULL

   It records "which instrument was this SOURCE or this TRANSACTION
   reassigned to". Correcting an instrument's OWN IDENTITY — its last
   four, its external identifier, its display name — is not an
   assignment, has no batch and no transaction to point at, and would
   violate that constraint. The fact genuinely has nowhere to live.

   So this table records one row per corrected field: what it was, what it
   became, why, on what evidence, who did it and when. It never changes
   the instrument itself; it is the memory of why the instrument now reads
   the way it does.

2. `bank_historical_instrument_candidates`

   An account or card that the EVIDENCE names but the registry does not
   contain. Discovered either directly (a source file whose identity
   matches no instrument) or indirectly (a transaction referring to an
   account RF-One has never been told about).

   `BankMonthlyInstrumentCoverage` already carries the human-resolution
   vocabulary, but every one of its rows is anchored to a
   `payment_instrument_id` that is NOT NULL. A candidate is, by
   definition, an identity with no instrument row, so it cannot be
   represented there without first inventing the very instrument the
   human has not yet confirmed exists.

   The resolution vocabulary is REUSED rather than reinvented: SOURCE FILE
   MISSING, CLOSED / LOST / REPLACED / OTHER and a confirmation that the
   identity is genuinely not ours, plus the CONFIRMED outcome that
   promotes a candidate into a real `PaymentInstrument`. Absence alone
   selects none of them, which is why `resolution` is nullable and stays
   NULL until a person decides.

Neither table stores a full account or card number. `last_four` is four
characters by constraint, and the free-text columns are for the operator's
own words and for file-level provenance.

NOTHING IS SEEDED. Both tables are created empty. No candidate is inferred
and no audit row is manufactured for a correction that has not happened.

Runs unchanged on an empty disposable database, on the local golden
database, and on AWS RDS through an ordinary `alembic upgrade head`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c8f1a3e04d97"
down_revision: str | None = "b7d4e92a1c58"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "bank_instrument_identity_audits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "payment_instrument_id", sa.Integer(),
            sa.ForeignKey("payment_instruments.id"), nullable=False,
        ),
        sa.Column("field_name", sa.String(length=64), nullable=False),
        sa.Column("previous_value", sa.String(length=255), nullable=True),
        sa.Column("new_value", sa.String(length=255), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source_evidence", sa.Text(), nullable=False),
        sa.Column(
            "changed_by_account_id", sa.Integer(),
            sa.ForeignKey("rfone_accounts.id"), nullable=True,
        ),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_biia_payment_instrument_id",
        "bank_instrument_identity_audits", ["payment_instrument_id"],
    )

    op.create_table(
        "bank_historical_instrument_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("institution", sa.String(length=64), nullable=True),
        sa.Column("last_four", sa.String(length=4), nullable=False),
        sa.Column("discovery", sa.String(length=48), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("first_seen_date", sa.Date(), nullable=True),
        sa.Column("last_seen_date", sa.Date(), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resolution", sa.String(length=40), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolution_effective_date", sa.Date(), nullable=True),
        sa.Column(
            "resolved_payment_instrument_id", sa.Integer(),
            sa.ForeignKey("payment_instruments.id"), nullable=True,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "resolved_by_account_id", sa.Integer(),
            sa.ForeignKey("rfone_accounts.id"), nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("institution", "last_four", name="uq_bhic_identity"),
        sa.CheckConstraint("length(last_four) = 4", name="ck_bhic_last_four"),
        sa.CheckConstraint(
            "discovery IN ('DIRECT_SOURCE', 'INDIRECT_REFERENCE')",
            name="ck_bhic_discovery",
        ),
        sa.CheckConstraint(
            "resolution IS NULL OR resolution IN "
            "('CONFIRMED_INSTRUMENT', 'SOURCE_FILE_MISSING', 'CLOSED', 'LOST', "
            "'REPLACED', 'OTHER', 'NOT_OUR_INSTRUMENT')",
            name="ck_bhic_resolution",
        ),
    )


def downgrade() -> None:
    op.drop_table("bank_historical_instrument_candidates")
    op.drop_index(
        "ix_biia_payment_instrument_id", table_name="bank_instrument_identity_audits")
    op.drop_table("bank_instrument_identity_audits")
