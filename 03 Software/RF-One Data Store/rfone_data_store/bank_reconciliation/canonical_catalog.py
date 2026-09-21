"""The canonical RF-One restaurant accounting catalog
(BANK_CANONICAL_ACCOUNTING_CATALOG_001 /
BANK_ACCOUNTING_CLASSIFICATION_SEMANTICS_001 /
BANK_CANONICAL_ACCOUNTING_CORRECTIONS_001 /
BANK_CANONICAL_MIGRATION_IMMUTABILITY_001).

This module is the RUNTIME / CURRENT-STATE side of the catalog. It answers
"what is the approved chart of accounts NOW, and does this database agree
with it". It is NOT what Alembic history runs on — see the separation
below, and `migrations/migration_data/README.md`.

RF-One defines its own Chart of Accounts. It is not waiting for, and is not
derived from, the accountant's QuickBooks structure: `Bank/RfBank.xlsx` is
historical classification EVIDENCE, never the semantic source of truth.
Kermali may later review and approve tax/accounting mappings on top of this
catalog, and doing so must not require changing RF-One's own meaning.

The definition lives in `canonical/RFONE_RESTAURANT_COA_V1.csv`, inside the
package and therefore under version control and shipped with the code. That
is what makes a fresh or production database able to seed the identical
catalog through the ordinary deployment, with no manual SQL and no XLSX
upload. The CSV — not the database — remains the canonical definition, and
it keeps evolving as the Product Owner approves changes (134 accounts at
first approval, 136 after the equity/disposal corrections).

**Two concerns, deliberately kept apart**
(BANK_CANONICAL_MIGRATION_IMMUTABILITY_001):

* MIGRATION-TIME SEEDING — what the catalog WAS at a given Alembic
  revision. Each revision carries its own frozen copy of its input, in
  `migrations/migration_data/` or inline in the revision file, and NEVER
  reads the CSV below. That is what lets a database built from `base`
  years from now reproduce the same history: 134 accounts at
  `b8d3f1a72c64`, still 134 with explicit semantics at `c5f8b2e91a47`,
  136 after the corrections in `d7a4c9e2f318`.
* RUNTIME / CURRENT CANONICAL RECONCILIATION — this module. `seed`,
  `validate_hierarchy` and `semantic_problems` all compare a live database
  against the CURRENT CSV, which is exactly what they should do: they
  answer "is this database the approved catalog today?", a question whose
  answer must change when the approved catalog changes.

Editing the CSV therefore changes what the application bootstraps and
validates against, and changes nothing about what any shipped migration
does.

`seed` reuses the existing importer (`what_catalog_import.parse` +
`apply_import`) rather than re-implementing validation, so the canonical
load is subject to exactly the same rules as an operator's own upload:
structure only, totals and headings skipped, statement type mandatory,
parent and child in the same statement, and — the property that matters
most here — **a code that already exists with a different meaning is a
conflict, never an overwrite**. Since
BANK_ACCOUNTING_CLASSIFICATION_SEMANTICS_001 "meaning" includes the four
semantic fields: the same code under the same name but with a different
node type, normal balance, contra flag or review sensitivity is a
canonical-definition conflict, reported rather than silently accepted.

Four facts are now columns on `BankAccountingClassification` rather than
inferences:

* `node_type` — GROUP / POSTING / POSTING_CATEGORY. Read, never derived
  from whether the account currently has children. A GROUP may legitimately
  be empty for a while; a POSTING_CATEGORY may legitimately have children
  (2600 Loans & Financing does: a bank line says "loan", never short vs
  long term).
* `is_contra` — the account subtracts from its reporting group. Reporting
  reads this and `normal_balance`; there is no list of contra account codes
  anywhere in this repository any more.
* `review_sensitive` — a residual account a human may select explicitly but
  that automated recognition must never fall back to.
* `normal_balance` — DEBIT / CREDIT, which is what signs a subtree total.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
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

GROUP = what_catalog_import.GROUP
POSTING = what_catalog_import.POSTING
POSTING_CATEGORY = what_catalog_import.POSTING_CATEGORY
NODE_TYPES = what_catalog_import.NODE_TYPES

DEBIT = what_catalog_import.DEBIT
CREDIT = what_catalog_import.CREDIT
NORMAL_BALANCES = what_catalog_import.NORMAL_BALANCES

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
    """The CURRENT canonical rows, parsed straight from the CSV.

    Deliberately not used by any Alembic revision: a migration runs on its
    own frozen snapshot, so that editing this CSV can never change what a
    shipped migration did (BANK_CANONICAL_MIGRATION_IMMUTABILITY_001)."""
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
    """Reconcile this database with the CURRENT canonical catalog. Idempotent.

    This is the runtime path, not the migration path. It reads the live
    CSV on purpose: its job is to answer "does this database hold the
    approved catalog as approved TODAY", so it must follow the CSV as the
    CSV evolves. Alembic history runs on frozen per-revision snapshots and
    is unaffected by anything this function reads.

    A second run creates nothing and changes nothing: every code already
    present with the same name AND the same semantics is counted as
    unchanged. A code present with a different name, or with the same name
    but a different node type, normal balance, contra flag or review
    sensitivity, is a conflict — and with `strict` (the default) that
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

    blank = [
        row.code for row in parsed.importable_rows
        if not row.states_full_semantics
    ]
    if blank:
        raise ValueError(
            f"The canonical catalog {CATALOG_VERSION} leaves account semantics blank for "
            + ", ".join(sorted(blank))
            + ". Every canonical account states its node type, normal balance, contra flag "
            "and review sensitivity explicitly."
        )

    for row in parsed.rows:
        row.source_label = CATALOG_VERSION

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


