"""add cardholder history, card settlement account and accounting deduplication

Revision ID: a4e2f8c15b73
Revises: f1c7a94d6e02
Create Date: 2026-09-20

BANK_CARDHOLDER_AND_ACCOUNTING_DEDUPLICATION_001 — purely additive. Two
new tables and six new nullable columns on `financial_transactions`. No
existing table is restructured, no existing column changes type or
nullability, and no row of any kind is created, deleted or rewritten.

  * NEW `bank_card_settlement_accounts` — the historized bank account a
    Credit Card settles to. This is the accounting-authoritative source of
    the chain Card -> Settlement Bank Account -> Company/Legal Entity, and
    it scopes accounting deduplication. A partial unique index enforces at
    most ONE open assignment per card, mirroring the pattern
    `ux_employee_assignments_one_active_role_per_restaurant` and
    `ux_restaurant_locations_one_open_primary` already establish. Both
    `sqlite_where` and `postgresql_where` are declared: SQLAlchemy honours
    only the dialect-specific kwarg it recognizes and silently ignores the
    other, so omitting one would create a FULL unique index on that
    dialect and wrongly reject legitimate history.
  * NEW `bank_card_holder_assignments` — the historized person who held a
    card. Responsibility only: it never derives Company, never derives the
    settlement account, and never takes part in duplicate identity. The
    holder is a TYPED reference (`ACTING_IDENTITY` / `EMPLOYEE` /
    `UNLINKED_PERSON`), reusing a canonical identity wherever one genuinely
    exists — the same convention `AuthorityGrant.scope_type`/`scope_id`
    already uses — because neither `acting_identities` nor `employees`
    covers every cardholder on its own.
  * `financial_transactions` gains `payee_normalized`,
    `payee_normalization_version`, `accounting_dedup_key`,
    `accounting_status`, `accounting_canonical_transaction_id`,
    `accounting_dedup_reason` and `accounting_settlement_account_id`.

**No backfill, deliberately.** Every new column is left NULL on existing
rows, and `accounting_status = NULL` is defined to mean "not yet
recomputed", which `accounting_dedup.is_accounting_visible` treats as
VISIBLE. An existing database therefore keeps exporting exactly what it
exported before this migration, and deduplication only starts affecting
the books once a human has configured the settlement accounts and run the
recompute. Computing keys here instead would either guess settlement
accounts that nobody confirmed, or mark real transactions as
un-deduplicable on a schema change — neither is acceptable for a silent
migration step.

The raw preservation layer (`bank_import_batches.raw_file_bytes`,
`raw_bank_transactions.raw_fields`) is neither read nor written.

Runs on SQLite and PostgreSQL. SQLite cannot add a CHECK constraint to an
existing table, so `financial_transactions` gains its two new columns-plus-
constraints through an Alembic batch rebuild there, and through plain
`op.add_column` / `op.create_check_constraint` on PostgreSQL. SQLAlchemy
2.x DOES reflect SQLite CHECK constraints (verified against the version
this repository pins), so the rebuild carries the table's existing
constraints over by itself and this migration must not re-declare them —
doing so would be redundant at best. The same fact drives the downgrade:
the two new CHECK constraints are dropped explicitly BEFORE their columns,
because a reflected constraint referencing a dropped column would make the
rebuilt table invalid.

Downgrade removes only what this migration added.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4e2f8c15b73'
down_revision: Union[str, Sequence[str], None] = 'f1c7a94d6e02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_FT_NEW_COLUMNS = (
    ("payee_normalized", sa.String(length=512)),
    ("payee_normalization_version", sa.String(length=16)),
    ("accounting_dedup_key", sa.String(length=128)),
    ("accounting_status", sa.String(length=40)),
    ("accounting_canonical_transaction_id", sa.Integer()),
    ("accounting_dedup_reason", sa.Text()),
    ("accounting_settlement_account_id", sa.Integer()),
)

# `financial_transactions` already carries several CHECK constraints
# (`ck_ft_classification`, `ck_ft_status`, `ck_ft_duplicate_status`,
# `ck_ft_review_status`). They are deliberately NOT listed or re-declared
# here: SQLAlchemy reflects SQLite CHECK constraints, so a batch rebuild
# carries them over unchanged, and enumerating them would only create a
# second place to keep in sync with the model.
_FT_NEW_CHECKS = (
    (
        "ck_ft_accounting_status",
        "accounting_status IS NULL OR accounting_status IN "
        "('CANONICAL', 'DUPLICATE_SUPPRESSED', 'UNRESOLVED_NO_SETTLEMENT_ACCOUNT')",
    ),
    (
        "ck_ft_accounting_canonical_not_self",
        "accounting_canonical_transaction_id IS NULL "
        "OR accounting_canonical_transaction_id <> id",
    ),
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # --- Card -> Settlement Bank Account (historized) -----------------------
    op.create_table(
        "bank_card_settlement_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("credit_card_payment_instrument_id", sa.Integer(), nullable=False),
        sa.Column("settlement_bank_account_id", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_account_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "credit_card_payment_instrument_id <> settlement_bank_account_id",
            name="ck_bcsa_not_self",
        ),
        sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_bcsa_period"),
        sa.ForeignKeyConstraint(["credit_card_payment_instrument_id"], ["payment_instruments.id"]),
        sa.ForeignKeyConstraint(["settlement_bank_account_id"], ["payment_instruments.id"]),
        sa.ForeignKeyConstraint(["created_by_account_id"], ["rfone_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bcsa_card_id", "bank_card_settlement_accounts",
        ["credit_card_payment_instrument_id"], unique=False,
    )
    op.create_index(
        "ix_bcsa_settlement_id", "bank_card_settlement_accounts",
        ["settlement_bank_account_id"], unique=False,
    )
    op.create_index(
        "ux_bcsa_one_open_per_card", "bank_card_settlement_accounts",
        ["credit_card_payment_instrument_id"], unique=True,
        sqlite_where=sa.text("valid_to IS NULL"),
        postgresql_where=sa.text("valid_to IS NULL"),
    )

    # --- Card -> Cardholder (historized, responsibility only) ---------------
    op.create_table(
        "bank_card_holder_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("credit_card_payment_instrument_id", sa.Integer(), nullable=False),
        sa.Column("holder_kind", sa.String(length=24), nullable=False),
        sa.Column("holder_acting_identity_id", sa.Integer(), nullable=True),
        sa.Column("holder_employee_id", sa.Integer(), nullable=True),
        sa.Column("holder_display_name", sa.String(length=255), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_account_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "holder_kind IN ('ACTING_IDENTITY', 'EMPLOYEE', 'UNLINKED_PERSON')",
            name="ck_bcha_holder_kind",
        ),
        sa.CheckConstraint(
            "(holder_kind = 'ACTING_IDENTITY' AND holder_acting_identity_id IS NOT NULL "
            " AND holder_employee_id IS NULL) OR "
            "(holder_kind = 'EMPLOYEE' AND holder_employee_id IS NOT NULL "
            " AND holder_acting_identity_id IS NULL) OR "
            "(holder_kind = 'UNLINKED_PERSON' AND holder_acting_identity_id IS NULL "
            " AND holder_employee_id IS NULL)",
            name="ck_bcha_holder_reference_matches_kind",
        ),
        sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_bcha_period"),
        sa.ForeignKeyConstraint(["credit_card_payment_instrument_id"], ["payment_instruments.id"]),
        sa.ForeignKeyConstraint(["holder_acting_identity_id"], ["acting_identities.id"]),
        sa.ForeignKeyConstraint(["holder_employee_id"], ["employees.id"]),
        sa.ForeignKeyConstraint(["created_by_account_id"], ["rfone_accounts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bcha_card_id", "bank_card_holder_assignments",
        ["credit_card_payment_instrument_id"], unique=False,
    )
    op.create_index(
        "ux_bcha_one_open_per_card", "bank_card_holder_assignments",
        ["credit_card_payment_instrument_id"], unique=True,
        sqlite_where=sa.text("valid_to IS NULL"),
        postgresql_where=sa.text("valid_to IS NULL"),
    )

    # --- Accounting deduplication columns -----------------------------------
    if is_sqlite:
        with op.batch_alter_table("financial_transactions", schema=None, recreate="always") as batch_op:
            for column_name, column_type in _FT_NEW_COLUMNS:
                batch_op.add_column(sa.Column(column_name, column_type, nullable=True))
            batch_op.create_foreign_key(
                "fk_ft_accounting_canonical_transaction_id", "financial_transactions",
                ["accounting_canonical_transaction_id"], ["id"],
            )
            batch_op.create_foreign_key(
                "fk_ft_accounting_settlement_account_id", "payment_instruments",
                ["accounting_settlement_account_id"], ["id"],
            )
            for name, condition in _FT_NEW_CHECKS:
                batch_op.create_check_constraint(name, condition)
    else:
        for column_name, column_type in _FT_NEW_COLUMNS:
            op.add_column(
                "financial_transactions", sa.Column(column_name, column_type, nullable=True),
            )
        op.create_foreign_key(
            "fk_ft_accounting_canonical_transaction_id", "financial_transactions",
            "financial_transactions", ["accounting_canonical_transaction_id"], ["id"],
        )
        op.create_foreign_key(
            "fk_ft_accounting_settlement_account_id", "financial_transactions",
            "payment_instruments", ["accounting_settlement_account_id"], ["id"],
        )
        for name, condition in _FT_NEW_CHECKS:
            op.create_check_constraint(name, "financial_transactions", condition)

    op.create_index(
        "ix_ft_accounting_dedup_key", "financial_transactions", ["accounting_dedup_key"], unique=False,
    )
    op.create_index(
        "ix_ft_accounting_canonical_id", "financial_transactions",
        ["accounting_canonical_transaction_id"], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    op.drop_index("ix_ft_accounting_canonical_id", table_name="financial_transactions")
    op.drop_index("ix_ft_accounting_dedup_key", table_name="financial_transactions")

    # Only columns this migration added are dropped. Every pre-existing
    # column of `financial_transactions` — including the original
    # `duplicate_status` / `duplicate_of_transaction_id` human-review
    # fields and every amount, date and description — is untouched, so no
    # historical accounting value is lost by downgrading.
    if is_sqlite:
        with op.batch_alter_table("financial_transactions", schema=None, recreate="always") as batch_op:
            # Dropped FIRST: these constraints reference the columns below,
            # and the rebuild reflects them, so a rebuilt table that still
            # declared them would reference columns that no longer exist.
            for name, _ in _FT_NEW_CHECKS:
                batch_op.drop_constraint(name, type_="check")
            for column_name, _ in reversed(_FT_NEW_COLUMNS):
                batch_op.drop_column(column_name)
    else:
        for name, _ in _FT_NEW_CHECKS:
            op.drop_constraint(name, "financial_transactions", type_="check")
        op.drop_constraint(
            "fk_ft_accounting_settlement_account_id", "financial_transactions", type_="foreignkey",
        )
        op.drop_constraint(
            "fk_ft_accounting_canonical_transaction_id", "financial_transactions", type_="foreignkey",
        )
        for column_name, _ in reversed(_FT_NEW_COLUMNS):
            op.drop_column("financial_transactions", column_name)

    op.drop_index("ux_bcha_one_open_per_card", table_name="bank_card_holder_assignments")
    op.drop_index("ix_bcha_card_id", table_name="bank_card_holder_assignments")
    op.drop_table("bank_card_holder_assignments")

    op.drop_index("ux_bcsa_one_open_per_card", table_name="bank_card_settlement_accounts")
    op.drop_index("ix_bcsa_settlement_id", table_name="bank_card_settlement_accounts")
    op.drop_index("ix_bcsa_card_id", table_name="bank_card_settlement_accounts")
    op.drop_table("bank_card_settlement_accounts")
