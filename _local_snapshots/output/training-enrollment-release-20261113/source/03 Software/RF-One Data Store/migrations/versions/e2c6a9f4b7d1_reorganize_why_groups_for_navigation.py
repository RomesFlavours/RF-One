"""reorganize the WHY management groups into the 15 navigation groups

Revision ID: e2c6a9f4b7d1
Revises: d8e2f5a9c3b7
Create Date: 2026-10-04

BANK_WHY_NAVIGATION_GROUPS_001 — Product Owner approved. DATA ONLY: no
schema change, no WHY created, renamed or re-pointed, no WHAT or accounting
destination touched, no transaction, decision, association or rule written.

`bank_reason_groups` stays the ONE grouping of WHY. Its purpose for the
operator is navigation in the "Select WHO / WHY" popup: a group has no
accounting effect — nothing is posted to it, nothing is exported from it.

What changes

  * the 14 groups become 15, in the approved navigation order. A group whose
    concept is unchanged keeps its code and only gets the approved name and
    order (PRODUCT_COST -> "Food, Beverage & Supplies", OCCUPANCY -> "Rent &
    Occupancy", FACILITY -> "Maintenance, Repairs & Cleaning", MARKETING ->
    "Marketing & Entertainment", BANKING -> "Banking, Fees & Interest",
    OWNER_PERSONAL -> "Owner", CAPITAL_PROJECTS -> "Capital Purchases", ...);
    six are new: PAYROLL, PROFESSIONAL_SERVICES, OFFICE_ADMIN, INSURANCE,
    TRANSFERS_CARD_PAYMENTS, DEPOSITS_SETTLEMENTS;
  * every canonical WHY is assigned to exactly one of them;
  * the five groups no longer used — KITCHEN_LABOR, FOH_LABOR, PEOPLE,
    ADMINISTRATION, MONEY_MOVEMENT — are DEACTIVATED, never deleted, and only
    when no WHY still points at them.

A WHY that is not in the canonical catalog (one an operator created in
Configuration) keeps whatever group it had.

The assignment comes from this revision's OWN FROZEN SNAPSHOT
(BANK_CANONICAL_MIGRATION_IMMUTABILITY_001):

    migrations/migration_data/e2c6a9f4b7d1_why_navigation_groups.csv

which also records each WHY's previous group, so the downgrade restores it.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e2c6a9f4b7d1'
down_revision: Union[str, Sequence[str], None] = 'd8e2f5a9c3b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


GROUPS = "bank_reason_groups"
REASONS = "bank_transaction_reasons"

# This revision's own frozen input. IMMUTABLE: a correction is a new revision.
_SNAPSHOT = (
    Path(__file__).resolve().parents[1]
    / "migration_data" / "e2c6a9f4b7d1_why_navigation_groups.csv"
)
_EXPECTED_ROWS = 81
_EXPECTED_GROUPS = 15

# The groups this revision retires, and the names/orders the downgrade gives
# back to every group it touched (as left by c4a9e7d21b56).
_RETIRED = ("KITCHEN_LABOR", "FOH_LABOR", "PEOPLE", "ADMINISTRATION", "MONEY_MOVEMENT")
_PREVIOUS = {
    "KITCHEN_LABOR": ("Kitchen Labor", 10),
    "FOH_LABOR": ("Serving / FOH Labor", 20),
    "PEOPLE": ("Management & Personnel", 30),
    "PRODUCT_COST": ("Product Cost", 40),
    "OCCUPANCY": ("Occupancy", 50),
    "FACILITY": ("Facility / Structural", 60),
    "UTILITIES": ("Utilities & Communications", 70),
    "ADMINISTRATION": ("Administration & Professional", 80),
    "BANKING": ("Banking & Payment Costs", 90),
    "MARKETING": ("Marketing & Business Development", 100),
    "VEHICLE_TRAVEL": ("Vehicles & Travel", 110),
    "OWNER_PERSONAL": ("Owner / Personal", 120),
    "MONEY_MOVEMENT": ("Money Movements / Liabilities", 130),
    "CAPITAL_PROJECTS": ("Capital / Projects", 140),
}


def _rows() -> list[dict]:
    rows = list(csv.DictReader(io.StringIO(_SNAPSHOT.read_text(encoding="utf-8-sig"))))
    groups = {r["Group Code"] for r in rows}
    if len(rows) != _EXPECTED_ROWS or len(groups) != _EXPECTED_GROUPS:
        raise RuntimeError(
            f"The frozen snapshot {_SNAPSHOT.name} holds {len(rows)} row(s) in {len(groups)} group(s); "
            f"revision e2c6a9f4b7d1 was written against exactly {_EXPECTED_ROWS} in {_EXPECTED_GROUPS}. "
            "A migration snapshot is immutable — restore it and express any change as a new revision."
        )
    return rows


def _group_ids(bind) -> dict[str, int]:
    return {code: gid for gid, code in bind.execute(sa.text(f"SELECT id, code FROM {GROUPS}"))}


def upgrade() -> None:
    bind = op.get_bind()
    rows = _rows()

    targets = sorted({(r["Group Code"], r["Group Name"], int(r["Group Order"])) for r in rows},
                     key=lambda item: item[2])
    existing = _group_ids(bind)
    for code, name, order in targets:
        if code in existing:
            bind.execute(sa.text(
                f"UPDATE {GROUPS} SET name = :name, display_order = :order, active = :active WHERE code = :code"
            ), {"name": name, "order": order, "active": True, "code": code})
        else:
            bind.execute(sa.text(
                f"INSERT INTO {GROUPS} (code, name, display_order, active) VALUES (:code, :name, :order, :active)"
            ), {"code": code, "name": name, "order": order, "active": True})
    ids = _group_ids(bind)

    for row in rows:
        bind.execute(sa.text(f"UPDATE {REASONS} SET reason_group_id = :group WHERE code = :code"),
                     {"group": ids[row["Group Code"]], "code": row["Code"]})

    for code in _RETIRED:
        if code not in ids:
            continue
        still_used = bind.execute(sa.text(f"SELECT COUNT(*) FROM {REASONS} WHERE reason_group_id = :group"),
                                  {"group": ids[code]}).scalar()
        if not still_used:
            bind.execute(sa.text(f"UPDATE {GROUPS} SET active = :active WHERE id = :group"),
                         {"active": False, "group": ids[code]})


def downgrade() -> None:
    bind = op.get_bind()
    rows = _rows()
    ids = _group_ids(bind)
    for code, (name, order) in _PREVIOUS.items():
        if code in ids:
            bind.execute(sa.text(
                f"UPDATE {GROUPS} SET name = :name, display_order = :order, active = :active WHERE code = :code"
            ), {"name": name, "order": order, "active": True, "code": code})
    for row in rows:
        previous = ids.get(row["Previous Group Code"])
        if previous is not None:
            bind.execute(sa.text(f"UPDATE {REASONS} SET reason_group_id = :group WHERE code = :code"),
                         {"group": previous, "code": row["Code"]})
    new_codes = sorted({r["Group Code"] for r in rows} - set(_PREVIOUS))
    for code in new_codes:
        if code not in ids:
            continue
        used = bind.execute(sa.text(f"SELECT COUNT(*) FROM {REASONS} WHERE reason_group_id = :group"),
                            {"group": ids[code]}).scalar()
        if not used:
            bind.execute(sa.text(f"DELETE FROM {GROUPS} WHERE id = :group"), {"group": ids[code]})
