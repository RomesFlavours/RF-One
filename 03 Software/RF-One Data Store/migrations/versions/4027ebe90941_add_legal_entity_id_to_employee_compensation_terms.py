"""add legal_entity_id to employee_compensation_terms

Revision ID: 4027ebe90941
Revises: 6ab2b01f7172
Create Date: 2026-09-08 19:23:00.000000

Adds the Legal Entity dimension (`legal_entity_id`) required by the Employee
Income Composition & Payroll functional specification (`01 Domains/Cross
Domain/Personnel Management/Payroll/
EMPLOYEE_INCOME_COMPOSITION_AND_PAYROLL_001.md` §5) to the existing,
already-approved `employee_compensation_terms` table (TASK_PAYROLL_001).

Product Owner correction: an earlier version of this change added a column
named `restaurant_id` pointing at `restaurants.id`. A follow-up read-only
verification then confirmed `Restaurant` is formally an Operational Unit
(`01 Domains/Business Domain/Restaurant/Model/OU-Restaurant.md`, "Extends:
Operational Unit"), never the Legal Entity itself — a Legal Entity may
legitimately own several Restaurants, so scoping compensation by
`restaurant_id` would have incorrectly required a separate compensation
term per Restaurant even for one Legal Entity's single employment
relationship. That earlier change was itself still uncommitted, so this
migration replaces it outright with `legal_entity_id` pointing at the new
canonical `LegalEntity` model, rather than shipping the wrong column and
correcting it in a second migration.

`legal_entity_id` is nullable: historical rows created before this column
existed never had a value to record (same convention as
`payroll_runs.payment_execution_provider` /
`payroll_import_runs.acquisition_method`) — never guessed. The Payroll
Calculation Engine's validation requires it to be set, and to match the
calculation run's Legal Entity, before a term can be used; a NULL
`legal_entity_id` is always rejected by the engine (a data-readiness/
backfill condition, not a model contradiction — see the engine's own
docstring).

The unique constraint is `UNIQUE (employee_id, legal_entity_id,
function_label, valid_from)` so the same Employee can hold
concurrently-effective, same-`function_label` terms for two different Legal
Entities without a uniqueness violation. SQLite has no `ALTER TABLE`/
`DROP CONSTRAINT` support for changing an unnamed unique constraint, so this
table is rebuilt explicitly rather than via `batch_alter_table`, which
cannot address an unnamed constraint either.

Rebuild order is deliberately: create the replacement under a TEMPORARY name
-> copy data -> drop the original -> rename the replacement into the
original's name. Renaming the ORIGINAL table away first (the naive order)
triggers SQLite's automatic rewrite of every OTHER table's stored
`FOREIGN KEY ... REFERENCES employee_compensation_terms` clause to point at
the temporary name instead — and `employee_payroll_calculation_earning_lines`
has exactly such a foreign key. Dropping the temporary name afterward then
leaves that other table permanently pointing at a nonexistent table.
Creating the replacement under a temporary name that nothing references,
then renaming it INTO the final name only after the original is gone, never
triggers that rewrite, so every other table's existing
`REFERENCES employee_compensation_terms` clause simply resolves correctly
again once the rename completes. Table currently has 0 rows in every
environment this has been applied to so far, but the copy step is written
to preserve any real data regardless.

No other table, and no other column of `employee_compensation_terms`, is
changed.

PostgreSQL correction (2026-09-10): the table-rebuild approach above is
SQLite-only motivated (SQLite cannot `ALTER`/`DROP CONSTRAINT` an unnamed
unique constraint). On PostgreSQL it is actively wrong: `DROP TABLE
employee_compensation_terms` fails once any other table holds an inbound FK
to it (`employee_payroll_results.compensation_term_id`, and — within this
same migration chain — `employee_payroll_calculation_earning_lines.
compensation_term_id` added by the immediately preceding revision,
`6ab2b01f7172`), and dropping/recreating it would in any case discard those
FKs and any real data. PostgreSQL *can* address the existing unnamed unique
constraint directly, because it auto-named it on creation
(`employee_compensation_terms_employee_id_function_label_vali_key`,
confirmed via `pg_constraint` against the live `rfone-dev` database) — so
this migration now branches on dialect: SQLite keeps the original
table-rebuild exactly as written above; PostgreSQL instead adds the column,
foreign key and index in place with plain `ALTER TABLE`-style operations,
and swaps the unique constraint for a same-shaped one covering
`legal_entity_id`, without ever dropping the table itself.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4027ebe90941'
down_revision: Union[str, Sequence[str], None] = '6ab2b01f7172'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_COLUMNS = (
    "id, employee_id, function_label, restaurant_role_id, compensation_basis, "
    "hourly_rate_minor, salaried_period_amount_minor, valid_from, valid_to, "
    "source_note, created_at, updated_at"
)
_NEW_COLUMNS_FROM_OLD = (
    "id, employee_id, NULL, function_label, restaurant_role_id, compensation_basis, "
    "hourly_rate_minor, salaried_period_amount_minor, valid_from, valid_to, "
    "source_note, created_at, updated_at"
)
_NEW_COLUMNS = (
    "id, employee_id, legal_entity_id, function_label, restaurant_role_id, "
    "compensation_basis, hourly_rate_minor, salaried_period_amount_minor, valid_from, "
    "valid_to, source_note, created_at, updated_at"
)

_BASIS_CHECK = (
    "(compensation_basis = 'HOURLY' AND hourly_rate_minor IS NOT NULL "
    "AND salaried_period_amount_minor IS NULL) "
    "OR (compensation_basis = 'SALARIED' AND salaried_period_amount_minor IS NOT NULL "
    "AND hourly_rate_minor IS NULL)"
)


def upgrade() -> None:
    """Upgrade schema."""
    if op.get_bind().dialect.name == "sqlite":
        _upgrade_sqlite()
    else:
        _upgrade_postgresql()


def _upgrade_sqlite() -> None:
    op.create_table(
        '_employee_compensation_terms_new',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('legal_entity_id', sa.Integer(), sa.ForeignKey('legal_entities.id'), nullable=True),
        sa.Column('function_label', sa.String(length=255), nullable=False),
        sa.Column(
            'restaurant_role_id', sa.Integer(), sa.ForeignKey('restaurant_roles.id'), nullable=True
        ),
        sa.Column('compensation_basis', sa.String(length=16), nullable=False),
        sa.Column('hourly_rate_minor', sa.Integer(), nullable=True),
        sa.Column('salaried_period_amount_minor', sa.Integer(), nullable=True),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source_note', sa.Text(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.CheckConstraint(_BASIS_CHECK, name='ck_employee_compensation_terms_basis_matches_amount'),
        sa.UniqueConstraint('employee_id', 'legal_entity_id', 'function_label', 'valid_from'),
    )
    op.execute(
        f"INSERT INTO _employee_compensation_terms_new ({_NEW_COLUMNS}) "
        f"SELECT {_NEW_COLUMNS_FROM_OLD} FROM employee_compensation_terms"
    )
    op.drop_table('employee_compensation_terms')
    op.rename_table('_employee_compensation_terms_new', 'employee_compensation_terms')

    op.create_index(
        op.f('ix_employee_compensation_terms_employee_id'), 'employee_compensation_terms',
        ['employee_id'], unique=False,
    )
    op.create_index(
        op.f('ix_employee_compensation_terms_legal_entity_id'), 'employee_compensation_terms',
        ['legal_entity_id'], unique=False,
    )


def _upgrade_postgresql() -> None:
    op.add_column(
        'employee_compensation_terms',
        sa.Column('legal_entity_id', sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        'fk_employee_compensation_terms_legal_entity_id',
        'employee_compensation_terms',
        'legal_entities',
        ['legal_entity_id'],
        ['id'],
    )
    op.create_index(
        op.f('ix_employee_compensation_terms_legal_entity_id'), 'employee_compensation_terms',
        ['legal_entity_id'], unique=False,
    )
    # ix_employee_compensation_terms_employee_id already exists (created by
    # 47b3d9bb8108) — the table is never dropped on this path, so it is left
    # untouched rather than recreated.
    op.drop_constraint(
        'employee_compensation_terms_employee_id_function_label_vali_key',
        'employee_compensation_terms',
        type_='unique',
    )
    op.create_unique_constraint(
        'uq_ect_employee_legal_entity_function_valid_from',
        'employee_compensation_terms',
        ['employee_id', 'legal_entity_id', 'function_label', 'valid_from'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    if op.get_bind().dialect.name == "sqlite":
        _downgrade_sqlite()
    else:
        _downgrade_postgresql()


def _downgrade_sqlite() -> None:
    op.create_table(
        '_employee_compensation_terms_old',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('function_label', sa.String(length=255), nullable=False),
        sa.Column(
            'restaurant_role_id', sa.Integer(), sa.ForeignKey('restaurant_roles.id'), nullable=True
        ),
        sa.Column('compensation_basis', sa.String(length=16), nullable=False),
        sa.Column('hourly_rate_minor', sa.Integer(), nullable=True),
        sa.Column('salaried_period_amount_minor', sa.Integer(), nullable=True),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source_note', sa.Text(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.CheckConstraint(_BASIS_CHECK, name='ck_employee_compensation_terms_basis_matches_amount'),
        sa.UniqueConstraint('employee_id', 'function_label', 'valid_from'),
    )
    op.execute(
        f"INSERT INTO _employee_compensation_terms_old ({_OLD_COLUMNS}) "
        f"SELECT {_OLD_COLUMNS} FROM employee_compensation_terms"
    )
    op.drop_table('employee_compensation_terms')
    op.rename_table('_employee_compensation_terms_old', 'employee_compensation_terms')

    op.create_index(
        op.f('ix_employee_compensation_terms_employee_id'), 'employee_compensation_terms',
        ['employee_id'], unique=False,
    )


def _downgrade_postgresql() -> None:
    op.drop_constraint(
        'uq_ect_employee_legal_entity_function_valid_from',
        'employee_compensation_terms',
        type_='unique',
    )
    op.create_unique_constraint(
        'employee_compensation_terms_employee_id_function_label_vali_key',
        'employee_compensation_terms',
        ['employee_id', 'function_label', 'valid_from'],
    )
    op.drop_index(
        op.f('ix_employee_compensation_terms_legal_entity_id'),
        table_name='employee_compensation_terms',
    )
    op.drop_constraint(
        'fk_employee_compensation_terms_legal_entity_id',
        'employee_compensation_terms',
        type_='foreignkey',
    )
    op.drop_column('employee_compensation_terms', 'legal_entity_id')
