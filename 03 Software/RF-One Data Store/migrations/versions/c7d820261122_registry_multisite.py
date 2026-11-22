"""New multi-site Registry (REGISTRY_MULTISITE_001, Product Owner specification 2026-11-22).

Data only, no schema change:
- A Registry card linked to a physical person (`person_employee_links`) no longer implies the EMPLOYEE
  company status: a Trainee created by Training has a card too (`people_registry.company_statuses`).
  To keep every existing status unchanged, the EMPLOYEE status is recorded explicitly for each person who
  is linked to a card today and does not have it yet. On AWS (a1c220261121, read 2026-11-22) the link
  table is empty, so nothing is written there.
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
    links = sa.table('person_employee_links', sa.column('person_id', sa.Integer))
    statuses = sa.table('person_company_statuses', sa.column('person_id', sa.Integer),
                        sa.column('code', sa.String), sa.column('assigned_at', sa.DateTime(timezone=True)))
    linked = {row[0] for row in bind.execute(sa.select(links.c.person_id).distinct())}
    already = {row[0] for row in bind.execute(sa.select(statuses.c.person_id).where(statuses.c.code == 'EMPLOYEE'))}
    now = datetime.now(timezone.utc)
    rows = [{'person_id': person_id, 'code': 'EMPLOYEE', 'assigned_at': now} for person_id in sorted(linked - already)]
    if rows:
        op.bulk_insert(statuses, rows)


def downgrade() -> None:
    pass
