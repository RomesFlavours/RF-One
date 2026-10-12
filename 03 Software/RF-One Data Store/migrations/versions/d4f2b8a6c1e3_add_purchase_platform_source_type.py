"""add the PURCHASE_PLATFORM Source type (documentary source)

Revision ID: d4f2b8a6c1e3
Revises: c9e4a1f7d3b6
Create Date: 2026-10-07

BANK_PURCHASE_PLATFORM_SOURCE_001 — Product Owner decision. ADDITIVE, no data
change.

  * `payment_instruments.instrument_type` admits `PURCHASE_PLATFORM`: a
    platform (Amazon, Sam's, Instacart, ...) that provides orders, receipts,
    invoices and refunds to be linked to the movements of the PAYMENT sources
    (bank account, credit card, PayPal). It is not another account: it never
    carries transactions of its own and is never counted as spend or payment.
    Every existing Source keeps its type.

Runs on SQLite (Alembic batch rebuild, which keeps the table's named
constraints) and on PostgreSQL (the constraint is dropped and re-created in
place). Downgrade refuses while a purchase platform exists.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd4f2b8a6c1e3'
down_revision: Union[str, Sequence[str], None] = 'c9e4a1f7d3b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NAME = "ck_pi_instrument_type"
_NEW = "instrument_type IN ('BANK_ACCOUNT', 'CREDIT_CARD', 'PAYPAL', 'PURCHASE_PLATFORM')"
_OLD = "instrument_type IN ('BANK_ACCOUNT', 'CREDIT_CARD', 'PAYPAL')"


def _replace(condition: str) -> None:
    with op.batch_alter_table("payment_instruments", schema=None) as batch_op:
        batch_op.drop_constraint(_NAME, type_="check")
        batch_op.create_check_constraint(_NAME, condition)


def upgrade() -> None:
    _replace(_NEW)


def downgrade() -> None:
    platforms = op.get_bind().execute(sa.text(
        "SELECT COUNT(*) FROM payment_instruments WHERE instrument_type = 'PURCHASE_PLATFORM'")).scalar() or 0
    if platforms:
        raise RuntimeError(
            f"Refusing to downgrade: {platforms} purchase platform Source(s) exist and would have no valid type."
        )
    _replace(_OLD)