def is_posting_account(classification: "m.BankAccountingClassification") -> bool:
    """Whether this classification may be posted to at all.

    Read from `node_type`. Until
    BANK_ACCOUNTING_CLASSIFICATION_SEMANTICS_001 this was derived as "a
    classification with children is a group", which was true of this
    catalog but was a structural coincidence rather than a stated fact."""
    return classification.is_posting_account


def may_receive_automatic_classification(
    classification: "m.BankAccountingClassification | None",
) -> bool:
    """Whether automated recognition may land a transaction on this account.

    The single place that rule lives. A GROUP never may — it is a reporting
    node, not a destination. A review-sensitive account never may either:
    those exist for genuine residual cases a human recognises, and reaching
    for one because nothing better matched is exactly the behaviour the
    catalog forbids. An incomplete account (no statement side) never may.

    An explicit human decision does NOT go through here: a human may select
    a review-sensitive account, and their decision keeps precedence over
    every automated rule."""
    return classification is not None and classification.may_receive_automatic_classification


def contra_accounts(session: Session) -> list["m.BankAccountingClassification"]:
    """The accounts that subtract from their reporting group, read from the
    data. There is deliberately no hardcoded list of contra account codes."""
    return list(session.scalars(
        select(m.BankAccountingClassification)
        .where(m.BankAccountingClassification.is_contra.is_(True))
        .order_by(m.BankAccountingClassification.code)
    ).all())


def review_sensitive_accounts(session: Session) -> list["m.BankAccountingClassification"]:
    """The accounts a human may select but automated recognition may not."""
    return list(session.scalars(
        select(m.BankAccountingClassification)
        .where(m.BankAccountingClassification.review_sensitive.is_(True))
        .order_by(m.BankAccountingClassification.code)
    ).all())


def subtree(session: Session, root_code: str) -> list["m.BankAccountingClassification"]:
    """Every account at or below `root_code`, the root first."""
    root = by_code(session, root_code)
    if root is None:
        return []
    found = [root]
    seen = {root.id}
    frontier = [root.id]
    while frontier:
        children = session.scalars(
            select(m.BankAccountingClassification)
            .where(m.BankAccountingClassification.parent_id.in_(frontier))
            .order_by(m.BankAccountingClassification.code)
        ).all()
        children = [child for child in children if child.id not in seen]
        if not children:
            break
        found.extend(children)
        seen.update(child.id for child in children)
        frontier = [child.id for child in children]
    return found


def subtree_codes(session: Session, root_code: str) -> set[str]:
    """Every code at or below `root_code`. Used by the P&L presentation, which
    is computed from the hierarchy — no total is ever a stored account."""
    return {row.code for row in subtree(session, root_code)}


# ---------------------------------------------------------------------------
# Reporting: a subtree total, signed from the data
# ---------------------------------------------------------------------------


