"""add employee_assignments one-active-role-per-restaurant index (EMPLOYEE_ASSIGNMENT_CLOVER_ALIGNMENT_001)

Revision ID: e7c1a9f4d6b3
Revises: d4f9b2c8e1a6
Create Date: 2026-09-19 00:00:00.000000

Corrects `EmployeeAssignment`'s original TASK_ORGANIZATION_002 design point
("no constraint forces one Employee to have only one Role/Area globally or
at a given instant") to match Clover's actual operating model: one Clover
Employee account = exactly one active Role at a time, within one
Restaurant/merchant. Adds a partial unique index —
`(employee_id, restaurant_id)` WHERE `valid_to IS NULL` — enforcing at most
one OPEN Assignment per Employee per Restaurant at the database level,
regardless of Area/Location. Mirrors the exact same pattern already
established for `restaurant_locations.ux_restaurant_locations_one_open_primary`
(migration `c1a9f0d3e7b2`).

Purely additive: no column, table, or existing row is touched. Safe against
the current live data (`employee_assignments` has zero rows in production
today), and does not prevent legitimate history — a Role change still
closes the prior row's `valid_to` and opens a new one, never two open rows
for the same (Employee, Restaurant) at once. The same Employee may still
hold an independent, concurrently-open Role at a DIFFERENT Restaurant —
this index is scoped per Restaurant, never globally per Identity.

Cross-dialect fix (AWS_RDS_ALEMBIC_RECONCILIATION_001, found during the
first real audit of this migration against PostgreSQL): the original
`sqlite_where` kwarg is only honored by SQLAlchemy's SQLite dialect —
Alembic/SQLAlchemy silently ignore an unrecognized dialect-specific kwarg
rather than erroring, so on PostgreSQL this created a FULL unique index on
`(employee_id, restaurant_id)` instead of the intended partial one, which
would incorrectly reject a closed historical row coexisting with a new
open one. Adding the matching `postgresql_where` kwarg makes both dialects
enforce the same, originally-intended constraint. No behavior change on
SQLite.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7c1a9f4d6b3'
down_revision: Union[str, Sequence[str], None] = 'd4f9b2c8e1a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        'ux_employee_assignments_one_active_role_per_restaurant',
        'employee_assignments',
        ['employee_id', 'restaurant_id'],
        unique=True,
        sqlite_where=sa.text('valid_to IS NULL'),
        postgresql_where=sa.text('valid_to IS NULL'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ux_employee_assignments_one_active_role_per_restaurant', table_name='employee_assignments')
