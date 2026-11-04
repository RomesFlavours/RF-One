"""add management groups, the canonical WHY catalog and WHO<->WHY

Revision ID: c4a9e7d21b56
Revises: b6e1c47a20f9
Create Date: 2026-09-21

BANK_CANONICAL_WHY_AND_WHO_RELATIONSHIPS_001 — an ADDITIVE schema change
plus a deterministic seed. No canonical account changes, no transaction is
created or reclassified, no Who is created and no recognition rule is
written.

WHY is RF-One's operational/management classification — what kind of
business purpose a transaction served. It is the language the Company
Panel and Cognito will aggregate over, and it is deliberately finer than
the P&L: `JANITORIAL_CLEANING` and `HOOD_CLEANING` are two purposes the
business wants to see apart, and both resolve to 7810.

Every Why resolves to exactly ONE accounting destination, and what that
destination IS decides whether there is a WHAT:

    a P&L posting category   -> that IS the WHAT
    a Balance Sheet account  -> NO WHAT; the transaction settles a
                                liability, moves money between the
                                company's own accounts, or capitalises an
                                asset

Schema

  * NEW `bank_reason_groups` — the 14 management groups. Organisation
    only: nothing is ever posted to a group, and ordinary reconciliation
    never shows one.
  * NEW `bank_occurrence_reason_associations` — WHO <-> WHY, many to many,
    unique on (occurrence, reason). A Who may have zero, one or many Whys;
    a Why may apply to many Whos. These rows are a PRODUCTIVITY SHORTCUT
    that shortens the dropdown, never proof about a new transaction:
    BANK_WHO_WHY_INVARIANT_001 is untouched, and
    `bank_occurrences.default_transaction_reason_id` stays a suggestion.
  * `bank_transaction_reasons.reason_group_id` — nullable, so a Why that
    predates the catalog survives ungrouped rather than being guessed at.

Data

77 canonical Whys are seeded — 59 resolving to a WHAT and 18 to a
Balance Sheet destination. The five structural Whys seeded by
`b6e1c47a20f9` are REUSED, not duplicated: FOREIGN_TRANSACTION_FEE,
CREDIT_CARD_SETTLEMENT, LOAN_ADVANCE, INTERNAL_BANK_TRANSFER and
SALES_TAX_REMITTANCE keep their ids and destinations and simply gain a
management group.

The rows come from this revision's OWN FROZEN SNAPSHOT
(BANK_CANONICAL_MIGRATION_IMMUTABILITY_001):

    migrations/migration_data/c4a9e7d21b56_rfone_restaurant_why_v1.csv

never from the live `canonical/RFONE_RESTAURANT_WHY_V1.csv`, which is the
current definition and will keep evolving.

Idempotent and non-destructive:

  * a Why already present with the SAME destination is left alone and
    only gains its group;
  * a Why present with a DIFFERENT destination RAISES — a Why is what
    historical decisions resolved their What through, and re-pointing one
    would rewrite what those decisions meant;
  * a destination that does not exist, or that is a reporting GROUP,
    RAISES rather than producing a Why nothing can post to.

Downgrade drops the two new tables and the new column, and removes only
the Whys this revision created that nothing references.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4a9e7d21b56'
down_revision: Union[str, Sequence[str], None] = 'b6e1c47a20f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


GROUPS = "bank_reason_groups"
REASONS = "bank_transaction_reasons"
ASSOCIATIONS = "bank_occurrence_reason_associations"
ACCOUNTS = "bank_accounting_classifications"

# This revision's own frozen input. IMMUTABLE: editing it would change what
# a shipped migration does. A correction is a new revision.
_CATALOG_PATH = (
    Path(__file__).resolve().parents[1]
    / "migration_data" / "c4a9e7d21b56_rfone_restaurant_why_v1.csv"
)
_EXPECTED_ROWS = 77
_EXPECTED_GROUPS = 14


def _catalog() -> list[dict]:
    rows = list(csv.DictReader(io.StringIO(
        _CATALOG_PATH.read_text(encoding="utf-8-sig")
    )))
    if len(rows) != _EXPECTED_ROWS:
        raise RuntimeError(
            f"The frozen WHY catalog {_CATALOG_PATH.name} holds {len(rows)} row(s); "
            f"revision c4a9e7d21b56 was written against exactly {_EXPECTED_ROWS}. A migration "
            "snapshot is immutable — restore it and express any change as a new revision."
        )
    return rows


def upgrade() -> None:
    """Add the group/association tables, then seed the canonical Whys."""
    bind = op.get_bind()
    rows = _catalog()

    op.create_table(
        GROUPS,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_bank_reason_group_code"),
    )

    op.create_table(
        ASSOCIATIONS,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("occurrence_id", sa.Integer(), nullable=False),
        sa.Column("transaction_reason_id", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("confirmation_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("first_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["occurrence_id"], ["bank_occurrences.id"]),
        sa.ForeignKeyConstraint(["transaction_reason_id"], ["bank_transaction_reasons.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "occurrence_id", "transaction_reason_id",
            name="uq_bank_occurrence_reason_association",
        ),
    )
    op.create_index("ix_bora_occurrence_id", ASSOCIATIONS, ["occurrence_id"], unique=False)
    op.create_index("ix_bora_reason_id", ASSOCIATIONS, ["transaction_reason_id"], unique=False)

    op.add_column(REASONS, sa.Column("reason_group_id", sa.Integer(), nullable=True))
    op.create_index("ix_btr_reason_group_id", REASONS, ["reason_group_id"], unique=False)
    # A named FK on an existing table needs a batch rebuild on SQLite;
    # the column alone is enough for correctness and the ORM declares the
    # relationship, so the constraint is added only where it is free.
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_btr_reason_group_id", REASONS, GROUPS, ["reason_group_id"], ["id"],
        )

    # --- groups ------------------------------------------------------------
    seen: dict[str, int] = {}
    for code, name, order in sorted(
        {(r["Group Code"], r["Group Name"], int(r["Group Order"])) for r in rows},
        key=lambda item: item[2],
    ):
        # `active` is deliberately not listed: its column default already
        # says ACTIVE, and a literal 1 here is an integer, which PostgreSQL
        # refuses to put in a boolean column ("column is of type boolean
        # but expression is of type integer"). Letting the default apply is
        # both portable and one less place for the two to disagree.
        bind.execute(
            sa.text(
                f"INSERT INTO {GROUPS} (code, name, display_order) "
                "VALUES (:code, :name, :display_order)"
            ),
            {"code": code, "name": name, "display_order": order},
        )
    seen = {
        code: identifier for code, identifier in bind.execute(
            sa.text(f"SELECT code, id FROM {GROUPS}")
        ).fetchall()
    }
    if len(seen) != _EXPECTED_GROUPS:
        raise RuntimeError(
            f"Expected {_EXPECTED_GROUPS} management groups after seeding, found {len(seen)}."
        )

    # --- reasons -----------------------------------------------------------
    accounts = {
        code: (identifier, statement_type, node_type)
        for code, identifier, statement_type, node_type in bind.execute(
            sa.text(f"SELECT code, id, statement_type, node_type FROM {ACCOUNTS}")
        ).fetchall()
    }
    existing = {
        code: (identifier, classification_id)
        for code, identifier, classification_id in bind.execute(
            sa.text(f"SELECT code, id, accounting_classification_id FROM {REASONS}")
        ).fetchall()
    }
    by_id = {identifier: code for code, (identifier, _, _) in accounts.items()}

    missing = [r["Account Code"] for r in rows if r["Account Code"] not in accounts]
    if missing:
        raise RuntimeError(
            "Refusing to seed the canonical WHY catalog: these accounting destinations do not "
            "exist — " + ", ".join(sorted(set(missing)))
            + ". Run the canonical accounting catalog migrations first."
        )
    grouped = [
        r["Code"] for r in rows if accounts[r["Account Code"]][2] == "GROUP"
    ]
    if grouped:
        raise RuntimeError(
            "Refusing to seed the canonical WHY catalog: these Whys resolve to a reporting "
            "GROUP, which nothing may be posted to — " + ", ".join(sorted(grouped))
        )
    conflicts = [
        f"{r['Code']}: already resolves to {by_id.get(existing[r['Code']][1], 'nothing')!r}, "
        f"the canonical catalog says {r['Account Code']!r}"
        for r in rows
        if r["Code"] in existing
        and existing[r["Code"]][1] != accounts[r["Account Code"]][0]
    ]
    if conflicts:
        raise RuntimeError(
            "Refusing to seed the canonical WHY catalog: these codes already resolve elsewhere, "
            "and a Why that historical decisions resolved their What through is never silently "
            "re-pointed. Resolve them by hand, then re-run. " + "; ".join(conflicts)
        )

    created = reused = 0
    for row in rows:
        account_id, statement_type, _ = accounts[row["Account Code"]]
        group_id = seen[row["Group Code"]]
        is_pl = statement_type == "PROFIT_LOSS"
        description = (
            f"Canonical RF-One WHY (RFONE_RESTAURANT_WHY_V1), management group "
            f"{row['Group Name']}. Resolves to "
            + (
                f"WHAT {row['Account Code']}."
                if is_pl else
                f"accounting destination {row['Account Code']} — no WHAT, because this is "
                "not a Profit & Loss event."
            )
            + " Seeded by migration c4a9e7d21b56."
        )
        if row["Code"] in existing:
            bind.execute(
                sa.text(f"UPDATE {REASONS} SET reason_group_id = :group_id WHERE code = :code"),
                {"group_id": group_id, "code": row["Code"]},
            )
            reused += 1
            continue
        bind.execute(
            sa.text(
                f"INSERT INTO {REASONS} "
                "(code, name, description, status, accounting_classification_id, reason_group_id) "
                "VALUES (:code, :name, :description, 'ACTIVE', :account_id, :group_id)"
            ),
            {
                "code": row["Code"], "name": row["Name"], "description": description,
                "account_id": account_id, "group_id": group_id,
            },
        )
        created += 1

    print(
        f"[c4a9e7d21b56] canonical WHY catalog: {created} created, {reused} already present "
        f"(reused, only grouped); {len(seen)} management groups. "
        "No Who, association, rule or transaction was created."
    )


def downgrade() -> None:
    """Drop the two tables and the column; remove only unused seeded Whys."""
    bind = op.get_bind()
    rows = _catalog()

    referenced: set[int] = set()
    for statement in (
        "SELECT DISTINCT default_transaction_reason_id FROM bank_occurrences "
        "WHERE default_transaction_reason_id IS NOT NULL",
        "SELECT DISTINCT transaction_reason_id FROM bank_recognition_rules",
        "SELECT DISTINCT transaction_reason_id FROM bank_transaction_explanations "
        "WHERE transaction_reason_id IS NOT NULL",
        "SELECT DISTINCT bank_transaction_reason_id FROM bank_transaction_reason_export_mappings",
    ):
        referenced.update(row[0] for row in bind.execute(sa.text(statement)).fetchall())

    # The five structural Whys predate this revision and stay.
    keep = {
        "FOREIGN_TRANSACTION_FEE", "CREDIT_CARD_SETTLEMENT", "LOAN_ADVANCE",
        "INTERNAL_BANK_TRANSFER", "SALES_TAX_REMITTANCE",
    }
    for row in rows:
        if row["Code"] in keep:
            continue
        found = bind.execute(
            sa.text(f"SELECT id FROM {REASONS} WHERE code = :code"), {"code": row["Code"]},
        ).fetchone()
        if found is None or found[0] in referenced:
            continue
        bind.execute(sa.text(f"DELETE FROM {REASONS} WHERE id = :id"), {"id": found[0]})

    op.drop_index("ix_btr_reason_group_id", table_name=REASONS)
    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_btr_reason_group_id", REASONS, type_="foreignkey")
    op.drop_column(REASONS, "reason_group_id")
    op.drop_index("ix_bora_reason_id", table_name=ASSOCIATIONS)
    op.drop_index("ix_bora_occurrence_id", table_name=ASSOCIATIONS)
    op.drop_table(ASSOCIATIONS)
    op.drop_table(GROUPS)
