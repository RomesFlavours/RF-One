"""add 7460 Municipal Utilities and the four approved settlement / utility WHYs

Revision ID: a7c3e9d5f2b8
Revises: b9e4c2a7d5f3
Create Date: 2026-10-01

BANK_WHO_WHY_CANONICAL_CATALOG_001 — a DATA migration only. No table is
created, altered or dropped. It makes canonical what the Product Owner
approved on 2026-10-01 (decisions D20–D23 of the WHO/WHY staging):

1. 7460 Municipal Utilities — a P&L POSTING WHAT under the existing GROUP
   7400 Utilities, DEBIT, non-contra, not review-sensitive: the same
   conventions as its siblings 7410–7450. A municipal invoice that bundles
   electricity, water and sewer/waste in one payment is posted here as one
   amount rather than split by guesswork. 7400 itself is not touched.

2. Four WHY:

       MERCHANT_CARD_SETTLEMENT  -> 1210 Merchant Processor Receivable / Clearing (Balance Sheet)
       GIFT_CARD_SETTLEMENT      -> 2800 Other Current Liabilities              (Balance Sheet)
       CASH_CHECK_DEPOSIT        -> 1130 Cash on Hand                           (Balance Sheet)
       MUNICIPAL_UTILITIES       -> 7460 Municipal Utilities                    (P&L WHAT)

   The first three settle receipts whose sales are already recorded from
   the POS: depositing them must not create revenue a second time, so they
   have NO WHAT. There is deliberately no generic "Incoming" WHY.

No export mapping (Food Cost / Operative / Deductable) is created: that is
a separate Product Owner decision. No WHO is seeded here.

This revision CARRIES ITS VALUES INLINE (BANK_CANONICAL_MIGRATION_IMMUTABILITY_001):
it never reads the live catalog files, so later edits to them cannot change
what it does. Writes go through SQLAlchemy Core so it runs against the
schema of its own revision, on SQLite and PostgreSQL alike.

Idempotent and non-destructive:

* 7460 and each WHY are inserted only if absent;
* a row already present with the SAME meaning (same name/parent/statement/
  node for 7460; same accounting destination for a WHY) is kept exactly as
  it is — for example one created by an earlier approved import;
* a code present with a DIFFERENT meaning RAISES: an account or a WHY that
  historical decisions may reference is never silently redefined.

Downgrade removes a row only while nothing references it.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7c3e9d5f2b8'
down_revision: Union[str, Sequence[str], None] = 'b9e4c2a7d5f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ACCOUNTS = "bank_accounting_classifications"
REASONS = "bank_transaction_reasons"
GROUPS = "bank_reason_groups"

# This revision's frozen input, inline. IMMUTABLE: a correction is a new revision.
# Code -> (name, statement type, parent, node type, normal balance, contra, review-sensitive)
NEW_ACCOUNT_CODE = "7460"
NEW_ACCOUNT = ("Municipal Utilities", "PROFIT_LOSS", "7400", "POSTING", "DEBIT", False, False)
ACCOUNT_NOTE = (
    "Canonical RF-One restaurant accounting catalog (RFONE_RESTAURANT_COA_V1). A municipal "
    "invoice bundling electricity, water and sewer/waste in one payment. Added by migration "
    "a7c3e9d5f2b8 (Product Owner decision D23)."
)

# Code -> (name, group code, group name, account code)
NEW_WHYS = {
    "MERCHANT_CARD_SETTLEMENT": ("Merchant / Card Sales Settlement", "MONEY_MOVEMENT",
                                 "Money Movements / Liabilities", "1210"),
    "GIFT_CARD_SETTLEMENT": ("Gift Card Sales Settlement", "MONEY_MOVEMENT",
                             "Money Movements / Liabilities", "2800"),
    "CASH_CHECK_DEPOSIT": ("Cash / Check Deposit", "MONEY_MOVEMENT",
                           "Money Movements / Liabilities", "1130"),
    "MUNICIPAL_UTILITIES": ("Municipal Utilities", "UTILITIES",
                            "Utilities & Communications", "7460"),
}

def _accounts(bind) -> dict[str, tuple]:
    return {
        code: (identifier, name, statement_type, parent_id, node_type)
        for identifier, code, name, statement_type, parent_id, node_type in bind.execute(
            sa.text(f"SELECT id, code, name, statement_type, parent_id, node_type FROM {ACCOUNTS}")
        ).fetchall()
    }


def upgrade() -> None:
    bind = op.get_bind()

    # --- 1. 7460 Municipal Utilities ---------------------------------------
    accounts = _accounts(bind)
    name, statement_type, parent_code, node_type, normal_balance, is_contra, review_sensitive = NEW_ACCOUNT
    parent = accounts.get(parent_code)
    if parent is None or parent[2] != statement_type or parent[4] != "GROUP":
        raise RuntimeError(
            f"Refusing to add {NEW_ACCOUNT_CODE}: its parent {parent_code} must exist as a "
            f"{statement_type} GROUP. Run the canonical accounting catalog migrations first."
        )
    current = accounts.get(NEW_ACCOUNT_CODE)
    if current is not None:
        _, held_name, held_statement, held_parent, held_node = current
        if (held_name.strip().casefold(), held_statement, held_parent, held_node) != (
            name.casefold(), statement_type, parent[0], node_type
        ):
            raise RuntimeError(
                f"Refusing to add {NEW_ACCOUNT_CODE} {name!r}: the code already exists as "
                f"{held_name!r} ({held_statement}, {held_node}, parent id {held_parent}). An account "
                "historical decisions may reference is never silently redefined. Resolve it by "
                "hand, then re-run the migration."
            )
    else:
        bind.execute(
            sa.text(
                f"INSERT INTO {ACCOUNTS} (code, name, statement_type, parent_id, description, active, "
                "node_type, is_contra, review_sensitive, normal_balance) VALUES (:code, :name, "
                ":statement_type, :parent_id, :description, :active, :node_type, :is_contra, "
                ":review_sensitive, :normal_balance)"
            ),
            {
                "code": NEW_ACCOUNT_CODE, "name": name, "statement_type": statement_type,
                "parent_id": parent[0], "description": ACCOUNT_NOTE, "active": True,
                "node_type": node_type, "is_contra": is_contra,
                "review_sensitive": review_sensitive, "normal_balance": normal_balance,
            },
        )

    # --- 2. the four WHY ------------------------------------------------------
    accounts = _accounts(bind)
    groups = {code: identifier for identifier, code in bind.execute(
        sa.text(f"SELECT id, code FROM {GROUPS}")
    ).fetchall()}
    existing = {code: (identifier, account_id, group_id)
                for identifier, code, account_id, group_id in bind.execute(
                    sa.text(f"SELECT id, code, accounting_classification_id, reason_group_id FROM {REASONS}")
                ).fetchall()}
    by_account_id = {values[0]: code for code, values in accounts.items()}

    problems = []
    for code, (why_name, group_code, _, account_code) in NEW_WHYS.items():
        if account_code not in accounts:
            problems.append(f"{code}: destination {account_code} does not exist")
        elif accounts[account_code][4] == "GROUP":
            problems.append(f"{code}: destination {account_code} is a reporting GROUP")
        if group_code not in groups:
            problems.append(f"{code}: management group {group_code} does not exist")
        if code in existing and existing[code][1] != (accounts.get(account_code) or (None,))[0]:
            problems.append(
                f"{code}: already resolves to {by_account_id.get(existing[code][1], 'nothing')!r}, "
                f"this revision means {account_code!r}"
            )
    if problems:
        raise RuntimeError(
            "Refusing to add the approved WHYs: a WHY that historical decisions resolved their "
            "WHAT through is never silently re-pointed. Resolve these by hand, then re-run. "
            + "; ".join(problems)
        )

    for code, (why_name, group_code, group_name, account_code) in NEW_WHYS.items():
        if code in existing:
            if existing[code][2] is None:  # same meaning; only an absent group is filled
                bind.execute(sa.text(f"UPDATE {REASONS} SET reason_group_id = :g WHERE code = :c"),
                             {"g": groups[group_code], "c": code})
            continue
        is_pl = accounts[account_code][2] == "PROFIT_LOSS"
        description = (
            f"Canonical RF-One WHY (RFONE_RESTAURANT_WHY_V1), management group {group_name}. "
            "Resolves to "
            + (f"WHAT {account_code}." if is_pl else
               f"accounting destination {account_code} — no WHAT, because this is not a Profit & "
               "Loss event.")
            + " Added by migration a7c3e9d5f2b8 (Product Owner decisions D20–D23)."
        )
        bind.execute(
            sa.text(
                f"INSERT INTO {REASONS} (code, name, description, status, "
                "accounting_classification_id, reason_group_id) "
                "VALUES (:code, :name, :description, 'ACTIVE', :account_id, :group_id)"
            ),
            {"code": code, "name": why_name, "description": description,
             "account_id": accounts[account_code][0], "group_id": groups[group_code]},
        )

    # --- the promise this revision makes ------------------------------------
    accounts = _accounts(bind)
    for code, (_, _, _, account_code) in NEW_WHYS.items():
        held = bind.execute(sa.text(f"SELECT accounting_classification_id FROM {REASONS} WHERE code = :c"),
                            {"c": code}).scalar()
        if held != accounts[account_code][0]:
            raise RuntimeError(f"{code} does not resolve to {account_code} after this revision.")


def _referenced(bind, target_table: str, identifier: int) -> bool:
    """Whether any row, in any table with a foreign key to `target_table`,
    points at `identifier`. Read from the live schema, so a table added by a
    later revision is covered without being named here."""
    inspector = sa.inspect(bind)
    for table in inspector.get_table_names():
        for fk in inspector.get_foreign_keys(table):
            if fk["referred_table"] != target_table:
                continue
            for column in fk["constrained_columns"]:
                if bind.execute(sa.text(f"SELECT COUNT(*) FROM {table} WHERE {column} = :i"),
                                {"i": identifier}).scalar():
                    return True
    return False


def downgrade() -> None:
    """Remove what this revision added, but only while nothing references it."""
    bind = op.get_bind()
    for code in NEW_WHYS:
        identifier = bind.execute(sa.text(f"SELECT id FROM {REASONS} WHERE code = :c"), {"c": code}).scalar()
        if identifier is not None and not _referenced(bind, REASONS, identifier):
            bind.execute(sa.text(f"DELETE FROM {REASONS} WHERE id = :i"), {"i": identifier})
    identifier = bind.execute(sa.text(f"SELECT id FROM {ACCOUNTS} WHERE code = :c"),
                              {"c": NEW_ACCOUNT_CODE}).scalar()
    if identifier is not None and not _referenced(bind, ACCOUNTS, identifier):
        bind.execute(sa.text(f"DELETE FROM {ACCOUNTS} WHERE id = :i"), {"i": identifier})
