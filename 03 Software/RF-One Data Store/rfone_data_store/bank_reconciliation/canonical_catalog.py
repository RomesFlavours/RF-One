"""The canonical RF-One restaurant accounting catalog
(BANK_CANONICAL_ACCOUNTING_CATALOG_001).

RF-One defines its own Chart of Accounts. It is not waiting for, and is not
derived from, the accountant's QuickBooks structure: `Bank/RfBank.xlsx` is
historical classification EVIDENCE, never the semantic source of truth.
Kermali may later review and approve tax/accounting mappings on top of this
catalog, and doing so must not require changing RF-One's own meaning.

The definition lives in `canonical/RFONE_RESTAURANT_COA_V1.csv`, inside the
package and therefore under version control and shipped with the code. That
is what makes a fresh or production database able to seed the identical
catalog through the ordinary deployment, with no manual SQL and no XLSX
upload.

`seed` reuses the existing importer (`what_catalog_import.parse` +
`apply_import`) rather than re-implementing validation, so the canonical
load is subject to exactly the same rules as an operator's own upload:
structure only, totals and headings skipped, statement type mandatory,
parent and child in the same statement, and — the property that matters
most here — **a code that already exists with a different meaning is a
conflict, never an overwrite**.

Node types (GROUP / POSTING / CONTRA / REVIEW-SENSITIVE) are recorded in
the row's description because `BankAccountingClassification` has no field
for them; `is_posting_account` derives "may be posted to" from the
hierarchy instead, since a group is exactly a classification that has
children. See MISSING_MODEL_CAPABILITIES for the precise gap, reported
rather than worked around with a second accounting model.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from . import what_catalog_import

CATALOG_VERSION = "RFONE_RESTAURANT_COA_V1"
CATALOG_PATH = Path(__file__).resolve().parent / "canonical" / f"{CATALOG_VERSION}.csv"

SOURCE_NOTE = (
    f"Canonical RF-One restaurant accounting catalog ({CATALOG_VERSION}). "
    "RF-One's own semantics — not derived from QuickBooks/Kermali, which may map onto "
    "this catalog later without changing its meaning."
)

# Reported, deliberately NOT invented. Each of these is a real property of
# the approved chart that `BankAccountingClassification` cannot express as a
# queryable field today. None of them blocks this task — every one is either
# derivable or descriptive — so no second accounting model was created.
MISSING_MODEL_CAPABILITIES = (
    (
        "node_type",
        "GROUP vs POSTING vs POSTING_CATEGORY. Derived here as 'a classification with "
        "children is a group', which is true of this catalog but is a structural "
        "coincidence rather than a stated fact. A posting-account flag would let the "
        "service layer refuse a Why pointing at a presentation node even in a catalog "
        "where a group legitimately has no children yet.",
    ),
    (
        "contra",
        "1590 Accumulated Depreciation, 4910 Discounts/Comps and 4920 Refunds/Returns are "
        "contra accounts: they belong to their parent's subtree but subtract from it. A "
        "report that sums a subtree has no way to know this from the model, so Net Revenue "
        "is computed with an explicit contra list rather than read from the data.",
    ),
    (
        "review_sensitive",
        "6900, 7880, 8500 and 8600 exist but must never be an automatic fallback for "
        "'unknown'. The catalog says so in prose; nothing enforces it at the model level.",
    ),
)

# Contra accounts, by code. Stated here because the model cannot carry the
# fact (see MISSING_MODEL_CAPABILITIES) and a subtree sum would otherwise
# add what should be subtracted.
CONTRA_REVENUE_CODES = ("4910", "4920")
CONTRA_ASSET_CODES = ("1590",)

# Accounts that exist but must never be chosen automatically. "I don't know"
# is REVIEW_REQUIRED, never Miscellaneous.
REVIEW_SENSITIVE_CODES = ("6900", "7880", "8500", "8600")

# Subtree roots the P&L presentation is computed from.
REVENUE_ROOT = "4000"
COGS_ROOT = "5000"
LABOR_ROOT = "6000"
OPERATING_ROOT = "7000"
OTHER_ROOT = "8000"
DEPRECIATION_CODE = "8300"


def catalog_bytes() -> bytes:
    """The canonical definition as shipped. Read from the package, so every
    environment seeds byte-identical content."""
    return CATALOG_PATH.read_bytes()


def catalog_rows() -> list[dict]:
    """The canonical rows, parsed straight from the CSV — used by the
    Alembic data migration, which must not depend on the ORM."""
    text = catalog_bytes().decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


@dataclass
class SeedOutcome:
    created: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.conflicts


def seed(session: Session, *, strict: bool = True) -> SeedOutcome:
    """Install the canonical catalog. Idempotent.

    A second run creates nothing and changes nothing: every code already
    present with the same name is counted as unchanged. A code present with
    a DIFFERENT name is a conflict — and with `strict` (the default) that
    raises, loudly, rather than mutating an account that historical
    decisions may already reference by code.

    Nothing is ever deleted, and an account a human has since renamed or
    deactivated is left exactly as it is."""
    parsed = what_catalog_import.parse(
        catalog_bytes(), file_name=f"{CATALOG_VERSION}.csv",
    )
    if parsed.file_anomalies:
        raise ValueError(
            f"The canonical catalog {CATALOG_VERSION} is not loadable: "
            + "; ".join(parsed.file_anomalies)
        )

    # The node type belongs on the row, and the model has nowhere to put it,
    # so it goes into the description where a reader can at least see it.
    node_types = {row["Code"]: row.get("Node Type", "") for row in catalog_rows()}
    for row in parsed.rows:
        node_type = node_types.get(row.code or "", "")
        if node_type:
            row.source_label = f"{CATALOG_VERSION} · {node_type}"

    outcome = what_catalog_import.apply_import(session, parsed, source_note=SOURCE_NOTE)
    result = SeedOutcome(
        created=list(outcome.created),
        unchanged=list(outcome.unchanged),
        conflicts=list(outcome.conflicts),
    )
    if strict and result.conflicts:
        raise ValueError(
            f"The canonical catalog {CATALOG_VERSION} conflicts with what is already in "
            "this database, and nothing was overwritten. Resolve these by hand: "
            + "; ".join(result.conflicts)
        )
    return result


# ---------------------------------------------------------------------------
# Reading the catalog back
# ---------------------------------------------------------------------------


def by_code(session: Session, code: str) -> "m.BankAccountingClassification | None":
    return session.scalars(
        select(m.BankAccountingClassification)
        .where(m.BankAccountingClassification.code == code)
    ).first()


def is_posting_account(session: Session, classification: "m.BankAccountingClassification") -> bool:
    """Whether this classification may be posted to.

    Derived: a classification with children is a presentation group. See
    MISSING_MODEL_CAPABILITIES — the model has no node-type field, and this
    derivation is what stands in for one."""
    children = session.scalar(
        select(func.count(m.BankAccountingClassification.id))
        .where(m.BankAccountingClassification.parent_id == classification.id)
    ) or 0
    return children == 0


def subtree_codes(session: Session, root_code: str) -> set[str]:
    """Every code at or below `root_code`. Used by the P&L presentation, which
    is computed from the hierarchy — no total is ever a stored account."""
    root = by_code(session, root_code)
    if root is None:
        return set()
    codes = {root.code}
    frontier = [root.id]
    while frontier:
        children = session.scalars(
            select(m.BankAccountingClassification)
            .where(m.BankAccountingClassification.parent_id.in_(frontier))
        ).all()
        if not children:
            break
        codes.update(child.code for child in children)
        frontier = [child.id for child in children]
    return codes


def validate_hierarchy(session: Session) -> list[str]:
    """Every structural rule the catalog must satisfy, checked against what is
    actually stored. An empty list means the catalog is sound."""
    problems: list[str] = []
    rows = session.scalars(select(m.BankAccountingClassification)).all()
    by_id = {row.id: row for row in rows}

    for row in rows:
        if row.statement_type not in (
            what_catalog_import.PROFIT_LOSS, what_catalog_import.BALANCE_SHEET
        ):
            problems.append(f"{row.code}: statement type is {row.statement_type!r}")
        if row.parent_id is None:
            continue
        parent = by_id.get(row.parent_id)
        if parent is None:
            problems.append(f"{row.code}: parent {row.parent_id} does not exist")
            continue
        if parent.statement_type != row.statement_type:
            problems.append(
                f"{row.code}: {row.statement_type} under a {parent.statement_type} parent "
                f"({parent.code})"
            )
        # Walk to the root, guarding against a cycle.
        seen = {row.id}
        current = parent
        while current is not None and current.parent_id is not None:
            if current.parent_id in seen:
                problems.append(f"{row.code}: its ancestry contains a cycle")
                break
            seen.add(current.parent_id)
            current = by_id.get(current.parent_id)

    codes = [row.code for row in rows]
    duplicates = {code for code in codes if codes.count(code) > 1}
    for code in sorted(duplicates):
        problems.append(f"{code}: appears more than once")
    return problems
