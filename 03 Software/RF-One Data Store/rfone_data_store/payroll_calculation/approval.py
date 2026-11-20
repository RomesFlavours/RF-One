"""Compensation Preparation approval + Approved Compensation Snapshot
(Compensation V1 Task 1, Product Owner decision).

RF-One does not process Payroll. This module implements exactly the
boundary the Compensation functional specification describes (`01 Domains/
Shared Domains/Personnel Management/Compensation/
COMPENSATION_AND_INCOME_COMPOSITION_001.md` §19-20): a calculated
`CompensationPreparationRun` (software status `CALCULATED` — the software
state equivalent to the spec's "PREPARED", not renamed per Product Owner
decision) may be reviewed and explicitly APPROVED by an authorized actor.
Approval copies the current, already-calculated values into an immutable
`ApprovedCompensationSnapshot` — never a pointer to the mutable calculation
rows — and transitions the run to `APPROVED`. No Payroll calculation
(Regular Rate, Overtime premium, tax, withholding, deduction, employer
liability, net pay) is computed or stored here; that belongs to the Payroll
Provider, downstream of this module.

This module deliberately does NOT transition a run from `OPEN` to
`CALCULATED` — that remains the caller's responsibility (a simple
`run.status = "CALCULATED"` assignment once every `EmployeePayrollCalculation`
row for the run has been produced by `payroll_calculation.engine`), matching
this codebase's existing convention that the calculation engine itself never
manages run-level status transitions beyond initial creation.

No function in this module ever updates or deletes a row in
`ApprovedCompensationSnapshot`/`ApprovedEmployeeCompensationResult`/
`ApprovedEmployeeEarningLine` once created — this is the ONLY code that
writes those tables, and it only ever inserts. Mirrors this schema's
existing "no update path exposed" immutability convention (e.g. Purchasing's
`repository.py`).

Nothing here commits — matches this codebase's existing convention
(`payroll_calculation.engine`, `tips.distribution_engine`): the caller
decides when to commit, and a caller-driven `session.rollback()` after any
exception leaves no partial snapshot behind (every row this module adds is
flushed, never committed, within one caller-controlled transaction).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m

UTC = timezone.utc

STATUS_CALCULATED = "CALCULATED"
STATUS_APPROVED = "APPROVED"


class CompensationPreparationNotFoundError(ValueError):
    """Raised when the requested `CompensationPreparationRun` does not exist."""


class CompensationPreparationNotReadyError(ValueError):
    """Raised when a `CompensationPreparationRun` is not eligible for
    approval — not in `CALCULATED` status, or with no persisted
    `EmployeePayrollCalculation` results at all."""


class CompensationPreparationIncompleteDataError(CompensationPreparationNotReadyError):
    """Raised when the run has `EmployeePayrollCalculation` rows, but at
    least one of them is incomplete — no earning line at all (nothing was
    actually computed for that Employee), or an earning line referencing a
    Compensation Term that is not HOURLY or no longer exists. RF-One V1
    only calculates HOURLY compensation (SALARIED is explicitly
    unsupported — functional spec, Compensation V1 manual Payroll Handoff
    task) — this is the approval-time re-check that enforces that boundary
    even if a caller bypassed `payroll_calculation.engine.
    calculate_employee_payroll`'s own validation by writing
    `EmployeePayrollCalculation`/`EmployeePayrollCalculationEarningLine`
    rows directly. Never approved with a zero or fabricated value for the
    affected Employee — the whole run is refused until the data is
    completed or the Employee is removed from this run's calculations."""


