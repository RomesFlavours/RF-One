"""Automated synthetic tests for Compensation from real hours
(`payroll_calculation/compensation_period.py`): who is in a Compensation
Run (Shifts at a Location of the run's Legal Entity — never Compensation
Terms), Regular / Overtime / Total Hours per Workweek, wage / bonus / tips
shown when known and MISSING when not, and the two separate statuses.

Same pattern as `compensation_period_summary_validation.py`: synthetic
fixture, disposable database, always rolled back, never touches real data.
The fixture mirrors Winter Park's configuration (America/New_York, 04:00
operating-day cutoff, Monday Workweek) on the weeks of 7 and 14 September
2026 (EDT)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .payroll_calculation import compensation_period as cp
from .payroll_calculation import incentives as incentives_service
from .payroll_calculation import workweek as ww

UTC = timezone.utc
NY = ZoneInfo("America/New_York")

WEEK1 = date(2026, 9, 7)   # Monday
WEEK2 = date(2026, 9, 14)  # Monday
NOW = datetime(2027, 1, 1, tzinfo=UTC)


@dataclass
class ValidationResult:
    success: bool
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)

    def check(self, description: str, condition: bool, detail: object = "") -> None:
        if condition:
            self.checks_passed.append(description)
        else:
            self.checks_failed.append(f"{description} {detail}".strip())
            self.success = False


def run_validation(session_factory: sessionmaker[Session]) -> ValidationResult:
    result = ValidationResult(success=True)
    for test in (
        _test_a_35_hours,
        _test_b_40_hours,
        _test_c_46_hours,
        _test_d_two_weeks_46_and_38,
        _test_e_two_employees_are_independent,
        _test_f_shifts_without_compensation_term_appear,
        _test_g_no_shift_no_row,
        _test_h_wage_is_shown,
        _test_i_bonus_is_shown,
        _test_j_wage_missing_bonus_present,
        _test_k_open_or_invalid_shift_marks_hours_incomplete,
        _test_complete_data_when_wage_and_tips_are_known,
        _test_only_this_legal_entitys_locations_count,
        _test_restaurant_without_legal_entity_is_reported,
        _test_no_workweek_keeps_total_hours,
        _test_period_still_open_is_provisional_not_incomplete,
        _test_shift_history_starting_late_makes_hours_incomplete,
        _test_salaried_listed_with_or_without_shifts,
    ):
        with session_factory() as session:
            try:
                test(session, result)
            except Exception as exc:  # a crash is a failed check, not a lost suite
                result.check(f"{test.__name__} ran without error", False, repr(exc))
            finally:
                session.rollback()
    return result


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


@dataclass
class _Site:
    location: m.Location
    restaurant: m.Restaurant
    legal_entity: m.LegalEntity | None


def _site(session: Session, name: str = "Winter Park", *, linked: bool = True, workweek: bool = True,
          history: bool = True) -> _Site:
    merchant = m.Merchant(name=f"{name} Merchant")
    session.add(merchant)
    session.flush()
    location = m.Location(
        merchant_id=merchant.id, name=f"{name} Location",
        timezone="America/New_York", operating_day_cutoff_time=time(4, 0),
    )
    legal_entity = m.LegalEntity(legal_name=f"{name} LLC", status="ACTIVE")
    session.add_all([location, legal_entity])
    session.flush()
    restaurant = m.Restaurant(name=f"{name} Restaurant", legal_entity_id=legal_entity.id if linked else None)
    session.add(restaurant)
    session.flush()
    session.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
    if workweek:
        ww.set_workweek_start(
            session, restaurant_id=restaurant.id, start_weekday=0,
            effective_from=datetime(2000, 1, 1, tzinfo=UTC),
        )
    session.flush()
    if history:
        # The acquired Shift history at this Location covers September 2026
        # (one Shift well before and one well after), as in real use.
        anchor = m.Employee(location_id=location.id, display_name="History Anchor")
        session.add(anchor)
        session.flush()
        for day in (date(2026, 8, 3), date(2026, 12, 1)):
            start = _local(day, 10)
            session.add(m.Shift(employee_id=anchor.id, clock_in=start, clock_out=start + timedelta(hours=1)))
        session.flush()
    return _Site(location, restaurant, legal_entity)


def _employee(session: Session, site: _Site, name: str) -> m.Employee:
    employee = m.Employee(location_id=site.location.id, display_name=name)
    session.add(employee)
    session.flush()
    return employee


def _local(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=NY).astimezone(UTC)


def _shift(session: Session, employee: m.Employee, start: datetime, hours: float | None, **extra) -> m.Shift:
    shift = m.Shift(
        employee_id=employee.id, clock_in=start,
        clock_out=start + timedelta(hours=hours) if hours is not None else None, **extra,
    )
    session.add(shift)
    session.flush()
    return shift


def _week(session: Session, employee: m.Employee, monday: date, daily_hours: list[float]) -> None:
    for offset, hours in enumerate(daily_hours):
        _shift(session, employee, _local(monday + timedelta(days=offset), 10), hours)


def _run(session: Session, legal_entity: m.LegalEntity, first: date, last: date) -> m.CompensationPreparationRun:
    run = m.CompensationPreparationRun(
        legal_entity_id=legal_entity.id,
        period_start=datetime(first.year, first.month, first.day, tzinfo=UTC),
        period_end=datetime(last.year, last.month, last.day, tzinfo=UTC),
        status="OPEN",
    )
    session.add(run)
    session.flush()
    return run


def _term(session: Session, employee: m.Employee, legal_entity: m.LegalEntity, rate_minor: int = 2000,
          function_label: str = "Server") -> m.EmployeeCompensationTerm:
    term = m.EmployeeCompensationTerm(
        employee_id=employee.id, legal_entity_id=legal_entity.id, function_label=function_label,
        compensation_basis="HOURLY", hourly_rate_minor=rate_minor,
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
    )
    session.add(term)
    session.flush()
    return term


def _final_tips(session: Session, site: _Site, first: date, last: date, payable: dict[int, int]) -> None:
    run = m.TipDistributionCalculationRun(
        restaurant_id=site.restaurant.id, period_start=_local(first, 4), period_end=_local(last + timedelta(days=1), 4),
        status="COMPLETE", state=m.TIPS_RUN_STATE_FINAL, first_business_date=first, last_business_date=last,
        timezone_name="America/New_York", operating_day_cutoff_time=time(4, 0), control_difference_minor=0,
        finalized_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    for employee_id, amount in payable.items():
        session.add(m.TipEntitlement(
            calculation_run_id=run.id, restaurant_id=site.restaurant.id, employee_id=employee_id,
            gross_amount_minor=amount, outbound_amount_minor=0, inbound_amount_minor=0,
            payable_amount_minor=amount,
        ))
    session.flush()


def _hours(session: Session, run: m.CompensationPreparationRun, now: datetime = NOW) -> cp.RunHours:
    return cp.build_run_hours(session, run, now=now)


def _row(hours: cp.RunHours, employee: m.Employee) -> cp.PersonRow | None:
    return next((r for r in hours.rows if r.employee_id == employee.id), None)


def _split(row: cp.PersonRow | None) -> tuple:
    return (row.regular_hours, row.overtime_hours, row.total_hours) if row else None


def _one_week(session: Session, result: ValidationResult, label: str, daily: list[float],
              expected: tuple[str, str, str]) -> None:
    site = _site(session)
    emp = _employee(session, site, "Tatiana Ceban")
    _week(session, emp, WEEK1, daily)
    row = _row(_hours(session, _run(session, site.legal_entity, WEEK1, WEEK1 + timedelta(days=6))), emp)
    want = tuple(Decimal(x) for x in expected)
    result.check(f"{label}: Regular / Overtime / Total = {' / '.join(expected)}", _split(row) == want, _split(row))
    result.check(f"{label}: hours COMPLETE", row is not None and row.hours_status == cp.HOURS_COMPLETE,
                 row and row.hours_reasons)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _test_a_35_hours(session: Session, result: ValidationResult) -> None:
    _one_week(session, result, "A 35 h", [7, 7, 7, 7, 7], ("35.00", "0.00", "35.00"))


def _test_b_40_hours(session: Session, result: ValidationResult) -> None:
    _one_week(session, result, "B 40 h", [8, 8, 8, 8, 8], ("40.00", "0.00", "40.00"))


def _test_c_46_hours(session: Session, result: ValidationResult) -> None:
    _one_week(session, result, "C 46 h", [10, 10, 10, 10, 6], ("40.00", "6.00", "46.00"))


def _test_d_two_weeks_46_and_38(session: Session, result: ValidationResult) -> None:
    site = _site(session)
    emp = _employee(session, site, "Andrew Muller")
    _week(session, emp, WEEK1, [10, 10, 10, 10, 6])  # 46 h
    _week(session, emp, WEEK2, [8, 8, 8, 8, 6])      # 38 h
    row = _row(_hours(session, _run(session, site.legal_entity, WEEK1, WEEK2 + timedelta(days=6))), emp)
    result.check("D 46 + 38 h: 78 Regular / 6 Overtime / 84 Total (the 40 restart each Workweek)",
                 _split(row) == (Decimal("78.00"), Decimal("6.00"), Decimal("84.00")), _split(row))


def _test_e_two_employees_are_independent(session: Session, result: ValidationResult) -> None:
    site = _site(session)
    long_week = _employee(session, site, "Maria De Luca")
    short_week = _employee(session, site, "Luca Rossi")
    _week(session, long_week, WEEK1, [10, 10, 10, 10, 6])  # 46 h
    _week(session, short_week, WEEK1, [6, 6, 6, 6, 6])     # 30 h
    hours = _hours(session, _run(session, site.legal_entity, WEEK1, WEEK1 + timedelta(days=6)))
    result.check("E first Employee: 40 / 6 / 46",
                 _split(_row(hours, long_week)) == (Decimal("40.00"), Decimal("6.00"), Decimal("46.00")),
                 _split(_row(hours, long_week)))
    result.check("E second Employee: 30 / 0 / 30 (never pooled with the first)",
                 _split(_row(hours, short_week)) == (Decimal("30.00"), Decimal("0.00"), Decimal("30.00")),
                 _split(_row(hours, short_week)))


def _test_f_shifts_without_compensation_term_appear(session: Session, result: ValidationResult) -> None:
    site = _site(session)
    emp = _employee(session, site, "Elena Riva")
    _week(session, emp, WEEK1, [8, 8])
    row = _row(_hours(session, _run(session, site.legal_entity, WEEK1, WEEK1 + timedelta(days=6))), emp)
    result.check("F Shifts but no Compensation Term: the person is in the run", row is not None)
    result.check("F ... with hours", row is not None and row.total_hours == Decimal("16.00"), row and row.total_hours)
    result.check("F ... and Hourly Wage MISSING, compensation data INCOMPLETE with the reason",
                 row is not None and row.hourly_wage is None and row.data_status == cp.DATA_INCOMPLETE
                 and any("Hourly wage missing" in r for r in row.data_reasons), row and row.data_reasons)
    result.check("F ... while the hours stay COMPLETE",
                 row is not None and row.hours_status == cp.HOURS_COMPLETE, row and row.hours_reasons)


def _test_g_no_shift_no_row(session: Session, result: ValidationResult) -> None:
    site = _site(session)
    worked = _employee(session, site, "Anna Bianchi")
    idle = _employee(session, site, "Paolo Verdi")
    _term(session, idle, site.legal_entity)  # a Compensation Term alone never brings a person in
    _week(session, worked, WEEK1, [8])
    _shift(session, idle, _local(WEEK2, 10), 8)  # outside the period
    hours = _hours(session, _run(session, site.legal_entity, WEEK1, WEEK1 + timedelta(days=6)))
    result.check("G no Shift in the period: not in the run, even with a Compensation Term",
                 _row(hours, idle) is None and _row(hours, worked) is not None,
                 [r.employee_id for r in hours.rows])


def _test_h_wage_is_shown(session: Session, result: ValidationResult) -> None:
    site = _site(session)
    emp = _employee(session, site, "Giulia Neri")
    _term(session, emp, site.legal_entity, rate_minor=1850)
    _week(session, emp, WEEK1, [8])
    row = _row(_hours(session, _run(session, site.legal_entity, WEEK1, WEEK1 + timedelta(days=6))), emp)
    result.check("H wage present: shown as 18.50/hr",
                 row is not None and row.hourly_wage == Decimal("18.50"), row and row.hourly_wage)
    result.check("H wage present: no wage reason",
                 row is not None and not any("wage" in r.lower() for r in row.data_reasons), row and row.data_reasons)


def _test_i_bonus_is_shown(session: Session, result: ValidationResult) -> None:
    site = _site(session)
    emp = _employee(session, site, "Sara Gallo")
    _term(session, emp, site.legal_entity)
    _week(session, emp, WEEK1, [8])
    run = _run(session, site.legal_entity, WEEK1, WEEK1 + timedelta(days=6))
    incentives_service.add_incentive_contribution(
        session, calculation_run_id=run.id, employee_id=emp.id, label="Wine sales",
        amount=Decimal("150.00"), created_by="test",
    )
    row = _row(_hours(session, run), emp)
    result.check("I bonus present: shown as 150.00", row is not None and row.bonus == Decimal("150.00"),
                 row and row.bonus)


def _test_j_wage_missing_bonus_present(session: Session, result: ValidationResult) -> None:
    site = _site(session)
    emp = _employee(session, site, "John Smith")
    _week(session, emp, WEEK1, [10, 10, 10, 10, 6])  # 46 h
    _week(session, emp, WEEK2, [8, 8, 8, 8, 6])      # 38 h
    run = _run(session, site.legal_entity, WEEK1, WEEK2 + timedelta(days=6))
    incentives_service.add_incentive_contribution(
        session, calculation_run_id=run.id, employee_id=emp.id, label="Bonus",
        amount=Decimal("150.00"), created_by="test",
    )
    row = _row(_hours(session, run), emp)
    result.check("J wage missing + bonus: hours 78 / 6 / 84 shown",
                 _split(row) == (Decimal("78.00"), Decimal("6.00"), Decimal("84.00")), _split(row))
    result.check("J ... bonus 150.00 shown, wage MISSING, data INCOMPLETE",
                 row is not None and row.bonus == Decimal("150.00") and row.hourly_wage is None
                 and row.data_status == cp.DATA_INCOMPLETE, row and (row.bonus, row.data_reasons))


def _test_k_open_or_invalid_shift_marks_hours_incomplete(session: Session, result: ValidationResult) -> None:
    site = _site(session)
    open_emp = _employee(session, site, "Marco Blu")
    invalid_emp = _employee(session, site, "Chiara Verdi")
    _shift(session, open_emp, _local(WEEK1, 10), None)               # still open
    _shift(session, invalid_emp, _local(WEEK1, 10), 8)
    start = _local(WEEK1 + timedelta(days=1), 10)
    _shift(session, invalid_emp, start, None, override_out_time=start - timedelta(hours=1))  # out before in
    hours = _hours(session, _run(session, site.legal_entity, WEEK1, WEEK1 + timedelta(days=6)))
    open_row, invalid_row = _row(hours, open_emp), _row(hours, invalid_emp)
    result.check("K open Shift: the person is visible, hours INCOMPLETE with the reason",
                 open_row is not None and open_row.hours_status == cp.HOURS_INCOMPLETE
                 and any("still open" in r for r in open_row.hours_reasons), open_row and open_row.hours_reasons)
    result.check("K invalid Shift: visible with the valid 8 h, hours INCOMPLETE with the reason",
                 invalid_row is not None and invalid_row.total_hours == Decimal("8.00")
                 and invalid_row.hours_status == cp.HOURS_INCOMPLETE
                 and any("not after clock-in" in r for r in invalid_row.hours_reasons),
                 invalid_row and (invalid_row.total_hours, invalid_row.hours_reasons))


def _test_complete_data_when_wage_and_tips_are_known(session: Session, result: ValidationResult) -> None:
    site = _site(session)
    emp = _employee(session, site, "Tatiana Ceban")
    _term(session, emp, site.legal_entity)
    _week(session, emp, WEEK1, [8])
    run = _run(session, site.legal_entity, WEEK1, WEEK1 + timedelta(days=6))
    before = _row(_hours(session, run), emp)
    result.check("no FINAL Tips run: Tips NOT AVAILABLE, data INCOMPLETE, hours still COMPLETE",
                 before is not None and before.tips is None and before.data_status == cp.DATA_INCOMPLETE
                 and before.hours_status == cp.HOURS_COMPLETE, before and before.data_reasons)
    _final_tips(session, site, WEEK1, WEEK1 + timedelta(days=6), {emp.id: 12345})
    after = _row(_hours(session, run), emp)
    result.check("wage + FINAL Tips: Tips 123.45, compensation data COMPLETE",
                 after is not None and after.tips == Decimal("123.45") and after.data_status == cp.DATA_COMPLETE,
                 after and (after.tips, after.data_reasons))
    result.check("missing overtime money is never a reason: no reason mentions an overtime amount",
                 after is not None and not after.hours_reasons and not after.data_reasons)


def _test_only_this_legal_entitys_locations_count(session: Session, result: ValidationResult) -> None:
    winter_park = _site(session, "Winter Park")
    mount_dora = _site(session, "Mount Dora")
    emp = _employee(session, winter_park, "Luca Rossi")
    _shift(session, emp, _local(WEEK1, 10), 8, location_id=winter_park.location.id)
    _shift(session, emp, _local(WEEK1 + timedelta(days=1), 10), 5, location_id=mount_dora.location.id)
    wp = _row(_hours(session, _run(session, winter_park.legal_entity, WEEK1, WEEK1 + timedelta(days=6))), emp)
    md = _row(_hours(session, _run(session, mount_dora.legal_entity, WEEK1, WEEK1 + timedelta(days=6))), emp)
    result.check("Winter Park run counts only the Winter Park Shift (8 h)",
                 wp is not None and wp.total_hours == Decimal("8.00"), wp and wp.total_hours)
    result.check("Mount Dora run counts only the Mount Dora Shift (5 h)",
                 md is not None and md.total_hours == Decimal("5.00"), md and md.total_hours)


def _test_restaurant_without_legal_entity_is_reported(session: Session, result: ValidationResult) -> None:
    unlinked = _site(session, "Unlinked", linked=False)
    emp = _employee(session, unlinked, "Paolo Verdi")
    _week(session, emp, WEEK1, [8, 8])
    hours = _hours(session, _run(session, unlinked.legal_entity, WEEK1, WEEK1 + timedelta(days=6)))
    result.check("Restaurant without Legal Entity: the run states the problem, no hours are invented",
                 not hours.rows and any("No Restaurant is linked" in p for p in hours.problems), hours.problems)
    found = [u for u in hours.unattributed if u.location_id == unlinked.location.id]
    result.check("... and its 2 Shifts of 1 Employee are reported as not attributable, never silently dropped",
                 len(found) == 1 and found[0].shifts == 2 and found[0].employees == 1
                 and found[0].restaurant_name == "Unlinked Restaurant", found)
    session.refresh(unlinked.restaurant)
    result.check("... and the Restaurant is not modified", unlinked.restaurant.legal_entity_id is None)


def _test_no_workweek_keeps_total_hours(session: Session, result: ValidationResult) -> None:
    site = _site(session, workweek=False)
    emp = _employee(session, site, "Andrew Muller")
    _week(session, emp, WEEK1, [10, 10, 10, 10, 6])
    row = _row(_hours(session, _run(session, site.legal_entity, WEEK1, WEEK1 + timedelta(days=6))), emp)
    result.check("no Workweek configured: Total 46 h still shown, Regular/Overtime NOT AVAILABLE, hours INCOMPLETE",
                 row is not None and row.total_hours == Decimal("46.00") and row.overtime_hours is None
                 and row.regular_hours is None and row.hours_status == cp.HOURS_INCOMPLETE
                 and any("Workweek" in r for r in row.hours_reasons), row and (row.total_hours, row.hours_reasons))


def _test_period_still_open_is_provisional_not_incomplete(session: Session, result: ValidationResult) -> None:
    site = _site(session)
    emp = _employee(session, site, "Tatiana Ceban")
    _week(session, emp, WEEK1, [8, 8])                         # Monday + Tuesday, both closed
    run = _run(session, site.legal_entity, WEEK1, WEEK1 + timedelta(days=6))
    hours = _hours(session, run, now=_local(WEEK1 + timedelta(days=3), 12))  # Thursday noon
    row = _row(hours, emp)
    result.check("period still open: the run is PROVISIONAL", hours.provisional)
    result.check("period still open: hours so far are counted (16 h) and stay COMPLETE",
                 row is not None and row.total_hours == Decimal("16.00") and row.hours_status == cp.HOURS_COMPLETE,
                 row and (row.total_hours, row.hours_reasons))
    result.check("period still open: stated once, never as a per-Location hours warning",
                 not any("not ended" in w for w in hours.hours_warnings), hours.hours_warnings)
    ended = _hours(session, run)
    result.check("period ended: no longer PROVISIONAL", not ended.provisional)


def _test_shift_history_starting_late_makes_hours_incomplete(session: Session, result: ValidationResult) -> None:
    site = _site(session, history=False)                       # first acquired Shift is inside the period
    emp = _employee(session, site, "Andrew Muller")
    other = _employee(session, site, "Luca Rossi")
    _week(session, emp, WEEK1 + timedelta(days=2), [8, 8])      # Wednesday + Thursday
    _week(session, other, WEEK1 + timedelta(days=3), [5])
    hours = _hours(session, _run(session, site.legal_entity, WEEK1, WEEK1 + timedelta(days=6)))
    rows = [_row(hours, emp), _row(hours, other)]
    result.check("history starting late: stated above the table",
                 any("Acquired Shifts start at" in w for w in hours.hours_warnings), hours.hours_warnings)
    result.check("history starting late: every affected Employee is HOURS INCOMPLETE with the reason",
                 all(r is not None and r.hours_status == cp.HOURS_INCOMPLETE
                     and any("Shift history starts after the beginning of the period" in x for x in r.hours_reasons)
                     for r in rows), [r and r.hours_reasons for r in rows])
    result.check("history starting late: the hours that do exist are still counted (16 h)",
                 rows[0] is not None and rows[0].total_hours == Decimal("16.00"), rows[0] and rows[0].total_hours)
    result.check("history starting late is not PROVISIONAL (the period has ended)", not hours.provisional)


def _test_salaried_listed_with_or_without_shifts(session: Session, result: ValidationResult) -> None:
    site = _site(session)
    manager = _employee(session, site, "Sam Salaried")          # SALARIED, no Shift
    chef = _employee(session, site, "Clara Chef")               # SALARIED, with Shifts
    hourly_idle = _employee(session, site, "Ivan Idle")         # HOURLY, no Shift
    hourly_no_wage = _employee(session, site, "Nina Noterm")    # Shifts, no Compensation Term
    for emp, amount in ((manager, 150000), (chef, 120000)):
        session.add(m.EmployeeCompensationTerm(
            employee_id=emp.id, legal_entity_id=site.legal_entity.id, function_label="Manager",
            compensation_basis="SALARIED", salaried_period_amount_minor=amount,
            valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        ))
    _term(session, hourly_idle, site.legal_entity)
    _week(session, chef, WEEK1, [10, 10, 10, 10, 6])            # 46 h — never Regular/Overtime
    _week(session, hourly_no_wage, WEEK1, [8])
    session.flush()
    hours = _hours(session, _run(session, site.legal_entity, WEEK1, WEEK1 + timedelta(days=6)))
    salaried = {r.employee_id: r for r in hours.salaried}
    result.check("SALARIED without Shifts is listed", manager.id in salaried
                 and salaried[manager.id].informational_hours is None, list(salaried))
    result.check("SALARIED with Shifts is listed with informational hours only (46 h)",
                 chef.id in salaried and salaried[chef.id].informational_hours == Decimal("46.00"),
                 chef.id in salaried and salaried[chef.id].informational_hours)
    result.check("SALARIED people are never hourly rows (no Regular/Overtime on a salary)",
                 _row(hours, manager) is None and _row(hours, chef) is None)
    result.check("HOURLY without Shifts is not listed", _row(hours, hourly_idle) is None
                 and hourly_idle.id not in salaried)
    no_wage = _row(hours, hourly_no_wage)
    result.check("HOURLY with Shifts and no wage is listed, Hourly Wage MISSING",
                 no_wage is not None and no_wage.hourly_wage is None and no_wage.total_hours == Decimal("8.00")
                 and any("Hourly wage missing" in r for r in no_wage.data_reasons), no_wage and no_wage.data_reasons)
