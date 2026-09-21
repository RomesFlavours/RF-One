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

The values come from the version-controlled definition that ships inside
the package, exactly as b8d3f1a72c64 and c5f8b2e91a47 do:

    rfone_data_store/bank_reconciliation/canonical/RFONE_RESTAURANT_COA_V1.csv

read with the standard library and written with SQLAlchemy Core, NOT
through the ORM. Because that CSV is read at run time, this revision
first asserts it still says exactly what the revision was written for —
a drifted catalog fails loudly here rather than silently migrating a
database to something nobody approved.

Idempotent and non-destructive:

* on a FRESH database b8d3f1a72c64 already seeds all 136 accounts from
  the same CSV and c5f8b2e91a47 already sets their semantics, so this
  revision finds everything correct and writes nothing — the fresh and
  the upgraded database end identical;
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

import csv
import io
from pathlib import Path
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

_CATALOG_PATH = (
    Path(__file__).resolve().parents[2]
    / "rfone_data_store" / "bank_reconciliation" / "canonical"
    / f"{CATALOG_VERSION}.csv"
)

_SOURCE_NOTE = (
    f"Canonical RF-One restaurant accounting catalog ({CATALOG_VERSION}). "
    "RF-One's own semantics — not derived from QuickBooks/Kermali, which may map onto "
    "this catalog later without changing its meaning. Added by migration d7a4c9e2f318."
)

# The four codes this revision touches, and nothing else.
CORRECTED_CODES = ("3400", "8400")
NEW_CODES = ("8410", "8420")

# What the CSV must say for this revision to be the right thing to run.
# Code -> (name, statement type, parent, node type, normal balance, contra,
# review-sensitive).
_EXPECTED = {
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


def _flag(value: str) -> bool:
    return (value or "").strip().upper() in ("TRUE", "1", "YES", "Y")


def _canonical_rows() -> dict[str, dict]:
    text = _CATALOG_PATH.read_text(encoding="utf-8-sig")
    rows = {row["Code"]: row for row in csv.DictReader(io.StringIO(text))}
    if not rows:
        raise RuntimeError(f"The canonical catalog {_CATALOG_PATH} is empty.")

    drifted: list[str] = []
    for code, expected in _EXPECTED.items():
        row = rows.get(code)
        if row is None:
            drifted.append(f"{code}: not in the canonical catalog at all")
            continue
        actual = (
            row["Name"].strip(), row["Statement Type"].strip(), row["Parent"].strip(),
            row["Node Type"].strip(), row["Normal Balance"].strip(),
            _flag(row["Is Contra"]), _flag(row["Review Sensitive"]),
        )
        if actual != expected:
            drifted.append(f"{code}: catalog says {actual}, this revision expects {expected}")
    if drifted:
        raise RuntimeError(
            "The canonical catalog no longer matches what migration d7a4c9e2f318 was written "
            "for, and running it would migrate this database to something nobody approved: "
            + "; ".join(drifted)
        )
    return rows


def upgrade() -> None:
    """Correct 3400, turn 8400 into a group, add 8410 and 8420."""
    bind = op.get_bind()
    rows = _canonical_rows()

    existing = {
        row[0]: row[1]
        for row in bind.execute(sa.text(f"SELECT code, name FROM {TABLE}")).fetchall()
    }

    # An account already present under a DIFFERENT name means a human has
    # repurposed that code. Imposing the canonical meaning on it would
    # redefine an account historical decisions already reference.
    conflicts = [
        f"{code}: already present as {existing[code]!r}, the canonical catalog says "
        f"{rows[code]['Name']!r}"
        for code in CORRECTED_CODES + NEW_CODES
        if code in existing
        and existing[code].strip().casefold() != rows[code]["Name"].strip().casefold()
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
        row = rows[code]
        bind.execute(
            sa.text(
                f"UPDATE {TABLE} SET node_type = :node_type, normal_balance = :normal_balance, "
                "is_contra = :is_contra, review_sensitive = :review_sensitive WHERE code = :code"
            ),
            {
                "node_type": row["Node Type"].strip(),
                "normal_balance": row["Normal Balance"].strip(),
                "is_contra": _flag(row["Is Contra"]),
                "review_sensitive": _flag(row["Review Sensitive"]),
                "code": code,
            },
        )

    # --- 3. the two new posting accounts -----------------------------------
    to_insert = [code for code in NEW_CODES if code not in existing]
    for code in to_insert:
        row = rows[code]
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
                "name": row["Name"],
                "statement_type": row["Statement Type"],
                "description": _SOURCE_NOTE,
                "active": True,
                "node_type": row["Node Type"].strip(),
                "is_contra": _flag(row["Is Contra"]),
                "review_sensitive": _flag(row["Review Sensitive"]),
                "normal_balance": row["Normal Balance"].strip(),
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
            parent_code = rows[code]["Parent"].strip()
            parent_id = ids.get(parent_code)
            if parent_id is None:
                raise RuntimeError(
                    f"The canonical catalog names parent {parent_code!r} for {code}, but no "
                    "such account exists in this database."
                )
            bind.execute(
                sa.text(f"UPDATE {TABLE} SET parent_id = :parent_id WHERE code = :code"),
                {"parent_id": parent_id, "code": code},
            )

    # --- the promise this revision makes ------------------------------------
    for code, expected in _EXPECTED.items():
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
                f"after the corrections; the canonical catalog says {expected[3:]}."
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
        if name.strip().casefold() != _EXPECTED[code][0].strip().casefold():
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
