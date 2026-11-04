"""drop persisted Tip calculation history (TIPS_STATELESS_CALCULATION_001)

Tips no longer persists calculation results. `distribution_engine.
calculate_tips` derives any requested period in memory from source facts
(Orders, Payments, Shifts, EmployeeAssignments) and effective-dated
`TipDistributionRuleVersion` rows, so any period can be recalculated
freely and repeatedly — including periods that overlap, contain, or sit
inside a previously calculated one.

This migration therefore removes the two pieces of schema whose only
purpose was storing a Tips calculation:

  * `tip_distribution_allocations` — the whole table. Every row was a
    DERIVED result, never a source fact, and is fully reproducible by
    recalculating its period. Nothing outside Tips calculation/audit ever
    read it.
  * `tip_distribution_calculation_runs.superseded_by_calculation_run_id` —
    supersession only existed to arbitrate between stored results. With no
    stored result there is nothing to supersede.

DELIBERATELY KEPT:

  * `tip_distribution_calculation_runs` (the table itself) — it is NOT a
    Tips result any more but a PAYOUT ANCHOR. `tip_entitlements.
    calculation_run_id` is a NOT NULL foreign key to it, and entitlements
    feed Payment Cycles / Payment Instructions / Mercury payout. Dropping
    it would break downstream payment structures, which is out of scope.
  * `tip_entitlements` and everything downstream — the crystallized amount
    a payment commits to, exactly the boundary Compensation uses.
  * Every source fact (Orders, Payments, Shifts, EmployeeAssignments) and
    all Rule / RuleVersion history — untouched.

Downgrade recreates the dropped table and column empty: the historical
allocation ROWS are not restored, because they were derived output rather
than source data. Re-running the relevant periods reproduces them.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b7d3e5c920"
down_revision: Union[str, Sequence[str], None] = "e7c1a9f4d6b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "tip_distribution_allocations" in tables:
        op.drop_table("tip_distribution_allocations")

    if "tip_distribution_calculation_runs" in tables:
        columns = {c["name"] for c in inspector.get_columns("tip_distribution_calculation_runs")}
        if "superseded_by_calculation_run_id" in columns:
            # SQLite cannot DROP a column carrying a self-referential FK
            # without a table rebuild; batch_alter_table performs that
            # rebuild, and is a plain ALTER on PostgreSQL.
            with op.batch_alter_table("tip_distribution_calculation_runs") as batch_op:
                batch_op.drop_column("superseded_by_calculation_run_id")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "tip_distribution_calculation_runs" in tables:
        columns = {c["name"] for c in inspector.get_columns("tip_distribution_calculation_runs")}
        if "superseded_by_calculation_run_id" not in columns:
            with op.batch_alter_table("tip_distribution_calculation_runs") as batch_op:
                batch_op.add_column(sa.Column("superseded_by_calculation_run_id", sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_tip_distribution_runs_superseded_by",
                    "tip_distribution_calculation_runs",
                    ["superseded_by_calculation_run_id"],
                    ["id"],
                )

    if "tip_distribution_allocations" not in tables:
        op.create_table(
            "tip_distribution_allocations",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("calculation_run_id", sa.Integer(), nullable=False),
            sa.Column("order_id", sa.Integer(), nullable=False),
            sa.Column("source_employee_id", sa.Integer(), nullable=True),
            sa.Column("rule_version_id", sa.Integer(), nullable=False),
            sa.Column("calculation_base", sa.String(length=32), nullable=False),
            sa.Column("rate", sa.Numeric(precision=7, scale=4), nullable=False),
            sa.Column("base_amount_minor", sa.Integer(), nullable=False),
            sa.Column("pool_amount_minor", sa.Integer(), nullable=False),
            sa.Column("recipient_employee_id", sa.Integer(), nullable=True),
            sa.Column("recipient_eligibility_basis", sa.Text(), nullable=False),
            sa.Column("no_eligible_recipient", sa.Boolean(), nullable=False),
            sa.Column("allocated_amount_minor", sa.Integer(), nullable=False),
            sa.Column("settlement_time", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["calculation_run_id"], ["tip_distribution_calculation_runs.id"]),
            sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
            sa.ForeignKeyConstraint(["recipient_employee_id"], ["employees.id"]),
            sa.ForeignKeyConstraint(["rule_version_id"], ["tip_distribution_rule_versions.id"]),
            sa.ForeignKeyConstraint(["source_employee_id"], ["employees.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "calculation_run_id", "order_id", "rule_version_id", "recipient_employee_id",
                name="uq_tip_distribution_allocation_recipient",
            ),
        )
        op.create_index(
            "ix_tip_distribution_allocations_calculation_run_id",
            "tip_distribution_allocations", ["calculation_run_id"],
        )
        op.create_index(
            "ix_tip_distribution_allocations_order_id", "tip_distribution_allocations", ["order_id"],
        )
        op.create_index(
            "ix_tip_distribution_allocations_recipient_employee_id",
            "tip_distribution_allocations", ["recipient_employee_id"],
        )
