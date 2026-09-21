"""add purpose evidence to transactions and scope to recognition rules

Revision ID: f2b8e4a61c93
Revises: d7a4c9e2f318
Create Date: 2026-09-21

BANK_MEMO_PURPOSE_CLASSIFICATION_001 — an ADDITIVE schema change plus a
deterministic backfill from already-preserved raw source rows. No
transaction is reclassified, no decision is rewritten, no recognition rule
changes meaning, no raw source fact is modified and no accounting account
is touched.

Why

The identity of a payee answers WHO. It does not answer WHY money moved.
`ZELLE PAYMENT TO MARIO ROSSI` may be a tips distribution, 1099 contract
labour, a reimbursement, settlement of a recorded payable or an owner
draw, and the bank line says which PERSON while saying nothing about
which of those it is. Until now RF-One had one text field per transaction
— the bank's own description — so purpose evidence had nowhere to live
and a learned rule could only ever mean "this description means this
Who", whose Why and What follow automatically.

Schema

`financial_transactions` gains:

  * `source_memo`        the user-entered or bank-provided PURPOSE text,
                         verbatim. Chase's card exports carry a `Memo`
                         column; a future Mercury connector would supply
                         its note / memo / external memo here. NULL means
                         the source has no such field at all.
  * `source_memo_field`  which source column it came from ("Memo",
                         "Note", ...), so Description, Memo and Note stay
                         distinguishable instead of being flattened into
                         one irreversible string.

`bank_recognition_rules` gains:

  * `match_field`        DESCRIPTION | MEMO — which text the pattern
                         matches. DESCRIPTION is what every existing rule
                         does and is the default.
  * `determines_purpose` whether matching supplies the WHAT or only the
                         WHO. TRUE for every existing rule, which is
                         exactly what they do today, so no rule changes
                         behaviour.

Backfill

`source_memo` is filled from `raw_bank_transactions.raw_fields`, which has
preserved every source column since the import layer was written — so
this recovers purpose text that was parsed but not promoted, WITHOUT
re-reading any file and without touching the raw rows themselves. Only a
non-empty value is written: a source column that exists and is blank
leaves `source_memo` NULL and records nothing, because "the bank offered
a memo box and nobody filled it" is not purpose evidence.

The accepted source column names are fixed here, in this revision, and
are matched case-insensitively against whatever the raw row holds. They
are NOT read from a parser module: a migration must keep working against
the code of its own revision
(BANK_CANONICAL_MIGRATION_IMMUTABILITY_001).

Runs on SQLite and PostgreSQL. SQLite cannot add a CHECK constraint to an
existing table, so `bank_recognition_rules` gains its column-plus-
constraint through an Alembic batch rebuild there and through plain
`op.add_column` / `op.create_check_constraint` on PostgreSQL.
`financial_transactions` gains two plain nullable columns with no
constraint, so it needs no rebuild on either dialect.

Downgrade removes only what this revision added.
"""
from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f2b8e4a61c93'
down_revision: Union[str, Sequence[str], None] = 'd7a4c9e2f318'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TRANSACTIONS = "financial_transactions"
RULES = "bank_recognition_rules"

_TRANSACTION_COLUMNS = (
    ("source_memo", sa.Text()),
    ("source_memo_field", sa.String(length=64)),
)

_RULE_COLUMNS = (
    ("match_field", sa.String(length=16), "DESCRIPTION"),
    ("determines_purpose", sa.Boolean(), sa.text("1")),
)

_RULE_CHECKS = (
    ("ck_bank_recognition_rule_match_field", "match_field IN ('DESCRIPTION', 'MEMO')"),
)

# Source columns that carry PURPOSE text rather than the bank's own
# description. Frozen in this revision on purpose — see the docstring.
# "Category" is deliberately absent: Chase writes its own merchant
# category there, which is the bank's guess about a merchant, not a human
# statement about why the money moved.
_PURPOSE_COLUMNS = ("memo", "note", "notes", "description memo", "external memo", "reference memo")


def _purpose_from_raw(raw_fields: str | None) -> tuple[str, str] | None:
    """The purpose text a preserved raw row holds, and the column it came
    from. None when the source has no such column or left it blank."""
    if not raw_fields:
        return None
    try:
        fields = json.loads(raw_fields)
    except (TypeError, ValueError):
        return None
    if not isinstance(fields, dict):
        return None
    for name, value in fields.items():
        if (name or "").strip().lower() not in _PURPOSE_COLUMNS:
            continue
        text = (value or "").strip() if isinstance(value, str) else ""
        if text:
            return text, name.strip()
    return None


def upgrade() -> None:
    """Add the purpose-evidence columns and the rule scope, then backfill."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    for name, column_type in _TRANSACTION_COLUMNS:
        op.add_column(TRANSACTIONS, sa.Column(name, column_type, nullable=True))

    if is_sqlite:
        with op.batch_alter_table(RULES, schema=None, recreate="always") as batch_op:
            for name, column_type, default in _RULE_COLUMNS:
                batch_op.add_column(
                    sa.Column(name, column_type, nullable=False, server_default=default),
                )
            for name, condition in _RULE_CHECKS:
                batch_op.create_check_constraint(name, condition)
    else:
        for name, column_type, default in _RULE_COLUMNS:
            op.add_column(
                RULES, sa.Column(name, column_type, nullable=False, server_default=default),
            )
        for name, condition in _RULE_CHECKS:
            op.create_check_constraint(name, RULES, condition)

    # --- backfill purpose text from the preserved raw rows -----------------
    #
    # Read-only over `raw_bank_transactions`: this recovers text the import
    # already kept, and writes it only onto the normalized transaction.
    rows = bind.execute(sa.text(
        "SELECT normalized_transaction_id, raw_fields FROM raw_bank_transactions "
        "WHERE normalized_transaction_id IS NOT NULL AND raw_fields IS NOT NULL"
    )).fetchall()

    recovered = 0
    for transaction_id, raw_fields in rows:
        found = _purpose_from_raw(raw_fields)
        if found is None:
            continue
        text, column = found
        bind.execute(
            sa.text(
                f"UPDATE {TRANSACTIONS} SET source_memo = :memo, source_memo_field = :field "
                "WHERE id = :id AND source_memo IS NULL"
            ),
            {"memo": text, "field": column, "id": transaction_id},
        )
        recovered += 1

    # Stated rather than silently assumed: an environment whose exports
    # never filled a memo box legitimately recovers nothing, and that is a
    # finding about the data, not a failure of the migration.
    print(
        f"[f2b8e4a61c93] purpose text recovered from preserved raw rows: {recovered} "
        f"of {len(rows)} linked raw row(s)."
    )


def downgrade() -> None:
    """Remove the four columns and the one constraint this revision added."""
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if is_sqlite:
        with op.batch_alter_table(RULES, schema=None, recreate="always") as batch_op:
            for name, _ in _RULE_CHECKS:
                batch_op.drop_constraint(name, type_="check")
            for name, _, _ in reversed(_RULE_COLUMNS):
                batch_op.drop_column(name)
    else:
        for name, _ in _RULE_CHECKS:
            op.drop_constraint(name, RULES, type_="check")
        for name, _, _ in reversed(_RULE_COLUMNS):
            op.drop_column(RULES, name)

    for name, _ in reversed(_TRANSACTION_COLUMNS):
        op.drop_column(TRANSACTIONS, name)
