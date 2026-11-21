"""add the Bank Reconciliation control start month

Revision ID: b7d4e92a1c58
Revises: a5e1c93f7b20
Create Date: 2026-09-22

BANK_RECONCILIATION_CONTROL_START_DATE_001.

Purely ADDITIVE. One new table, nothing dropped, nothing rewritten, no
existing row touched and no data file read. `down_revision` is the actual
single Alembic head observed at the time of writing (`a5e1c93f7b20`, the
Bank monthly source completeness migration), confirmed through
`ScriptDirectory.get_heads()` rather than assumed.

What it adds
------------
`bank_reconciliation_control_configs` — the single month from which RF-One
takes responsibility for Bank source completeness.

  control_start_month   `YYYY-MM`, the same shape and meaning as
                        `bank_monthly_source_periods.period_month`. Bank
                        completeness is monthly, so the boundary is a
                        month; there is no stored day-of-month to be
                        ambiguous about and no partial-month state to
                        interpret.
  note                  why it was set where it was, in the operator's
                        own words.
  updated_by_account_id who set it.

Two constraints carry meaning rather than defensiveness:

  ck_brcc_singleton     `id = 1`. Exactly ONE authoritative value can
                        exist. Bank completeness is global in this schema
                        (`period_month` is unique database-wide), so its
                        boundary is global too.
  ck_brcc_month_shape   `length(control_start_month) = 7`, the `YYYY-MM`
                        shape. Both forms run unchanged on SQLite and on
                        PostgreSQL.

NO ROW IS INSERTED. The table is created empty on purpose: the value has
no default and is never inferred — not from today, not from the oldest
transaction, not from a file name, not from `created_at`. Until a human
sets it, RF-One has not been told when it takes responsibility and takes
none automatically. Seeding a guess here would be exactly the invented
certainty this boundary exists to prevent.

Nothing about existing months changes. Periods, coverage rows, human
resolutions and transactions that already exist are untouched by this
migration and are untouched by the setting itself, which governs only what
is created AUTOMATICALLY from here on.

Runs unchanged on an empty disposable database, on the local QA database,
and on AWS RDS through an ordinary `alembic upgrade head`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "b7d4e92a1c58"
down_revision: str | None = "a5e1c93f7b20"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "bank_reconciliation_control_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("control_start_month", sa.String(length=7), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "updated_by_account_id", sa.Integer(),
            sa.ForeignKey("rfone_accounts.id"), nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.CheckConstraint("id = 1", name="ck_brcc_singleton"),
        sa.CheckConstraint("length(control_start_month) = 7", name="ck_brcc_month_shape"),
    )


def downgrade() -> None:
    op.drop_table("bank_reconciliation_control_configs")
