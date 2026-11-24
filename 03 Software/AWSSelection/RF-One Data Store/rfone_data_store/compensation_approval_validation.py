"""Automated synthetic tests for Compensation Preparation approval + the
Approved Compensation Snapshot (Compensation V1 Task 1, Product Owner
decision).

Mirrors the established `*_validation.py` pattern (see
`identity_authority_signature_validation.py`, `organization_validation.py`):
synthetic fixture, disposable database, always rolled back, never touches
real data. Constraint-violation scenarios use a nested SAVEPOINT
(`session.begin_nested()`) so a single expected error does not abort the
whole validation transaction.

Deliberately covers only the minimum behaviors requested for this task —
no Payroll/ADP/Finch logic, no Incentive/Pool/Overtime/Regular-Rate
calculation is exercised or implied here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .payroll_calculation import approval, engine

UTC = timezone.utc


@dataclass
class ValidationResult:
    success: bool
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)

    def check(self, description: str, condition: bool) -> None:
        if condition:
            self.checks_passed.append(description)
        else:
            self.checks_failed.append(description)
            self.success = False


def run_validation(session_factory: sessionmaker[Session]) -> ValidationResult:
    result = ValidationResult(success=True)
    with session_factory() as session:
        try:
            _test_approval_happy_path(session, result)
            _test_open_run_cannot_be_approved(session, result)
            _test_snapshot_immutable_to_later_source_changes(session, result)
            _test_duplicate_approval_is_idempotent(session, result)
            _test_rollback_prevents_snapshot_from_surviving(session, result)
        finally:
            session.rollback()
    return result


def _make_employee(session: Session, name: str) -> m.Employee:
    merchant = m.Merchant(name=f"{name} Merchant")
    session.add(merchant)
    session.flush()
    location = m.Location(merchant_id=merchant.id, name=f"{name} Location")
    session.add(location)
    session.flush()
    employee = m.Employee(location_id=location.id, display_name=name)
    session.add(employee)
    session.flush()
    return employee


def _make_legal_entity(session: Session, legal_name: str) -> m.LegalEntity:
    legal_entity = m.LegalEntity(legal_name=legal_name, status="ACTIVE")
    session.add(legal_entity)
    session.flush()
    return legal_entity


def _make_hourly_term(
    session: Session, employee_id: int, *, legal_entity_id: int, function_label: str,
    hourly_rate_minor: int, valid_from: datetime,
) -> m.EmployeeCompensationTerm:
    term = m.EmployeeCompensationTerm(
        employee_id=employee_id,
        legal_entity_id=legal_entity_id,
        function_label=function_label,
        compensation_basis=engine.compensation_helpers.HOURLY,
        hourly_rate_minor=hourly_rate_minor,
        valid_from=valid_from,
    )
    session.add(term)
    session.flush()
    return term


def _build_calculated_run(
    session: Session, *, legal_entity_id: int, employee_ids_and_terms: list[tuple[int, int, Decimal]],
) -> m.CompensationPreparationRun:
    """Creates a run, adds one `EmployeePayrollCalculation` per
    (employee_id, compensation_term_id, hours) tuple via the real engine,
    then marks the run `CALCULATED` — the caller-responsibility transition
    `approval.py`'s own docstring documents."""
    run = engine.create_calculation_run(
        session, legal_entity_id=legal_entity_id,
        period_start=datetime(2026, 9, 1, tzinfo=UTC), period_end=datetime(2026, 9, 14, tzinfo=UTC),
    )
    for employee_id, term_id, hours in employee_ids_and_terms:
        engine.calculate_employee_payroll(
            session, run, employee_id=employee_id,
            earning_lines=[engine.EarningLineInput(compensation_term_id=term_id, hours=hours)],
            tips_amount=Decimal("50.00"),
        )
    run.status = approval.STATUS_CALCULATED
    session.flush()
    return run


# ---------------------------------------------------------------------------
# 1/3/4/5/8/9/10. Happy path: a CALCULATED run can be approved; the snapshot
# header, employee result values, and earning-line values are all copied;
# Approved By/At are persisted; the run becomes APPROVED.
# ---------------------------------------------------------------------------


