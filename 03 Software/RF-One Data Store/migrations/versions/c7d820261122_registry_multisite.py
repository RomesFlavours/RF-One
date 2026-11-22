"""New multi-site Registry (REGISTRY_MULTISITE_001, Product Owner specification 2026-11-22).

Data only, no schema change:
- A Registry card linked to a physical person (`person_employee_links`) no longer implies the EMPLOYEE
  company status: a Trainee created by Training has a card too (`people_registry.company_statuses`).
  To keep every existing status unchanged, the EMPLOYEE status is recorded explicitly for each person who
  is linked to a card today and does not have it yet — except the Trainees whose card was linked by the
  new Training entry (card event TRAINING_LINK, written only by this release's code): they are Trainees,
  and are Employee only after Confirm hire (which records the status itself). This keeps a re-upgrade
  after a rollback from turning those Trainees into Employees. On AWS (a1c220261121, read 2026-11-22) the
  link table is empty, so nothing is written there. `registry_multisite_migration_check.py` computes the
  same list (`employee_status_to_record`) and `compare` requires exactly that list to be added.
No card, identity, assignment, Clover link or Tips record is created, changed or removed. Former pending
Clover identities stay in `employee_clover_links` as history: no screen or job proposes them any more.

Downgrade: nothing to undo. The former code derives EMPLOYEE from the same links, so the explicit rows are
equivalent to what it computed.
"""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = 'c7d820261122'
down_revision = 'b2c320261121'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if not {'person_employee_links', 'person_company_statuses'} <= tables:
        return
    statuses = sa.table('person_company_statuses', sa.column('person_id', sa.Integer),
                        sa.column('code', sa.String), sa.column('assigned_at', sa.DateTime(timezone=True)))
    now = datetime.now(timezone.utc)
    rows = [{'person_id': person_id, 'code': 'EMPLOYEE', 'assigned_at': now}
            for person_id in employee_status_to_record(bind)]
    if rows:
        op.bulk_insert(statuses, rows)


EMPLOYEE_STATUS_TO_RECORD_SQL = """
    SELECT DISTINCT l.person_id FROM person_employee_links l
    WHERE l.person_id NOT IN (SELECT person_id FROM person_company_statuses WHERE code = 'EMPLOYEE')
      AND l.employee_id NOT IN (SELECT employee_id FROM employee_directory_events
                                WHERE action = 'TRAINING_LINK' AND employee_id IS NOT NULL)
    ORDER BY l.person_id"""


def employee_status_to_record(bind):
    """Persons linked to a card who would lose the EMPLOYEE status they have today (see module docstring)."""
    return [row[0] for row in bind.execute(sa.text(EMPLOYEE_STATUS_TO_RECORD_SQL))]


def downgrade() -> None:
    pass