def _reject_if_any_calculation_incomplete(
    session: Session, employee_calculations: list[m.EmployeePayrollCalculation],
) -> None:
    """Re-validates every included Employee's calculation at approval time
    — never trusts that `payroll_calculation.engine.calculate_employee_payroll`
    was the only path that ever wrote these rows. Raises
    `CompensationPreparationIncompleteDataError` naming every affected
    Employee and exactly what is missing, without persisting anything, if
    any is found incomplete."""

    problems: list[str] = []
    for calc in employee_calculations:
        employee = session.get(m.Employee, calc.employee_id)
        who = f"{employee.display_name} (employee_id={calc.employee_id})" if employee else (
            f"employee_id={calc.employee_id}"
        )

        if not calc.earning_lines:
            problems.append(f"{who}: no earning lines recorded — hours/rate were never calculated")
            continue

        for line in calc.earning_lines:
            term = session.get(m.EmployeeCompensationTerm, line.compensation_term_id)
            if term is None:
                problems.append(
                    f"{who}: earning line references Compensation Term "
                    f"{line.compensation_term_id}, which no longer exists"
                )
            elif term.compensation_basis != "HOURLY":
                problems.append(
                    f"{who}: earning line uses a {term.compensation_basis} Compensation Term "
                    f"(id={term.id}) — RF-One V1 only calculates HOURLY compensation; SALARIED is "
                    "not supported and must be completed outside RF-One, never approved here"
                )

    if problems:
        raise CompensationPreparationIncompleteDataError(
            "Cannot approve — the following Employees have missing or incomplete data: "
            + "; ".join(problems)
        )