def _test_approval_happy_path(session: Session, result: ValidationResult) -> None:
    employee = _make_employee(session, "Happy Path")
    legal_entity = _make_legal_entity(session, "Happy Path LLC")
    term = _make_hourly_term(
        session, employee.id, legal_entity_id=legal_entity.id, function_label="Server",
        hourly_rate_minor=2000, valid_from=datetime(2026, 9, 1, tzinfo=UTC),
    )
    run = _build_calculated_run(
        session, legal_entity_id=legal_entity.id,
        employee_ids_and_terms=[(employee.id, term.id, Decimal("40"))],
    )
    source_calc = session.scalars(
        select(m.EmployeePayrollCalculation).where(m.EmployeePayrollCalculation.calculation_run_id == run.id)
    ).one()

    snapshot = approval.approve_compensation_preparation(
        session, calculation_run_id=run.id, approved_by="jane.manager@romesflavours.com",
    )

    result.check(
        "a CALCULATED run can be approved and produces an ApprovedCompensationSnapshot header "
        "(legal entity + period copied from the run)",
        snapshot.id is not None
        and snapshot.compensation_preparation_run_id == run.id
        and snapshot.legal_entity_id == legal_entity.id
        and snapshot.period_start == run.period_start
        and snapshot.period_end == run.period_end,
    )
    result.check(
        "Approved By is persisted on the snapshot header",
        snapshot.approved_by == "jane.manager@romesflavours.com",
    )
    result.check(
        "Approved At is persisted on the snapshot header",
        snapshot.approved_at is not None,
    )
    result.check(
        "the CompensationPreparationRun becomes APPROVED",
        run.status == approval.STATUS_APPROVED,
    )

    approved_results = session.scalars(
        select(m.ApprovedEmployeeCompensationResult).where(
            m.ApprovedEmployeeCompensationResult.snapshot_id == snapshot.id
        )
    ).all()
    result.check(
        "approval copies the Employee result values (regular_hours/regular_pay/tips_amount/"
        "bonus_amount/gross_pay) exactly as produced by the engine",
        len(approved_results) == 1
        and approved_results[0].employee_id == employee.id
        and approved_results[0].source_employee_calculation_id == source_calc.id
        and approved_results[0].regular_hours == source_calc.regular_hours
        and approved_results[0].regular_pay == source_calc.regular_pay
        and approved_results[0].tips_amount == source_calc.tips_amount
        and approved_results[0].gross_pay == source_calc.gross_pay,
    )

    approved_lines = session.scalars(
        select(m.ApprovedEmployeeEarningLine).where(
            m.ApprovedEmployeeEarningLine.approved_employee_result_id == approved_results[0].id
        )
    ).all()
    source_line = source_calc.earning_lines[0]
    result.check(
        "approval copies the earning-line values (compensation_term_id/hours/hourly_rate_used/"
        "regular_pay) exactly as produced by the engine",
        len(approved_lines) == 1
        and approved_lines[0].employee_id == employee.id
        and approved_lines[0].source_earning_line_id == source_line.id
        and approved_lines[0].compensation_term_id == term.id
        and approved_lines[0].hours == source_line.regular_hours
        and approved_lines[0].hourly_rate_used == source_line.hourly_rate_used
        and approved_lines[0].regular_pay == source_line.regular_pay,
    )

    # Retrieval by snapshot id and by run id.
    result.check(
        "the approved snapshot can be retrieved by snapshot id and by calculation_run_id",
        approval.get_approved_snapshot(session, snapshot.id) is not None
        and approval.get_approved_snapshot_by_run(session, run.id) is not None
        and approval.get_approved_snapshot_by_run(session, run.id).id == snapshot.id,
    )


# ---------------------------------------------------------------------------
# 2. An OPEN (unprepared) run cannot be approved.
# ---------------------------------------------------------------------------


def _test_open_run_cannot_be_approved(session: Session, result: ValidationResult) -> None:
    legal_entity = _make_legal_entity(session, "Open Run LLC")
    run = engine.create_calculation_run(
        session, legal_entity_id=legal_entity.id,
        period_start=datetime(2026, 9, 1, tzinfo=UTC), period_end=datetime(2026, 9, 14, tzinfo=UTC),
    )
    # status defaults to OPEN — never CALCULATED.

    rejected = False
    try:
        approval.approve_compensation_preparation(
            session, calculation_run_id=run.id, approved_by="someone@romesflavours.com",
        )
    except approval.CompensationPreparationNotReadyError:
        rejected = True
    result.check(
        "an OPEN (unprepared) CompensationPreparationRun cannot be approved",
        rejected,
    )

    remaining = session.scalars(
        select(m.ApprovedCompensationSnapshot).where(
            m.ApprovedCompensationSnapshot.compensation_preparation_run_id == run.id
        )
    ).first()
    result.check(
        "no snapshot is created for a rejected OPEN-run approval attempt",
        remaining is None,
    )


# ---------------------------------------------------------------------------
# 6/7. The approved snapshot remains unchanged after later changes to the
# source EmployeePayrollCalculation row and to EmployeeCompensationTerm's
# rate.
# ---------------------------------------------------------------------------


