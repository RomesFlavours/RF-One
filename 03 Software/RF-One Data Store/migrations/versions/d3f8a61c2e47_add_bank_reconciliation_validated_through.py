"""add the Bank Reconciliation validated-through month

Revision ID: d3f8a61c2e47
Revises: c6a2e8f41d93
Create Date: 2026-09-24

BANK_ACCOUNT_BIRTH_AND_VALIDATED_HORIZON_001.

Purely ADDITIVE: one nullable column on the existing singleton
`bank_reconciliation_control_configs` row, plus its shape CHECK. No row is
inserted or rewritten; NULL keeps the previous behaviour (no horizon).

  validated_through_month   `YYYY-MM`, the last month whose loaded data a
                            human has certified complete. Months after it
                            are provisional: shown, never enforced.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "d3f8a61c2e47"
down_revision: str | None = "c6a2e8f41d93"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("bank_reconciliation_control_configs") as batch:
        batch.add_column(sa.Column("validated_through_month", sa.String(length=7), nullable=True))
        batch.create_check_constraint(
            "ck_brcc_validated_through_shape",
            "validated_through_month IS NULL OR length(validated_through_month) = 7",
        )


def downgrade() -> None:
    with op.batch_alter_table("bank_reconciliation_control_configs") as batch:
        batch.drop_constraint("ck_brcc_validated_through_shape", type_="check")
        batch.drop_column("validated_through_month")
