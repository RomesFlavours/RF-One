"""Organizational applicability of a person, owned by the Employee Directory.

Additive only: two new tables, no backfill. Every existing person starts as
NOT_CONFIGURED (no row), which RF-One never reads as the whole group; the
Product Owner sets each scope explicitly in the Employee Directory.
"""
from alembic import op
import sqlalchemy as sa

revision = "e4a120261103"
down_revision = "e3f120261103"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "employee_applicability",
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), primary_key=True),
        sa.Column("scope_kind", sa.String(16), nullable=False),
        sa.Column("updated_by_account_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("scope_kind IN ('RESTAURANT', 'RESTAURANTS', 'GROUP')",
                           name="ck_employee_applicability_kind"),
    )
    op.create_table(
        "employee_applicability_restaurants",
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), primary_key=True),
        sa.Column("restaurant_id", sa.Integer(), sa.ForeignKey("restaurants.id"), primary_key=True),
    )
    op.create_index("ix_employee_applicability_restaurants_restaurant_id",
                    "employee_applicability_restaurants", ["restaurant_id"])


def downgrade():
    db = op.get_bind()
    if db.execute(sa.text("SELECT COUNT(*) FROM employee_applicability")).scalar():
        raise RuntimeError("Applicability has been configured; restore a verified backup instead of downgrading.")
    op.drop_index("ix_employee_applicability_restaurants_restaurant_id", "employee_applicability_restaurants")
    op.drop_table("employee_applicability_restaurants")
    op.drop_table("employee_applicability")
