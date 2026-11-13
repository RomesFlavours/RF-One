"""correct member draws and split the asset disposal account

Revision ID: d7a4c9e2f318
Revises: c5f8b2e91a47
Create Date: 2026-09-21

BANK_CANONICAL_ACCOUNTING_CORRECTIONS_001 — a DATA migration only. No
table is created, altered or dropped, and the schema is byte-identical
before and after. It resolves the two accounting questions the previous
task left open, now decided by the Product Owner.

1. 3400 Member Distributions / Draws

   A distribution REDUCES equity. Carrying it as an ordinary credit
   account made the Equity subtree add what it should subtract, so the
   account becomes DEBIT and CONTRA. Its code, name, statement side
   (Balance Sheet) and parent are untouched: only the semantics that were
   wrong are corrected.

2. 8400 Gain / Loss on Asset Disposal

   One posting account cannot have an unambiguous normal balance for both
   a gain and a loss, so the sign would have had to be guessed at
   reporting time. 8400 becomes a GROUP and gains two posting children:

       8410 Gain on Asset Disposal   CREDIT
       8420 Loss on Asset Disposal   DEBIT

   A disposal workflow chooses between them from the actual economic
   result, never from the sign of a bank line. 8400 keeps its code, name
   and parent; it simply stops being a destination.

The canonical catalog therefore grows from 134 to 136 accounts. No other
account changes.

This revision touches four accounts, so it CARRIES THEIR VALUES INLINE
(`_CORRECTIONS` below) rather than reading any file
(BANK_CANONICAL_MIGRATION_IMMUTABILITY_001). It originally read the live
canonical definition at
`rfone_data_store/bank_reconciliation/canonical/RFONE_RESTAURANT_COA_V1.csv`,
which is the CURRENT canonical source of truth and is actively
maintained — so a later approved change to it would have changed what
this September 2026 revision does. Four rows are small enough that a
frozen snapshot file would be more indirection than data; the sibling
revisions, which need 134 rows each, use
`migrations/migration_data/` instead.

Writes go through SQLAlchemy Core, NOT the ORM: a migration must keep
working against the schema of its own revision.

Idempotent and non-destructive:

* a fresh database reaches this revision with the 134 historical accounts
  `b8d3f1a72c64` seeded and `c5f8b2e91a47` gave semantics to, and leaves
  it with the same 136 an existing database does — the chain, not the
  current catalog file, is what makes the two identical;
* re-running it writes the same values and inserts nothing twice;
* a code present with a DIFFERENT name RAISES: an account that historical
  decisions may reference by code is never silently redefined;
* no classification, decision, recognition rule, raw row or transaction
  is read or written.

Downgrade restores 3400 and 8400 to what c5f8b2e91a47 left, and removes
8410/8420 only while they are still untouched and unreferenced — an
account a human has renamed, or that a Why or a historical decision now
points at, is kept, because removing it would break records that
reference it.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd7a4c9e2f318'
down_revision: Union[str, Sequence[str], None] = 'c5f8b2e91a47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "bank_accounting_classifications"
CATALOG_VERSION = "RFONE_RESTAURANT_COA_V1"

_SOURCE_NOTE = (
    f"Canonical RF-One restaurant accounting catalog ({CATALOG_VERSION}). "
    "RF-One's own semantics — not derived from QuickBooks/Kermali, which may map onto "
    "this catalog later without changing its meaning. Added by migration d7a4c9e2f318."
)

# The four codes this revision touches, and nothing else.
CORRECTED_CODES = ("3400", "8400")
NEW_CODES = ("8410", "8420")

# This revision's frozen input, inline. IMMUTABLE: editing it would change
# what a shipped migration does. A correction is a new revision.
# Code -> (name, statement type, parent, node type, normal balance, contra,
# review-sensitive).
_CORRECTIONS = {
    "3400": ("Member Distributions / Draws", "BALANCE_SHEET", "3000",
             "POSTING", "DEBIT", True, False),
    "8400": ("Gain / Loss on Asset Disposal", "PROFIT_LOSS", "8000",
             "GROUP", "CREDIT", False, False),
    "8410": ("Gain on Asset Disposal", "PROFIT_LOSS", "8400",
             "POSTING", "CREDIT", False, False),
    "8420": ("Loss on Asset Disposal", "PROFIT_LOSS", "8400",
             "POSTING", "DEBIT", False, False),
}

# What c5f8b2e91a47 left, so the downgrade puts back exactly that.
_PREVIOUS = {
    "3400": ("POSTING", "CREDIT", False),
    "8400": ("POSTING", "CREDIT", False),
}


def upgrade() -> None:
    """Correct 3400, turn 8400 into a group, add 8410 and 8420."""
    bind = op.get_bind()

    existing = {
        row[0]: row[1]
        for row in bind.execute(sa.text(f"SELECT code, name FROM {TABLE}")).fetchall()
    }

    # An account already present under a DIFFERENT name means a human has
    # repurposed that code. Imposing the canonical meaning on it would
    # redefine an account historical decisions already reference.
    conflicts = [
        f"{code}: already present as {existing[code]!r}, this revision means "
        f"{_CORRECTIONS[code][0]!r}"
        for code in CORRECTED_CODES + NEW_CODES
        if code in existing
        and existing[code].strip().casefold() != _CORRECTIONS[code][0].strip().casefold()
    ]
    if conflicts:
        raise RuntimeError(
            "Refusing to apply the canonical accounting corrections: these codes already exist "
            "with a different meaning, and an account referenced by historical decisions is "
            "never silently redefined. Resolve them by hand, then re-run the migration. "
            + "; ".join(conflicts)
        )

    # --- 1/2. the two corrections ------------------------------------------
    for code in CORRECTED_CODES:
        if code not in existing:
            # A database that never had this account gets it from the seed
            # migration, not from here.
            continue
        _, _, _, node_type, normal_balance, is_contra, review_sensitive = _CORRECTIONS[code]
        bind.execute(
            sa.text(
                f"UPDATE {TABLE} SET node_type = :node_type, normal_balance = :normal_balance, "
                "is_contra = :is_contra, review_sensitive = :review_sensitive WHERE code = :code"
            ),
            {
                "node_type": node_type,
                "normal_balance": normal_balance,
                "is_contra": is_contra,
                "review_sensitive": review_sensitive,
                "code": code,
            },
        )

    # --- 3. the two new posting accounts -----------------------------------
    to_insert = [code for code in NEW_CODES if code not in existing]
    for code in to_insert:
        name, statement_type, _, node_type, normal_balance, is_contra, review_sensitive = (
            _CORRECTIONS[code]
        )
        bind.execute(
            sa.text(
                f"INSERT INTO {TABLE} "
                "(code, name, statement_type, parent_id, description, active, "
                " node_type, is_contra, review_sensitive, normal_balance) "
                "VALUES (:code, :name, :statement_type, NULL, :description, :active, "
                " :node_type, :is_contra, :review_sensitive, :normal_balance)"
            ),
            {
                "code": code,
                "name": name,
                "statement_type": statement_type,
                "description": _SOURCE_NOTE,
                "active": True,
                "node_type": node_type,
                "is_contra": is_contra,
                "review_sensitive": review_sensitive,
                "normal_balance": normal_balance,
            },
        )

    if to_insert:
        ids = {
            code: identifier
            for code, identifier in bind.execute(
                sa.text(f"SELECT code, id FROM {TABLE}")
            ).fetchall()
        }
        for code in to_insert:
            parent_code = _CORRECTIONS[code][2]
            parent_id = ids.get(parent_code)
            if parent_id is None:
                raise RuntimeError(
                    f"This revision names parent {parent_code!r} for {code}, but no such "
                    "account exists in this database."
                )
            bind.execute(
                sa.text(f"UPDATE {TABLE} SET parent_id = :parent_id WHERE code = :code"),
                {"parent_id": parent_id, "code": code},
            )

    # --- the promise this revision makes ------------------------------------
    for code, expected in _CORRECTIONS.items():
        found = bind.execute(
            sa.text(
                f"SELECT node_type, normal_balance, is_contra, review_sensitive FROM {TABLE} "
                "WHERE code = :code"
            ),
            {"code": code},
        ).fetchone()
        if found is None:
            raise RuntimeError(f"{code} is missing after the corrections were applied.")
        node_type, normal_balance, is_contra, review_sensitive = found
        if (node_type, normal_balance, bool(is_contra), bool(review_sensitive)) != expected[3:]:
            raise RuntimeError(
                f"{code} still reads {(node_type, normal_balance, bool(is_contra), bool(review_sensitive))} "
                f"after the corrections; this revision means {expected[3:]}."
            )


def downgrade() -> None:
    """Put 3400 and 8400 back, and remove 8410/8420 while still untouched."""
    bind = op.get_bind()

    for code, (node_type, normal_balance, is_contra) in _PREVIOUS.items():
        bind.execute(
            sa.text(
                f"UPDATE {TABLE} SET node_type = :node_type, normal_balance = :normal_balance, "
                "is_contra = :is_contra WHERE code = :code"
            ),
            {
                "node_type": node_type, "normal_balance": normal_balance,
                "is_contra": is_contra, "code": code,
            },
        )

    referenced = {
        row[0] for row in bind.execute(sa.text(
            "SELECT DISTINCT accounting_classification_id FROM bank_transaction_reasons "
            "WHERE accounting_classification_id IS NOT NULL"
        )).fetchall()
    } | {
        row[0] for row in bind.execute(sa.text(
            "SELECT DISTINCT accounting_classification_id FROM bank_transaction_explanations "
            "WHERE accounting_classification_id IS NOT NULL"
        )).fetchall()
    }

    for code in NEW_CODES:
        found = bind.execute(
            sa.text(f"SELECT id, name FROM {TABLE} WHERE code = :code"), {"code": code},
        ).fetchone()
        if found is None:
            continue
        identifier, name = found
        if name.strip().casefold() != _CORRECTIONS[code][0].strip().casefold():
            continue  # renamed by a human — left alone
        if identifier in referenced:
            continue  # in use — left alone
        bind.execute(
            sa.text(
                f"DELETE FROM {TABLE} WHERE code = :code AND NOT EXISTS "
                f"(SELECT 1 FROM {TABLE} child WHERE child.parent_id = {TABLE}.id)"
            ),
            {"code": code},
        )