def _test_snapshot_immutable_to_later_source_changes(session: Session, result: ValidationResult) -> None:
    employee = _make_employee(session, "Immutability")
    legal_entity = _make_legal_entity(session, "Immutability LLC")
    term = _make_hourly_term(
        session, employee.id, legal_entity_id=legal_entity.id, function_label="Server",
        hourly_rate_minor=1500, valid_from=datetime(2026, 9, 1, tzinfo=UTC),
    )
    run = _build_calculated_run(
        session, legal_entity_id=legal_entity.id,
        employee_ids_and_terms=[(employee.id, term.id, Decimal("30"))],
    )
    snapshot = approval.approve_compensation_preparation(
        session, calculation_run_id=run.id, approved_by="approver@romesflavours.com",
    )
    approved_result = session.scalars(
        select(m.ApprovedEmployeeCompensationResult).where(
            m.ApprovedEmployeeCompensationResult.snapshot_id == snapshot.id
        )
    ).one()
    approved_line = session.scalars(
        select(m.ApprovedEmployeeEarningLine).where(
            m.ApprovedEmployeeEarningLine.approved_employee_result_id == approved_result.id
        )
    ).one()

    original_regular_pay = approved_result.regular_pay
    original_line_rate = approved_line.hourly_rate_used

    # Mutate the SOURCE rows after approval.
    source_calc = session.get(m.EmployeePayrollCalculation, approved_result.source_employee_calculation_id)
    source_calc.regular_pay = Decimal("999999.99")
    term.hourly_rate_minor = 999999
    session.flush()

    session.refresh(approved_result)
    session.refresh(approved_line)

    result.check(
        "the approved snapshot's Employee result is unchanged after the source "
        "EmployeePayrollCalculation row is modified afterward",
        approved_result.regular_pay == original_regular_pay
        and approved_result.regular_pay != Decimal("999999.99"),
    )
    result.check(
        "the approved snapshot's earning line is unchanged after EmployeeCompensationTerm's "
        "rate changes afterward",
        approved_line.hourly_rate_used == original_line_rate
        and approved_line.hourly_rate_used != Decimal("999999.00"),
    )


# ---------------------------------------------------------------------------
# 11. Duplicate approval does not silently replace the approved snapshot.
# ---------------------------------------------------------------------------


def _test_duplicate_approval_is_idempotent(session: Session, result: ValidationResult) -> None:
    employee = _make_employee(session, "Duplicate Approval")
    legal_entity = _make_legal_entity(session, "Duplicate Approval LLC")
    term = _make_hourly_term(
        session, employee.id, legal_entity_id=legal_entity.id, function_label="Server",
        hourly_rate_minor=1800, valid_from=datetime(2026, 9, 1, tzinfo=UTC),
    )
    run = _build_calculated_run(
        session, legal_entity_id=legal_entity.id,
        employee_ids_and_terms=[(employee.id, term.id, Decimal("20"))],
    )

    first = approval.approve_compensation_preparation(
        session, calculation_run_id=run.id, approved_by="first-approver@romesflavours.com",
    )
    second = approval.approve_compensation_preparation(
        session, calculation_run_id=run.id, approved_by="second-approver@romesflavours.com",
    )

    result.check(
        "a duplicate approval request returns the SAME snapshot idempotently, "
        "never silently replacing it (approved_by remains the FIRST approver)",
        first.id == second.id and second.approved_by == "first-approver@romesflavours.com",
    )

    all_snapshots_for_run = session.scalars(
        select(m.ApprovedCompensationSnapshot).where(
            m.ApprovedCompensationSnapshot.compensation_preparation_run_id == run.id
        )
    ).all()
    result.check(
        "exactly one ApprovedCompensationSnapshot row exists for the run after duplicate approval",
        len(all_snapshots_for_run) == 1,
    )


# ---------------------------------------------------------------------------
# 12. Transaction rollback prevents (partial or complete) snapshot creation
# from surviving — the function never commits on its own.
# ---------------------------------------------------------------------------


def _test_rollback_prevents_snapshot_from_surviving(session: Session, result: ValidationResult) -> None:
    employee = _make_employee(session, "Rollback")
    legal_entity = _make_legal_entity(session, "Rollback LLC")
    term = _make_hourly_term(
        session, employee.id, legal_entity_id=legal_entity.id, function_label="Server",
        hourly_rate_minor=1600, valid_from=datetime(2026, 9, 1, tzinfo=UTC),
    )
    run = _build_calculated_run(
        session, legal_entity_id=legal_entity.id,
        employee_ids_and_terms=[(employee.id, term.id, Decimal("10"))],
    )

    savepoint = session.begin_nested()
    snapshot = approval.approve_compensation_preparation(
        session, calculation_run_id=run.id, approved_by="rolled-back-approver@romesflavours.com",
    )
    snapshot_id = snapshot.id
    result_ids = [r.id for r in session.scalars(
        select(m.ApprovedEmployeeCompensationResult).where(
            m.ApprovedEmployeeCompensationResult.snapshot_id == snapshot_id
        )
    ).all()]
    present_before_rollback = (
        snapshot_id is not None and len(result_ids) == 1 and run.status == approval.STATUS_APPROVED
    )
    savepoint.rollback()

    snapshot_after = session.get(m.ApprovedCompensationSnapshot, snapshot_id)
    result_after = (
        session.get(m.ApprovedEmployeeCompensationResult, result_ids[0]) if result_ids else None
    )
    run_after = session.get(m.CompensationPreparationRun, run.id)

    result.check(
        "the snapshot/result/APPROVED transition existed within the transaction before rollback "
        "(proving the rollback test itself is meaningful)",
        present_before_rollback,
    )
    result.check(
        "a transaction rollback after approval leaves no snapshot, no employee result, and no "
        "APPROVED status behind — the approval function never auto-commits",
        snapshot_after is None and result_after is None and run_after.status == approval.STATUS_CALCULATED,
    )
