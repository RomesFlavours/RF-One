"""seed the canonical RF-One restaurant accounting catalog

Revision ID: b8d3f1a72c64
Revises: a4e2f8c15b73
Create Date: 2026-09-21

BANK_CANONICAL_ACCOUNTING_CATALOG_001 — a DATA migration only. No table is
created, altered or dropped, and the schema is byte-identical before and
after.

Why a migration rather than a startup hook or a manual upload: the
canonical chart must simply BE there after an ordinary deployment, in
every environment, without anyone running SQL or uploading a spreadsheet,
and without any per-request work that could rewrite data. A data migration
is the mechanism this repository already uses for exactly that (see
`8ddfe6f314be`, `c1a9f0d3e7b2`, `f1c7a94d6e02`), so no second deployment
framework is introduced to avoid a revision.

The rows come from the version-controlled definition that ships inside the
package:

    rfone_data_store/bank_reconciliation/canonical/RFONE_RESTAURANT_COA_V1.csv

They are read with the standard library and written with SQLAlchemy Core,
NOT through the ORM. A migration must keep working against the schema of
its own revision, and importing the ORM would couple this file to whatever
`models.py` looks like in the future. The general-purpose importer
(`what_catalog_import`) remains the validated path for an operator's own
upload and is what the canonical seeder and the tests use; this migration
is a pinned load of an already-validated definition.

Idempotent and non-destructive:

* a code that is already present with the SAME name is left untouched;
* a code present with a DIFFERENT name RAISES — an account that historical
  decisions may reference by code is never silently redefined;
* nothing is ever deleted or deactivated.

Downgrade removes only the rows this migration inserted, and only those
still untouched: any account a human has since renamed, reparented or
pointed a Why at is kept, because removing it would break decisions that
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
revision: str = 'b8d3f1a72c64'
down_revision: Union[str, Sequence[str], None] = 'a4e2f8c15b73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CATALOG_VERSION = "RFONE_RESTAURANT_COA_V1"

# Located relative to this file so the migration works from any working
# directory, exactly as `alembic upgrade head` is run in deployment.
_CATALOG_PATH = (
    Path(__file__).resolve().parents[2]
    / "rfone_data_store" / "bank_reconciliation" / "canonical"
    / f"{CATALOG_VERSION}.csv"
)

_SOURCE_NOTE = (
    f"Canonical RF-One restaurant accounting catalog ({CATALOG_VERSION}). "
    "RF-One's own semantics — not derived from QuickBooks/Kermali, which may map onto "
    "this catalog later without changing its meaning. Seeded by migration b8d3f1a72c64."
)


def _canonical_rows() -> list[dict]:
    text = _CATALOG_PATH.read_text(encoding="utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise RuntimeError(f"The canonical catalog {_CATALOG_PATH} is empty.")
    return rows


def upgrade() -> None:
    """Seed the canonical catalog."""
    bind = op.get_bind()
    rows = _canonical_rows()

    existing = {
        row[0]: (row[1], row[2])
        for row in bind.execute(
            sa.text("SELECT code, name, id FROM bank_accounting_classifications")
        ).fetchall()
    }

    conflicts = [
        f"{row['Code']}: already present as {existing[row['Code']][0]!r}, the canonical "
        f"catalog says {row['Name']!r}"
        for row in rows
        if row["Code"] in existing
        and existing[row["Code"]][0].strip().casefold() != row["Name"].strip().casefold()
    ]
    if conflicts:
        raise RuntimeError(
            "Refusing to seed the canonical accounting catalog: these codes already exist "
            "with a different meaning, and an account referenced by historical decisions is "
            "never silently redefined. Resolve them by hand, then re-run the migration. "
            + "; ".join(conflicts)
        )

    # Pass 1 — insert every missing account, unparented.
    to_insert = [row for row in rows if row["Code"] not in existing]
    for row in to_insert:
        description = f"{_SOURCE_NOTE} Node type: {row.get('Node Type') or 'POSTING'}."
        bind.execute(
            sa.text(
                "INSERT INTO bank_accounting_classifications "
                "(code, name, statement_type, parent_id, description, active) "
                "VALUES (:code, :name, :statement_type, NULL, :description, :active)"
            ),
            {
                "code": row["Code"],
                "name": row["Name"],
                "statement_type": row["Statement Type"],
                "description": description,
                "active": True,
            },
        )

    # Pass 2 — link parents, now that every account exists.
    ids = {
        code: identifier
        for code, identifier in bind.execute(
            sa.text("SELECT code, id FROM bank_accounting_classifications")
        ).fetchall()
    }
    inserted_codes = {row["Code"] for row in to_insert}
    for row in rows:
        parent_code = (row.get("Parent") or "").strip()
        if not parent_code or row["Code"] not in inserted_codes:
            continue
        parent_id = ids.get(parent_code)
        if parent_id is None:
            raise RuntimeError(
                f"The canonical catalog names parent {parent_code!r} for {row['Code']}, "
                "but no such account exists after seeding."
            )
        bind.execute(
            sa.text(
                "UPDATE bank_accounting_classifications SET parent_id = :parent_id "
                "WHERE code = :code"
            ),
            {"parent_id": parent_id, "code": row["Code"]},
        )


def downgrade() -> None:
    """Remove the seeded accounts that are still untouched.

    An account a human has since renamed, or that a Why or a historical
    decision now references, is DELIBERATELY KEPT: removing it would break
    records that point at it, and a downgrade must not destroy accounting
    history to tidy up a catalog."""
    bind = op.get_bind()
    rows = _canonical_rows()

    referenced_by_reason = {
        row[0] for row in bind.execute(sa.text(
            "SELECT DISTINCT accounting_classification_id FROM bank_transaction_reasons "
            "WHERE accounting_classification_id IS NOT NULL"
        )).fetchall()
    }
    referenced_by_decision = {
        row[0] for row in bind.execute(sa.text(
            "SELECT DISTINCT accounting_classification_id FROM bank_transaction_explanations "
            "WHERE accounting_classification_id IS NOT NULL"
        )).fetchall()
    }
    referenced = referenced_by_reason | referenced_by_decision

    current = {
        row[0]: (row[1], row[2])
        for row in bind.execute(sa.text(
            "SELECT code, name, id FROM bank_accounting_classifications"
        )).fetchall()
    }

    removable: list[str] = []
    for row in rows:
        entry = current.get(row["Code"])
        if entry is None:
            continue
        name, identifier = entry
        if name.strip().casefold() != row["Name"].strip().casefold():
            continue  # renamed by a human — left alone
        if identifier in referenced:
            continue  # in use — left alone
        removable.append(row["Code"])

    # Children first, so a parent is never deleted out from under one.
    for code in sorted(removable, reverse=True):
        bind.execute(
            sa.text(
                "DELETE FROM bank_accounting_classifications WHERE code = :code "
                "AND NOT EXISTS (SELECT 1 FROM bank_accounting_classifications child "
                "WHERE child.parent_id = bank_accounting_classifications.id)"
            ),
            {"code": code},
        )