def signed_subtree(
    session: Session, root_code: str,
) -> list[tuple["m.BankAccountingClassification", int]]:
    """Every postable account under `root_code`, each with the sign that
    expresses it in the ROOT's natural direction.

    The sign is read from `normal_balance`: an account that sits on the
    opposite side of the ledger from its reporting root reduces that root's
    total. That is what makes 4910 Discounts / Comps subtract from Revenue
    and 1590 Accumulated Depreciation subtract from Fixed Assets without
    anything in this repository knowing those code numbers.

    `is_contra` is the catalog's DECLARATION of that same fact, and
    `semantic_problems` checks the two agree; the arithmetic itself is
    driven by `normal_balance` so that an account which reverses its group
    without being called a contra account is still summed correctly."""
    root = by_code(session, root_code)
    if root is None or root.normal_balance is None:
        return []
    return [
        (account, 1 if account.normal_balance == root.normal_balance else -1)
        for account in subtree(session, root_code)
        if account.is_posting_account and account.normal_balance is not None
    ]


def subtree_total(session: Session, root_code: str, amounts: dict[str, int]) -> int:
    """`amounts` are per-account balances stated in each account's OWN normal
    direction. The result is the subtree total in the root's direction.

    Net Revenue is `subtree_total(session, "4000", amounts)`: the positive
    revenue accounts minus the contra-revenue ones, with no list of codes
    subtracted by hand anywhere."""
    return sum(
        sign * amounts.get(account.code, 0)
        for account, sign in signed_subtree(session, root_code)
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


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


def semantic_problems(session: Session) -> list[str]:
    """Every rule the four semantic fields must satisfy for the CANONICAL
    accounts. An empty list means the catalog's semantics are sound.

    Only canonical codes are judged: a legacy-migrated row whose statement
    side was never determinable legitimately has no normal balance, and
    inventing one for it is exactly what this repository refuses to do."""
    problems: list[str] = []
    canonical = {row["Code"]: row for row in catalog_rows()}
    rows = session.scalars(select(m.BankAccountingClassification)).all()
    by_id = {row.id: row for row in rows}

    for row in rows:
        if row.node_type not in NODE_TYPES:
            problems.append(f"{row.code}: node type is {row.node_type!r}")
        if row.normal_balance is not None and row.normal_balance not in NORMAL_BALANCES:
            problems.append(f"{row.code}: normal balance is {row.normal_balance!r}")

        if row.code not in canonical:
            continue
        expected = canonical[row.code]
        if row.node_type != expected["Node Type"].strip():
            problems.append(
                f"{row.code}: node type is {row.node_type!r}, the canonical catalog says "
                f"{expected['Node Type'].strip()!r}"
            )
        if row.normal_balance != expected["Normal Balance"].strip():
            problems.append(
                f"{row.code}: normal balance is {row.normal_balance!r}, the canonical catalog "
                f"says {expected['Normal Balance'].strip()!r}"
            )
        if bool(row.is_contra) != what_catalog_import.parse_flag(expected["Is Contra"]):
            problems.append(f"{row.code}: contra flag disagrees with the canonical catalog")
        if bool(row.review_sensitive) != what_catalog_import.parse_flag(
            expected["Review Sensitive"]
        ):
            problems.append(
                f"{row.code}: review-sensitive flag disagrees with the canonical catalog"
            )

        # A contra account must actually reverse its parent, or calling it
        # contra says nothing a report can act on.
        if row.is_contra:
            parent = by_id.get(row.parent_id) if row.parent_id is not None else None
            if parent is None:
                problems.append(f"{row.code}: marked contra but has no reporting group")
            elif parent.normal_balance is None:
                problems.append(
                    f"{row.code}: marked contra but its group {parent.code} has no normal balance"
                )
            elif parent.normal_balance == row.normal_balance:
                problems.append(
                    f"{row.code}: marked contra but sits on the same side ({row.normal_balance}) "
                    f"as its group {parent.code}"
                )
            if not row.is_posting_account:
                problems.append(f"{row.code}: marked contra but is a {row.node_type}")

        if row.review_sensitive and not row.is_posting_account:
            problems.append(f"{row.code}: marked review-sensitive but is a {row.node_type}")

    return problems
