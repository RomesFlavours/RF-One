"""add stable evidence identity for historical instrument candidates

Revision ID: b31e7c0d9a54
Revises: a9e6d3c71f24
Create Date: 2026-09-23

BANK_HISTORICAL_CHECKPOINT_AND_CANDIDATE_IDEMPOTENCY_001.

Purely ADDITIVE. One new table, nothing dropped, nothing rewritten, no
existing row touched and no row inserted. `down_revision` is the actual
single Alembic head observed at the time of writing (`a9e6d3c71f24`),
confirmed through `ScriptDirectory.get_heads()`. No earlier migration is
edited.

Why
---
`historical_source.record_candidate` stored a candidate's evidence as a
free-text summary plus an `occurrence_count` that every call INCREMENTED.
Nothing remembered WHICH evidence had already been counted, so processing
the same raw rows twice doubled the count. The generic persistence
function could not be made idempotent without a stable identity for each
piece of evidence, and the candidate row has nowhere to keep a set.

`bank_historical_instrument_candidate_evidence` is that set: one row per
distinct piece of evidence, unique on (candidate_id, evidence_key). The
candidate's `occurrence_count` and first/last dates become a deterministic
function of it. Existing candidate rows are not modified here; the next
discovery run attaches their evidence, and because the figures are
recomputed from the same raw rows they come out unchanged.

No full account or card number is stored: the evidence points at raw and
canonical rows by id.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "b31e7c0d9a54"
down_revision: str | None = "a9e6d3c71f24"
branch_labels: str | None = None
depends_on: str | None = None

TABLE = "bank_historical_instrument_candidate_evidence"
INDEX = "ix_bank_historical_instrument_candidate_evidence_candidate_id"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "candidate_id", sa.Integer(),
            sa.ForeignKey("bank_historical_instrument_candidates.id"), nullable=False,
        ),
        sa.Column("evidence_key", sa.String(length=128), nullable=False),
        sa.Column("evidence_kind", sa.String(length=48), nullable=False),
        sa.Column(
            "raw_bank_transaction_id", sa.Integer(),
            sa.ForeignKey("raw_bank_transactions.id"), nullable=True,
        ),
        sa.Column(
            "financial_transaction_id", sa.Integer(),
            sa.ForeignKey("financial_transactions.id"), nullable=True,
        ),
        sa.Column("first_observed_date", sa.Date(), nullable=True),
        sa.Column("last_observed_date", sa.Date(), nullable=True),
        sa.Column("occurrences", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("candidate_id", "evidence_key", name="uq_bhice_candidate_evidence"),
        sa.CheckConstraint("occurrences >= 1", name="ck_bhice_occurrences_positive"),
    )
    op.create_index(INDEX, TABLE, ["candidate_id"])


def downgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_table(TABLE)
