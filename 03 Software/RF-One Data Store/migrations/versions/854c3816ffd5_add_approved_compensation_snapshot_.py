"""add approved compensation snapshot foundation

Revision ID: 854c3816ffd5
Revises: aa3edadc9816
Create Date: 2026-09-09 21:40:37.977075

Adds the Approved Compensation Snapshot foundation (Compensation V1 Task 1,
Product Owner decision): `approved_compensation_snapshots` (one immutable
header per approved `CompensationPreparationRun` — physical table
`payroll_calculation_runs`), `approved_employee_compensation_results` (one
immutable, value-copied row per Employee per snapshot), and
`approved_employee_earning_lines` (one immutable, value-copied row per
earning line). None of these tables is ever updated or deleted by
application code once a row is created — see
`rfone_data_store/payroll_calculation/approval.py`, the only code that
writes them.

Also widens `payroll_calculation_runs`'s existing `status` CheckConstraint
from `('OPEN', 'CALCULATED')` to `('OPEN', 'CALCULATED', 'APPROVED')` —
`EXPORTED`/`CLOSED` (functional spec §19) remain out of scope for this task.
Autogenerate does not reliably diff CHECK constraint bodies on SQLite, so
this part was added by hand and applied via `batch_alter_table` (the
constraint is named, so no unnamed-constraint table rebuild is needed here
— see the note on the earlier `employee_compensation_terms` migration for
when that WAS required).

Autogenerate also detected pre-existing, unrelated drift on Selection tables
(`applications`, `in_person_interview_plans`, `phone_interview_plans`) —
those are intentionally NOT included here; this migration only adds the
three new tables and widens the one status constraint.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '854c3816ffd5'
down_revision: Union[str, Sequence[str], None] = 'aa3edadc9816'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('payroll_calculation_runs', schema=None) as batch_op:
        batch_op.drop_constraint('ck_payroll_calculation_runs_status', type_='check')
        batch_op.create_check_constraint(
            'ck_payroll_calculation_runs_status',
            "status IN ('OPEN', 'CALCULATED', 'APPROVED')",
        )

    op.create_table('approved_compensation_snapshots',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('compensation_preparation_run_id', sa.Integer(), nullable=False),
    sa.Column('legal_entity_id', sa.Integer(), nullable=False),
    sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
    sa.Column('approved_by', sa.String(length=255), nullable=False),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['compensation_preparation_run_id'], ['payroll_calculation_runs.id'], ),
    sa.ForeignKeyConstraint(['legal_entity_id'], ['legal_entities.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('compensation_preparation_run_id', name='uq_approved_compensation_snapshot_run')
    )
    op.create_index(op.f('ix_approved_compensation_snapshots_compensation_preparation_run_id'), 'approved_compensation_snapshots', ['compensation_preparation_run_id'], unique=False)
    op.create_table('approved_employee_compensation_results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('snapshot_id', sa.Integer(), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=False),
    sa.Column('source_employee_calculation_id', sa.Integer(), nullable=True),
    sa.Column('regular_hours', sa.Numeric(precision=12, scale=4), nullable=False),
    sa.Column('regular_pay', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('tips_amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('bonus_amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('gross_pay', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('bonus_amount >= 0', name='ck_approved_employee_compensation_result_bonus_amount'),
    sa.CheckConstraint('regular_hours >= 0', name='ck_approved_employee_compensation_result_regular_hours'),
    sa.CheckConstraint('regular_pay >= 0', name='ck_approved_employee_compensation_result_regular_pay'),
    sa.CheckConstraint('tips_amount >= 0', name='ck_approved_employee_compensation_result_tips_amount'),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
    sa.ForeignKeyConstraint(['snapshot_id'], ['approved_compensation_snapshots.id'], ),
    sa.ForeignKeyConstraint(['source_employee_calculation_id'], ['employee_payroll_calculations.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('snapshot_id', 'employee_id', name='uq_approved_employee_compensation_result')
    )
    op.create_index(op.f('ix_approved_employee_compensation_results_employee_id'), 'approved_employee_compensation_results', ['employee_id'], unique=False)
    op.create_index(op.f('ix_approved_employee_compensation_results_snapshot_id'), 'approved_employee_compensation_results', ['snapshot_id'], unique=False)
    op.create_table('approved_employee_earning_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('approved_employee_result_id', sa.Integer(), nullable=False),
    sa.Column('employee_id', sa.Integer(), nullable=False),
    sa.Column('source_earning_line_id', sa.Integer(), nullable=True),
    sa.Column('work_date', sa.Date(), nullable=True),
    sa.Column('compensation_term_id', sa.Integer(), nullable=False),
    sa.Column('hours', sa.Numeric(precision=12, scale=4), nullable=False),
    sa.Column('hourly_rate_used', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('regular_pay', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('hourly_rate_used >= 0', name='ck_approved_employee_earning_line_hourly_rate'),
    sa.CheckConstraint('hours >= 0', name='ck_approved_employee_earning_line_hours'),
    sa.CheckConstraint('regular_pay >= 0', name='ck_approved_employee_earning_line_regular_pay'),
    sa.ForeignKeyConstraint(['approved_employee_result_id'], ['approved_employee_compensation_results.id'], ),
    sa.ForeignKeyConstraint(['compensation_term_id'], ['employee_compensation_terms.id'], ),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
    sa.ForeignKeyConstraint(['source_earning_line_id'], ['employee_payroll_calculation_earning_lines.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_approved_employee_earning_lines_approved_employee_result_id'), 'approved_employee_earning_lines', ['approved_employee_result_id'], unique=False)
    op.create_index(op.f('ix_approved_employee_earning_lines_compensation_term_id'), 'approved_employee_earning_lines', ['compensation_term_id'], unique=False)
    op.create_index(op.f('ix_approved_employee_earning_lines_employee_id'), 'approved_employee_earning_lines', ['employee_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_approved_employee_earning_lines_employee_id'), table_name='approved_employee_earning_lines')
    op.drop_index(op.f('ix_approved_employee_earning_lines_compensation_term_id'), table_name='approved_employee_earning_lines')
    op.drop_index(op.f('ix_approved_employee_earning_lines_approved_employee_result_id'), table_name='approved_employee_earning_lines')
    op.drop_table('approved_employee_earning_lines')
    op.drop_index(op.f('ix_approved_employee_compensation_results_snapshot_id'), table_name='approved_employee_compensation_results')
    op.drop_index(op.f('ix_approved_employee_compensation_results_employee_id'), table_name='approved_employee_compensation_results')
    op.drop_table('approved_employee_compensation_results')
    op.drop_index(op.f('ix_approved_compensation_snapshots_compensation_preparation_run_id'), table_name='approved_compensation_snapshots')
    op.drop_table('approved_compensation_snapshots')

    with op.batch_alter_table('payroll_calculation_runs', schema=None) as batch_op:
        batch_op.drop_constraint('ck_payroll_calculation_runs_status', type_='check')
        batch_op.create_check_constraint(
            'ck_payroll_calculation_runs_status',
            "status IN ('OPEN', 'CALCULATED')",
        )
