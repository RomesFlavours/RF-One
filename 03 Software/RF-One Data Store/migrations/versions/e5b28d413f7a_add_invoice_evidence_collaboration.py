"""add invoice evidence collaboration

Revision ID: e5b28d413f7a
Revises: d3a7c9f15b28
Create Date: 2026-09-23

BANK_INVOICE_EVIDENCE_COLLABORATION_001.

Five new tables, four new columns on `bank_occurrences`, and one widened
CHECK constraint. Nothing is dropped except that one constraint's table,
which is rebuilt identically apart from the constraint and is verified
EMPTY first (see §3 below). No existing row is rewritten, no data file is
read and no row is inserted. `down_revision` is the actual single Alembic
head observed at the time of writing (`d3a7c9f15b28`), confirmed through
`alembic heads`. Migrations `b7d4e92a1c58`, `c8f1a3e04d97` and
`d3a7c9f15b28` are NOT edited.

1. New tables, and why existing ones could not carry the fact
-------------------------------------------------------------

`bank_occurrence_suppliers`
    A bank counterparty is not a Supplier — `BankOccurrence`'s own
    docstring says so, and its `occurrence_type` may be a tax authority or
    a payroll provider. `Supplier` meanwhile is Restaurant-scoped
    purchasing configuration. Neither table can hold a pointer to the
    other without lying about cardinality, so the correspondence is its
    own many-to-many table. It exists purely so Bank -> Invoice matching
    knows whose invoices to read; it classifies nothing.

`bank_invoice_matches`
    `FinancialTransactionMatch` already links two bank transactions as the
    two sides of one internal transfer, and its CHECK constraints say
    exactly that (`transaction_a_id < transaction_b_id`, `match_type IN
    ('INTERNAL_TRANSFER')`). A bank-to-invoice link is a different
    relation between different tables and would have required breaking
    both constraints. It is also genuinely many-to-many with amounts: one
    payment settles several invoices, one invoice is paid in instalments.
    A foreign key on either side would have been a false statement about
    how suppliers are paid.

`purchase_line_classifications`
    `PurchaseLine` is immutable by convention (Purchasing/BusinessRules.md
    Rule 2 — the repository never updates a line once inserted), and its
    `economic_classification` column is Purchasing's merchandise
    classification (FOOD / DRINK / SUPPLIES / OTHER), not RF-One's
    accounting WHY. Writing an accounting decision into either would
    overload a source-evidence row with a judgement about it. This table
    is append-only, one row per decision event, so an override never
    erases the learned proposal it replaced.

`supplier_item_category_learnings`
    `SupplierProduct.economic_classification` is the nearest existing
    thing and is deliberately not reused: it is a single current
    merchandise value with no confirmation count, no contradiction state
    and no accounting WHY. The Product Owner's rule needs all three —
    two consistent confirmations promote a mapping, and a competing
    confirmed mapping must contradict rather than overwrite.
    `supplier_format_training` in InvoiceIntake is also not reused: it
    trains how to PARSE a supplier's document layout, which is a different
    question in a different application and a different database.

`bank_evidence_bypass_authorizations`
    A bypass must outlive the allocation it authorized.
    `BankTransactionAllocation` rows are restated as a whole set whenever
    a split is corrected, so an authorization recorded there would vanish
    the first time somebody fixed a number. Append-only, never deleted —
    including after the missing invoice turns up.

2. New columns on `bank_occurrences`
------------------------------------

`category_capability` / `capability_source` / `capability_established_at`
/ `capability_evidence`. A statement about what the counterparty CAN
supply, kept apart from `default_transaction_reason_id`, which is a
suggestion about what its movements usually MEAN. The capability answers a
different question: must a matching invoice be read before classifying?

Every existing row defaults to `UNKNOWN`, which is the honest value and is
never treated as `SINGLE_CATEGORY`. No occurrence is given a capability
this migration invented.

3. Widening `ck_bta_intercompany_outcome`
-----------------------------------------

The Product Owner has now decided what a personal payment instrument's
business-side consequence is (§19): `2710 Due To Related Parties` by
default, `3300 Member Contributions` only on an explicit operator choice.
`PERSONAL_PAYER_UNDEFINED`, introduced by `d3a7c9f15b28` to state that the
question was open, is therefore replaced by `PERSONAL_PAYER_DUE_TO` and
`PERSONAL_PAYER_CONTRIBUTION`.

This is the one non-additive change in this migration, and it is fenced:

* `bank_transaction_allocations` was created by the IMMEDIATELY PRECEDING
  migration and is empty in every environment, the golden database
  included;
* the upgrade COUNTS THE ROWS FIRST and refuses to run if any exist,
  rather than rebuilding a table with data in it;
* on PostgreSQL the constraint is dropped and recreated in place, with no
  table rebuild at all;
* on SQLite, which cannot drop a CHECK, the empty table is recreated
  identically apart from that one constraint.

No value any row could hold is removed, because there are no rows.

NOTHING IS SEEDED. All five tables are created empty. No supplier, no WHO
capability, no learned mapping, no reporting entity, no invoice and no
transaction is created.

Runs unchanged on an empty disposable database, on the local golden
database, and on AWS RDS through an ordinary `alembic upgrade head`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "e5b28d413f7a"
down_revision: str | None = "d3a7c9f15b28"
branch_labels: str | None = None
depends_on: str | None = None


ALLOCATION_TABLE = "bank_transaction_allocations"

# The widened vocabulary. `PERSONAL_PAYER_UNDEFINED` is gone because the
# question it represented has been answered, not because it was renamed.
INTERCOMPANY_OUTCOME_CHECK = (
    "intercompany_outcome IS NULL OR intercompany_outcome IN "
    "('NONE', 'CROSS_ENTITY', 'PERSONAL_PAYER_DUE_TO', "
    "'PERSONAL_PAYER_CONTRIBUTION', 'NOT_DERIVABLE')"
)
OLD_INTERCOMPANY_OUTCOME_CHECK = (
    "intercompany_outcome IS NULL OR intercompany_outcome IN "
    "('NONE', 'CROSS_ENTITY', 'PERSONAL_PAYER_UNDEFINED', 'NOT_DERIVABLE')"
)


def _allocation_columns() -> list[sa.Column]:
    """The allocation table's columns, exactly as `d3a7c9f15b28` created
    them. Repeated here rather than reflected because a SQLite rebuild
    must reproduce every constraint verbatim, and reflection does not
    return CHECK constraints reliably."""
    return [
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
        sa.Column("accounting_classification_code_snapshot", sa.String(length=64), nullable=True),
        sa.Column("accounting_classification_name_snapshot", sa.String(length=255), nullable=True),
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
        sa.Column("status", sa.String(length=24), nullable=False, server_default="UNALLOCATED"),
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
    ]


def _allocation_constraints(intercompany_check: str) -> list:
    return [
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
        sa.CheckConstraint(intercompany_check, name="ck_bta_intercompany_outcome"),
        sa.CheckConstraint(
            "status <> 'COMPLETE' OR ("
            "reporting_entity_id IS NOT NULL AND transaction_reason_id IS NOT NULL "
            "AND accounting_classification_code_snapshot IS NOT NULL)",
            name="ck_bta_complete_requires_resolution",
        ),
    ]


ALLOCATION_INDEXES = (
    ("ix_bta_financial_transaction_id", ["financial_transaction_id"]),
    ("ix_bta_reporting_entity_id", ["reporting_entity_id"]),
    ("ix_bta_transaction_reason_id", ["transaction_reason_id"]),
    ("ix_bta_status", ["status"]),
)


def _rewrite_intercompany_check(new_check: str, old_check: str) -> None:
    """Replace the allocation table's intercompany CHECK constraint.

    Refuses outright if the table holds any row. Rebuilding a table with
    data in it to change a constraint is exactly the kind of quiet
    migration this repository does not do — and it is unnecessary here,
    because the table is one migration old and empty everywhere."""
    bind = op.get_bind()
    existing = bind.execute(sa.text(f"SELECT COUNT(*) FROM {ALLOCATION_TABLE}")).scalar() or 0
    if existing:
        raise RuntimeError(
            f"{ALLOCATION_TABLE} holds {existing} row(s). This migration widens a CHECK "
            "constraint and will not rebuild a table that contains data. Migrate those rows "
            "deliberately, then re-run."
        )

    if bind.dialect.name == "postgresql":
        # No table rebuild needed: drop and re-add the one constraint.
        op.drop_constraint("ck_bta_intercompany_outcome", ALLOCATION_TABLE, type_="check")
        op.create_check_constraint("ck_bta_intercompany_outcome", ALLOCATION_TABLE, new_check)
        return

    # SQLite cannot drop a CHECK constraint, so the empty table is
    # recreated identically apart from that one constraint.
    for index_name, _ in ALLOCATION_INDEXES:
        op.drop_index(index_name, table_name=ALLOCATION_TABLE)
    op.drop_table(ALLOCATION_TABLE)
    op.create_table(
        ALLOCATION_TABLE, *_allocation_columns(), *_allocation_constraints(new_check),
    )
    for index_name, columns in ALLOCATION_INDEXES:
        op.create_index(index_name, ALLOCATION_TABLE, columns)


def upgrade() -> None:
    # --- WHO accounting-category capability --------------------------------
    # Every existing occurrence becomes UNKNOWN, which is the truth: RF-One
    # has not been told whether these counterparties decompose.
    op.add_column(
        "bank_occurrences",
        sa.Column(
            "category_capability", sa.String(length=24),
            nullable=False, server_default="UNKNOWN",
        ),
    )
    op.add_column(
        "bank_occurrences", sa.Column("capability_source", sa.String(length=24), nullable=True),
    )
    op.add_column(
        "bank_occurrences",
        sa.Column("capability_established_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "bank_occurrences", sa.Column("capability_evidence", sa.Text(), nullable=True),
    )

    # --- WHO <-> Supplier ---------------------------------------------------
    op.create_table(
        "bank_occurrence_suppliers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "occurrence_id", sa.Integer(),
            sa.ForeignKey("bank_occurrences.id"), nullable=False,
        ),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("link_source", sa.String(length=16), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("occurrence_id", "supplier_id", name="uq_bos_occurrence_supplier"),
    )
    op.create_index("ix_bos_occurrence_id", "bank_occurrence_suppliers", ["occurrence_id"])
    op.create_index("ix_bos_supplier_id", "bank_occurrence_suppliers", ["supplier_id"])

    # --- Bank <-> Invoice, many-to-many with amounts ------------------------
    op.create_table(
        "bank_invoice_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "financial_transaction_id", sa.Integer(),
            sa.ForeignKey("financial_transactions.id"), nullable=False,
        ),
        sa.Column(
            "purchase_document_id", sa.Integer(),
            sa.ForeignKey("purchase_documents.id"), nullable=False,
        ),
        sa.Column("matched_amount_minor", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PROPOSED"),
        sa.Column("match_method", sa.String(length=8), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=True),
        sa.Column("match_basis", sa.Text(), nullable=True),
        sa.Column("difference_minor", sa.Integer(), nullable=True),
        sa.Column("difference_kind", sa.String(length=24), nullable=True),
        sa.Column("difference_note", sa.Text(), nullable=True),
        sa.Column(
            "decided_by_account_id", sa.Integer(),
            sa.ForeignKey("rfone_accounts.id"), nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "financial_transaction_id", "purchase_document_id",
            name="uq_bim_transaction_document",
        ),
        sa.CheckConstraint(
            "status IN ('PROPOSED', 'CONFIRMED', 'REJECTED')", name="ck_bim_status",
        ),
        sa.CheckConstraint("match_method IN ('AUTO', 'HUMAN')", name="ck_bim_match_method"),
        sa.CheckConstraint("matched_amount_minor <> 0", name="ck_bim_amount_not_zero"),
        sa.CheckConstraint(
            "difference_kind IS NULL OR difference_kind IN "
            "('NONE', 'TAX', 'FREIGHT', 'FEE', 'CREDIT', 'DISCOUNT', "
            "'PARTIAL_PAYMENT', 'UNEXPLAINED')",
            name="ck_bim_difference_kind",
        ),
    )
    op.create_index(
        "ix_bim_financial_transaction_id", "bank_invoice_matches", ["financial_transaction_id"],
    )
    op.create_index(
        "ix_bim_purchase_document_id", "bank_invoice_matches", ["purchase_document_id"],
    )
    op.create_index("ix_bim_status", "bank_invoice_matches", ["status"])

    # --- Supplier item learning ---------------------------------------------
    # Created BEFORE `purchase_line_classifications`, which carries a
    # foreign key to it.
    op.create_table(
        "supplier_item_category_learnings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("identity_kind", sa.String(length=32), nullable=False),
        sa.Column("identity_value", sa.String(length=512), nullable=False),
        sa.Column(
            "supplier_product_id", sa.Integer(),
            sa.ForeignKey("supplier_products.id"), nullable=True,
        ),
        sa.Column(
            "transaction_reason_id", sa.Integer(),
            sa.ForeignKey("bank_transaction_reasons.id"), nullable=False,
        ),
        sa.Column("confirmation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="OBSERVED"),
        sa.Column("contradiction_note", sa.Text(), nullable=True),
        sa.Column("first_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "supplier_id", "identity_kind", "identity_value", "transaction_reason_id",
            name="uq_sicl_identity_reason",
        ),
        sa.CheckConstraint(
            "identity_kind IN ('SUPPLIER_PRODUCT', 'SUPPLIER_ITEM_CODE', "
            "'NORMALIZED_DESCRIPTION')",
            name="ck_sicl_identity_kind",
        ),
        sa.CheckConstraint(
            "status IN ('OBSERVED', 'LEARNED', 'CONTRADICTED')", name="ck_sicl_status",
        ),
        sa.CheckConstraint("confirmation_count >= 0", name="ck_sicl_confirmation_count"),
    )
    op.create_index(
        "ix_sicl_supplier_identity", "supplier_item_category_learnings",
        ["supplier_id", "identity_kind", "identity_value"],
    )

    # --- Invoice line economic classification -------------------------------
    op.create_table(
        "purchase_line_classifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "purchase_line_id", sa.Integer(),
            sa.ForeignKey("purchase_lines.id"), nullable=False,
        ),
        sa.Column(
            "purchase_document_id", sa.Integer(),
            sa.ForeignKey("purchase_documents.id"), nullable=False,
        ),
        sa.Column(
            "transaction_reason_id", sa.Integer(),
            sa.ForeignKey("bank_transaction_reasons.id"), nullable=True,
        ),
        sa.Column(
            "reporting_entity_id", sa.Integer(),
            sa.ForeignKey("reporting_entities.id"), nullable=True,
        ),
        sa.Column(
            "accounting_classification_id", sa.Integer(),
            sa.ForeignKey("bank_accounting_classifications.id"), nullable=True,
        ),
        sa.Column("accounting_classification_code_snapshot", sa.String(length=64), nullable=True),
        sa.Column("accounting_statement_type_snapshot", sa.String(length=16), nullable=True),
        sa.Column("transaction_reason_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("decision_source", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PROPOSED"),
        sa.Column("confidence", sa.String(length=16), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column(
            "learning_id", sa.Integer(),
            sa.ForeignKey("supplier_item_category_learnings.id"), nullable=True,
        ),
        sa.Column("is_override", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "decided_by_account_id", sa.Integer(),
            sa.ForeignKey("rfone_accounts.id"), nullable=True,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "decision_source IN ('HUMAN', 'LEARNED', 'DOCUMENT_EVIDENCE')",
            name="ck_plc_decision_source",
        ),
        sa.CheckConstraint("status IN ('PROPOSED', 'CONFIRMED')", name="ck_plc_status"),
    )
    op.create_index(
        "ix_plc_purchase_line_id", "purchase_line_classifications", ["purchase_line_id"],
    )
    op.create_index(
        "ix_plc_purchase_document_id", "purchase_line_classifications", ["purchase_document_id"],
    )
    op.create_index(
        "ix_plc_reporting_entity_id", "purchase_line_classifications", ["reporting_entity_id"],
    )

    # --- Explicit human bypass of a missing document ------------------------
    op.create_table(
        "bank_evidence_bypass_authorizations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "financial_transaction_id", sa.Integer(),
            sa.ForeignKey("financial_transactions.id"), nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("missing_document_note", sa.Text(), nullable=True),
        sa.Column(
            "occurrence_id", sa.Integer(),
            sa.ForeignKey("bank_occurrences.id"), nullable=True,
        ),
        sa.Column("occurrence_name_snapshot", sa.String(length=255), nullable=True),
        sa.Column("capability_snapshot", sa.String(length=32), nullable=True),
        sa.Column(
            "authorized_by_account_id", sa.Integer(),
            sa.ForeignKey("rfone_accounts.id"), nullable=True,
        ),
        sa.Column("authorized_by_name", sa.String(length=255), nullable=True),
        sa.Column(
            "authorized_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_beba_financial_transaction_id", "bank_evidence_bypass_authorizations",
        ["financial_transaction_id"],
    )

    # --- The one widened constraint -----------------------------------------
    _rewrite_intercompany_check(INTERCOMPANY_OUTCOME_CHECK, OLD_INTERCOMPANY_OUTCOME_CHECK)


def downgrade() -> None:
    _rewrite_intercompany_check(OLD_INTERCOMPANY_OUTCOME_CHECK, INTERCOMPANY_OUTCOME_CHECK)

    op.drop_index(
        "ix_beba_financial_transaction_id", table_name="bank_evidence_bypass_authorizations",
    )
    op.drop_table("bank_evidence_bypass_authorizations")

    op.drop_index("ix_plc_reporting_entity_id", table_name="purchase_line_classifications")
    op.drop_index("ix_plc_purchase_document_id", table_name="purchase_line_classifications")
    op.drop_index("ix_plc_purchase_line_id", table_name="purchase_line_classifications")
    op.drop_table("purchase_line_classifications")

    op.drop_index("ix_sicl_supplier_identity", table_name="supplier_item_category_learnings")
    op.drop_table("supplier_item_category_learnings")

    op.drop_index("ix_bim_status", table_name="bank_invoice_matches")
    op.drop_index("ix_bim_purchase_document_id", table_name="bank_invoice_matches")
    op.drop_index("ix_bim_financial_transaction_id", table_name="bank_invoice_matches")
    op.drop_table("bank_invoice_matches")

    op.drop_index("ix_bos_supplier_id", table_name="bank_occurrence_suppliers")
    op.drop_index("ix_bos_occurrence_id", table_name="bank_occurrence_suppliers")
    op.drop_table("bank_occurrence_suppliers")

    op.drop_column("bank_occurrences", "capability_evidence")
    op.drop_column("bank_occurrences", "capability_established_at")
    op.drop_column("bank_occurrences", "capability_source")
    op.drop_column("bank_occurrences", "category_capability")
