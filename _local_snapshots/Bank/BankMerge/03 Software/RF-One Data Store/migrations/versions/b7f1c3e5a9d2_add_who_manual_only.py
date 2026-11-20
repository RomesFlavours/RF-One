"""add Manual Only to WHO (excluded from individual WHO Rule automation)

Revision ID: b7f1c3e5a9d2
Revises: a5d9e3f7b2c4
Create Date: 2026-10-05

BANK_WHO_MANUAL_ONLY_001 — Product Owner approved. ADDITIVE, no data change.

  * `bank_occurrences.manual_only` — a person decided this WHO is reconciled by
    hand when it occurs (e.g. a restaurant visited occasionally): no individual
    WHO Rule is offered, applied or proposed for it. General Rules, WHY and manual
    reconciliation are unaffected. Every existing WHO starts as not Manual Only.

Downgrade drops the column.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b7f1c3e5a9d2'
down_revision: Union[str, Sequence[str], None] = 'a5d9e3f7b2c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bank_occurrences", schema=None) as batch_op:
        batch_op.add_column(sa.Column("manual_only", sa.Boolean(), nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    with op.batch_alter_table("bank_occurrences", schema=None) as batch_op:
        batch_op.drop_column("manual_only")
