"""Automated synthetic tests for the Compensation Period Summary
(COMPENSATION_PERIOD_SUMMARY_001) and the shared Workweek setting.

Same pattern as `compensation_v1_validation.py`: synthetic fixture,
disposable database, always rolled back, never touches real data.

The fixture mirrors Winter Park's configuration (America/New_York, 04:00
operating-day cutoff, Monday Workweek) using the weeks of 7 and 14
September 2026 (EDT), so every boundary below is a real local instant."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .payroll_calculation import period_summary as ps
from .payroll_calculation import workweek as ww

UTC = timezone.utc
NY = ZoneInfo("America/New_York")

WEEK1 = date(2026, 9, 7)   # Monday
WEEK2 = date(2026, 9, 14)  # Monday


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
        _test_weekly_excess_is_not_netted_across_weeks,
        _test_partial_week_counts_earlier_hours_but_shows_only_period,
        _test_shift_crossing_the_week_boundary_is_split,
        _test_override_times_are_the_official_times,
        _test_home_location_fallback_is_counted,
        _test_finalized_tips_are_summed_once_and_only_when_covering,
        _test_zero_is_distinct_from_not_available,
        _test_open_and_overlapping_shifts_are_reported,
        _test_missing_workweek_or_location_configuration_is_stated,
        _test_workweek_setting_is_effective_dated,
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


def _site(session: Session, *, workweek: bool = True, configured: bool = True) -> _Site:
    merchant = m.Merchant(name="Summary Merchant")
    session.add(merchant)
    session.flush()
    location = m.Location(
        merchant_id=merchant.id, name="Summary Location",
        timezone="America/New_York" if configured else None,
        operating_day_cutoff_time=time(4, 0) if configured else None,
    )
    legal_entity = m.LegalEntity(legal_name="Summary LLC", status="ACTIVE")
    session.add_all([location, legal_entity])
    session.flush()
    restaurant = m.Restaurant(name="Summary Restaurant", legal_entity_id=legal_entity.id)
    session.add(restaurant)
    session.flush()
    session.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
    if workweek:
        ww.set_workweek_start(
            session, restaurant_id=restaurant.id, start_weekday=0,
            effective_from=datetime(2000, 1, 1, tzinfo=UTC),
        )
    session.flush()
    return _Site(location, restaurant)


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


def _final_run(session: Session, site: _Site, first: date, last: date, payable: dict[int, int],
               *, state: str = m.TIPS_RUN_STATE_FINAL) -> m.TipDistributionCalculationRun:
    run = m.TipDistributionCalculationRun(
        restaurant_id=site.restaurant.id, period_start=_local(first, 4), period_end=_local(last + timedelta(days=1), 4),
        status="COMPLETE", state=state, first_business_date=first, last_business_date=last,
        timezone_name="America/New_York", operating_day_cutoff_time=time(4, 0), control_difference_minor=0,
        finalized_at=datetime.now(UTC) if state == m.TIPS_RUN_STATE_FINAL else None,
    )
    session.add(run)
    session.flush()
    for employee_id, amount in payable.items():
        session.add(m.TipEntitlement(
            calculation_run_id=run.id, restaurant_id=site.restaurant.id, employee_id=employee_id,
            gross_amount_minor=amount * 3, outbound_amount_minor=amount * 2, inbound_amount_minor=0,
            payable_amount_minor=amount,
        ))
    session.flush()
    return run


def _summary(session: Session, site: _Site, first: date, last: date) -> ps.PeriodSummary:
    return ps.build_period_summary(
        session, location_id=site.location.id, first_business_date=first, last_business_date=last,
        now=datetime(2027, 1, 1, tzinfo=UTC),
    )


def _row(summary: ps.PeriodSummary, employee: m.Employee) -> ps.EmployeeSummaryRow | None:
    return next((r for r in summary.rows if r.employee_id == employee.id), None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _test_weekly_excess_is_not_netted_across_weeks(session: Session, result: ValidationResult) -> None:
    site = _site(session)
    emp = _employee(session, site, "Tatiana Ceban")
    for offset in range(5):
        _shift(session, emp, _local(WEEK1 + timedelta(days=offset), 10), 9)   # 45 h
        _shift(session, emp, _local(WEEK2 + timedelta(days=offset), 10), 7)   # 35 h
    row = _row(_summary(session, site, WEEK1, WEEK2 + timedelta(days=6)), emp)
    result.check("45 h + 35 h -> 80 worked hours", row is not None and row.worked_hours == Decimal("80.00"),
                 row and row.worked_hours)
    result.check("45 h + 35 h -> 5 overtime hours (no netting)", row is not None and row.overtime_hours == Decimal("5.00"),
                 row and row.overtime_hours)


def _test_partial_week_counts_earlier_hours_but_shows_only_period(session: Session, result: ValidationResult) -> None:
    site = _site(session)
    emp = _employee(session, site, "Andrew Muller")
    _shift(session, emp, _local(WEEK1, 9), 15)                      # Monday 15 h (before the period)
    _shift(session, emp, _local(WEEK1 + timedelta(days=1), 9), 15)  # Tuesday 15 h (before the period)
    for offset in (2, 3):                                           # Wednesday, Thursday: 10 h each
        _shift(session, emp, _local(WEEK1 + timedelta(days=offset), 9), 10)
    summary = _summary(session, site, WEEK1 + timedelta(days=2), WEEK1 + timedelta(days=6))
    row = _row(summary, emp)
    result.check("partial week shows only the period's 20 h", row is not None and row.worked_hours == Decimal("20.00"),
                 row and row.worked_hours)
    result.check("partial week: 30 h earlier in the week push 10 of the 20 h past 40",
                 row is not None and row.overtime_hours == Decimal("10.00"), row and row.overtime_hours)


def _test_shift_crossing_the_week_boundary_is_split(session: Session, result: ValidationResult) -> None:
    site = _site(session)
    emp = _employee(session, site, "Maria De Luca")
    for offset in range(4):                                          # Mon-Thu 9.5 h = 38 h
        _shift(session, emp, _local(WEEK1 + timedelta(days=offset), 10), 9.5)
    crossing = _shift(session, emp, _local(WEEK1 + timedelta(days=6), 22), 8)  # Sun 22:00 -> Mon 06:00
    week1 = _row(_summary(session, site, WEEK1, WEEK1 + timedelta(days=6)), emp)
    week2 = _row(_summary(session, site, WEEK2, WEEK2 + timedelta(days=6)), emp)
    result.check("boundary shift: 6 h before Monday 04:00 stay in week 1 (38 + 6 = 44)",
                 week1 is not None and week1.worked_hours == Decimal("44.00"), week1 and week1.worked_hours)
    result.check("boundary shift: week 1 overtime is 4 h", week1 is not None and week1.overtime_hours == Decimal("4.00"),
                 week1 and week1.overtime_hours)
    result.check("boundary shift: 2 h after Monday 04:00 open week 2 with no overtime",
                 week2 is not None and week2.worked_hours == Decimal("2.00") and week2.overtime_hours == Decimal("0.00"),
                 week2 and (week2.worked_hours, week2.overtime_hours))
    session.refresh(crossing)
    result.check("the original Shift is not modified",
                 ps._aware_utc(crossing.clock_out) - ps._aware_utc(crossing.clock_in) == timedelta(hours=8))


def _test_override_times_are_the_official_times(session: Session, result: ValidationResult) -> None:
    site = _site(session)
    emp = _employee(session, site, "Luca Rossi")
    start = _local(WEEK1, 10)
    _shift(session, emp, start, 10, override_out_time=start + timedelta(hours=6))
    row = _row(_summary(session, site, WEEK1, WEEK1), emp)
    result.check("a manager override replaces the raw clock-out", row is not None and row.worked_hours == Decimal("6.00"),
                 row and row.worked_hours)


def _test_home_location_fallback_is_counted(session: Session, result: ValidationResult) -> None:
    site = _site(session)
    emp = _employee(session, site, "Elena Riva")
    _shift(session, emp, _local(WEEK1, 10), 5)                                   # no Location on the Shift
    _shift(session, emp, _local(WEEK1 + timedelta(days=1), 10), 5, location_id=site.location.id)
    summary = _summary(session, site, WEEK1, WEEK1 + timedelta(days=6))
    row = _row(summary, emp)
    result.check("both Shifts are counted (10 h)", row is not None and row.worked_hours == Decimal("10.00"))
    result.check("only the Shift without a Location is reported as home-Location attribution",
                 row is not None and row.home_location_fallback_shifts == 1
                 and summary.home_location_fallback_shifts == 1 and summary.shifts_counted == 2,
                 row and (row.home_location_fallback_shifts, summary.shifts_counted))


def _test_finalized_tips_are_summed_once_and_only_when_covering(session: Session, result: ValidationResult) -> None:
    site = _site(session)
    server = _employee(session, site, "Anna Bianchi")
    host = _employee(session, site, "Paolo Verdi")
    _shift(session, server, _local(WEEK1, 17), 6)
    run1 = _final_run(session, site, WEEK1, WEEK1 + timedelta(days=6), {server.id: 10000, host.id: 2500})
    run2 = _final_run(session, site, WEEK2, WEEK2 + timedelta(days=6), {server.id: 5050})
    _final_run(session, site, WEEK1, WEEK2 + timedelta(days=6), {server.id: 999999},
               state=m.TIPS_RUN_STATE_CALCULATED)  # never a Payroll source

    both = _summary(session, site, WEEK1, WEEK2 + timedelta(days=6))
    srow, hrow = _row(both, server), _row(both, host)
    result.check("two adjacent FINAL runs are summed once", srow is not None and srow.tips_payable == Decimal("150.50"),
                 srow and srow.tips_payable)
    result.check("CALCULATED runs are ignored", both.tips_status == ps.TIPS_AVAILABLE
                 and {r.run_id for r in both.tip_runs_used} == {run1.id, run2.id})
    result.check("an employee with tips only is still a row", hrow is not None and hrow.worked_hours == Decimal("0.00")
                 and hrow.tips_payable == Decimal("25.00"))

    one_day_more = _summary(session, site, WEEK1, WEEK2)
    result.check("a range cutting a FINAL run is not available (never prorated)",
                 one_day_more.tips_status == ps.TIPS_NOT_AVAILABLE
                 and all(r.tips_payable is None for r in one_day_more.rows)
                 and run2.id in {r.run_id for r in one_day_more.tip_runs_not_used},
                 one_day_more.tips_unavailable_reason)
    result.check("hours stay available when tips are not",
                 (_row(one_day_more, server) or ps.EmployeeSummaryRow(0, None)).worked_hours == Decimal("6.00"))

    inside = _summary(session, site, WEEK1 + timedelta(days=1), WEEK1 + timedelta(days=6))
    result.check("a range inside one FINAL run is not available", inside.tips_status == ps.TIPS_NOT_AVAILABLE)


def _test_zero_is_distinct_from_not_available(session: Session, result: ValidationResult) -> None:
    site = _site(session)
    cook = _employee(session, site, "Giulia Neri")
    _shift(session, cook, _local(WEEK1, 9), 8)
    available = _summary(session, site, WEEK1, WEEK1 + timedelta(days=6))
    result.check("no FINAL run -> tips not available (None), not zero",
                 available.tips_status == ps.TIPS_NOT_AVAILABLE and _row(available, cook).tips_payable is None)
    _final_run(session, site, WEEK1, WEEK1 + timedelta(days=6), {})
    finalized = _summary(session, site, WEEK1, WEEK1 + timedelta(days=6))
    result.check("FINAL run without an entitlement for this person -> 0.00",
                 finalized.tips_status == ps.TIPS_AVAILABLE and _row(finalized, cook).tips_payable == Decimal("0.00")
                 and not _row(finalized, cook).has_tip_entitlement)


def _test_open_and_overlapping_shifts_are_reported(session: Session, result: ValidationResult) -> None:
    site = _site(session)
    emp = _employee(session, site, "Sara Gallo")
    _shift(session, emp, _local(WEEK1, 10), 6)                 # 10:00-16:00
    _shift(session, emp, _local(WEEK1, 14), 4)                 # 14:00-18:00, overlaps 2 h
    _shift(session, emp, _local(WEEK1 + timedelta(days=1), 10), None)  # open
    summary = _summary(session, site, WEEK1, WEEK1 + timedelta(days=6))
    row = _row(summary, emp)
    kinds = {i.kind for i in summary.issues}
    result.check("overlap counted once (10:00-18:00 = 8 h)", row is not None and row.worked_hours == Decimal("8.00"),
                 row and row.worked_hours)
    result.check("overlap and open shift are reported", {ps.ISSUE_OVERLAP, ps.ISSUE_OPEN} <= kinds, kinds)
    result.check("hours are not presented as definitive", not summary.hours_definitive and not row.hours_complete)


def _test_missing_workweek_or_location_configuration_is_stated(session: Session, result: ValidationResult) -> None:
    site = _site(session, workweek=False)
    emp = _employee(session, site, "Marco Blu")
    _shift(session, emp, _local(WEEK1, 9), 45)
    summary = _summary(session, site, WEEK1, WEEK1 + timedelta(days=6))
    result.check("no Workweek -> overtime unavailable, hours still shown",
                 not summary.overtime_available and summary.overtime_unavailable_reason
                 and _row(summary, emp).worked_hours == Decimal("45.00"))
    bare = _site(session, configured=False)
    blocked = _summary(session, bare, WEEK1, WEEK1)
    result.check("no timezone/cutoff -> blocked with a reason, no default", bool(blocked.blocked_reason) and not blocked.rows)


def _test_workweek_setting_is_effective_dated(session: Session, result: ValidationResult) -> None:
    site = _site(session)
    change = datetime(2026, 10, 1, tzinfo=UTC)
    ww.set_workweek_start(session, restaurant_id=site.restaurant.id, start_weekday=6, effective_from=change)
    before = ww.effective_workweek_definition(session, site.restaurant.id, change - timedelta(seconds=1))
    after = ww.effective_workweek_definition(session, site.restaurant.id, change)
    result.check("a new Workweek start closes the old one and keeps history",
                 before is not None and before.start_weekday == 0 and after is not None and after.start_weekday == 6
                 and len(ww.workweek_definitions_for(session, site.restaurant.id)) == 2)
    try:
        ww.set_workweek_start(session, restaurant_id=site.restaurant.id, start_weekday=2,
                              effective_from=datetime(2026, 9, 1, tzinfo=UTC))
        rewritten = True
    except ValueError:
        rewritten = False
    result.check("a change dated inside existing history is refused", not rewritten)
