"""The canonical RF-One restaurant WHY catalog
(BANK_CANONICAL_WHY_AND_WHO_RELATIONSHIPS_001).

WHY is RF-One's OPERATIONAL/MANAGEMENT classification: what kind of
business purpose a transaction serves. It exists for company management,
the future Company Panel and Cognito analysis — not for the accountant.

    WHO   who the money concerns.
    WHY   what kind of business purpose it served. A Who may have ZERO,
          ONE or MANY.
    WHAT  the official P&L posting category, DERIVED from the Why.

A Why carries management granularity; a What carries P&L structure, and
the two are deliberately not the same shape. `JANITORIAL_CLEANING` and
`HOOD_CLEANING` are two purposes the business wants to see apart and both
resolve to 7810 Janitorial / Cleaning. Several Whys to one What is normal.

Every Why resolves to exactly ONE accounting destination, and what that
destination is decides whether there is a WHAT at all:

    destination is a P&L posting category   -> that IS the WHAT
    destination is a Balance Sheet account  -> NO WHAT; the transaction
                                               settles a liability, moves
                                               money between the
                                               company's own accounts, or
                                               capitalises an asset

`catalog_problems` fails loudly on any Why with no destination, two
destinations, or a destination that is a P&L GROUP.

**Management groups organise the catalog and nothing else.** They are
shown in the "+ New" modal, where 77 purposes have to be browsable, and
in a future Company Panel. Ordinary Bank reconciliation never shows one:
after the Who is chosen the operator sees only the Whys already
associated with that Who, plus "+ New".

The definition lives in `canonical/RFONE_RESTAURANT_WHY_V1.csv`, inside
the package and under version control, following the same split the
accounting catalog uses: this module reads the CURRENT file, while each
Alembic revision carries its own frozen copy and never reads this one
(BANK_CANONICAL_MIGRATION_IMMUTABILITY_001).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from . import canonical_catalog

CATALOG_VERSION = "RFONE_RESTAURANT_WHY_V1"
CATALOG_PATH = Path(__file__).resolve().parent / "canonical" / f"{CATALOG_VERSION}.csv"


def catalog_rows() -> list[dict]:
    """The CURRENT canonical WHY rows. Deliberately not read by any
    migration — a shipped revision runs on its own frozen copy."""
    return list(csv.DictReader(io.StringIO(
        CATALOG_PATH.read_text(encoding="utf-8-sig")
    )))


# ---------------------------------------------------------------------------
# Legacy labels (§17 / §18)
# ---------------------------------------------------------------------------
#
# The Product Owner's old manual labels. Design input only — never a
# source of accounting truth, and never applied to a transaction
# automatically. They exist so that typing an old word in a search box
# still finds the right canonical purpose.

LEGACY_ALIASES: dict[str, str] = {
    "Accountant": "ACCOUNTING_BOOKKEEPING",
    "Bank Costs": "BANK_SERVICE_CHARGE",
    "Bank Transfer": "INTERNAL_BANK_TRANSFER",
    "Card Fees": "MERCHANT_PROCESSING_FEE",
    "Emploees -Extra Cost": "OTHER_PERSONNEL_COST",
    "General Liability": "GENERAL_LIABILITY_INSURANCE",
    "Home": "OWNER_PERSONAL_HOME",
    "Improving": "LEASEHOLD_IMPROVEMENT",
    "Lease Central st": "BASE_RENT",
    "Lease Morse": "BASE_RENT",
    "Lease Storage": "STORAGE_RENT",
    "Legal": "LEGAL",
    "Licences": "LICENSES_PERMITS",
    "Maintenance": "FACILITY_MAINTENANCE",
    "Marketing": "MARKETING_ADVERTISING",
    "New Appliances": "EQUIPMENT_PURCHASE_CAPEX",
    "Payroll - BOH": "BOH_REGULAR_PAYROLL",
    "Payroll - FOH": "FOH_REGULAR_PAYROLL",
    "Payroll - Management": "MANAGEMENT_PAYROLL",
    "Payroll - Tax": "EMPLOYER_PAYROLL_TAX",
    "Personal - Food": "OWNER_PERSONAL_FOOD",
    "Personal - Healt": "OWNER_PERSONAL_HEALTH",
    "Personal - Restaurant": "OWNER_PERSONAL_RESTAURANT",
    "Personal - Tax": "OWNER_PERSONAL_TAX",
    "Personal Various": "OWNER_PERSONAL_OTHER",
    "Products-Beer": "BEER_PURCHASES",
    "Products-Drinks": "NON_ALCOHOLIC_BEVERAGES",
    "Products-Food": "FOOD_PURCHASES",
    "Products-Supports": "RESTAURANT_OPERATING_SUPPLIES",
    "Products-Wine": "WINE_PURCHASES",
    "Register Costs": "SOFTWARE_POS_TECHNOLOGY",
    "Remodeling": "LEASEHOLD_IMPROVEMENT",
    "Sales Tax": "SALES_TAX_REMITTANCE",
    "Scouting": "BUSINESS_TRAVEL_SCOUTING",
    "Tips": "TIPS_SETTLEMENT",
    "UR-Recruiting/Training": "RECRUITING_TRAINING",
    "Web/Phone": "PHONE_INTERNET",
    "Work Compensation": "WORKERS_COMPENSATION",
}

# Labels that are NOT normalised, with the reason. Each one would need a
# human to say which purpose was meant, and guessing would put a number in
# the P&L that nobody chose.
LEGACY_REQUIRES_HUMAN_CHOICE: dict[str, str] = {
    "Company Cars": "could be lease, fuel, insurance, repairs or tolls — five different purposes",
    "Company Tax": "the nature of the tax is not stated, and the treatments differ",
    "Da Verificare": "a REVIEW STATUS, not a purpose",
    "Incoming": "says money arrived, not why",
    "Incoming RFG": "the intercompany economic meaning is not proven by the label",
    "Mount Dora Start up": "mixes rent, utilities, equipment and remodelling — P&L and capital together",
    "Personal Deductable": "asserts a tax treatment, not a business purpose",
    "Products-Pers": "the meaning is not clear enough to act on",
    "RF Gelati": "a counterparty name, which is a WHO",
    "Utility Morse/Central": "could be electricity, water, gas or waste",
}


def normalize_legacy_label(label: str | None) -> str | None:
    """The canonical Why code an old label unambiguously meant, or None.

    None for anything in `LEGACY_REQUIRES_HUMAN_CHOICE` and for anything
    unrecognised: an umbrella label never resolves itself."""
    text = (label or "").strip()
    if not text:
        return None
    for known, code in LEGACY_ALIASES.items():
        if known.casefold() == text.casefold():
            return code
    return None


def legacy_label_needs_human(label: str | None) -> str | None:
    """Why an old label was deliberately left unmapped, if it was."""
    text = (label or "").strip()
    for known, reason in LEGACY_REQUIRES_HUMAN_CHOICE.items():
        if known.casefold() == text.casefold():
            return reason
    return None


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


@dataclass
class SeedOutcome:
    groups_created: list[str] = field(default_factory=list)
    groups_unchanged: list[str] = field(default_factory=list)
    reasons_created: list[str] = field(default_factory=list)
    reasons_unchanged: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.conflicts


def seed(session: Session, *, strict: bool = True) -> SeedOutcome:
    """Install the canonical WHY catalog and its management groups.

    Idempotent: a Why already present with the same accounting
    destination is unchanged. A Why present with a DIFFERENT destination
    is a CONFLICT and, with `strict`, raises — a Why is what historical
    decisions resolved their What through, so it is never silently
    re-pointed.

    Creates vocabulary only: no Who, no Who<->Why association, no rule,
    no transaction."""
    outcome = SeedOutcome()
    rows = catalog_rows()

    # --- groups ------------------------------------------------------------
    groups = {g.code: g for g in session.scalars(select(m.BankReasonGroup)).all()}
    for code, name, order in sorted(
        {(r["Group Code"], r["Group Name"], int(r["Group Order"])) for r in rows},
        key=lambda item: item[2],
    ):
        current = groups.get(code)
        if current is not None:
            outcome.groups_unchanged.append(code)
            continue
        group = m.BankReasonGroup(code=code, name=name, display_order=order, active=True)
        session.add(group)
        groups[code] = group
        outcome.groups_created.append(code)
    session.flush()

    # --- reasons -----------------------------------------------------------
    existing = {r.code: r for r in session.scalars(select(m.BankTransactionReason)).all()}
    for row in rows:
        account = canonical_catalog.by_code(session, row["Account Code"])
        if account is None:
            outcome.conflicts.append(
                f"{row['Code']}: accounting destination {row['Account Code']} does not exist "
                "— seed the canonical accounting catalog first."
            )
            continue
        if account.node_type == canonical_catalog.GROUP:
            outcome.conflicts.append(
                f"{row['Code']}: destination {account.code} is a reporting GROUP, which "
                "nothing may be posted to."
            )
            continue

        current = existing.get(row["Code"])
        if current is not None:
            if current.accounting_classification_id != account.id:
                held = session.get(
                    m.BankAccountingClassification, current.accounting_classification_id,
                )
                outcome.conflicts.append(
                    f"{row['Code']}: already resolves to {held.code if held else 'nothing'}, "
                    f"the canonical catalog says {account.code}. Not re-pointed."
                )
                continue
            if current.reason_group_id != groups[row["Group Code"]].id:
                current.reason_group_id = groups[row["Group Code"]].id
            outcome.reasons_unchanged.append(row["Code"])
            continue

        reason = m.BankTransactionReason(
            code=row["Code"], name=row["Name"], status="ACTIVE",
            accounting_classification_id=account.id,
            reason_group_id=groups[row["Group Code"]].id,
            description=(
                f"Canonical RF-One WHY ({CATALOG_VERSION}), management group "
                f"{row['Group Name']}. Resolves to "
                + (
                    f"WHAT {account.code} {account.name}."
                    if account.is_what else
                    f"accounting destination {account.code} {account.name} — no WHAT, because "
                    "this is not a Profit & Loss event."
                )
            ),
        )
        session.add(reason)
        existing[row["Code"]] = reason
        outcome.reasons_created.append(row["Code"])

    session.flush()
    if strict and outcome.conflicts:
        raise ValueError(
            f"The canonical WHY catalog {CATALOG_VERSION} conflicts with what is already in "
            "this database, and nothing was re-pointed. Resolve these by hand: "
            + "; ".join(outcome.conflicts)
        )
    return outcome


# ---------------------------------------------------------------------------
# Reading the catalog back
# ---------------------------------------------------------------------------


def by_code(session: Session, code: str) -> "m.BankTransactionReason | None":
    return session.scalars(
        select(m.BankTransactionReason).where(m.BankTransactionReason.code == code)
    ).first()


def active_reasons(session: Session) -> list["m.BankTransactionReason"]:
    """Every active Why, ordered by management group then name."""
    return list(session.scalars(
        select(m.BankTransactionReason)
        .where(m.BankTransactionReason.status == "ACTIVE")
        .order_by(m.BankTransactionReason.name)
    ).all())


def groups(session: Session) -> list["m.BankReasonGroup"]:
    return list(session.scalars(
        select(m.BankReasonGroup)
        .where(m.BankReasonGroup.active.is_(True))
        .order_by(m.BankReasonGroup.display_order, m.BankReasonGroup.code)
    ).all())


def catalog_by_group(session: Session) -> list[tuple["m.BankReasonGroup", list]]:
    """The full active catalog, grouped — the "+ New" modal's content, and
    the shape a future Company Panel aggregates over.

    Used NOWHERE in ordinary reconciliation: after the Who is chosen the
    operator sees `reasons_for_occurrence` instead."""
    reasons = active_reasons(session)
    by_group: dict[int, list] = {}
    for reason in reasons:
        by_group.setdefault(reason.reason_group_id, []).append(reason)
    result = [
        (group, sorted(by_group.get(group.id, []), key=lambda r: r.name))
        for group in groups(session)
    ]
    ungrouped = sorted(by_group.get(None, []), key=lambda r: r.name)
    if ungrouped:
        result.append((None, ungrouped))
    return [(group, items) for group, items in result if items]


def catalog_problems(session: Session) -> list[str]:
    """The WHY -> WHAT invariant (§19), checked against what is stored.

    An empty list means: every P&L Why has exactly one What, every non-P&L
    Why has an explicit Balance Sheet destination, and no Why points at a
    reporting group."""
    problems: list[str] = []
    canonical = {row["Code"]: row for row in catalog_rows()}

    for reason in session.scalars(select(m.BankTransactionReason)).all():
        destination = reason.accounting_classification
        if destination is None:
            problems.append(f"{reason.code}: has no accounting destination at all")
            continue
        if destination.node_type == canonical_catalog.GROUP:
            problems.append(
                f"{reason.code}: resolves to {destination.code}, a reporting GROUP"
            )
        if reason.is_profit_loss and reason.what is None:
            problems.append(f"{reason.code}: is a P&L Why with no WHAT")
        if not reason.is_profit_loss and reason.accounting_destination is None:
            problems.append(
                f"{reason.code}: resolves to {destination.code}, which is neither a WHAT nor a "
                "Balance Sheet destination"
            )
        if reason.what is not None and reason.accounting_destination is not None:
            problems.append(f"{reason.code}: has both a WHAT and a Balance Sheet destination")

        expected = canonical.get(reason.code)
        if expected is not None and destination.code != expected["Account Code"]:
            problems.append(
                f"{reason.code}: resolves to {destination.code}, the canonical catalog says "
                f"{expected['Account Code']}"
            )
        if expected is not None and reason.reason_group_id is None:
            problems.append(f"{reason.code}: is canonical but belongs to no management group")

    return problems


# ---------------------------------------------------------------------------
# WHO <-> WHY (§20 / §21 / §22 / §24)
# ---------------------------------------------------------------------------


def reasons_for_occurrence(
    session: Session, occurrence_id: int,
) -> list["m.BankTransactionReason"]:
    """The Whys ALREADY associated with this Who — the whole content of the
    ordinary reconciliation dropdown (§21).

    Not the catalog. Not the groups. Just the handful a human has already
    confirmed for this counterparty, which is what makes the dropdown
    short enough to be useful. The caller adds "+ New" after these."""
    return list(session.scalars(
        select(m.BankTransactionReason)
        .join(
            m.BankOccurrenceReasonAssociation,
            m.BankOccurrenceReasonAssociation.transaction_reason_id
            == m.BankTransactionReason.id,
        )
        .where(
            m.BankOccurrenceReasonAssociation.occurrence_id == occurrence_id,
            m.BankOccurrenceReasonAssociation.active.is_(True),
            m.BankTransactionReason.status == "ACTIVE",
        )
        .order_by(m.BankTransactionReason.name)
    ).all())


def reasons_by_occurrence(session: Session) -> dict[int, list["m.BankTransactionReason"]]:
    """`reasons_for_occurrence` for every Who at once, in one query
    (BANK_PERFORMANCE_N_PLUS_ONE_001). Same rows, same order per Who; a Who
    with no association is simply absent."""
    result: dict[int, list[m.BankTransactionReason]] = {}
    for occurrence_id, reason in session.execute(
        select(m.BankOccurrenceReasonAssociation.occurrence_id, m.BankTransactionReason)
        .join(
            m.BankOccurrenceReasonAssociation,
            m.BankOccurrenceReasonAssociation.transaction_reason_id
            == m.BankTransactionReason.id,
        )
        .where(
            m.BankOccurrenceReasonAssociation.active.is_(True),
            m.BankTransactionReason.status == "ACTIVE",
        )
        .order_by(m.BankOccurrenceReasonAssociation.occurrence_id, m.BankTransactionReason.name)
    ):
        result.setdefault(occurrence_id, []).append(reason)
    return result


def occurrences_for_reason(
    session: Session, transaction_reason_id: int,
) -> list["m.BankOccurrence"]:
    """Every Who this Why applies to — the other direction of the same
    many-to-many."""
    return list(session.scalars(
        select(m.BankOccurrence)
        .join(
            m.BankOccurrenceReasonAssociation,
            m.BankOccurrenceReasonAssociation.occurrence_id == m.BankOccurrence.id,
        )
        .where(
            m.BankOccurrenceReasonAssociation.transaction_reason_id == transaction_reason_id,
            m.BankOccurrenceReasonAssociation.active.is_(True),
        )
        .order_by(m.BankOccurrence.canonical_name)
    ).all())


def associate(
    session: Session, *, occurrence_id: int, transaction_reason_id: int,
    source: str = "HUMAN",
) -> "m.BankOccurrenceReasonAssociation":
    """Record that a human confirmed this Why for this Who.

    ADDITIVE, always. Associating a second Why never replaces the first:
    Amazon gains Office Supplies while keeping Restaurant Operating
    Supplies, and the dropdown then offers both. What is learned is
    "Amazon has been these things", never "Amazon means this thing" —
    which is why this writes an association and not a recognition rule
    (BANK_WHO_WHY_INVARIANT_001)."""
    occurrence = session.get(m.BankOccurrence, occurrence_id)
    if occurrence is None:
        raise ValueError(f"Who {occurrence_id} does not exist.")
    reason = session.get(m.BankTransactionReason, transaction_reason_id)
    if reason is None:
        raise ValueError(f"Why {transaction_reason_id} does not exist.")
    if reason.status != "ACTIVE":
        raise ValueError(f"Why {reason.code} is inactive and cannot be associated.")
    if reason.accounting_classification_id is None:
        raise ValueError(
            f"Why {reason.code} has no accounting destination and cannot be associated."
        )

    now = datetime.now(UTC)
    existing = session.scalars(
        select(m.BankOccurrenceReasonAssociation).where(
            m.BankOccurrenceReasonAssociation.occurrence_id == occurrence_id,
            m.BankOccurrenceReasonAssociation.transaction_reason_id == transaction_reason_id,
        )
    ).first()
    if existing is not None:
        existing.active = True
        existing.confirmation_count += 1
        existing.last_confirmed_at = now
        session.flush()
        return existing

    association = m.BankOccurrenceReasonAssociation(
        occurrence_id=occurrence_id, transaction_reason_id=transaction_reason_id,
        active=True, confirmation_count=1,
        first_confirmed_at=now, last_confirmed_at=now, source=source,
    )
    session.add(association)
    session.flush()
    return association
