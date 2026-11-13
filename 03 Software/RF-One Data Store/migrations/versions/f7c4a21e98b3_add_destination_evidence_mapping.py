"""add destination evidence mapping

Revision ID: f7c4a21e98b3
Revises: e5b28d413f7a
Create Date: 2026-09-23

BANK_REPORTING_CONFIGURATION_001 §5-§6.

Purely ADDITIVE. One new table, nothing dropped, nothing rewritten, no
existing column altered, no existing row touched, no data file read and NO
ROW INSERTED. `down_revision` is the actual single Alembic head observed at
the time of writing (`e5b28d413f7a`), confirmed through `alembic heads`.
Migrations `b7d4e92a1c58`, `c8f1a3e04d97`, `d3a7c9f15b28` and
`e5b28d413f7a` are NOT edited.

Why this table, and why nothing existing could carry the fact
-------------------------------------------------------------

`BANK_INVOICE_EVIDENCE_COLLABORATION_001` recognized an economic owner from
a document only when `PurchaseDocument.destination_location` matched a
`ReportingEntity`'s own name exactly, and recorded that as a known gap. It
is too fragile to survive real paperwork: suppliers write a trading name, a
store label or a street address, never "Angeli E Demoni, LLC".

Nothing existing can hold the mapping:

* `SupplierAlias` maps a source's spelling of a SUPPLIER to a canonical
  Supplier. A ship-to is the opposite end of the document — who RECEIVED
  the goods, not who sent them — and pointing a supplier alias at a
  reporting entity would overload one table with two unrelated questions.
* `PurchaseDocument.destination_location` is immutable source evidence
  (Purchasing/BusinessRules.md Rule 2). Resolving it in place would
  overwrite what the supplier actually wrote.
* `ReportingEntity` itself could carry a list of names, but the mapping is
  not a property of the entity: the same text can mean different entities
  on different suppliers' paperwork, which an entity-level field cannot
  express.

Scope is the reason the table exists in this shape. A `SUPPLIER`-scoped row
claims only what that supplier's documents mean; a `GLOBAL` row claims the
text means the same thing everywhere. Two partial unique indexes keep one
meaning per key per scope, so a contradiction is impossible rather than
merely discouraged, and resolution prefers the narrowest matching scope.

`evidence` is NOT NULL on purpose: a mapping without stated evidence is an
opinion, and this table exists precisely so that economic ownership stops
being guessed.

NOTHING IS SEEDED. The table is created empty. The real reporting
configuration is applied separately and idempotently by
`configure_reporting_structure.py`, which is a reviewable script rather
than mutable seed data buried in a migration — the same convention this
repository already applies to configuration.

Runs unchanged on an empty disposable database, on the local golden
database, and on AWS RDS through an ordinary `alembic upgrade head`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "f7c4a21e98b3"
down_revision: str | None = "e5b28d413f7a"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "reporting_entity_destination_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("normalized_key", sa.String(length=512), nullable=False),
        sa.Column("raw_value", sa.String(length=512), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False, server_default="GLOBAL"),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=True),
        sa.Column(
            "reporting_entity_id", sa.Integer(),
            sa.ForeignKey("reporting_entities.id"), nullable=False,
        ),
        sa.Column("confirmation_source", sa.String(length=24), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "confirmed_by_account_id", sa.Integer(),
            sa.ForeignKey("rfone_accounts.id"), nullable=True,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.CheckConstraint("scope IN ('GLOBAL', 'SUPPLIER')", name="ck_reda_scope"),
        # A supplier-specific claim can never silently become a universal one.
        sa.CheckConstraint(
            "(scope = 'GLOBAL' AND supplier_id IS NULL) OR "
            "(scope = 'SUPPLIER' AND supplier_id IS NOT NULL)",
            name="ck_reda_scope_supplier",
        ),
        sa.CheckConstraint(
            "confirmation_source IN ('DOCUMENT_EVIDENCE', 'SYSTEM_EVIDENCE', 'HUMAN')",
            name="ck_reda_confirmation_source",
        ),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_reda_status"),
        sa.CheckConstraint("length(normalized_key) > 0", name="ck_reda_key_not_empty"),
    )
    # One meaning per key per scope: two ACTIVE global mappings for the same
    # text would be a contradiction, not a choice.
    op.create_index(
        "ux_reda_global_key",
        "reporting_entity_destination_aliases", ["normalized_key"],
        unique=True,
        sqlite_where=sa.text("supplier_id IS NULL"),
        postgresql_where=sa.text("supplier_id IS NULL"),
    )
    op.create_index(
        "ux_reda_supplier_key",
        "reporting_entity_destination_aliases", ["supplier_id", "normalized_key"],
        unique=True,
        sqlite_where=sa.text("supplier_id IS NOT NULL"),
        postgresql_where=sa.text("supplier_id IS NOT NULL"),
    )
    op.create_index(
        "ix_reda_normalized_key",
        "reporting_entity_destination_aliases", ["normalized_key"],
    )
    op.create_index(
        "ix_reda_reporting_entity_id",
        "reporting_entity_destination_aliases", ["reporting_entity_id"],
    )
    op.create_index(
        "ix_reda_supplier_id", "reporting_entity_destination_aliases", ["supplier_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_reda_supplier_id", table_name="reporting_entity_destination_aliases")
    op.drop_index(
        "ix_reda_reporting_entity_id", table_name="reporting_entity_destination_aliases",
    )
    op.drop_index("ix_reda_normalized_key", table_name="reporting_entity_destination_aliases")
    op.drop_index("ux_reda_supplier_key", table_name="reporting_entity_destination_aliases")
    op.drop_index("ux_reda_global_key", table_name="reporting_entity_destination_aliases")
    op.drop_table("reporting_entity_destination_aliases")
