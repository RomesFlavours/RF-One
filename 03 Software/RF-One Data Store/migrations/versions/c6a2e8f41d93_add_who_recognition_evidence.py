"""add WHO recognition evidence and counterparty aliases

Revision ID: c6a2e8f41d93
Revises: b31e7c0d9a54
Create Date: 2026-09-23

BANK_HISTORICAL_WHO_RECOGNITION_001.

Purely ADDITIVE. Two new tables, nothing dropped, nothing rewritten, no
existing row touched and no row inserted. `down_revision` is the actual
single Alembic head observed at the time of writing (`b31e7c0d9a54`). No
earlier migration is edited.

Why two new tables rather than the existing decision row
--------------------------------------------------------
RF-One already records a per-transaction decision in
`bank_transaction_explanations`, and that row may carry a WHO
(`occurrence_id`) with no WHY. It cannot be used for historical WHO
recognition, for two reasons written into the existing design:

* creating a decision row repoints `financial_transactions.explanation_id`
  at it (Phase 4B Decision 6), so recording a WHO would modify every
  canonical transaction it touches;
* a decision row is the reconciliation DECISION — what the WHY/WHAT review
  and the export read. Recognition is an earlier, separate fact: what the
  bank's own text proves about the counterparty. Recording it as a decision
  would present 12,678 historical rows as reviewed.

`bank_recognition_rules` cannot hold the recognizers either: a rule maps
one fixed pattern to one fixed WHO and requires a WHY
(`transaction_reason_id NOT NULL`). A generic parser — "the recipient is
the text between `Zelle payment to` and the bank's reference" — yields a
different WHO per transaction and has no WHY at all.

1. `bank_who_recognitions` — one row per (transaction, recognizer
   version): the tier (DETERMINISTIC / PROPOSED / UNRESOLVED / STRUCTURAL),
   the family and parser that decided, the name the text supplied, the
   resulting `bank_occurrences` row when the WHO is deterministic, the
   internal instrument or legal entity when the counterparty is RF-One
   itself, and the evidence. It references the transaction and never
   writes to it.

2. `bank_occurrence_aliases` — every raw name a WHO was recognised from,
   preserved as supplied, so one counterparty can carry many source
   spellings without any history being rewritten.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "c6a2e8f41d93"
down_revision: str | None = "b31e7c0d9a54"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "bank_occurrence_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("occurrence_id", sa.Integer(), sa.ForeignKey("bank_occurrences.id"),
                  nullable=False),
        sa.Column("alias_text", sa.String(length=255), nullable=False),
        sa.Column("alias_key", sa.String(length=255), nullable=False),
        sa.Column("source_family", sa.String(length=48), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="PARSER"),
        sa.Column("first_financial_transaction_id", sa.Integer(),
                  sa.ForeignKey("financial_transactions.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("occurrence_id", "alias_text", "source_family",
                            name="uq_bank_occurrence_alias"),
        sa.CheckConstraint("source IN ('PARSER', 'HUMAN')", name="ck_bank_occurrence_alias_source"),
    )
    op.create_index("ix_bank_occurrence_aliases_occurrence_id", "bank_occurrence_aliases",
                    ["occurrence_id"])
    op.create_index("ix_bank_occurrence_aliases_alias_key", "bank_occurrence_aliases",
                    ["alias_key"])

    op.create_table(
        "bank_who_recognitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("financial_transaction_id", sa.Integer(),
                  sa.ForeignKey("financial_transactions.id"), nullable=False),
        sa.Column("recognizer_version", sa.String(length=32), nullable=False),
        sa.Column("tier", sa.String(length=16), nullable=False),
        sa.Column("family", sa.String(length=48), nullable=False),
        sa.Column("parser_code", sa.String(length=64), nullable=False),
        sa.Column("extracted_name", sa.String(length=255), nullable=True),
        sa.Column("proposed_name", sa.String(length=255), nullable=True),
        sa.Column("occurrence_id", sa.Integer(), sa.ForeignKey("bank_occurrences.id"),
                  nullable=True),
        sa.Column("internal_payment_instrument_id", sa.Integer(),
                  sa.ForeignKey("payment_instruments.id"), nullable=True),
        sa.Column("internal_legal_entity_id", sa.Integer(), sa.ForeignKey("legal_entities.id"),
                  nullable=True),
        sa.Column("referenced_last_four", sa.String(length=4), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("financial_transaction_id", "recognizer_version",
                            name="uq_bank_who_recognition_version"),
        sa.CheckConstraint(
            "tier IN ('DETERMINISTIC', 'PROPOSED', 'UNRESOLVED', 'STRUCTURAL')",
            name="ck_bank_who_recognition_tier",
        ),
        # A DETERMINISTIC WHO always names its counterparty; nothing else may.
        sa.CheckConstraint(
            "(tier = 'DETERMINISTIC') = (occurrence_id IS NOT NULL)",
            name="ck_bank_who_recognition_occurrence",
        ),
    )
    op.create_index("ix_bank_who_recognitions_financial_transaction_id", "bank_who_recognitions",
                    ["financial_transaction_id"])
    op.create_index("ix_bank_who_recognitions_occurrence_id", "bank_who_recognitions",
                    ["occurrence_id"])


def downgrade() -> None:
    op.drop_index("ix_bank_who_recognitions_occurrence_id", table_name="bank_who_recognitions")
    op.drop_index("ix_bank_who_recognitions_financial_transaction_id",
                  table_name="bank_who_recognitions")
    op.drop_table("bank_who_recognitions")
    op.drop_index("ix_bank_occurrence_aliases_alias_key", table_name="bank_occurrence_aliases")
    op.drop_index("ix_bank_occurrence_aliases_occurrence_id", table_name="bank_occurrence_aliases")
    op.drop_table("bank_occurrence_aliases")
