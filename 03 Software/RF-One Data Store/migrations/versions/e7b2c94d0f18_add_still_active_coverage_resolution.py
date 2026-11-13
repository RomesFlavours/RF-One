"""admit the STILL_ACTIVE monthly coverage resolution

Revision ID: e7b2c94d0f18
Revises: d3f8a61c2e47
Create Date: 2026-09-24

BANK_EXPLICIT_STILL_ACTIVE_DECISION_001.

Widens `ck_bmic_resolution` on `bank_monthly_instrument_coverages` by one
value, `STILL_ACTIVE`. Purely additive: every existing value stays valid,
no row is written. Downgrade restores the original list and refuses if a
STILL_ACTIVE row exists, rather than silently deleting a human decision.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "e7b2c94d0f18"
down_revision: str | None = "d3f8a61c2e47"
branch_labels: str | None = None
depends_on: str | None = None

_BASE = (
    "'NO_ACTIVITY', 'CLOSED', 'LOST', 'REPLACED', 'OTHER', "
    "'SOURCE_FILE_MISSING', 'NOT_EXPECTED_CONFIRMED'"
)


def upgrade() -> None:
    with op.batch_alter_table("bank_monthly_instrument_coverages") as batch:
        batch.drop_constraint("ck_bmic_resolution", type_="check")
        batch.create_check_constraint(
            "ck_bmic_resolution",
            f"resolution IS NULL OR resolution IN ({_BASE}, 'STILL_ACTIVE')",
        )


def downgrade() -> None:
    bind = op.get_bind()
    used = bind.execute(sa.text(
        "SELECT COUNT(*) FROM bank_monthly_instrument_coverages WHERE resolution = 'STILL_ACTIVE'"
    )).scalar()
    if used:
        raise RuntimeError(
            f"{used} coverage row(s) record a human STILL_ACTIVE decision; clear them before "
            "downgrading. A human decision is never deleted by a migration."
        )
    with op.batch_alter_table("bank_monthly_instrument_coverages") as batch:
        batch.drop_constraint("ck_bmic_resolution", type_="check")
        batch.create_check_constraint(
            "ck_bmic_resolution", f"resolution IS NULL OR resolution IN ({_BASE})",
        )
