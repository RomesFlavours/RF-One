"""persist finalized Tips periods and the rule version lifecycle

TIPS_FINALIZED_PERIOD_CALCULATION_AND_REPORT_001 §7/§12/§13/§16.

Four additive changes, no data rewritten:

1. `tip_distribution_rule_versions.status` — ACTIVE / OLD / CANCELLED (§7).
   Every existing row becomes ACTIVE. The migration deliberately does NOT
   try to infer which historical versions "should" have been OLD or
   CANCELLED: those statuses are the consequence of a replacement actually
   being performed (`distribution_rule_service.create_new_version`), and
   guessing them here would be this migration inventing rule history it
   was not told. An ACTIVE version with a zero-length window governs no
   instant in time either way, so nothing is misreported in the meantime.

2. `tip_distribution_calculation_runs` gains the Business Dates, the
   Business Day configuration and Rule Versions the run was computed
   under, its period totals and single control, and its validation/
   finalization record (§12/§14/§15/§16/§17). All nullable: the existing
   payout-anchor rows were created before any of this existed and are not
   retro-fitted with figures nobody calculated. `state` and
   `finalized_automatically` are the two exceptions, with safe
   server-defaults — an old row reads as CALCULATED and not automatically
   finalized, which is exactly what it is.

3. `tip_entitlements` gains the per-person voluntary/gratuity split, the
   result type and the §6 retained-with-no-eligible-Host figure (§13),
   all nullable for the same reason.

4. `tips_validation_mode_configs` — the SEPARATE validation-mode
   configuration §16 asked for. No row is created for any Restaurant: the
   absence of a row means MANUAL, which is the default this task requires,
   so seeding rows would only add ways for the default to be got wrong.

Revision ID: e8b3d74f02a1
Revises: c4a9e7d21b56
Create Date: 2026-09-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e8b3d74f02a1"
down_revision = "c4a9e7d21b56"
branch_labels = None
depends_on = None

RULE_VERSIONS = "tip_distribution_rule_versions"
RUNS = "tip_distribution_calculation_runs"
ENTITLEMENTS = "tip_entitlements"
VALIDATION_MODE = "tips_validation_mode_configs"

_RULE_VERSION_STATUS_CHECK = (
    "ck_tip_distribution_rule_version_status",
    "status IN ('ACTIVE','OLD','CANCELLED')",
)

# (name, type, nullable, server_default)
_RUN_COLUMNS = [
    ("first_business_date", sa.Date(), True, None),
    ("last_business_date", sa.Date(), True, None),
    ("timezone_name", sa.String(length=64), True, None),
    ("operating_day_cutoff_time", sa.Time(), True, None),
    ("rule_version_ids", sa.String(length=255), True, None),
    ("voluntary_total_minor", sa.Integer(), True, None),
    ("gratuity_total_minor", sa.Integer(), True, None),
    ("service_owner_entitlements_minor", sa.Integer(), True, None),
    ("other_recipient_entitlements_minor", sa.Integer(), True, None),
    ("retained_no_eligible_host_minor", sa.Integer(), True, None),
    ("distributed_minor", sa.Integer(), True, None),
    ("control_difference_minor", sa.Integer(), True, None),
    ("state", sa.String(length=16), False, "CALCULATED"),
    ("validation_mode", sa.String(length=16), True, None),
    ("validated_at", sa.DateTime(timezone=True), True, None),
    ("validated_by_account_id", sa.Integer(), True, None),
    ("finalized_at", sa.DateTime(timezone=True), True, None),
    ("finalized_by_account_id", sa.Integer(), True, None),
    # sa.false(), not "0": PostgreSQL rejects an integer default on a
    # boolean column, and this chain is applied to RDS PostgreSQL.
    ("finalized_automatically", sa.Boolean(), False, sa.false()),
]

_ENTITLEMENT_COLUMNS = [
    ("voluntary_amount_minor", sa.Integer()),
    ("gratuity_amount_minor", sa.Integer()),
    ("result_type", sa.String(length=16)),
    ("retained_no_eligible_host_minor", sa.Integer()),
]


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # --- 1. rule version lifecycle (§7) ---------------------------------
    # SQLite cannot add a CHECK to an existing table, so the column and its
    # constraint go in together through a table rebuild — the same pattern
    # the earlier Bank migrations in this repository already use.
    name, condition = _RULE_VERSION_STATUS_CHECK
    if is_sqlite:
        with op.batch_alter_table(RULE_VERSIONS, schema=None, recreate="always") as batch_op:
            batch_op.add_column(
                sa.Column("status", sa.String(length=16), nullable=False, server_default="ACTIVE")
            )
            batch_op.create_check_constraint(name, condition)
    else:
        op.add_column(
            RULE_VERSIONS,
            sa.Column("status", sa.String(length=16), nullable=False, server_default="ACTIVE"),
        )
        op.create_check_constraint(name, RULE_VERSIONS, condition)

    # --- 2. the persisted, finalizable run (§12/§14/§15/§16/§17) --------
    for col_name, col_type, nullable, default in _RUN_COLUMNS:
        op.add_column(
            RUNS, sa.Column(col_name, col_type, nullable=nullable, server_default=default)
        )
    op.create_index(
        "ix_tip_distribution_calculation_runs_first_business_date",
        RUNS, ["first_business_date"],
    )
    op.create_index(
        "ix_tip_distribution_calculation_runs_last_business_date",
        RUNS, ["last_business_date"],
    )
    if not is_sqlite:
        # The two validator/finalizer FKs. Skipped on SQLite, where adding
        # a foreign key to an existing table requires rebuilding it: the
        # ORM declares both relationships, and rebuilding this table just
        # to record a constraint SQLite does not enforce by default would
        # be more risk than the constraint is worth here.
        op.create_foreign_key(
            "fk_tip_run_validated_by_account", RUNS, "rfone_accounts",
            ["validated_by_account_id"], ["id"],
        )
        op.create_foreign_key(
            "fk_tip_run_finalized_by_account", RUNS, "rfone_accounts",
            ["finalized_by_account_id"], ["id"],
        )

    # --- 3. the per-person result (§13) ---------------------------------
    for col_name, col_type in _ENTITLEMENT_COLUMNS:
        op.add_column(ENTITLEMENTS, sa.Column(col_name, col_type, nullable=True))

    # --- 4. the separate validation-mode configuration (§16) -----------
    op.create_table(
        VALIDATION_MODE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), nullable=False),
        sa.Column(
            "validation_mode", sa.String(length=16), nullable=False, server_default="MANUAL"
        ),
        sa.Column(
            "updated_by_account_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("restaurant_id", name="uq_tips_validation_mode_config_restaurant"),
        sa.CheckConstraint(
            "validation_mode IN ('MANUAL','AUTOMATIC')",
            name="ck_tips_validation_mode_config_mode",
        ),
    )
    op.create_index(
        "ix_tips_validation_mode_configs_restaurant_id", VALIDATION_MODE, ["restaurant_id"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    op.drop_index("ix_tips_validation_mode_configs_restaurant_id", table_name=VALIDATION_MODE)
    op.drop_table(VALIDATION_MODE)

    for col_name, _ in reversed(_ENTITLEMENT_COLUMNS):
        op.drop_column(ENTITLEMENTS, col_name)

    if not is_sqlite:
        op.drop_constraint("fk_tip_run_finalized_by_account", RUNS, type_="foreignkey")
        op.drop_constraint("fk_tip_run_validated_by_account", RUNS, type_="foreignkey")
    op.drop_index("ix_tip_distribution_calculation_runs_last_business_date", table_name=RUNS)
    op.drop_index("ix_tip_distribution_calculation_runs_first_business_date", table_name=RUNS)
    for col_name, _, _, _ in reversed(_RUN_COLUMNS):
        op.drop_column(RUNS, col_name)

    name, _ = _RULE_VERSION_STATUS_CHECK
    if is_sqlite:
        with op.batch_alter_table(RULE_VERSIONS, schema=None, recreate="always") as batch_op:
            batch_op.drop_constraint(name, type_="check")
            batch_op.drop_column("status")
    else:
        op.drop_constraint(name, RULE_VERSIONS, type_="check")
        op.drop_column(RULE_VERSIONS, "status")
