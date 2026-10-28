"""Shared employee directory; preserve every existing employee ID."""
from alembic import op
import sqlalchemy as sa

revision = "c8e1f4a7b2d6"
down_revision = "d5a120261021"
branch_labels = None
depends_on = None


def upgrade():
    # These nullable columns already exist on AWS's deployed Clover reader,
    # but were absent from the older Git migration history. Preserve them on
    # AWS and make clean installations reproduce that deployed schema.
    for table, column, type_ in [("employees", "source_available", sa.Boolean()),
                                ("employees", "source_checked_at", sa.DateTime(timezone=True)),
                                ("order_items", "source_present", sa.Boolean())]:
        if column not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}:
            op.add_column(table, sa.Column(column, type_, nullable=True))
    # The legacy source-pair key incorrectly assumes an employee ID is global
    # across merchants. Keep the compatibility columns scoped to Location.
    old = next(c for c in sa.inspect(op.get_bind()).get_unique_constraints("employees")
               if c["column_names"] == ["source_system_id", "source_employee_id"])
    with op.batch_alter_table("employees", naming_convention={"uq": "uq_%(table_name)s_%(column_0_name)s_%(column_1_name)s"}) as batch:
        batch.drop_constraint(old["name"] or "uq_employees_source_system_id_source_employee_id", type_="unique")
        batch.create_unique_constraint("uq_employees_location_source_employee", ["location_id", "source_system_id", "source_employee_id"])
    op.create_table(
        "employee_clover_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("merchant_id", sa.String(128), nullable=False),
        sa.Column("external_employee_id", sa.String(128), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_id", sa.Integer(), sa.ForeignKey("ingestion_runs.id"), nullable=True),
        sa.Column("state", sa.String(24), nullable=False),
        sa.UniqueConstraint("merchant_id", "external_employee_id", name="uq_employee_clover_identity"),
    )
    op.create_index("ix_employee_clover_links_employee_id", "employee_clover_links", ["employee_id"])
    op.create_table(
        "employee_identity_aliases",
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), primary_key=True),
        sa.Column("canonical_employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=True),
        sa.Column("merged_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_employee_identity_aliases_canonical_employee_id", "employee_identity_aliases", ["canonical_employee_id"])
    op.create_table(
        "employee_directory_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("link_id", sa.Integer(), sa.ForeignKey("employee_clover_links.id"), nullable=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("rfone_accounts.id"), nullable=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_employee_directory_events_employee_id", "employee_directory_events", ["employee_id"])
    # SQL-only, no runtime imports: stable when future application code changes.
    op.execute(sa.text("""
        INSERT INTO employee_clover_links
            (employee_id, location_id, merchant_id, external_employee_id, state)
        SELECT e.id, e.location_id, l.source_location_id, e.source_employee_id, 'UNVERIFIED'
        FROM employees e JOIN locations l ON l.id = e.location_id
        JOIN source_systems s ON s.id = e.source_system_id
        WHERE s.code = 'CLOVER' AND l.source_system_id = s.id
          AND l.source_location_id IS NOT NULL AND e.source_employee_id IS NOT NULL
    """))
    # Bootstrap only the existing RF-One owner, who already administers
    # access grants. Other accounts receive no new access implicitly.
    op.execute(sa.text("""
        INSERT INTO rfone_account_domain_access (account_id, domain_code, role_code, enabled, scope)
        SELECT a.id, 'EMPLOYEES', 'admin', true, 'ALL' FROM rfone_accounts a
        WHERE a.is_owner = true AND a.status = 'ACTIVE'
          AND NOT EXISTS (SELECT 1 FROM rfone_account_domain_access d
                          WHERE d.account_id=a.id AND d.domain_code='EMPLOYEES')
    """))


def downgrade():
    # Directory history cannot be recreated by downgrade/upgrade; take a DB backup.
    op.drop_table("employee_directory_events")
    op.drop_table("employee_identity_aliases")
    op.drop_table("employee_clover_links")
    with op.batch_alter_table("employees") as batch:
        batch.drop_constraint("uq_employees_location_source_employee", type_="unique")
        batch.create_unique_constraint("uq_employees_source_system_id_source_employee_id", ["source_system_id", "source_employee_id"])
