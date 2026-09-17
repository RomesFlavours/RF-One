"""add compensation v1 manual payroll handoff (incentives, export, reconciliation)

Revision ID: f7174fa37e93
Revises: 590dcb3da39b
Create Date: 2026-09-11 15:00:00.000000

Completes the operational V1 of Compensation with manual, bidirectional
communication with the Payroll Provider (`01 Domains/Shared Domains/Personnel
Management/Compensation/COMPENSATION_AND_INCOME_COMPOSITION_001.md`,
`PAYROLL_HANDOFF_CONNECTOR.md`):

  - Widens `payroll_calculation_runs.status` from
    `('OPEN', 'CALCULATED', 'APPROVED')` to add `'EXPORTED'`/`'CLOSED'`
    (functional spec §19) — same batch-mode pattern as `854c3816ffd5`.
  - Adds `incentive_recognized_amount`/`tip_credit_makeup_amount` to
    `employee_payroll_calculations` and `approved_employee_compensation_results`
    — `incentive_recognized_amount` is MAX(0, SUM(Incentive Contributions))
    (spec §14 — no separate "Disincentive" concept), never negative.
    `tip_credit_makeup_amount` stays NULL until a value is explicitly
    supplied (Payroll-Provider-owned calculation; NULL means "to complete",
    never a false zero).
  - `incentive_contributions` — one positive or negative Incentive
    Contribution manually entered per Employee per `CompensationPreparationRun`
    (spec §14; V1 has no Event Log/Incentive Rule engine — a human enters
    each Contribution directly).
  - `approved_incentive_contribution_lines` — immutable, value-copied detail
    (mirrors `approved_employee_earning_lines`'s existing convention),
    preserving positive/negative Contribution detail at approval time (spec
    §20, "Incentive detail").
  - `compensation_export_confirmations` — one human confirmation that an
    `ApprovedCompensationSnapshot` was actually communicated to the Payroll
    Provider (`PAYROLL_HANDOFF_CONNECTOR.md`'s manual Connector).
  - `compensation_reconciliations` / `compensation_reconciliation_lines` —
    comparison between the Approved Snapshot and a manually recorded
    Payroll Provider result (`PayrollRun`), restricted to semantically
    comparable components — never Provider net pay vs. Compensation totals.

Purely additive — no existing row's data is rewritten, and no other Domain
(Training, Tips, Selection) is touched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7174fa37e93'
down_revision: Union[str, Sequence[str], None] = '590dcb3da39b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('payroll_calculation_runs', schema=None) as batch_op:
        batch_op.drop_constraint('ck_payroll_calculation_runs_status', type_='check')
        batch_op.create_check_constraint(
            'ck_payroll_calculation_runs_status',
            "status IN ('OPEN', 'CALCULATED', 'APPROVED', 'EXPORTED', 'CLOSED')",
        )

    with op.batch_alter_table('employee_payroll_calculations', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'incentive_recognized_amount', sa.Numeric(precision=12, scale=2),
            nullable=False, server_default='0',
        ))
        batch_op.add_column(sa.Column(
            'tip_credit_makeup_amount', sa.Numeric(precision=12, scale=2), nullable=True,
        ))
        batch_op.create_check_constraint(
            'ck_employee_payroll_calc_incentive_recognized_amount',
            'incentive_recognized_amount >= 0',
        )
        batch_op.create_check_constraint(
            'ck_employee_payroll_calc_tip_credit_makeup_amount',
            'tip_credit_makeup_amount IS NULL OR tip_credit_makeup_amount >= 0',
        )

    with op.batch_alter_table('approved_employee_compensation_results', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'incentive_recognized_amount', sa.Numeric(precision=12, scale=2),
            nullable=False, server_default='0',
        ))
        batch_op.add_column(sa.Column(
            'tip_credit_makeup_amount', sa.Numeric(precision=12, scale=2), nullable=True,
        ))
        # Shorter "ck_approved_emp_comp_result_..." prefix (not the fuller
        # "ck_approved_employee_compensation_result_..." used by the
        # pre-existing constraints on this table above) — PostgreSQL
        # rejects identifiers over 63 bytes (NAMEDATALEN); the fuller
        # prefix combined with either suffix here exceeds that (verified
        # against real RDS PostgreSQL).
        batch_op.create_check_constraint(
            'ck_approved_emp_comp_result_incentive_recognized_amt',
            'incentive_recognized_amount >= 0',
        )
        batch_op.create_check_constraint(
            'ck_approved_emp_comp_result_tip_credit_makeup_amt',
            'tip_credit_makeup_amount IS NULL OR tip_credit_makeup_amount >= 0',
        )

    op.create_table(
        'incentive_contributions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('calculation_run_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('source_note', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(length=255), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['calculation_run_id'], ['payroll_calculation_runs.id'], ),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_incentive_contributions_calculation_run_id'),
        'incentive_contributions', ['calculation_run_id'], unique=False,
    )
    op.create_index(
        op.f('ix_incentive_contributions_employee_id'),
        'incentive_contributions', ['employee_id'], unique=False,
    )

    op.create_table(
        'approved_incentive_contribution_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('approved_employee_result_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('source_contribution_id', sa.Integer(), nullable=True),
        sa.Column('label', sa.String(length=255), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['approved_employee_result_id'], ['approved_employee_compensation_results.id'], ),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
        sa.ForeignKeyConstraint(['source_contribution_id'], ['incentive_contributions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    # Explicit short name — the table+column-derived default
    # ("ix_approved_incentive_contribution_lines_approved_employee_result_id")
    # exceeds PostgreSQL's 63-byte identifier limit (verified against real
    # RDS PostgreSQL).
    op.create_index(
        'ix_approved_incentive_lines_result_id',
        'approved_incentive_contribution_lines', ['approved_employee_result_id'], unique=False,
    )
    op.create_index(
        op.f('ix_approved_incentive_contribution_lines_employee_id'),
        'approved_incentive_contribution_lines', ['employee_id'], unique=False,
    )

    op.create_table(
        'compensation_export_confirmations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('snapshot_id', sa.Integer(), nullable=False),
        sa.Column('communicated_by', sa.String(length=255), nullable=False),
        sa.Column('communicated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reference', sa.String(length=255), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['snapshot_id'], ['approved_compensation_snapshots.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_compensation_export_confirmations_snapshot_id'),
        'compensation_export_confirmations', ['snapshot_id'], unique=False,
    )

    op.create_table(
        'compensation_reconciliations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('snapshot_id', sa.Integer(), nullable=False),
        sa.Column('payroll_run_id', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.String(length=255), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['snapshot_id'], ['approved_compensation_snapshots.id'], ),
        sa.ForeignKeyConstraint(['payroll_run_id'], ['payroll_runs.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('snapshot_id', 'payroll_run_id', name='uq_compensation_reconciliation'),
    )
    op.create_index(
        op.f('ix_compensation_reconciliations_snapshot_id'),
        'compensation_reconciliations', ['snapshot_id'], unique=False,
    )
    op.create_index(
        op.f('ix_compensation_reconciliations_payroll_run_id'),
        'compensation_reconciliations', ['payroll_run_id'], unique=False,
    )

    op.create_table(
        'compensation_reconciliation_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reconciliation_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer(), nullable=False),
        sa.Column('component_label', sa.String(length=64), nullable=False),
        sa.Column('rfone_value', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('provider_value', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('resolution_status', sa.String(length=16), nullable=False, server_default='OPEN'),
        sa.Column('resolved_by', sa.String(length=255), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('MATCH','DIFFERENT','MISSING_IN_PROVIDER','MISSING_IN_RFONE')",
            name='ck_compensation_reconciliation_line_status',
        ),
        sa.CheckConstraint(
            "resolution_status IN ('OPEN','EXPLAINED','ACCEPTED')",
            name='ck_compensation_reconciliation_line_resolution_status',
        ),
        sa.ForeignKeyConstraint(['reconciliation_id'], ['compensation_reconciliations.id'], ),
        sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_compensation_reconciliation_lines_reconciliation_id'),
        'compensation_reconciliation_lines', ['reconciliation_id'], unique=False,
    )
    op.create_index(
        op.f('ix_compensation_reconciliation_lines_employee_id'),
        'compensation_reconciliation_lines', ['employee_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_compensation_reconciliation_lines_employee_id'),
        table_name='compensation_reconciliation_lines',
    )
    op.drop_index(
        op.f('ix_compensation_reconciliation_lines_reconciliation_id'),
        table_name='compensation_reconciliation_lines',
    )
    op.drop_table('compensation_reconciliation_lines')

    op.drop_index(
        op.f('ix_compensation_reconciliations_payroll_run_id'), table_name='compensation_reconciliations',
    )
    op.drop_index(
        op.f('ix_compensation_reconciliations_snapshot_id'), table_name='compensation_reconciliations',
    )
    op.drop_table('compensation_reconciliations')

    op.drop_index(
        op.f('ix_compensation_export_confirmations_snapshot_id'),
        table_name='compensation_export_confirmations',
    )
    op.drop_table('compensation_export_confirmations')

    op.drop_index(
        op.f('ix_approved_incentive_contribution_lines_employee_id'),
        table_name='approved_incentive_contribution_lines',
    )
    op.drop_index(
        'ix_approved_incentive_lines_result_id',
        table_name='approved_incentive_contribution_lines',
    )
    op.drop_table('approved_incentive_contribution_lines')

    op.drop_index(op.f('ix_incentive_contributions_employee_id'), table_name='incentive_contributions')
    op.drop_index(
        op.f('ix_incentive_contributions_calculation_run_id'), table_name='incentive_contributions',
    )
    op.drop_table('incentive_contributions')

    with op.batch_alter_table('approved_employee_compensation_results', schema=None) as batch_op:
        batch_op.drop_constraint(
            'ck_approved_emp_comp_result_tip_credit_makeup_amt', type_='check',
        )
        batch_op.drop_constraint(
            'ck_approved_emp_comp_result_incentive_recognized_amt', type_='check',
        )
        batch_op.drop_column('tip_credit_makeup_amount')
        batch_op.drop_column('incentive_recognized_amount')

    with op.batch_alter_table('employee_payroll_calculations', schema=None) as batch_op:
        batch_op.drop_constraint('ck_employee_payroll_calc_tip_credit_makeup_amount', type_='check')
        batch_op.drop_constraint('ck_employee_payroll_calc_incentive_recognized_amount', type_='check')
        batch_op.drop_column('tip_credit_makeup_amount')
        batch_op.drop_column('incentive_recognized_amount')

    with op.batch_alter_table('payroll_calculation_runs', schema=None) as batch_op:
        batch_op.drop_constraint('ck_payroll_calculation_runs_status', type_='check')
        batch_op.create_check_constraint(
            'ck_payroll_calculation_runs_status',
            "status IN ('OPEN', 'CALCULATED', 'APPROVED')",
        )
