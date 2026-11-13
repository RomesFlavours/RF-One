"""Employee lifecycle and exactly one provisioned RF1 account per person.

No inferred matches or cessation backfill. Complete source scans establish status.
Refuses, before any DDL, existing person/account conflicts (direct or through the
confirmed RF1-Training-human bridges). Reuses confirmed associations; otherwise
provisions INACTIVE shells (no password, email or grant). Downgrade refuses once
lifecycle or account history exists: restore a verified backup instead.
"""
from uuid import uuid4
from alembic import op
import sqlalchemy as sa
revision = "e3f120261103"
down_revision = "e1b220261102"
branch_labels = None
depends_on = None


def upgrade():
    db = op.get_bind()
    # Follow only confirmed authentication bridges, never names or email.
    pairs_sql = """SELECT employee_id, rfone_account_id AS account_id FROM employee_context_links WHERE rfone_account_id IS NOT NULL
        UNION SELECT c.employee_id, b.rfone_account_id FROM employee_context_links c
        JOIN rfone_training_identity_links b ON b.training_account_id = c.training_account_id
        UNION SELECT c.employee_id, b.rfone_account_id FROM employee_context_links c
        JOIN training_accounts t ON t.acting_identity_id = c.acting_identity_id
        JOIN rfone_training_identity_links b ON b.training_account_id = t.id"""
    by_person, by_account = {}, {}
    for employee, account in db.execute(sa.text(pairs_sql)):
        by_person.setdefault(employee, set()).add(account)
        by_account.setdefault(account, set()).add(employee)
    conflicts = [employee for employee, accounts in by_person.items() if len(accounts) > 1]
    if conflicts or any(len(people) > 1 for people in by_account.values()):
        raise RuntimeError("Multiple RF1 accounts or conflicting person associations: " + str(conflicts) + "; explicit reconciliation required before migration.")
    with op.batch_alter_table("employees") as batch:
        batch.add_column(sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("directory_eligible", sa.Boolean(), nullable=False, server_default=sa.true()))
    with op.batch_alter_table("employee_clover_links") as batch:
        for name in ("last_clock_in", "last_clock_out", "clocks_checked_at", "dismissed_at"):
            batch.add_column(sa.Column(name, sa.DateTime(timezone=True), nullable=True))
    op.create_index("uq_employee_one_rfone_account", "employee_context_links", ["employee_id"], unique=True,
        postgresql_where=sa.text("rfone_account_id IS NOT NULL"), sqlite_where=sa.text("rfone_account_id IS NOT NULL"))
    metadata = sa.MetaData()
    accounts = sa.Table("rfone_accounts", metadata, autoload_with=db)
    links = sa.Table("employee_context_links", metadata, autoload_with=db)
    events = sa.Table("employee_directory_events", metadata, autoload_with=db)
    # Source-backed records without any local clock are not yet known to be
    # employees: their account waits for the first complete clock scan (or an
    # explicit confirmation), never inferred from this old database snapshot.
    people = list(db.execute(sa.text("""SELECT e.id, e.display_name, e.source_employee_id IS NULL
            OR EXISTS (SELECT 1 FROM shifts s WHERE s.employee_id = e.id
                       AND (s.clock_in IS NOT NULL OR s.clock_out IS NOT NULL)) AS evidenced
        FROM employees e WHERE e.id NOT IN (SELECT employee_id FROM employee_identity_aliases)
        AND e.id NOT IN (SELECT employee_id FROM employee_context_links WHERE rfone_account_id IS NOT NULL)
        ORDER BY e.id""")))
    for identity, name, evidenced in people:
        known = by_person.get(identity, set())
        if not known and not evidenced:
            continue
        if known:
            account = next(iter(known))
            action = "ACCOUNT_ASSOCIATED"
        else:
            account = db.execute(accounts.insert().values(username="employee-" + uuid4().hex,
                display_name=name or "Nome da completare", password_hash="!", status="INACTIVE",
                is_admin=False, is_owner=False, session_version=1)).inserted_primary_key[0]
            action = "ACCOUNT_PROVISIONED"
        db.execute(links.insert().values(employee_id=identity, rfone_account_id=account))
        db.execute(events.insert().values(employee_id=identity, action=action,
                                          details={"account_id": account, "migration": revision}))


def downgrade():
    db = op.get_bind()
    used = db.scalar(sa.text("SELECT count(*) FROM employee_clover_links WHERE clocks_checked_at IS NOT NULL"))
    provisioned = db.scalar(sa.text("SELECT count(*) FROM employee_directory_events WHERE action IN ('ACCOUNT_PROVISIONED', 'ACCOUNT_ASSOCIATED')"))
    if used or provisioned or db.scalar(sa.text("SELECT count(*) FROM employees WHERE dismissed_at IS NOT NULL OR directory_eligible = false")):
        raise RuntimeError("Employee lifecycle/account history is retained; restore a verified backup instead.")
    op.drop_index("uq_employee_one_rfone_account", table_name="employee_context_links")
    with op.batch_alter_table("employee_clover_links") as batch:
        for name in ("last_clock_in", "last_clock_out", "clocks_checked_at", "dismissed_at"):
            batch.drop_column(name)
    with op.batch_alter_table("employees") as batch:
        batch.drop_column("directory_eligible")
        batch.drop_column("dismissed_at")
