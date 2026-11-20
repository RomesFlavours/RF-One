"""Automated synthetic tests for the Payroll Calculation Engine (Product
Owner decisions: corrected Option C; multi-rate earning lines; Legal Entity
separation).

Mirrors the established `*_validation.py` pattern (see
`identity_authority_signature_validation.py`, `organization_validation.py`):
synthetic fixture, disposable database, always rolled back, never touches
real data. Constraint-violation scenarios use a nested SAVEPOINT
(`session.begin_nested()`) so a single expected `IntegrityError` does not
abort the whole validation transaction. Deliberately covers only the minimum
behaviors requested for this MVP — not an exhaustive suite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .payroll_calculation import engine

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
            _test_single_rate_employee(session, result)
            _test_multi_rate_employee_aggregates_lines_and_preserves_history(session, result)
            _test_invalid_compensation_term_rejected(session, result)
            _test_legal_entity_can_be_created(session, result)
            _test_two_restaurants_share_one_legal_entity(session, result)
            _test_legal_entity_separation(session, result)
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
    """The canonical Legal Entity fixture (Product Owner correction: the
    canonical `LegalEntity` model, never `Restaurant` — see the model's own
    docstring)."""
    legal_entity = m.LegalEntity(legal_name=legal_name, status="ACTIVE")
    session.add(legal_entity)
    session.flush()
    return legal_entity


def _make_restaurant(session: Session, name: str, *, legal_entity_id: int) -> m.Restaurant:
    """A Restaurant (Operational Unit) fixture, belonging to the given
    Legal Entity."""
    restaurant = m.Restaurant(name=name, legal_entity_id=legal_entity_id)
    session.add(restaurant)
    session.flush()
    return restaurant


def _make_hourly_term(
    session: Session, employee_id: int, *, legal_entity_id: int | None, function_label: str,
    hourly_rate_minor: int, valid_from: datetime, valid_to: datetime | None = None,
) -> m.EmployeeCompensationTerm:
    term = m.EmployeeCompensationTerm(
        employee_id=employee_id,
        legal_entity_id=legal_entity_id,
        function_label=function_label,
        compensation_basis=engine.compensation_helpers.HOURLY,
        hourly_rate_minor=hourly_rate_minor,
        valid_from=valid_from,
        valid_to=valid_to,
    )
    session.add(term)
    session.flush()
    return term


def _earning_lines_for(session: Session, calculation_id: int) -> list[m.EmployeePayrollCalculationEarningLine]:
    stmt = select(m.EmployeePayrollCalculationEarningLine).where(
        m.EmployeePayrollCalculationEarningLine.employee_payroll_calculation_id == calculation_id
    )
    return list(session.execute(stmt).scalars().all())


# ---------------------------------------------------------------------------
# A. Single-rate employee still works (40 hours x $20 = $800)
# ---------------------------------------------------------------------------


def _test_single_rate_employee(session: Session, result: ValidationResult) -> None:
    employee = _make_employee(session, "Single Rate")
    legal_entity = _make_legal_entity(session, "Single Rate Legal Entity LLC")
    term = _make_hourly_term(
        session, employee.id, legal_entity_id=legal_entity.id, function_label="Server",
        hourly_rate_minor=2000, valid_from=datetime(2026, 8, 1, tzinfo=UTC),
    )
    run = engine.create_calculation_run(
        session, legal_entity_id=legal_entity.id,
        period_start=datetime(2026, 8, 1, tzinfo=UTC), period_end=datetime(2026, 8, 14, tzinfo=UTC),
    )

    summary = engine.calculate_employee_payroll(
        session, run, employee_id=employee.id,
        earning_lines=[engine.EarningLineInput(compensation_term_id=term.id, hours=Decimal("40"))],
    )

    result.check(
        "single-rate employee: 40 hours x $20.00 = $800.00 regular_pay, gross_pay matches (no tips/bonus)",
        summary.regular_hours == Decimal("40")
        and summary.regular_pay == Decimal("800.00")
        and summary.gross_pay == Decimal("800.00"),
    )

    lines = _earning_lines_for(session, summary.id)
    result.check(
        "single-rate employee produces exactly one earning line with the selected term/rate/hours/pay",
        len(lines) == 1
        and lines[0].compensation_term_id == term.id
        and lines[0].hourly_rate_used == Decimal("20.00")
        and lines[0].regular_hours == Decimal("40")
        and lines[0].regular_pay == Decimal("800.00"),
    )


# ---------------------------------------------------------------------------
# B/C/D/E. Multi-rate employee aggregates correctly, each line persists its
# own term/rate/hours/pay, tips+bonus aggregate into gross_pay, and the
# underlying EmployeeCompensationTerm rows are never modified.
# ---------------------------------------------------------------------------


def _test_multi_rate_employee_aggregates_lines_and_preserves_history(
    session: Session, result: ValidationResult
) -> None:
    employee = _make_employee(session, "Multi Rate")
    legal_entity = _make_legal_entity(session, "Multi Rate Legal Entity LLC")
    server_term = _make_hourly_term(
        session, employee.id, legal_entity_id=legal_entity.id, function_label="Server",
        hourly_rate_minor=1200, valid_from=datetime(2026, 8, 1, tzinfo=UTC),
    )
    manager_term = _make_hourly_term(
        session, employee.id, legal_entity_id=legal_entity.id, function_label="Manager",
        hourly_rate_minor=2200, valid_from=datetime(2026, 8, 1, tzinfo=UTC),
    )
    run = engine.create_calculation_run(
        session, legal_entity_id=legal_entity.id,
        period_start=datetime(2026, 8, 1, tzinfo=UTC), period_end=datetime(2026, 8, 14, tzinfo=UTC),
    )

    # Two different, concurrently-valid HOURLY terms under different
    # function_labels for the SAME Employee — the existing compensation
    # model already allows this (Compensation Terms.md, "Multiple functions
    # / multiple rates"), so it is used as-is (Product Owner decision, rule
    # 6). One line exercises the work_date (day-level) effective-date path,
    # the other the period-level fallback.
    summary = engine.calculate_employee_payroll(
        session, run, employee_id=employee.id,
        earning_lines=[
            engine.EarningLineInput(
                compensation_term_id=server_term.id, hours=Decimal("20"), work_date=date(2026, 8, 3)
            ),
            engine.EarningLineInput(compensation_term_id=manager_term.id, hours=Decimal("15")),
        ],
        tips_amount=Decimal("100.00"),
        bonus_amount=Decimal("50.00"),
    )

    result.check(
        "multi-rate employee: regular_hours = 20 + 15 = 35, regular_pay = 240.00 + 330.00 = 570.00",
        summary.regular_hours == Decimal("35") and summary.regular_pay == Decimal("570.00"),
    )
    result.check(
        "tips ($100) and bonus ($50) aggregate on top of regular_pay: gross_pay = 570.00 + 100 + 50 = 720.00",
        summary.gross_pay == Decimal("720.00"),
    )

    lines_by_term = {line.compensation_term_id: line for line in _earning_lines_for(session, summary.id)}
    result.check(
        "both earning lines persisted, each with its own compensation_term_id/hourly_rate_used/hours/regular_pay",
        len(lines_by_term) == 2
        and lines_by_term[server_term.id].hourly_rate_used == Decimal("12.00")
        and lines_by_term[server_term.id].regular_hours == Decimal("20")
        and lines_by_term[server_term.id].regular_pay == Decimal("240.00")
        and lines_by_term[server_term.id].work_date == date(2026, 8, 3)
        and lines_by_term[manager_term.id].hourly_rate_used == Decimal("22.00")
        and lines_by_term[manager_term.id].regular_hours == Decimal("15")
        and lines_by_term[manager_term.id].regular_pay == Decimal("330.00")
        and lines_by_term[manager_term.id].work_date is None,
    )

    result.check(
        "the underlying EmployeeCompensationTerm rows were never modified by the calculation",
        server_term.hourly_rate_minor == 1200
        and server_term.function_label == "Server"
        and manager_term.hourly_rate_minor == 2200
        and manager_term.function_label == "Manager",
    )


# ---------------------------------------------------------------------------
# F. An invalid/non-effective compensation term is rejected — no line or
# summary is persisted.
# ---------------------------------------------------------------------------


def _test_invalid_compensation_term_rejected(session: Session, result: ValidationResult) -> None:
    employee = _make_employee(session, "Invalid Term Owner")
    other_employee = _make_employee(session, "Invalid Term Stranger")
    legal_entity = _make_legal_entity(session, "Invalid Term Legal Entity LLC")

    own_term = _make_hourly_term(
        session, employee.id, legal_entity_id=legal_entity.id, function_label="Server",
        hourly_rate_minor=1500, valid_from=datetime(2026, 8, 1, tzinfo=UTC),
        valid_to=datetime(2026, 8, 8, tzinfo=UTC),
    )
    stranger_term = _make_hourly_term(
        session, other_employee.id, legal_entity_id=legal_entity.id, function_label="Server",
        hourly_rate_minor=1500, valid_from=datetime(2026, 8, 1, tzinfo=UTC),
    )
    run = engine.create_calculation_run(
        session, legal_entity_id=legal_entity.id,
        period_start=datetime(2026, 8, 1, tzinfo=UTC), period_end=datetime(2026, 8, 14, tzinfo=UTC),
    )

    rejected_wrong_employee = False
    try:
        engine.calculate_employee_payroll(
            session, run, employee_id=employee.id,
            earning_lines=[engine.EarningLineInput(compensation_term_id=stranger_term.id, hours=Decimal("10"))],
        )
    except engine.InvalidCompensationTermError:
        rejected_wrong_employee = True
    result.check(
        "a compensation term belonging to a different Employee is rejected, not silently used",
        rejected_wrong_employee,
    )

    rejected_not_effective = False
    try:
        engine.calculate_employee_payroll(
            session, run, employee_id=employee.id,
            earning_lines=[
                engine.EarningLineInput(
                    compensation_term_id=own_term.id, hours=Decimal("10"), work_date=date(2026, 8, 20)
                )
            ],
        )
    except engine.InvalidCompensationTermError:
        rejected_not_effective = True
    result.check(
        "a compensation term not effective on the requested work_date (after its valid_to) is rejected",
        rejected_not_effective,
    )

    remaining = session.execute(
        select(m.EmployeePayrollCalculation).where(m.EmployeePayrollCalculation.employee_id == employee.id)
    ).scalars().all()
    result.check(
        "no EmployeePayrollCalculation summary was persisted for either rejected request",
        len(remaining) == 0,
    )


# ---------------------------------------------------------------------------
# A. LegalEntity can be created.
# ---------------------------------------------------------------------------


def _test_legal_entity_can_be_created(session: Session, result: ValidationResult) -> None:
    legal_entity = _make_legal_entity(session, "ABC Restaurants LLC")
    result.check(
        "a LegalEntity can be created with an id, legal_name and ACTIVE status",
        legal_entity.id is not None
        and legal_entity.legal_name == "ABC Restaurants LLC"
        and legal_entity.status == "ACTIVE",
    )


# ---------------------------------------------------------------------------
# B/I. Two Restaurants can belong to the SAME LegalEntity, and doing so does
# not create two different Legal Entity identities.
# ---------------------------------------------------------------------------


def _test_two_restaurants_share_one_legal_entity(session: Session, result: ValidationResult) -> None:
    legal_entity = _make_legal_entity(session, "ABC Restaurants Group LLC")
    restaurant_a = _make_restaurant(session, "Restaurant A", legal_entity_id=legal_entity.id)
    restaurant_b = _make_restaurant(session, "Restaurant B", legal_entity_id=legal_entity.id)

    result.check(
        "two different Restaurants (Operational Units) can belong to the same LegalEntity",
        restaurant_a.id != restaurant_b.id
        and restaurant_a.legal_entity_id == legal_entity.id
        and restaurant_b.legal_entity_id == legal_entity.id,
    )
    result.check(
        "sharing one LegalEntity across two Restaurants does not create two different "
        "Legal Entity identities — both Restaurants resolve to the exact same legal_entity_id",
        restaurant_a.legal_entity_id == restaurant_b.legal_entity_id,
    )


# ---------------------------------------------------------------------------
# Legal Entity separation (Product Owner decision): a CompensationPreparationRun
# requires a Legal Entity; the same Employee may hold overlapping
# compensation terms for different Legal Entities without conflict; a term
# from a different Legal Entity than the run's — or with no Legal Entity at
# all — is rejected.
# ---------------------------------------------------------------------------


def _test_legal_entity_separation(session: Session, result: ValidationResult) -> None:
    # C. CompensationPreparationRun requires a Legal Entity (legal_entity_id NOT NULL).
    savepoint = session.begin_nested()
    raised_missing_legal_entity = False
    try:
        session.add(
            m.CompensationPreparationRun(
                period_start=datetime(2026, 8, 1, tzinfo=UTC),
                period_end=datetime(2026, 8, 14, tzinfo=UTC),
                status="OPEN",
            )
        )
        session.flush()
    except IntegrityError:
        raised_missing_legal_entity = True
    finally:
        savepoint.rollback()
    result.check(
        "CompensationPreparationRun requires a Legal Entity (legal_entity_id) — omitting it raises IntegrityError",
        raised_missing_legal_entity,
    )

    # D. The same Employee may have overlapping compensation terms for two
    # different Legal Entities, same function_label, same valid_from — not a
    # conflict (widened UniqueConstraint on employee_compensation_terms).
    employee = _make_employee(session, "Legal Entity Employee")
    entity_a = _make_legal_entity(session, "Legal Entity A LLC")
    entity_b = _make_legal_entity(session, "Legal Entity B LLC")

    term_a = _make_hourly_term(
        session, employee.id, legal_entity_id=entity_a.id, function_label="Server",
        hourly_rate_minor=1200, valid_from=datetime(2026, 8, 1, tzinfo=UTC),
    )
    term_b = _make_hourly_term(
        session, employee.id, legal_entity_id=entity_b.id, function_label="Server",
        hourly_rate_minor=1500, valid_from=datetime(2026, 8, 1, tzinfo=UTC),
    )
    term_no_entity = _make_hourly_term(
        session, employee.id, legal_entity_id=None, function_label="Historical Server",
        hourly_rate_minor=1000, valid_from=datetime(2026, 1, 1, tzinfo=UTC),
    )
    result.check(
        "the same Employee holds overlapping same-function_label/same-valid_from compensation terms "
        "for two different Legal Entities without a uniqueness violation",
        term_a.id is not None and term_b.id is not None,
    )

    # E. A CompensationPreparationRun for Legal Entity A accepts only Compensation
    # Terms for Legal Entity A.
    run_a = engine.create_calculation_run(
        session, legal_entity_id=entity_a.id,
        period_start=datetime(2026, 8, 1, tzinfo=UTC), period_end=datetime(2026, 8, 14, tzinfo=UTC),
    )
    summary_a = engine.calculate_employee_payroll(
        session, run_a, employee_id=employee.id,
        earning_lines=[engine.EarningLineInput(compensation_term_id=term_a.id, hours=Decimal("10"))],
    )
    result.check(
        "a compensation term belonging to the run's own Legal Entity is accepted "
        "(10h x $12.00 = $120.00)",
        summary_a.regular_pay == Decimal("120.00"),
    )

    # F. A compensation term for the same Employee but ANOTHER Legal Entity
    # must be rejected before anything is persisted.
    rejected_cross_entity = False
    try:
        engine.calculate_employee_payroll(
            session, run_a, employee_id=employee.id,
            earning_lines=[engine.EarningLineInput(compensation_term_id=term_b.id, hours=Decimal("5"))],
        )
    except engine.InvalidCompensationTermError:
        rejected_cross_entity = True
    result.check(
        "a compensation term belonging to a different Legal Entity than the run's is rejected",
        rejected_cross_entity,
    )

    # G. A term with legal_entity_id = NULL is rejected by the calculation
    # engine — it cannot prove which Legal Entity it belongs to (a
    # data-readiness/backfill condition, not a model contradiction).
    rejected_null_entity = False
    try:
        engine.calculate_employee_payroll(
            session, run_a, employee_id=employee.id,
            earning_lines=[
                engine.EarningLineInput(compensation_term_id=term_no_entity.id, hours=Decimal("5"))
            ],
        )
    except engine.InvalidCompensationTermError:
        rejected_null_entity = True
    result.check(
        "a compensation term with legal_entity_id = NULL is rejected, never assumed to match",
        rejected_null_entity,
    )
