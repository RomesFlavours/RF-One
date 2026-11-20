"""add the economic allocation foundation

Revision ID: d3a7c9f15b28
Revises: c8f1a3e04d97
Create Date: 2026-09-23

BANK_ECONOMIC_ALLOCATION_FOUNDATION_001.

Purely ADDITIVE. Three new tables, nothing dropped, nothing rewritten, no
existing column altered, no existing row touched, no data file read and no
row inserted. `down_revision` is the actual single Alembic head observed at
the time of writing (`c8f1a3e04d97`), confirmed through `alembic heads`.
Migrations `b7d4e92a1c58` and `c8f1a3e04d97` are NOT edited.

What these tables are for, and why existing ones could not carry the fact
----------------------------------------------------------------------

RF-One already records, per bank movement, WHO was involved, WHY the
movement happened and WHICH canonical account it resolves to
(`bank_transaction_explanations`). What it has never been able to record is
FOR WHOM the economic result belongs, and that is a different question from
who paid.

A card belonging to RF Gelati can pay $500 of material destined for RF
Mount Dora. `FinancialTransaction` correctly attributes the CASH to RF
Gelati's settlement account. The COST belongs to RF Mount Dora. Nothing in
the existing schema can say that:

* `FinancialTransaction.classification` and the current
  `BankTransactionExplanation` both describe the movement as a whole, one
  accounting destination per transaction. A $2,000 payment covering food,
  packaging and supplies has three economic meanings and today can only be
  given one.
* The Legal Entity derived by `bank_reconciliation.card_configuration.
  legal_entity_for` is, by that module's own docstring, the Company of the
  SETTLEMENT ACCOUNT — the payer. It is the right answer to the question it
  asks, and the wrong answer to "whose P&L is this".
* Splitting the movement into several `FinancialTransaction` rows would
  manufacture bank transactions that never happened and would break
  reconciliation, deduplication and source provenance, all of which are
  anchored to the real movement.

1. `reporting_groups`

   The economic reporting perimeter several entities consolidate into.
   Deliberately not called `Corporate`: `00 Core/Corporate.md` defines
   Corporate as the highest organizational Entity with governance,
   ownership and strategy responsibilities, and `LegalEntity`'s docstring
   records the standing decision that no Corporate table is persisted in
   this schema. This is the narrower reporting concept only.

2. `reporting_entities`

   FOR WHOM an economic result is reported. `LEGAL` rows stand for exactly
   one real `LegalEntity`; `VIRTUAL` rows stand for a management entity
   that is NOT a legal organization and, by CHECK constraint, cannot point
   at one. `LegalEntity` therefore keeps its single meaning — a genuine
   juridical entity — and a virtual entity never becomes a fake LLC.

3. `bank_transaction_allocations`

   The economic meaning of a bank movement, 1..N rows per transaction,
   summing exactly to the parent amount in the parent's own sign
   convention. The P&L is read from these rows and never from the parent,
   which is what makes double counting structurally impossible rather than
   something a report must remember to avoid.

NOTHING IS SEEDED. All three tables are created empty. No reporting group,
no reporting entity and no allocation is invented — the real perimeter is a
Product Owner configuration decision. No account code is created either:
the intercompany consequence posts to `1610 Due From Related Parties` and
`2710 Due To Related Parties`, which already exist in the canonical
catalog.

Runs unchanged on an empty disposable database, on the local golden
database, and on AWS RDS through an ordinary `alembic upgrade head`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "d3a7c9f15b28"
down_revision: str | None = "c8f1a3e04d97"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "reporting_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="ACTIVE",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("code", name="uq_reporting_group_code"),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_reporting_group_status"),
    )

    op.create_table(
        "reporting_entities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("entity_type", sa.String(length=16), nullable=False),
        sa.Column(
            "legal_entity_id", sa.Integer(),
            sa.ForeignKey("legal_entities.id"), nullable=True,
        ),
        sa.Column(
            "reporting_group_id", sa.Integer(),
            sa.ForeignKey("reporting_groups.id"), nullable=True,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="ACTIVE",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("code", name="uq_reporting_entity_code"),
        sa.CheckConstraint(
            "entity_type IN ('LEGAL', 'VIRTUAL')", name="ck_reporting_entity_type",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'INACTIVE')", name="ck_reporting_entity_status",
        ),
        # A LEGAL reporting entity names exactly one real LegalEntity; a
        # VIRTUAL one names none. Structural, so no code path can produce a
        # virtual entity wearing an LLC's identity.
        sa.CheckConstraint(
            "(entity_type = 'LEGAL' AND legal_entity_id IS NOT NULL) OR "
            "(entity_type = 'VIRTUAL' AND legal_entity_id IS NULL)",
            name="ck_reporting_entity_type_legal_entity",
        ),
    )
    # One LegalEntity is represented by at most one LEGAL reporting entity,
    # so a consolidated total can never contain the same LLC twice. Partial,
    # because unlimited VIRTUAL rows legitimately carry NULL here.
    op.create_index(
        "ux_reporting_entity_legal_entity",
        "reporting_entities", ["legal_entity_id"],
        unique=True,
        sqlite_where=sa.text("legal_entity_id IS NOT NULL"),
        postgresql_where=sa.text("legal_entity_id IS NOT NULL"),
    )
    op.create_index(
        "ix_reporting_entity_group_id", "reporting_entities", ["reporting_group_id"],
    )

    op.create_table(
        "bank_transaction_allocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "financial_transaction_id", sa.Integer(),
            sa.ForeignKey("financial_transactions.id"), nullable=False,
        ),
        sa.Column("allocation_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column(
            "reporting_entity_id", sa.Integer(),
            sa.ForeignKey("reporting_entities.id"), nullable=True,
        ),
        sa.Column(
            "transaction_reason_id", sa.Integer(),
            sa.ForeignKey("bank_transaction_reasons.id"), nullable=True,
        ),
        sa.Column(
            "accounting_classification_id", sa.Integer(),
            sa.ForeignKey("bank_accounting_classifications.id"), nullable=True,
        ),
        sa.Column(
            "accounting_classification_code_snapshot", sa.String(length=64), nullable=True,
        ),
        sa.Column(
            "accounting_classification_name_snapshot", sa.String(length=255), nullable=True,
        ),
        sa.Column("accounting_statement_type_snapshot", sa.String(length=16), nullable=True),
        sa.Column("transaction_reason_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("reporting_entity_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column(
            "payer_legal_entity_id", sa.Integer(),
            sa.ForeignKey("legal_entities.id"), nullable=True,
        ),
        sa.Column("payer_kind", sa.String(length=16), nullable=True),
        sa.Column(
            "economic_owner_legal_entity_id", sa.Integer(),
            sa.ForeignKey("legal_entities.id"), nullable=True,
        ),
        sa.Column("intercompany_outcome", sa.String(length=32), nullable=True),
        sa.Column("intercompany_due_from_code_snapshot", sa.String(length=64), nullable=True),
        sa.Column("intercompany_due_to_code_snapshot", sa.String(length=64), nullable=True),
        sa.Column("intercompany_notes", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=24), nullable=False, server_default="UNALLOCATED",
        ),
        sa.Column("decision_source", sa.String(length=8), nullable=True),
        sa.Column(
            "decided_by_account_id", sa.Integer(),
            sa.ForeignKey("rfone_accounts.id"), nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_kind", sa.String(length=32), nullable=True),
        sa.Column("evidence_reference", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "financial_transaction_id", "allocation_index", name="uq_bta_transaction_index",
        ),
        sa.CheckConstraint(
            "status IN ('UNALLOCATED', 'PENDING_EVIDENCE', 'NEEDS_OPERATOR', 'COMPLETE')",
            name="ck_bta_status",
        ),
        sa.CheckConstraint("amount_minor <> 0", name="ck_bta_amount_not_zero"),
        sa.CheckConstraint(
            "decision_source IS NULL OR decision_source IN ('HUMAN', 'RULE')",
            name="ck_bta_decision_source",
        ),
        sa.CheckConstraint(
            "payer_kind IS NULL OR payer_kind IN ('LEGAL_ENTITY', 'PERSONAL', 'UNRESOLVED')",
            name="ck_bta_payer_kind",
        ),
        sa.CheckConstraint(
            "intercompany_outcome IS NULL OR intercompany_outcome IN "
            "('NONE', 'CROSS_ENTITY', 'PERSONAL_PAYER_UNDEFINED', 'NOT_DERIVABLE')",
            name="ck_bta_intercompany_outcome",
        ),
        # COMPLETE means somebody it belongs to, a reason, and a resolved
        # canonical account. Anything less is not accounting-closed.
        sa.CheckConstraint(
            "status <> 'COMPLETE' OR ("
            "reporting_entity_id IS NOT NULL AND transaction_reason_id IS NOT NULL "
            "AND accounting_classification_code_snapshot IS NOT NULL)",
            name="ck_bta_complete_requires_resolution",
        ),
    )
    op.create_index(
        "ix_bta_financial_transaction_id",
        "bank_transaction_allocations", ["financial_transaction_id"],
    )
    op.create_index(
        "ix_bta_reporting_entity_id",
        "bank_transaction_allocations", ["reporting_entity_id"],
    )
    op.create_index(
        "ix_bta_transaction_reason_id",
        "bank_transaction_allocations", ["transaction_reason_id"],
    )
    op.create_index("ix_bta_status", "bank_transaction_allocations", ["status"])


def downgrade() -> None:
    op.drop_index("ix_bta_status", table_name="bank_transaction_allocations")
    op.drop_index("ix_bta_transaction_reason_id", table_name="bank_transaction_allocations")
    op.drop_index("ix_bta_reporting_entity_id", table_name="bank_transaction_allocations")
    op.drop_index("ix_bta_financial_transaction_id", table_name="bank_transaction_allocations")
    op.drop_table("bank_transaction_allocations")
    op.drop_index("ix_reporting_entity_group_id", table_name="reporting_entities")
    op.drop_index("ux_reporting_entity_legal_entity", table_name="reporting_entities")
    op.drop_table("reporting_entities")
    op.drop_table("reporting_groups")
