"""Included RF-One person directory and explicit domain context links."""
from alembic import op
import sqlalchemy as sa
revision = "d9e220261029"
down_revision = "c8e1f4a7b2d6"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("employees") as batch:
        batch.alter_column("location_id", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("email", sa.String(255), nullable=True))
        batch.add_column(sa.Column("phone", sa.String(64), nullable=True))
    targets = {"rfone_account_id": "rfone_accounts", "acting_identity_id": "acting_identities",
               "training_account_id": "training_accounts", "candidate_person_id": "candidate_persons",
               "project_responsible_id": "project_responsible"}
    expression = " + ".join(f"CASE WHEN {col} IS NULL THEN 0 ELSE 1 END" for col in targets)
    op.create_table("employee_context_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        *(sa.Column(col, sa.Integer(), sa.ForeignKey(table + ".id"), unique=True) for col, table in targets.items()),
        sa.Column("created_by_account_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("(" + expression + ") = 1", name="ck_employee_context_one_target"))
    op.create_index("ix_employee_context_links_employee_id", "employee_context_links", ["employee_id"])

def downgrade():
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT count(*) FROM employee_context_links")) or connection.scalar(sa.text(
        "SELECT count(*) FROM employees WHERE location_id IS NULL OR email IS NOT NULL OR phone IS NOT NULL")):
        raise RuntimeError("Refusing to discard RF-One person data/context links; restore a verified backup instead.")
    op.drop_table("employee_context_links")
    with op.batch_alter_table("employees") as batch:
        batch.drop_column("phone")
        batch.drop_column("email")
        batch.alter_column("location_id", existing_type=sa.Integer(), nullable=False)
