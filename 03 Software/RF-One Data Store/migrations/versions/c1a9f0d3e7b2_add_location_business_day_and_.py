"""add location business day rule, employee assignment location, and
primary location integrity (TASK_ORGANIZATION_002)

Revision ID: c1a9f0d3e7b2
Revises: 93df95757d5e
Create Date: 2026-08-30 00:00:00.000000

Three additive, non-destructive changes, per the approved Product Owner
decisions in TASK_ORGANIZATION_002:

1. `locations.operating_day_cutoff_time` — the Location Business Day Rule
   configuration input (Restaurant Profile.md "Location Business Day Rule
   (Business Date)"; Restaurant Sales Model.md §6a). Nullable; no existing
   row's value is ever fabricated.

2. `employee_assignments.location_id` — optional Location scope for an
   Employee Assignment (Employee Assignment.md, TASK_ORGANIZATION_002).
   Nullable; every existing row is preserved with `location_id = NULL`
   (Restaurant-wide) — no historical row's Location is guessed from
   `Employee.location_id` or any other evidence (see
   TASK_ORGANIZATION_002_REPORT.md §C/§L for why this is deliberately not
   backfilled). The prior 4-column
   `UniqueConstraint(employee_id, operational_area_id, restaurant_role_id,
   valid_from)` is replaced with a 5-column one that also includes
   `location_id`, so a genuine second Assignment differing only by Location
   (e.g. Manager at Winter Park + Manager at Mount Dora, same instant) is no
   longer rejected as a false duplicate. A second, partial unique index
   catches the exact-duplicate case for Restaurant-wide (`location_id IS
   NULL`) Assignments specifically, since ordinary SQL UNIQUE semantics
   treat every NULL as distinct from every other NULL and the 5-column
   constraint alone would not catch that case.

   The prior UniqueConstraint has no explicit name (SQLAlchemy leaves
   unnamed constraints unnamed; SQLite reflects it as an internal
   `sqlite_autoindex_*`), so `batch_alter_table`'s constraint-by-name API
   cannot target it directly. This migration instead recreates
   `employee_assignments` explicitly (rename -> create new -> copy rows ->
   drop old), which both replaces the constraint and preserves every
   existing row's data — the same non-destructive outcome batch mode's
   copy-and-move strategy would produce, done explicitly because the
   constraint has no name to hand to `drop_constraint`.

3. `restaurant_locations` — a partial unique index enforcing "at most one
   currently-active (`valid_to IS NULL`) primary (`is_primary = true`)
   Location per Restaurant" (Restaurant Profile.md; TASK_ORGANIZATION_002
   Decision 2). Historical (closed) primary-Location rows are never
   constrained by this index, so changing a Restaurant's primary Location
   over time remains fully representable.

No existing row in any table is modified, reordered, or deleted by this
migration (rows are copied verbatim, `employee_assignments.id` preserved).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1a9f0d3e7b2'
down_revision: Union[str, Sequence[str], None] = '93df95757d5e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # --- 1. Location Business Day Rule configuration input ------------------
    # Plain additive nullable column; batch mode used only for consistency
    # with this schema's established convention for `locations`/similar
    # tables (e6df7aa7d83b), not because SQLite requires it for a simple
    # ADD COLUMN with no constraint.
    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('operating_day_cutoff_time', sa.Time(), nullable=True))

    # --- 2. Employee Assignment optional Location scope ---------------------
    op.rename_table('employee_assignments', '_employee_assignments_old')

    # These index names now point at the renamed table; they must be
    # dropped before recreating indexes of the same name on the new table
    # (SQLite index names are unique per schema, not per table).
    op.drop_index('ix_employee_assignments_employee_id', table_name='_employee_assignments_old')
    op.drop_index('ix_employee_assignments_employee_valid_from', table_name='_employee_assignments_old')
    op.drop_index('ix_employee_assignments_operational_area_id', table_name='_employee_assignments_old')
    op.drop_index('ix_employee_assignments_restaurant_id', table_name='_employee_assignments_old')
    op.drop_index('ix_employee_assignments_restaurant_role_id', table_name='_employee_assignments_old')

    op.create_table(
        'employee_assignments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=False),
        sa.Column('operational_area_id', sa.Integer(), nullable=False),
        sa.Column('restaurant_role_id', sa.Integer(), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=True),
        sa.Column('physical_area_id', sa.Integer(), nullable=True),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('assignment_source', sa.String(length=32), nullable=False),
        sa.Column('source_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id']),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id']),
        sa.ForeignKeyConstraint(['operational_area_id'], ['operational_areas.id']),
        sa.ForeignKeyConstraint(['physical_area_id'], ['physical_areas.id']),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id']),
        sa.ForeignKeyConstraint(['restaurant_role_id'], ['restaurant_roles.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'employee_id', 'operational_area_id', 'restaurant_role_id', 'location_id', 'valid_from'
        ),
    )

    op.execute(
        "INSERT INTO employee_assignments "
        "(id, employee_id, restaurant_id, operational_area_id, restaurant_role_id, "
        " location_id, physical_area_id, valid_from, valid_to, assignment_source, "
        " source_note, created_at, updated_at) "
        "SELECT id, employee_id, restaurant_id, operational_area_id, restaurant_role_id, "
        " NULL, physical_area_id, valid_from, valid_to, assignment_source, "
        " source_note, created_at, updated_at "
        "FROM _employee_assignments_old"
    )

    op.drop_table('_employee_assignments_old')

    op.create_index(op.f('ix_employee_assignments_employee_id'), 'employee_assignments', ['employee_id'], unique=False)
    op.create_index('ix_employee_assignments_employee_valid_from', 'employee_assignments', ['employee_id', 'valid_from'], unique=False)
    op.create_index(op.f('ix_employee_assignments_location_id'), 'employee_assignments', ['location_id'], unique=False)
    op.create_index(op.f('ix_employee_assignments_operational_area_id'), 'employee_assignments', ['operational_area_id'], unique=False)
    op.create_index(op.f('ix_employee_assignments_restaurant_id'), 'employee_assignments', ['restaurant_id'], unique=False)
    op.create_index(op.f('ix_employee_assignments_restaurant_role_id'), 'employee_assignments', ['restaurant_role_id'], unique=False)
    op.create_index(
        'ux_employee_assignments_dup_no_location',
        'employee_assignments',
        ['employee_id', 'operational_area_id', 'restaurant_role_id', 'valid_from'],
        unique=True,
        sqlite_where=sa.text('location_id IS NULL'),
    )

    # --- 3. Primary Location integrity --------------------------------------
    op.create_index(
        'ux_restaurant_locations_one_open_primary',
        'restaurant_locations',
        ['restaurant_id'],
        unique=True,
        sqlite_where=sa.text('is_primary = 1 AND valid_to IS NULL'),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index('ux_restaurant_locations_one_open_primary', table_name='restaurant_locations')

    op.drop_index('ux_employee_assignments_dup_no_location', table_name='employee_assignments')
    op.drop_index(op.f('ix_employee_assignments_restaurant_role_id'), table_name='employee_assignments')
    op.drop_index(op.f('ix_employee_assignments_restaurant_id'), table_name='employee_assignments')
    op.drop_index(op.f('ix_employee_assignments_operational_area_id'), table_name='employee_assignments')
    op.drop_index(op.f('ix_employee_assignments_location_id'), table_name='employee_assignments')
    op.drop_index('ix_employee_assignments_employee_valid_from', table_name='employee_assignments')
    op.drop_index(op.f('ix_employee_assignments_employee_id'), table_name='employee_assignments')

    op.rename_table('employee_assignments', '_employee_assignments_new')

    op.create_table(
        'employee_assignments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('restaurant_id', sa.Integer(), nullable=False),
        sa.Column('operational_area_id', sa.Integer(), nullable=False),
        sa.Column('restaurant_role_id', sa.Integer(), nullable=False),
        sa.Column('physical_area_id', sa.Integer(), nullable=True),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('assignment_source', sa.String(length=32), nullable=False),
        sa.Column('source_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id']),
        sa.ForeignKeyConstraint(['operational_area_id'], ['operational_areas.id']),
        sa.ForeignKeyConstraint(['physical_area_id'], ['physical_areas.id']),
        sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id']),
        sa.ForeignKeyConstraint(['restaurant_role_id'], ['restaurant_roles.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('employee_id', 'operational_area_id', 'restaurant_role_id', 'valid_from'),
    )

    op.execute(
        "INSERT INTO employee_assignments "
        "(id, employee_id, restaurant_id, operational_area_id, restaurant_role_id, "
        " physical_area_id, valid_from, valid_to, assignment_source, "
        " source_note, created_at, updated_at) "
        "SELECT id, employee_id, restaurant_id, operational_area_id, restaurant_role_id, "
        " physical_area_id, valid_from, valid_to, assignment_source, "
        " source_note, created_at, updated_at "
        "FROM _employee_assignments_new"
    )

    op.drop_table('_employee_assignments_new')

    op.create_index(op.f('ix_employee_assignments_employee_id'), 'employee_assignments', ['employee_id'], unique=False)
    op.create_index('ix_employee_assignments_employee_valid_from', 'employee_assignments', ['employee_id', 'valid_from'], unique=False)
    op.create_index(op.f('ix_employee_assignments_operational_area_id'), 'employee_assignments', ['operational_area_id'], unique=False)
    op.create_index(op.f('ix_employee_assignments_restaurant_id'), 'employee_assignments', ['restaurant_id'], unique=False)
    op.create_index(op.f('ix_employee_assignments_restaurant_role_id'), 'employee_assignments', ['restaurant_role_id'], unique=False)

    with op.batch_alter_table('locations', schema=None) as batch_op:
        batch_op.drop_column('operating_day_cutoff_time')
