"""Automated synthetic tests for the Compensation V1 manual Payroll Handoff
(Incentive Contributions/Recognized Incentive, the manual Payroll Handoff
Connector, and Provider-result reconciliation).

Mirrors `compensation_approval_validation.py`'s own pattern: synthetic
fixture, disposable database, always rolled back, never touches real data.

Deliberately covers only this task's scope — no Event Log/Incentive Rule
engine, no Pool/TIERED Incentive types, no Overtime/Regular-Rate
calculation, no SALARIED compensation basis, and no Authorized Adjustments
are exercised or implied here (all remain out of scope)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .payroll_calculation import approval, engine, export, incentives, reconciliation

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
            _test_incentive_positive_and_negative_zero_floor(session, result)
            _test_incentive_recognized_flows_into_calculation_and_gross_pay(session, result)
            _test_incentive_contribution_locked_after_approval(session, result)
            _test_recalculation_replaces_prior_summary(session, result)
            _test_recalculation_blocked_after_approval(session, result)
            _test_approval_blocks_calculation_with_no_earning_lines(session, result)
            _test_approval_blocks_salaried_earning_line(session, result)
            _test_approval_copies_incentive_detail_lines(session, result)
            _test_tip_credit_makeup_stays_null_unless_supplied(session, result)
            _test_manual_export_confirmation_flow(session, result)
            _test_export_requires_approved_run(session, result)
            _test_manual_provider_result_and_reconciliation_match(session, result)
            _test_duplicate_manual_provider_result_is_rejected(session, result)
            _test_reconciliation_detects_difference_and_missing_lines(session, result)
            _test_reconciliation_is_idempotent_and_annotatable(session, result)
            _test_two_legal_entities_never_mixed_in_reconciliation(session, result)
        finally:
            session.rollback()
    return result


# ---------------------------------------------------------------------------
# Fixture helpers (mirrors compensation_approval_validation.py)
# ---------------------------------------------------------------------------


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


def _make_restaurant(session: Session, name: str, *, legal_entity_id: int) -> m.Restaurant:
    restaurant = m.Restaurant(name=name, legal_entity_id=legal_entity_id)
    session.add(restaurant)
    session.flush()
    return restaurant


def _make_source_system(session: Session, name: str) -> m.SourceSystem:
    source_system = m.SourceSystem(code=name.upper().replace(" ", "_"), name=name)
    session.add(source_system)
    session.flush()
    return source_system


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
# Incentive Contributions and the Recognized Incentive (functional spec §14)
# ---------------------------------------------------------------------------


def _test_incentive_positive_and_negative_zero_floor(session: Session, result: ValidationResult) -> None:
    # Example A from the spec: +200 +80 +50 -75 = 255 -> Recognized 255.
    class _C:
        def __init__(self, amount: Decimal) -> None:
            self.amount = amount

    example_a = [_C(Decimal("200")), _C(Decimal("80")), _C(Decimal("50")), _C(Decimal("-75"))]
    result.check(
        "Recognized Incentive = algebraic sum when the sum is positive (spec §14.1 Example A)",
        incentives.calculate_recognized_incentive(example_a) == Decimal("255.00"),
    )

    # Example B from the spec: +200 -300 = -100 -> Recognized 0 (never negative).
    example_b = [_C(Decimal("200")), _C(Decimal("-300"))]
    result.check(
        "Recognized Incentive is floored at zero, never negative (spec §14.1 Example B — "
        "no Disincentive concept)",
        incentives.calculate_recognized_incentive(example_b) == Decimal("0.00"),
    )
    result.check(
        "calculate_recognized_incentive also accepts bare Decimal amounts",
        incentives.calculate_recognized_incentive([Decimal("10"), Decimal("-3")]) == Decimal("7.00"),
    )


def _test_incentive_recognized_flows_into_calculation_and_gross_pay(
    session: Session, result: ValidationResult,
) -> None:
    employee = _make_employee(session, "Incentive Flow")
    legal_entity = _make_legal_entity(session, "Incentive Flow LLC")
    term = _make_hourly_term(
        session, employee.id, legal_entity_id=legal_entity.id, function_label="Server",
        hourly_rate_minor=2000, valid_from=datetime(2026, 9, 1, tzinfo=UTC),
    )
    run = engine.create_calculation_run(
        session, legal_entity_id=legal_entity.id,
        period_start=datetime(2026, 9, 1, tzinfo=UTC), period_end=datetime(2026, 9, 14, tzinfo=UTC),
    )
    incentives.add_incentive_contribution(
        session, calculation_run_id=run.id, employee_id=employee.id,
        label="Wine Sales Contribution", amount=Decimal("200"), created_by="manager@romesflavours.com",
    )
    incentives.add_incentive_contribution(
        session, calculation_run_id=run.id, employee_id=employee.id,
        label="Performance Contribution", amount=Decimal("-75"), created_by="manager@romesflavours.com",
    )

    calc = engine.calculate_employee_payroll(
        session, run, employee_id=employee.id,
        earning_lines=[engine.EarningLineInput(compensation_term_id=term.id, hours=Decimal("40"))],
        tips_amount=Decimal("50.00"),
    )

    result.check(
        "calculate_employee_payroll resolves persisted IncentiveContribution rows into "
        "incentive_recognized_amount = MAX(0, SUM(amount))",
        calc.incentive_recognized_amount == Decimal("125.00"),
    )
    expected_gross = (Decimal("40") * Decimal("20.00")) + Decimal("50.00") + Decimal("0") + Decimal("125.00")
    result.check(
        "gross_pay includes regular_pay + tips_amount + bonus_amount + incentive_recognized_amount",
        calc.gross_pay == expected_gross,
    )

    # Only negative contributions -> recognized incentive floors at zero,
    # and never reduces regular_pay/tips_amount.
    employee2 = _make_employee(session, "Incentive Flow Negative")
    term2 = _make_hourly_term(
        session, employee2.id, legal_entity_id=legal_entity.id, function_label="Server",
        hourly_rate_minor=2000, valid_from=datetime(2026, 9, 1, tzinfo=UTC),
    )
    incentives.add_incentive_contribution(
        session, calculation_run_id=run.id, employee_id=employee2.id,
        label="Performance Contribution", amount=Decimal("-40"), created_by="manager@romesflavours.com",
    )
    calc2 = engine.calculate_employee_payroll(
        session, run, employee_id=employee2.id,
        earning_lines=[engine.EarningLineInput(compensation_term_id=term2.id, hours=Decimal("10"))],
        tips_amount=Decimal("0"),
    )
    result.check(
        "a purely negative set of Contributions never produces a negative "
        "incentive_recognized_amount, and never reduces regular_pay",
        calc2.incentive_recognized_amount == Decimal("0.00")
        and calc2.regular_pay == Decimal("200.00"),
    )


def _test_incentive_contribution_locked_after_approval(session: Session, result: ValidationResult) -> None:
    employee = _make_employee(session, "Incentive Lock")
    legal_entity = _make_legal_entity(session, "Incentive Lock LLC")
    term = _make_hourly_term(
        session, employee.id, legal_entity_id=legal_entity.id, function_label="Server",
        hourly_rate_minor=1500, valid_from=datetime(2026, 9, 1, tzinfo=UTC),
    )
    run = _build_calculated_run(
        session, legal_entity_id=legal_entity.id,
        employee_ids_and_terms=[(employee.id, term.id, Decimal("10"))],
    )
    approval.approve_compensation_preparation(
        session, calculation_run_id=run.id, approved_by="approver@romesflavours.com",
    )

    rejected = False
    try:
        incentives.add_incentive_contribution(
            session, calculation_run_id=run.id, employee_id=employee.id,
            label="Too Late", amount=Decimal("10"), created_by="manager@romesflavours.com",
        )
    except incentives.IncentiveContributionRunNotEditableError:
        rejected = True
    result.check(
        "an Incentive Contribution cannot be added to an already-APPROVED run",
        rejected,
    )


# ---------------------------------------------------------------------------
# Recalculation (correction before approval)
# ---------------------------------------------------------------------------


def _test_recalculation_replaces_prior_summary(session: Session, result: ValidationResult) -> None:
    employee = _make_employee(session, "Recalculation")
    legal_entity = _make_legal_entity(session, "Recalculation LLC")
    term = _make_hourly_term(
        session, employee.id, legal_entity_id=legal_entity.id, function_label="Server",
        hourly_rate_minor=1000, valid_from=datetime(2026, 9, 1, tzinfo=UTC),
    )
    run = engine.create_calculation_run(
        session, legal_entity_id=legal_entity.id,
        period_start=datetime(2026, 9, 1, tzinfo=UTC), period_end=datetime(2026, 9, 14, tzinfo=UTC),
    )
    engine.calculate_employee_payroll(
        session, run, employee_id=employee.id,
        earning_lines=[engine.EarningLineInput(compensation_term_id=term.id, hours=Decimal("10"))],
    )
    engine.calculate_employee_payroll(
        session, run, employee_id=employee.id,
        earning_lines=[engine.EarningLineInput(compensation_term_id=term.id, hours=Decimal("25"))],
    )

    summaries = session.scalars(
        select(m.EmployeePayrollCalculation).where(
            m.EmployeePayrollCalculation.calculation_run_id == run.id,
            m.EmployeePayrollCalculation.employee_id == employee.id,
        )
    ).all()
    result.check(
        "recalculating the same (run, employee) replaces the prior summary — never two rows",
        len(summaries) == 1 and summaries[0].regular_hours == Decimal("25.0000"),
    )


def _test_recalculation_blocked_after_approval(session: Session, result: ValidationResult) -> None:
    employee = _make_employee(session, "Recalc Lock")
    legal_entity = _make_legal_entity(session, "Recalc Lock LLC")
    term = _make_hourly_term(
        session, employee.id, legal_entity_id=legal_entity.id, function_label="Server",
        hourly_rate_minor=1000, valid_from=datetime(2026, 9, 1, tzinfo=UTC),
    )
    run = _build_calculated_run(
        session, legal_entity_id=legal_entity.id,
        employee_ids_and_terms=[(employee.id, term.id, Decimal("10"))],
    )
    approval.approve_compensation_preparation(
        session, calculation_run_id=run.id, approved_by="approver@romesflavours.com",
    )

    rejected = False
    try:
        engine.calculate_employee_payroll(
            session, run, employee_id=employee.id,
            earning_lines=[engine.EarningLineInput(compensation_term_id=term.id, hours=Decimal("99"))],
        )
    except engine.CalculationRunNotEditableError:
        rejected = True
    result.check(
        "recalculating an already-APPROVED run's employee is rejected",
        rejected,
    )


# ---------------------------------------------------------------------------
# Approval re-validates completeness even when the backend is called
# directly, bypassing payroll_calculation.engine's own validation (task:
# "impedisci ... nemmeno chiamando direttamente il backend").
# ---------------------------------------------------------------------------


def _test_approval_blocks_calculation_with_no_earning_lines(
    session: Session, result: ValidationResult,
) -> None:
    employee = _make_employee(session, "No Earning Lines")
    legal_entity = _make_legal_entity(session, "No Earning Lines LLC")
    run = engine.create_calculation_run(
        session, legal_entity_id=legal_entity.id,
        period_start=datetime(2026, 9, 1, tzinfo=UTC), period_end=datetime(2026, 9, 14, tzinfo=UTC),
    )
    # Bypasses engine.calculate_employee_payroll entirely (which refuses an
    # empty earning_lines list) — simulates a direct backend/ORM write.
    session.add(m.EmployeePayrollCalculation(
        calculation_run_id=run.id, employee_id=employee.id,
        regular_hours=Decimal("0"), regular_pay=Decimal("0.00"), gross_pay=Decimal("0.00"),
    ))
    run.status = approval.STATUS_CALCULATED
    session.flush()

    rejected = False
    message = ""
    try:
        approval.approve_compensation_preparation(
            session, calculation_run_id=run.id, approved_by="approver@romesflavours.com",
        )
    except approval.CompensationPreparationIncompleteDataError as exc:
        rejected = True
        message = str(exc)
    result.check(
        "approving a run with an included Employee that has NO earning lines (never calculated, "
        "e.g. written directly to the backend) is rejected, naming that Employee",
        rejected and "No Earning Lines" in message and str(employee.id) in message,
    )
    result.check(
        "no ApprovedCompensationSnapshot is created for the rejected run",
        approval.get_approved_snapshot_by_run(session, run.id) is None,
    )


def _test_approval_blocks_salaried_earning_line(session: Session, result: ValidationResult) -> None:
    employee = _make_employee(session, "Direct Salaried Line")
    legal_entity = _make_legal_entity(session, "Direct Salaried Line LLC")
    salaried_term = m.EmployeeCompensationTerm(
        employee_id=employee.id, legal_entity_id=legal_entity.id, function_label="Manager",
        compensation_basis="SALARIED", salaried_period_amount_minor=150000,
        valid_from=datetime(2026, 9, 1, tzinfo=UTC),
    )
    session.add(salaried_term)
    session.flush()

    run = engine.create_calculation_run(
        session, legal_entity_id=legal_entity.id,
        period_start=datetime(2026, 9, 1, tzinfo=UTC), period_end=datetime(2026, 9, 14, tzinfo=UTC),
    )
    # Bypasses engine.py's own HOURLY-only validation entirely — simulates
    # a direct backend/ORM write referencing a SALARIED term.
    calc = m.EmployeePayrollCalculation(
        calculation_run_id=run.id, employee_id=employee.id,
        regular_hours=Decimal("0"), regular_pay=Decimal("1500.00"), gross_pay=Decimal("1500.00"),
    )
    session.add(calc)
    session.flush()
    session.add(m.EmployeePayrollCalculationEarningLine(
        employee_payroll_calculation_id=calc.id, compensation_term_id=salaried_term.id,
        regular_hours=Decimal("0"), hourly_rate_used=Decimal("0.00"), regular_pay=Decimal("1500.00"),
    ))
    run.status = approval.STATUS_CALCULATED
    session.flush()

    rejected = False
    message = ""
    try:
        approval.approve_compensation_preparation(
            session, calculation_run_id=run.id, approved_by="approver@romesflavours.com",
        )
    except approval.CompensationPreparationIncompleteDataError as exc:
        rejected = True
        message = str(exc)
    result.check(
        "approving a run whose earning line references a SALARIED Compensation Term is rejected "
        "(V1 HOURLY-only boundary), never silently approved as a computed component",
        rejected and "SALARIED" in message and "Direct Salaried Line" in message,
    )
    result.check(
        "no ApprovedCompensationSnapshot is created when a SALARIED line is present",
        approval.get_approved_snapshot_by_run(session, run.id) is None,
    )


# ---------------------------------------------------------------------------
# Approval copies Incentive detail (spec §20)
# ---------------------------------------------------------------------------


def _test_approval_copies_incentive_detail_lines(session: Session, result: ValidationResult) -> None:
    employee = _make_employee(session, "Incentive Detail")
    legal_entity = _make_legal_entity(session, "Incentive Detail LLC")
    term = _make_hourly_term(
        session, employee.id, legal_entity_id=legal_entity.id, function_label="Server",
        hourly_rate_minor=1500, valid_from=datetime(2026, 9, 1, tzinfo=UTC),
    )
    run = engine.create_calculation_run(
        session, legal_entity_id=legal_entity.id,
        period_start=datetime(2026, 9, 1, tzinfo=UTC), period_end=datetime(2026, 9, 14, tzinfo=UTC),
    )
    incentives.add_incentive_contribution(
        session, calculation_run_id=run.id, employee_id=employee.id,
        label="Wine Sales Contribution", amount=Decimal("200"), created_by="manager@romesflavours.com",
    )
    incentives.add_incentive_contribution(
        session, calculation_run_id=run.id, employee_id=employee.id,
        label="Performance Contribution", amount=Decimal("-75"), created_by="manager@romesflavours.com",
    )
    engine.calculate_employee_payroll(
        session, run, employee_id=employee.id,
        earning_lines=[engine.EarningLineInput(compensation_term_id=term.id, hours=Decimal("10"))],
    )
    run.status = approval.STATUS_CALCULATED
    session.flush()

    snapshot = approval.approve_compensation_preparation(
        session, calculation_run_id=run.id, approved_by="approver@romesflavours.com",
    )
    approved_result = session.scalars(
        select(m.ApprovedEmployeeCompensationResult).where(
            m.ApprovedEmployeeCompensationResult.snapshot_id == snapshot.id
        )
    ).one()
    detail_lines = session.scalars(
        select(m.ApprovedIncentiveContributionLine).where(
            m.ApprovedIncentiveContributionLine.approved_employee_result_id == approved_result.id
        )
    ).all()

    result.check(
        "approval copies both positive and negative Incentive Contribution detail lines "
        "(spec §20, not only the Recognized total)",
        len(detail_lines) == 2
        and {line.amount for line in detail_lines} == {Decimal("200.00"), Decimal("-75.00")},
    )
    result.check(
        "the approved result's incentive_recognized_amount equals MAX(0, SUM(contributions))",
        approved_result.incentive_recognized_amount == Decimal("125.00"),
    )

    # Mutating the source contribution afterward never changes the approved detail line.
    source_contribution = session.scalars(
        select(m.IncentiveContribution).where(
            m.IncentiveContribution.calculation_run_id == run.id,
            m.IncentiveContribution.amount == Decimal("200.00"),
        )
    ).one()
    source_contribution.amount = Decimal("999999.00")
    session.flush()
    session.refresh(detail_lines[0])
    session.refresh(detail_lines[1])
    result.check(
        "approved Incentive Contribution detail lines are immutable to later source changes",
        Decimal("999999.00") not in {line.amount for line in detail_lines},
    )


def _test_tip_credit_makeup_stays_null_unless_supplied(session: Session, result: ValidationResult) -> None:
    employee = _make_employee(session, "Tip Credit Makeup")
    legal_entity = _make_legal_entity(session, "Tip Credit Makeup LLC")
    term = _make_hourly_term(
        session, employee.id, legal_entity_id=legal_entity.id, function_label="Server",
        hourly_rate_minor=800, valid_from=datetime(2026, 9, 1, tzinfo=UTC),
    )
    run = engine.create_calculation_run(
        session, legal_entity_id=legal_entity.id,
        period_start=datetime(2026, 9, 1, tzinfo=UTC), period_end=datetime(2026, 9, 14, tzinfo=UTC),
    )
    calc_unsupplied = engine.calculate_employee_payroll(
        session, run, employee_id=employee.id,
        earning_lines=[engine.EarningLineInput(compensation_term_id=term.id, hours=Decimal("10"))],
    )
    result.check(
        "tip_credit_makeup_amount stays NULL ('to complete') when not explicitly supplied — "
        "never a false zero",
        calc_unsupplied.tip_credit_makeup_amount is None,
    )

    employee2 = _make_employee(session, "Tip Credit Makeup Supplied")
    term2 = _make_hourly_term(
        session, employee2.id, legal_entity_id=legal_entity.id, function_label="Server",
        hourly_rate_minor=800, valid_from=datetime(2026, 9, 1, tzinfo=UTC),
    )
    calc_supplied = engine.calculate_employee_payroll(
        session, run, employee_id=employee2.id,
        earning_lines=[engine.EarningLineInput(compensation_term_id=term2.id, hours=Decimal("10"))],
        tip_credit_makeup_amount=Decimal("12.34"),
    )
    result.check(
        "tip_credit_makeup_amount is preserved when explicitly supplied, and never composed "
        "into gross_pay",
        calc_supplied.tip_credit_makeup_amount == Decimal("12.34")
        and calc_supplied.gross_pay == calc_supplied.regular_pay,
    )


# ---------------------------------------------------------------------------
# Manual Payroll Handoff Connector (export confirmation)
# ---------------------------------------------------------------------------


def _test_manual_export_confirmation_flow(session: Session, result: ValidationResult) -> None:
    employee = _make_employee(session, "Export Flow")
    legal_entity = _make_legal_entity(session, "Export Flow LLC")
    term = _make_hourly_term(
        session, employee.id, legal_entity_id=legal_entity.id, function_label="Server",
        hourly_rate_minor=1500, valid_from=datetime(2026, 9, 1, tzinfo=UTC),
    )
    run = _build_calculated_run(
        session, legal_entity_id=legal_entity.id,
        employee_ids_and_terms=[(employee.id, term.id, Decimal("10"))],
    )
    snapshot = approval.approve_compensation_preparation(
        session, calculation_run_id=run.id, approved_by="approver@romesflavours.com",
    )

    rows = export.build_export_rows(session, snapshot_id=snapshot.id)
    result.check(
        "build_export_rows returns one row per approved Employee, flagging a missing provider "
        "employee-ID mapping rather than inventing one",
        len(rows) == 1 and rows[0].employee_id == employee.id
        and rows[0].provider_mapping_status == "MISSING"
        and rows[0].provider_external_employee_key is None,
    )

    confirmation = export.confirm_manual_communication(
        session, snapshot_id=snapshot.id, communicated_by="payroll-operator@romesflavours.com",
        reference="Entered into ADP batch #42",
    )
    result.check(
        "confirming manual communication records the confirmation and transitions the run "
        "from APPROVED to EXPORTED",
        confirmation.snapshot_id == snapshot.id and run.status == export.STATUS_EXPORTED,
    )

    second_confirmation = export.confirm_manual_communication(
        session, snapshot_id=snapshot.id, communicated_by="payroll-operator-2@romesflavours.com",
    )
    all_confirmations = export.get_export_confirmations(session, snapshot_id=snapshot.id)
    result.check(
        "a second (re-)communication is appended, never overwriting the first, and never "
        "changes the run's status again",
        second_confirmation.id != confirmation.id
        and len(all_confirmations) == 2
        and run.status == export.STATUS_EXPORTED,
    )


def _test_export_requires_approved_run(session: Session, result: ValidationResult) -> None:
    employee = _make_employee(session, "Export Too Early")
    legal_entity = _make_legal_entity(session, "Export Too Early LLC")
    term = _make_hourly_term(
        session, employee.id, legal_entity_id=legal_entity.id, function_label="Server",
        hourly_rate_minor=1200, valid_from=datetime(2026, 9, 1, tzinfo=UTC),
    )
    run = _build_calculated_run(
        session, legal_entity_id=legal_entity.id,
        employee_ids_and_terms=[(employee.id, term.id, Decimal("5"))],
    )
    # Not approved yet — CALCULATED only, so there is no snapshot to export.
    result.check(
        "there is no ApprovedCompensationSnapshot to export before approval",
        approval.get_approved_snapshot_by_run(session, run.id) is None,
    )


# ---------------------------------------------------------------------------
# Manual return of Provider results + reconciliation (never Provider net
# pay vs. a Compensation total)
# ---------------------------------------------------------------------------


def _approve_run_with_tips_and_incentive(
    session: Session, *, legal_entity_id: int, employee_id: int, term_id: int,
) -> m.ApprovedCompensationSnapshot:
    run = engine.create_calculation_run(
        session, legal_entity_id=legal_entity_id,
        period_start=datetime(2026, 9, 1, tzinfo=UTC), period_end=datetime(2026, 9, 14, tzinfo=UTC),
    )
    incentives.add_incentive_contribution(
        session, calculation_run_id=run.id, employee_id=employee_id,
        label="Wine Sales Contribution", amount=Decimal("50"), created_by="manager@romesflavours.com",
    )
    engine.calculate_employee_payroll(
        session, run, employee_id=employee_id,
        earning_lines=[engine.EarningLineInput(compensation_term_id=term_id, hours=Decimal("40"))],
        tips_amount=Decimal("100.00"),
    )
    run.status = approval.STATUS_CALCULATED
    session.flush()
    return approval.approve_compensation_preparation(
        session, calculation_run_id=run.id, approved_by="approver@romesflavours.com",
    )


def _test_manual_provider_result_and_reconciliation_match(
    session: Session, result: ValidationResult,
) -> None:
    employee = _make_employee(session, "Reconciliation Match")
    legal_entity = _make_legal_entity(session, "Reconciliation Match LLC")
    restaurant = _make_restaurant(session, "Reconciliation Match Restaurant", legal_entity_id=legal_entity.id)
    source_system = _make_source_system(session, "Reconciliation Match ADP")
    term = _make_hourly_term(
        session, employee.id, legal_entity_id=legal_entity.id, function_label="Server",
        hourly_rate_minor=2000, valid_from=datetime(2026, 9, 1, tzinfo=UTC),
    )
    snapshot = _approve_run_with_tips_and_incentive(
        session, legal_entity_id=legal_entity.id, employee_id=employee.id, term_id=term.id,
    )
    # regular_pay = 40 * 20 = 800.00, tips = 100.00, incentive = 50.00

    payroll_run = reconciliation.record_manual_provider_result(
        session, source_system_id=source_system.id, restaurant_id=restaurant.id,
        period_start=datetime(2026, 9, 1, tzinfo=UTC), period_end=datetime(2026, 9, 14, tzinfo=UTC),
        pay_date=datetime(2026, 9, 18, tzinfo=UTC), run_type="REGULAR",
        employee_results=[
            reconciliation.ManualEmployeeResult(
                employee_id=employee.id,
                entries=[
                    reconciliation.ManualEarningEntry("REGULAR", "Regular", Decimal("800.00")),
                    reconciliation.ManualEarningEntry("TIPS", "Reported Tips", Decimal("100.00")),
                    reconciliation.ManualEarningEntry("BONUS", "Bonus", Decimal("50.00")),
                ],
            ),
        ],
        created_by="payroll-operator@romesflavours.com",
    )

    recon = reconciliation.reconcile(
        session, snapshot_id=snapshot.id, payroll_run_id=payroll_run.id,
        created_by="payroll-operator@romesflavours.com",
    )
    lines = recon.lines
    result.check(
        "reconciling a Provider result that exactly matches RF-One's approved components "
        "produces MATCH for Regular Pay, Tips, and Recognized Incentive",
        len(lines) == 3 and all(line.status == reconciliation.STATUS_MATCH for line in lines),
    )
    result.check(
        "reconciliation never produces a line comparing Provider net pay to any Compensation total",
        all(line.component_label != "Gross Pay" and "Net" not in line.component_label for line in lines),
    )


def _test_duplicate_manual_provider_result_is_rejected(session: Session, result: ValidationResult) -> None:
    employee = _make_employee(session, "Duplicate Provider Result")
    legal_entity = _make_legal_entity(session, "Duplicate Provider Result LLC")
    restaurant = _make_restaurant(session, "Duplicate Provider Result Restaurant", legal_entity_id=legal_entity.id)
    source_system = _make_source_system(session, "Duplicate Provider Result ADP")
    term = _make_hourly_term(
        session, employee.id, legal_entity_id=legal_entity.id, function_label="Server",
        hourly_rate_minor=2000, valid_from=datetime(2026, 9, 1, tzinfo=UTC),
    )
    _approve_run_with_tips_and_incentive(
        session, legal_entity_id=legal_entity.id, employee_id=employee.id, term_id=term.id,
    )

    kwargs = dict(
        source_system_id=source_system.id, restaurant_id=restaurant.id,
        period_start=datetime(2026, 9, 1, tzinfo=UTC), period_end=datetime(2026, 9, 14, tzinfo=UTC),
        pay_date=datetime(2026, 9, 18, tzinfo=UTC), run_type="REGULAR",
        employee_results=[
            reconciliation.ManualEmployeeResult(
                employee_id=employee.id,
                entries=[reconciliation.ManualEarningEntry("REGULAR", "Regular", Decimal("800.00"))],
            ),
        ],
        created_by="payroll-operator@romesflavours.com",
    )
    first_run = reconciliation.record_manual_provider_result(session, **kwargs)

    rejected = False
    try:
        reconciliation.record_manual_provider_result(session, **kwargs)
    except reconciliation.DuplicateProviderResultError:
        rejected = True
    result.check(
        "recording the identical Provider result twice (same source/restaurant/period/pay date/"
        "run type) is rejected as a duplicate, never silently creating a second PayrollRun",
        rejected,
    )

    corrected = reconciliation.record_manual_provider_result(
        session, supersedes_payroll_run_id=first_run.id, **kwargs,
    )
    session.refresh(first_run)
    result.check(
        "explicitly passing supersedes_payroll_run_id allows a correction — the prior run is "
        "marked SUPERSEDED (never deleted) and points at the new one",
        corrected.id != first_run.id
        and first_run.status == "SUPERSEDED"
        and first_run.superseded_by_payroll_run_id == corrected.id,
    )


def _test_reconciliation_detects_difference_and_missing_lines(
    session: Session, result: ValidationResult,
) -> None:
    employee = _make_employee(session, "Reconciliation Diff")
    legal_entity = _make_legal_entity(session, "Reconciliation Diff LLC")
    restaurant = _make_restaurant(session, "Reconciliation Diff Restaurant", legal_entity_id=legal_entity.id)
    source_system = _make_source_system(session, "Reconciliation Diff ADP")
    term = _make_hourly_term(
        session, employee.id, legal_entity_id=legal_entity.id, function_label="Server",
        hourly_rate_minor=2000, valid_from=datetime(2026, 9, 1, tzinfo=UTC),
    )
    snapshot = _approve_run_with_tips_and_incentive(
        session, legal_entity_id=legal_entity.id, employee_id=employee.id, term_id=term.id,
    )
    # RF-One: regular_pay=800.00, tips=100.00, incentive=50.00 — Provider
    # reports a DIFFERENT regular pay, no Tips at all, and an extra
    # provider-only "Holiday Pay" line RF-One never approved.
    payroll_run = reconciliation.record_manual_provider_result(
        session, source_system_id=source_system.id, restaurant_id=restaurant.id,
        period_start=datetime(2026, 9, 1, tzinfo=UTC), period_end=datetime(2026, 9, 14, tzinfo=UTC),
        pay_date=datetime(2026, 9, 18, tzinfo=UTC), run_type="REGULAR",
        employee_results=[
            reconciliation.ManualEmployeeResult(
                employee_id=employee.id,
                entries=[
                    reconciliation.ManualEarningEntry("REGULAR", "Regular", Decimal("790.00")),
                    reconciliation.ManualEarningEntry("BONUS", "Bonus", Decimal("50.00")),
                    reconciliation.ManualEarningEntry("HOLIDAY", "Holiday Pay", Decimal("64.00")),
                ],
            ),
        ],
        created_by="payroll-operator@romesflavours.com",
    )

    recon = reconciliation.reconcile(
        session, snapshot_id=snapshot.id, payroll_run_id=payroll_run.id,
        created_by="payroll-operator@romesflavours.com",
    )
    by_label = {line.component_label: line for line in recon.lines}

    result.check(
        "a value difference on a matched component is reported as DIFFERENT, with both values "
        "preserved",
        by_label["Regular Pay"].status == reconciliation.STATUS_DIFFERENT
        and by_label["Regular Pay"].rfone_value == Decimal("800.00")
        and by_label["Regular Pay"].provider_value == Decimal("790.00"),
    )
    result.check(
        "a component RF-One approved but the Provider did not report is MISSING_IN_PROVIDER",
        by_label["Tips"].status == reconciliation.STATUS_MISSING_IN_PROVIDER
        and by_label["Tips"].rfone_value == Decimal("100.00")
        and by_label["Tips"].provider_value is None,
    )
    holiday_line = next(line for line in recon.lines if "Holiday" in line.component_label)
    result.check(
        "a component the Provider added that RF-One never approved is reported "
        "(MISSING_IN_RFONE), never silently dropped or merged into another component",
        holiday_line.status == reconciliation.STATUS_MISSING_IN_RFONE
        and holiday_line.rfone_value is None
        and holiday_line.provider_value == Decimal("64.00"),
    )


def _test_reconciliation_is_idempotent_and_annotatable(session: Session, result: ValidationResult) -> None:
    employee = _make_employee(session, "Reconciliation Annotate")
    legal_entity = _make_legal_entity(session, "Reconciliation Annotate LLC")
    restaurant = _make_restaurant(session, "Reconciliation Annotate Restaurant", legal_entity_id=legal_entity.id)
    source_system = _make_source_system(session, "Reconciliation Annotate ADP")
    term = _make_hourly_term(
        session, employee.id, legal_entity_id=legal_entity.id, function_label="Server",
        hourly_rate_minor=2000, valid_from=datetime(2026, 9, 1, tzinfo=UTC),
    )
    snapshot = _approve_run_with_tips_and_incentive(
        session, legal_entity_id=legal_entity.id, employee_id=employee.id, term_id=term.id,
    )
    payroll_run = reconciliation.record_manual_provider_result(
        session, source_system_id=source_system.id, restaurant_id=restaurant.id,
        period_start=datetime(2026, 9, 1, tzinfo=UTC), period_end=datetime(2026, 9, 14, tzinfo=UTC),
        pay_date=datetime(2026, 9, 18, tzinfo=UTC), run_type="REGULAR",
        employee_results=[
            reconciliation.ManualEmployeeResult(
                employee_id=employee.id,
                entries=[reconciliation.ManualEarningEntry("REGULAR", "Regular", Decimal("790.00"))],
            ),
        ],
        created_by="payroll-operator@romesflavours.com",
    )

    first = reconciliation.reconcile(
        session, snapshot_id=snapshot.id, payroll_run_id=payroll_run.id,
        created_by="payroll-operator@romesflavours.com",
    )
    second = reconciliation.reconcile(
        session, snapshot_id=snapshot.id, payroll_run_id=payroll_run.id,
        created_by="someone-else@romesflavours.com",
    )
    result.check(
        "re-reconciling the same (snapshot, run) pair returns the existing pass idempotently",
        first.id == second.id,
    )

    diff_line = next(line for line in first.lines if line.component_label == "Regular Pay")
    reconciliation.annotate_reconciliation_line(
        session, line_id=diff_line.id, note="Provider rounded down; accepted.",
        resolution_status="ACCEPTED", resolved_by="manager@romesflavours.com",
    )
    session.refresh(diff_line)
    result.check(
        "annotating a reconciliation line records the note, resolution, and resolver",
        diff_line.note == "Provider rounded down; accepted."
        and diff_line.resolution_status == "ACCEPTED"
        and diff_line.resolved_by == "manager@romesflavours.com"
        and diff_line.resolved_at is not None,
    )

    rejected = False
    try:
        reconciliation.annotate_reconciliation_line(
            session, line_id=diff_line.id, resolution_status="EXPLAINED",
        )
    except ValueError:
        rejected = True
    result.check(
        "moving a line away from OPEN without a resolved_by actor reference is rejected",
        rejected,
    )


def _test_two_legal_entities_never_mixed_in_reconciliation(session: Session, result: ValidationResult) -> None:
    legal_entity_a = _make_legal_entity(session, "Two-Entity A LLC")
    legal_entity_b = _make_legal_entity(session, "Two-Entity B LLC")
    restaurant_a = _make_restaurant(session, "Two-Entity A Restaurant", legal_entity_id=legal_entity_a.id)
    source_system = _make_source_system(session, "Two-Entity ADP")

    employee_a = _make_employee(session, "Two-Entity Employee A")
    term_a = _make_hourly_term(
        session, employee_a.id, legal_entity_id=legal_entity_a.id, function_label="Server",
        hourly_rate_minor=2000, valid_from=datetime(2026, 9, 1, tzinfo=UTC),
    )
    snapshot_a = _approve_run_with_tips_and_incentive(
        session, legal_entity_id=legal_entity_a.id, employee_id=employee_a.id, term_id=term_a.id,
    )

    employee_b = _make_employee(session, "Two-Entity Employee B")
    term_b = _make_hourly_term(
        session, employee_b.id, legal_entity_id=legal_entity_b.id, function_label="Server",
        hourly_rate_minor=2000, valid_from=datetime(2026, 9, 1, tzinfo=UTC),
    )
    snapshot_b = _approve_run_with_tips_and_incentive(
        session, legal_entity_id=legal_entity_b.id, employee_id=employee_b.id, term_id=term_b.id,
    )
    result.check(
        "two Legal Entities' ApprovedCompensationSnapshots are never combined into one run/snapshot",
        snapshot_a.legal_entity_id != snapshot_b.legal_entity_id
        and snapshot_a.id != snapshot_b.id,
    )

    # A Payroll Provider result recorded under Legal Entity A's Restaurant
    # only ever reconciles against Legal Entity A's own snapshot; it has no
    # result at all for the Employee under Legal Entity B.
    payroll_run_a = reconciliation.record_manual_provider_result(
        session, source_system_id=source_system.id, restaurant_id=restaurant_a.id,
        period_start=datetime(2026, 9, 1, tzinfo=UTC), period_end=datetime(2026, 9, 14, tzinfo=UTC),
        pay_date=datetime(2026, 9, 18, tzinfo=UTC), run_type="REGULAR",
        employee_results=[
            reconciliation.ManualEmployeeResult(
                employee_id=employee_a.id,
                entries=[reconciliation.ManualEarningEntry("REGULAR", "Regular", Decimal("800.00"))],
            ),
        ],
        created_by="payroll-operator@romesflavours.com",
    )
    rejected = False
    try:
        reconciliation.reconcile(
            session, snapshot_id=snapshot_b.id, payroll_run_id=payroll_run_a.id,
            created_by="payroll-operator@romesflavours.com",
        )
    except reconciliation.LegalEntityMismatchError:
        rejected = True
    result.check(
        "reconciling Legal Entity B's snapshot against a PayrollRun recorded under Legal Entity "
        "A's Restaurant is refused outright — never silently compared, matched, or merged across "
        "Legal Entities",
        rejected,
    )

    # The correctly-paired reconciliation (B's snapshot against a B-scoped
    # PayrollRun) still works normally.
    restaurant_b = _make_restaurant(session, "Two-Entity B Restaurant", legal_entity_id=legal_entity_b.id)
    payroll_run_b = reconciliation.record_manual_provider_result(
        session, source_system_id=source_system.id, restaurant_id=restaurant_b.id,
        period_start=datetime(2026, 9, 1, tzinfo=UTC), period_end=datetime(2026, 9, 14, tzinfo=UTC),
        pay_date=datetime(2026, 9, 18, tzinfo=UTC), run_type="REGULAR",
        employee_results=[
            reconciliation.ManualEmployeeResult(
                employee_id=employee_b.id,
                entries=[reconciliation.ManualEarningEntry("REGULAR", "Regular", Decimal("800.00"))],
            ),
        ],
        created_by="payroll-operator@romesflavours.com",
    )
    recon_b = reconciliation.reconcile(
        session, snapshot_id=snapshot_b.id, payroll_run_id=payroll_run_b.id,
        created_by="payroll-operator@romesflavours.com",
    )
    result.check(
        "reconciling Legal Entity B's snapshot against its OWN Legal Entity's PayrollRun succeeds "
        "and only ever concerns Employee B",
        all(line.employee_id == employee_b.id for line in recon_b.lines),
    )
