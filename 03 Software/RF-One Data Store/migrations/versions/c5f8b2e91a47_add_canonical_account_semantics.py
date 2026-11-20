"""add canonical account semantics to bank accounting classifications

Revision ID: c5f8b2e91a47
Revises: b8d3f1a72c64
Create Date: 2026-09-21

BANK_ACCOUNTING_CLASSIFICATION_SEMANTICS_001 — an ADDITIVE schema change
plus a deterministic backfill. No account code, name, parent or statement
type is altered, no transaction is reclassified, no raw data is touched
and no recognition rule is rewritten.

Four facts the canonical chart always had, and that RF-One used to infer,
become real columns on `bank_accounting_classifications`:

  * `node_type`        GROUP | POSTING | POSTING_CATEGORY — read, never
                       inferred from child count again. A GROUP may be
                       legitimately empty; a POSTING_CATEGORY may
                       legitimately have children.
  * `is_contra`        the account subtracts from its reporting group.
                       Replaces the hardcoded contra-code list reporting
                       used to carry.
  * `review_sensitive` a residual account a human may choose but that
                       automated recognition must never fall back to.
  * `normal_balance`   DEBIT | CREDIT — which side the account naturally
                       sits on, so a subtree total is signed from data
                       rather than from special-cased codes.

The values come from this revision's OWN FROZEN SNAPSHOT
(BANK_CANONICAL_MIGRATION_IMMUTABILITY_001):

    migrations/migration_data/c5f8b2e91a47_account_semantics.csv

the same 134 accounts `b8d3f1a72c64` seeded, with the four semantic
columns exactly as approved when this revision was written. That file is
never edited again — see `migrations/migration_data/README.md`.

It is deliberately NOT the live canonical definition at
`rfone_data_store/bank_reconciliation/canonical/RFONE_RESTAURANT_COA_V1.csv`,
which this revision originally read. That file is the CURRENT canonical
source of truth and is actively maintained; a later approved change to it
must not alter what this September 2026 revision did. The accounting
corrections that followed (3400, 8400, 8410, 8420) belong to
`d7a4c9e2f318`, which is where this chain expresses them — not here,
retroactively.

The rows are read with the standard library and written with SQLAlchemy
Core, NOT through the ORM — a migration must keep working against the
schema of its own revision.

Backfill rules, all deterministic:

  * a canonical code present under its canonical name takes the CSV's
    values;
  * any OTHER row — a legacy-migrated Kermali `what_label`, an operator's
    own upload, or a canonical code a human has since renamed and
    therefore repurposed — takes `node_type` from the derivation that was
    in force until this revision (a classification WITH children is a
    group), `is_contra` and `review_sensitive` FALSE, and
    `normal_balance` NULL. Nothing is invented: a row whose statement side
    was never determinable does not acquire a made-up normal balance
    here, for the same reason `statement_type` was left NULL for it.

`normal_balance` is therefore nullable, like `statement_type`, while
`node_type`, `is_contra` and `review_sensitive` are NOT NULL with
defaults. Every one of the 134 accounts in this revision's snapshot ends
this migration with all four values explicitly set, which this revision
verifies before it completes.

The seeded descriptions written by b8d3f1a72c64 end in a generated
"Node type: X." sentence. It is removed here — not as cleanup, but
because that sentence is now a second, unversioned copy of a fact that
lives in a column, and for 1590 and 2600 it would contradict it.

Runs on SQLite and PostgreSQL. SQLite cannot add a CHECK constraint to an
existing table, so the columns and their two constraints arrive through an
Alembic batch rebuild there and through plain `op.add_column` /
`op.create_check_constraint` on PostgreSQL. SQLAlchemy reflects SQLite
CHECK constraints, so the rebuild carries the table's existing constraints
(`ck_bank_accounting_classification_statement_type`,
`ck_bac_parent_not_self`), its unique constraint and its self-referential
foreign key over by itself, and they must not be re-declared here.

Downgrade removes only the four columns and the two constraints this
revision added. No row is deleted and no other column is touched, so a
downgrade loses the new metadata and nothing else.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c5f8b2e91a47'
down_revision: Union[str, Sequence[str], None] = 'b8d3f1a72c64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "bank_accounting_classifications"
CATALOG_VERSION = "RFONE_RESTAURANT_COA_V1"

# This revision's own frozen input. IMMUTABLE: editing it would change what
# a shipped migration does. A correction is a new revision.
_CATALOG_PATH = (
    Path(__file__).resolve().parents[1]
    / "migration_data" / "c5f8b2e91a47_account_semantics.csv"
)

# What that snapshot must contain for this revision to be intact.
_EXPECTED_ROW_COUNT = 134

_NEW_COLUMNS = (
    ("node_type", sa.String(length=24), False, "POSTING"),
    # sa.false()/sa.true(), not sa.text("0")/("1"): PostgreSQL rejects an
    # integer default on a boolean column, and this chain is applied to
    # RDS PostgreSQL as well as to SQLite.
    ("is_contra", sa.Boolean(), False, sa.false()),
    ("review_sensitive", sa.Boolean(), False, sa.false()),
    ("normal_balance", sa.String(length=8), True, None),
)

_NEW_CHECKS = (
    ("ck_bac_node_type", "node_type IN ('GROUP', 'POSTING', 'POSTING_CATEGORY')"),
    ("ck_bac_normal_balance", "normal_balance IS NULL OR normal_balance IN ('DEBIT', 'CREDIT')"),
)

# The generated sentence b8d3f1a72c64 appended to every seeded description.
# Now a column, so the prose copy goes.
_NODE_TYPE_SENTENCE = " Node type: "


def _canonical_rows() -> list[dict]:
    """This revision's frozen catalog. Never the live canonical CSV."""
    text = _CATALOG_PATH.read_text(encoding="utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    if len(rows) != _EXPECTED_ROW_COUNT:
        raise RuntimeError(
            f"The frozen catalog {_CATALOG_PATH.name} holds {len(rows)} account(s); "
            f"revision c5f8b2e91a47 was written against exactly {_EXPECTED_ROW_COUNT}. "
            "A migration snapshot is immutable — restore it and express any change as a "
            "new revision."
        )
    missing = [
        row["Code"] for row in rows
        if not (row.get("Node Type") or "").strip()
        or not (row.get("Normal Balance") or "").strip()
        or not (row.get("Is Contra") or "").strip()
        or not (row.get("Review Sensitive") or "").strip()
    ]
    if missing:
        raise RuntimeError(
            f"The frozen catalog {_CATALOG_PATH.name} leaves account semantics blank for: "
            + ", ".join(missing)
            + ". Every canonical account must state node type, normal balance, contra and "
            "review sensitivity explicitly."
        )
    return rows


def _flag(value: str) -> bool:
    return (value or "").strip().upper() in ("TRUE", "1", "YES", "Y")


def upgrade() -> None:
    """Add the four semantic columns and backfill every existing row."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    rows = _canonical_rows()

    if is_sqlite:
        with op.batch_alter_table(TABLE, schema=None, recreate="always") as batch_op:
            for name, column_type, nullable, default in _NEW_COLUMNS:
                batch_op.add_column(
                    sa.Column(name, column_type, nullable=nullable, server_default=default),
                )
            for name, condition in _NEW_CHECKS:
                batch_op.create_check_constraint(name, condition)
    else:
        for name, column_type, nullable, default in _NEW_COLUMNS:
            op.add_column(
                TABLE, sa.Column(name, column_type, nullable=nullable, server_default=default),
            )
        for name, condition in _NEW_CHECKS:
            op.create_check_constraint(name, TABLE, condition)

    # --- backfill -----------------------------------------------------------
    existing = {
        row[0]: row[1]
        for row in bind.execute(sa.text(f"SELECT code, name FROM {TABLE}")).fetchall()
    }
    canonical_by_code = {row["Code"]: row for row in rows}

    # Every row whose code IS canonical and whose name still matches takes
    # the canonical semantics. A renamed row does not: the human repurposed
    # that code, and imposing the chart's meaning on it would redefine an
    # account that historical decisions already reference.
    canonical_targets = {
        code for code, name in existing.items()
        if code in canonical_by_code
        and name.strip().casefold() == canonical_by_code[code]["Name"].strip().casefold()
    }
    for code in sorted(canonical_targets):
        row = canonical_by_code[code]
        bind.execute(
            sa.text(
                f"UPDATE {TABLE} SET node_type = :node_type, is_contra = :is_contra, "
                "review_sensitive = :review_sensitive, normal_balance = :normal_balance "
                "WHERE code = :code"
            ),
            {
                "node_type": row["Node Type"].strip(),
                "is_contra": _flag(row["Is Contra"]),
                "review_sensitive": _flag(row["Review Sensitive"]),
                "normal_balance": row["Normal Balance"].strip(),
                "code": code,
            },
        )

    # Everything else keeps the behaviour that was in force until now: a
    # classification WITH children was treated as a non-postable group.
    # Recording that once, here, is what lets the running code stop
    # re-deriving it on every call.
    others = sorted(set(existing) - canonical_targets)
    if others:
        parents = {
            row[0] for row in bind.execute(sa.text(
                f"SELECT DISTINCT parent.code FROM {TABLE} parent "
                f"JOIN {TABLE} child ON child.parent_id = parent.id"
            )).fetchall()
        }
        for code in others:
            bind.execute(
                sa.text(f"UPDATE {TABLE} SET node_type = :node_type WHERE code = :code"),
                {"node_type": "GROUP" if code in parents else "POSTING", "code": code},
            )

    # --- the prose copy of the node type goes -------------------------------
    stale = bind.execute(
        sa.text(f"SELECT code, description FROM {TABLE} WHERE description IS NOT NULL")
    ).fetchall()
    for code, description in stale:
        marker = description.find(_NODE_TYPE_SENTENCE)
        if marker < 0:
            continue
        end = description.find(".", marker + len(_NODE_TYPE_SENTENCE))
        trimmed = (description[:marker] + (description[end + 1:] if end >= 0 else "")).strip()
        bind.execute(
            sa.text(f"UPDATE {TABLE} SET description = :description WHERE code = :code"),
            {"description": trimmed or None, "code": code},
        )

    # --- the promise this revision makes ------------------------------------
    incomplete = bind.execute(
        sa.text(
            f"SELECT count(*) FROM {TABLE} WHERE code IN :codes AND ("
            "node_type IS NULL OR is_contra IS NULL OR review_sensitive IS NULL "
            "OR normal_balance IS NULL)"
        ).bindparams(sa.bindparam("codes", expanding=True)),
        {"codes": sorted(canonical_targets) or [""]},
    ).scalar()
    if incomplete:
        raise RuntimeError(
            f"{incomplete} canonical account(s) still have no explicit semantics after the "
            "backfill. Refusing to leave the catalog half-defined."
        )


def downgrade() -> None:
    """Remove the four columns and their two constraints. Nothing else."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if is_sqlite:
        with op.batch_alter_table(TABLE, schema=None, recreate="always") as batch_op:
            # Dropped FIRST: a rebuilt table that still declared a constraint
            # over a dropped column would be invalid.
            for name, _ in _NEW_CHECKS:
                batch_op.drop_constraint(name, type_="check")
            for name, _, _, _ in reversed(_NEW_COLUMNS):
                batch_op.drop_column(name)
    else:
        for name, _ in _NEW_CHECKS:
            op.drop_constraint(name, TABLE, type_="check")
        for name, _, _, _ in reversed(_NEW_COLUMNS):
            op.drop_column(TABLE, name)