def approve_compensation_preparation(
    session: Session, *, calculation_run_id: int, approved_by: str,
) -> m.ApprovedCompensationSnapshot:
    """Approves one `CompensationPreparationRun`, creating its immutable
    `ApprovedCompensationSnapshot` (Product Owner decision: one canonical
    snapshot per approved run).

    Idempotent on repeat approval: if a snapshot already exists for this
    run, it is returned unchanged — no second snapshot is ever created, and
    no existing snapshot is ever replaced (Product Owner decision, "a
    repeated approval request must either return the existing approved
    snapshot idempotently or reject the duplicate explicitly" — the
    idempotent-return option was chosen as simplest).

    Preconditions (raises before persisting anything if not met):
    - the run must exist (`CompensationPreparationNotFoundError`);
    - `approved_by` must be a non-empty actor reference
      (`CompensationPreparationNotReadyError`) — no Identity & Access
      authorization rule is evaluated here, this is only presence
      validation of the caller-supplied input;
    - the run must be in `CALCULATED` status
      (`CompensationPreparationNotReadyError`) — never `OPEN`, and never a
      run already `APPROVED` under a DIFFERENT code path than the
      idempotent-return above (which is checked first, so an already-
      `APPROVED` run with an existing snapshot never reaches this check);
    - the run must have at least one persisted `EmployeePayrollCalculation`
      row (`CompensationPreparationNotReadyError`) — nothing to approve
      otherwise;
    - every persisted `EmployeePayrollCalculation` for the run must be
      complete — at least one earning line, every earning line's
      Compensation Term must exist and be HOURLY
      (`CompensationPreparationIncompleteDataError`, naming every affected
      Employee) — re-checked here regardless of whether the caller went
      through `payroll_calculation.engine.calculate_employee_payroll`.

    Copies, per `EmployeePayrollCalculation` currently persisted for the
    run, exactly the aggregate values that model already produces today
    (`regular_hours`, `regular_pay`, `tips_amount`, `bonus_amount`,
    `incentive_recognized_amount`, `tip_credit_makeup_amount`, `gross_pay`)
    and, per `EmployeePayrollCalculationEarningLine`, exactly the currently
    persisted per-line facts (`work_date`, `compensation_term_id`, hours,
    `hourly_rate_used`, `regular_pay`). Also copies, per persisted
    `IncentiveContribution`, an immutable `ApprovedIncentiveContributionLine`
    (Compensation V1 manual Payroll Handoff task) — preserving positive and
    negative Contribution detail, not only the Recognized Incentive total
    (functional spec §20). Authorized Adjustments remain out of scope
    (conceptual/documented only) — no field for that component is
    fabricated.

    Does not commit. Every row is only ever `session.add`ed/flushed; a
    caller-driven `session.rollback()` after any exception (including one
    raised mid-loop by a later, unrelated constraint violation) leaves
    nothing partially persisted."""

    run = session.get(m.CompensationPreparationRun, calculation_run_id)
    if run is None:
        raise CompensationPreparationNotFoundError(
            f"CompensationPreparationRun {calculation_run_id} does not exist"
        )

    existing = get_approved_snapshot_by_run(session, calculation_run_id)
    if existing is not None:
        return existing

    if not approved_by or not approved_by.strip():
        raise CompensationPreparationNotReadyError(
            "approve_compensation_preparation requires a non-empty approved_by actor reference"
        )

    if run.status != STATUS_CALCULATED:
        raise CompensationPreparationNotReadyError(
            f"CompensationPreparationRun {calculation_run_id} is not eligible for approval "
            f"(status={run.status!r}, expected {STATUS_CALCULATED!r})"
        )

    employee_calculations = session.scalars(
        select(m.EmployeePayrollCalculation).where(
            m.EmployeePayrollCalculation.calculation_run_id == calculation_run_id
        )
    ).all()
    if not employee_calculations:
        raise CompensationPreparationNotReadyError(
            f"CompensationPreparationRun {calculation_run_id} has no persisted "
            "EmployeePayrollCalculation results to approve"
        )

    _reject_if_any_calculation_incomplete(session, employee_calculations)

    approved_at = datetime.now(UTC)

    snapshot = m.ApprovedCompensationSnapshot(
        compensation_preparation_run_id=run.id,
        legal_entity_id=run.legal_entity_id,
        period_start=run.period_start,
        period_end=run.period_end,
        approved_by=approved_by,
        approved_at=approved_at,
    )
    session.add(snapshot)
    session.flush()

    for calc in employee_calculations:
        approved_result = m.ApprovedEmployeeCompensationResult(
            snapshot_id=snapshot.id,
            employee_id=calc.employee_id,
            source_employee_calculation_id=calc.id,
            regular_hours=calc.regular_hours,
            regular_pay=calc.regular_pay,
            tips_amount=calc.tips_amount,
            bonus_amount=calc.bonus_amount,
            incentive_recognized_amount=calc.incentive_recognized_amount,
            tip_credit_makeup_amount=calc.tip_credit_makeup_amount,
            gross_pay=calc.gross_pay,
        )
        session.add(approved_result)
        session.flush()

        for line in calc.earning_lines:
            session.add(
                m.ApprovedEmployeeEarningLine(
                    approved_employee_result_id=approved_result.id,
                    employee_id=calc.employee_id,
                    source_earning_line_id=line.id,
                    work_date=line.work_date,
                    compensation_term_id=line.compensation_term_id,
                    hours=line.regular_hours,
                    hourly_rate_used=line.hourly_rate_used,
                    regular_pay=line.regular_pay,
                )
            )

        contributions = session.scalars(
            select(m.IncentiveContribution).where(
                m.IncentiveContribution.calculation_run_id == calculation_run_id,
                m.IncentiveContribution.employee_id == calc.employee_id,
            )
        ).all()
        for contribution in contributions:
            session.add(
                m.ApprovedIncentiveContributionLine(
                    approved_employee_result_id=approved_result.id,
                    employee_id=calc.employee_id,
                    source_contribution_id=contribution.id,
                    label=contribution.label,
                    amount=contribution.amount,
                )
            )

    run.status = STATUS_APPROVED
    session.flush()

    return snapshot


def get_approved_snapshot(session: Session, snapshot_id: int) -> m.ApprovedCompensationSnapshot | None:
    return session.get(m.ApprovedCompensationSnapshot, snapshot_id)


def get_approved_snapshot_by_run(
    session: Session, calculation_run_id: int,
) -> m.ApprovedCompensationSnapshot | None:
    return session.scalars(
        select(m.ApprovedCompensationSnapshot).where(
            m.ApprovedCompensationSnapshot.compensation_preparation_run_id == calculation_run_id
        )
    ).first()
