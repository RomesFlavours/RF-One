"""Link existing people to employee records, logins and interviews."""
from alembic import op
import sqlalchemy as sa

revision = "f9e220261101"
down_revision = "f8d120261101"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("person_account_links",
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), primary_key=True),
        sa.Column("person_id", sa.Integer(), sa.ForeignKey("candidate_persons.id"), nullable=False, unique=True),
        sa.Column("linked_by_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("person_employee_links",
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), primary_key=True),
        sa.Column("person_id", sa.Integer(), sa.ForeignKey("candidate_persons.id"), nullable=False),
        sa.Column("linked_by_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_person_employee_links_person_id", "person_employee_links", ["person_id"])
    with op.batch_alter_table("interview_sessions") as batch:
        batch.add_column(sa.Column("person_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_interview_person", "candidate_persons", ["person_id"], ["id"])
    op.create_index("ix_interview_sessions_person_id", "interview_sessions", ["person_id"])


def downgrade():
    op.drop_index("ix_interview_sessions_person_id", table_name="interview_sessions")
    with op.batch_alter_table("interview_sessions") as batch:
        batch.drop_constraint("fk_interview_person", type_="foreignkey")
        batch.drop_column("person_id")
    op.drop_table("person_employee_links")
    op.drop_table("person_account_links")
