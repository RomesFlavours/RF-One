"""Compensation Period Summary (COMPENSATION_PERIOD_SUMMARY_001).

One read-only row per Employee for one Location and one INCLUSIVE range of
Business Dates, built to be compared with a person's own manual figures:

    worked hours | hours above 40 in each Workweek | Tips + Gratuity | Bonus

Nothing here writes to the database, needs a Compensation Term, or computes
money from hours. It only CONSUMES what already exists:

  * Hours come from the Clover Shifts already acquired (`Shift`). The
    official times of a Shift are its manager override when present, else
    the raw clock-in/out — the empirically confirmed Clover rule already
    documented in `Clover Data Explorer/clover_explorer/export_clock.py`.
    Clover has no break record: a break is the gap between two Shifts, so
    no break is deducted from inside a Shift. A Shift counts at a Location
    when it carries that Location, or carries none and its Employee's home
    Location is that one (`Shift.location_id` docstring). Shifts are never
    modified: a Shift crossing a boundary is split in memory only.
  * Business Dates, the timezone and the operating-day cutoff are the
    Location's own configuration, turned into instants by the one existing
    window definition (`tips.distribution_engine.business_date_window_utc`,
    a pure function — nothing in Tips is called that calculates). No
    default timezone or cutoff is ever substituted.
  * The Workweek is the Restaurant's `WorkweekDefinition` (`workweek.py`).
    A week is 7 Business Dates starting on its configured weekday, so it
    begins at the cutoff, like every Business Date.
  * Tips + Gratuity are each Employee's `TipEntitlement.payable_amount_minor`
    (gross - given out + received: what they are entitled to AFTER
    distribution, never what the Server collected) from FINAL Tips runs
    only (`Finalized Tips Period.md` §7). Runs are summed only when they
    lie wholly inside the requested range and cover every date exactly
    once. Anything else is "not available" — never zero, never prorated.

Hours above the threshold (Product Owner rule for this summary): inside each
Workweek, hours past the 40th, in chronological order, are overtime hours.
Weeks are never netted against each other. When the requested range starts
mid-week, earlier hours of that week still count towards the 40, but only
hours inside the range are shown. Worked hours INCLUDE overtime hours. This
is an hours count only; the statutory/monetary overtime treatment stays
with the Payroll Provider (`OVERTIME_RULE_MATRIX_001.md`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from ..tips.distribution_engine import business_date_window_utc
from . import worked_time as wt
# Hours are counted by the shared `worked_time` module (also used by the
# Compensation Run, `compensation_period.py`); these names stay importable
# from here unchanged.
from .worked_time import (  # noqa: F401
    ISSUE_INVALID,
    ISSUE_NO_CLOCK_IN,
    ISSUE_OPEN,
    ISSUE_OVERLAP,
    OVERTIME_WEEKLY_THRESHOLD_HOURS,
    ShiftIssue,
)

UTC = timezone.utc

TIPS_AVAILABLE = "AVAILABLE"
TIPS_NOT_AVAILABLE = "NOT_AVAILABLE"

_SECONDS_PER_HOUR = wt.SECONDS_PER_HOUR
_aware_utc = wt.aware_utc
_hours = wt.hours


# ---------------------------------------------------------------------------
# Result shapes
# ---------------------------------------------------------------------------


@dataclass
class TipRunReference:
    run_id: int
    first_business_date: date | None
    last_business_date: date | None
    finalized_at: datetime | None


@dataclass
class EmployeeSummaryRow:
    employee_id: int
    display_name: str | None
    worked_seconds: float = 0.0
    overtime_seconds: float = 0.0
    tips_payable_minor: int | None = None
    has_tip_entitlement: bool = False
    issues: list[ShiftIssue] = field(default_factory=list)
    # Shifts counted in the period that carry no Location of their own and
    # were attributed through the Employee's home Location (existing rule,
    # `Shift.location_id` docstring) — shown, never hidden.
    home_location_fallback_shifts: int = 0

    @property
    def worked_hours(self) -> Decimal:
        return _hours(self.worked_seconds)

    @property
    def overtime_hours(self) -> Decimal:
        return _hours(self.overtime_seconds)

    @property
    def tips_payable(self) -> Decimal | None:
        if self.tips_payable_minor is None:
            return None
        return (Decimal(self.tips_payable_minor) / 100).quantize(Decimal("0.01"))

    @property
    def hours_complete(self) -> bool:
        return not self.issues


@dataclass
class PeriodSummary:
    location_id: int
    location_name: str | None
    restaurant_id: int | None
    first_business_date: date
    last_business_date: date
    timezone_name: str | None = None
    operating_day_cutoff: time | None = None
    period_start_utc: datetime | None = None
    period_end_utc: datetime | None = None
    workweek_start_weekday: int | None = None
    workweek_definition_id: int | None = None
    workweek_valid_from: datetime | None = None
    overtime_threshold_hours: Decimal = OVERTIME_WEEKLY_THRESHOLD_HOURS
    # Why nothing at all could be computed (unconfigured Location, ...).
    blocked_reason: str = ""
    # Why the overtime column is unavailable (no Workweek configured, ...).
    overtime_unavailable_reason: str = ""
    tips_status: str = TIPS_NOT_AVAILABLE
    tips_unavailable_reason: str = ""
    tip_runs_used: list[TipRunReference] = field(default_factory=list)
    tip_runs_not_used: list[TipRunReference] = field(default_factory=list)
    rows: list[EmployeeSummaryRow] = field(default_factory=list)
    issues: list[ShiftIssue] = field(default_factory=list)
    # Coverage notes about the Shift data itself (history start, period not over, ...).
    hours_warnings: list[str] = field(default_factory=list)
    shifts_counted: int = 0

    @property
    def home_location_fallback_shifts(self) -> int:
        return sum(r.home_location_fallback_shifts for r in self.rows)

    @property
    def overtime_available(self) -> bool:
        return not self.blocked_reason and not self.overtime_unavailable_reason

    @property
    def hours_definitive(self) -> bool:
        return not self.blocked_reason and not self.issues and not self.hours_warnings

    @property
    def total_worked_hours(self) -> Decimal:
        return _hours(sum(r.worked_seconds for r in self.rows))

    @property
    def total_overtime_hours(self) -> Decimal:
        return _hours(sum(r.overtime_seconds for r in self.rows))

    @property
    def total_tips_payable(self) -> Decimal | None:
        if self.tips_status != TIPS_AVAILABLE:
            return None
        return (Decimal(sum(r.tips_payable_minor or 0 for r in self.rows)) / 100).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Context resolution
# ---------------------------------------------------------------------------


def restaurant_for_location(session: Session, location_id: int) -> int | None:
    return session.scalars(
        select(m.RestaurantLocation.restaurant_id)
        .where(m.RestaurantLocation.location_id == location_id)
        .order_by(m.RestaurantLocation.id)
    ).first()


def summary_locations(session: Session) -> list[m.Location]:
    """Locations a summary can be asked for: linked to a Restaurant."""
    linked = select(m.RestaurantLocation.location_id)
    return list(session.scalars(
        select(m.Location).where(m.Location.id.in_(linked)).order_by(m.Location.name)
    ).all())


# ---------------------------------------------------------------------------
# Tips
# ---------------------------------------------------------------------------


def _run_reference(run: m.TipDistributionCalculationRun) -> TipRunReference:
    return TipRunReference(run.id, run.first_business_date, run.last_business_date, run.finalized_at)


def _resolve_finalized_tips(
    session: Session, summary: PeriodSummary, location: m.Location,
) -> dict[int, int]:
    """Per-Employee payable minor units from FINAL runs exactly covering the
    range, or {} with `summary.tips_unavailable_reason` set."""
    first, last = summary.first_business_date, summary.last_business_date
    restaurant_id = summary.restaurant_id

    location_count = session.scalar(
        select(func.count()).select_from(m.RestaurantLocation)
        .where(m.RestaurantLocation.restaurant_id == restaurant_id)
    )
    if location_count and location_count > 1:
        summary.tips_unavailable_reason = (
            "Tips are finalized per Restaurant, and this Restaurant has more than one "
            "Location: its Tips cannot be attributed to this Location alone."
        )
        return {}

    runs = list(session.scalars(
        select(m.TipDistributionCalculationRun).where(
            m.TipDistributionCalculationRun.restaurant_id == restaurant_id,
            m.TipDistributionCalculationRun.state == m.TIPS_RUN_STATE_FINAL,
            m.TipDistributionCalculationRun.first_business_date <= last,
            m.TipDistributionCalculationRun.last_business_date >= first,
        ).order_by(m.TipDistributionCalculationRun.first_business_date, m.TipDistributionCalculationRun.id)
    ).all())
    inside = [r for r in runs if r.first_business_date >= first and r.last_business_date <= last]
    straddling = [r for r in runs if r not in inside]
    summary.tip_runs_not_used = [_run_reference(r) for r in straddling]

    coverage: dict[date, list[int]] = {}
    day = first
    while day <= last:
        coverage[day] = []
        day += timedelta(days=1)
    for run in inside:
        day = run.first_business_date
        while day <= run.last_business_date:
            coverage[day].append(run.id)
            day += timedelta(days=1)

    missing = [d for d, ids in coverage.items() if not ids]
    duplicated = {d: ids for d, ids in coverage.items() if len(ids) > 1}
    if duplicated:
        d, ids = next(iter(duplicated.items()))
        summary.tips_unavailable_reason = (
            f"Business Date {d} is covered by more than one FINAL Tips run ({', '.join(map(str, ids))}). "
            "Which one is payable is an open decision, so no Tips figure is shown."
        )
        return {}
    if missing:
        text = (
            f"No FINAL Tips run covers {len(missing)} of the requested Business Dates "
            f"(first missing: {missing[0]})."
        )
        if straddling:
            text += (
                " FINAL run(s) " + ", ".join(f"#{r.id} ({r.first_business_date} to {r.last_business_date})"
                                             for r in straddling)
                + " also cover dates outside this period and are never split."
            )
        summary.tips_unavailable_reason = text
        return {}

    summary.tips_status = TIPS_AVAILABLE
    summary.tip_runs_used = [_run_reference(r) for r in inside]
    for run in inside:
        if (run.timezone_name and run.timezone_name != location.timezone) or (
            run.operating_day_cutoff_time and run.operating_day_cutoff_time != location.operating_day_cutoff_time
        ):
            summary.hours_warnings.append(
                f"FINAL Tips run #{run.id} was computed with timezone {run.timezone_name} and cutoff "
                f"{run.operating_day_cutoff_time}, which differ from the Location's current settings "
                "used for hours."
            )

    payable: dict[int, int] = {}
    for entitlement in session.scalars(
        select(m.TipEntitlement).where(m.TipEntitlement.calculation_run_id.in_([r.id for r in inside]))
    ).all():
        payable[entitlement.employee_id] = payable.get(entitlement.employee_id, 0) + entitlement.payable_amount_minor
    return payable


# Also used by the Compensation Run (`compensation_period.py`), so FINAL Tips
# are read by one rule only.
resolve_finalized_tips = _resolve_finalized_tips


# ---------------------------------------------------------------------------
# The summary
# ---------------------------------------------------------------------------


def build_period_summary(
    session: Session, *, location_id: int, first_business_date: date, last_business_date: date,
    now: datetime | None = None,
) -> PeriodSummary:
    """Build the read-only summary. Never raises for a data condition: every
    gap is stated on the returned object instead."""
    if last_business_date < first_business_date:
        raise ValueError("The last Business Date cannot be before the first.")

    location = session.get(m.Location, location_id)
    if location is None:
        raise ValueError(f"Location {location_id} does not exist.")
    summary = PeriodSummary(
        location_id=location.id, location_name=location.name,
        restaurant_id=restaurant_for_location(session, location.id),
        first_business_date=first_business_date, last_business_date=last_business_date,
        timezone_name=location.timezone, operating_day_cutoff=location.operating_day_cutoff_time,
    )

    missing = [n for n, v in (("timezone", location.timezone),
                              ("operating-day cutoff", location.operating_day_cutoff_time)) if not v]
    if missing:
        summary.blocked_reason = (
            f"Location {location.name!r} has no {' and no '.join(missing)} configured. Business Dates "
            "cannot be turned into hours without it, and no default is ever assumed."
        )
        return summary
    if summary.restaurant_id is None:
        summary.blocked_reason = f"Location {location.name!r} is not linked to a Restaurant."
        return summary

    period_start, period_end = business_date_window_utc(location, first_business_date, last_business_date)
    summary.period_start_utc, summary.period_end_utc = period_start, period_end

    # --- Workweek ----------------------------------------------------------
    windows = wt.workweek_windows(
        session, restaurant_id=summary.restaurant_id, location=location,
        first_business_date=first_business_date, last_business_date=last_business_date,
        period_start=period_start,
    )
    weeks = windows.weeks
    window_start, window_end = windows.window_start, period_end
    summary.overtime_unavailable_reason = windows.unavailable_reason
    if windows.definition is not None:
        summary.workweek_start_weekday = windows.definition.start_weekday
        summary.workweek_definition_id = windows.definition.id
        summary.workweek_valid_from = _aware_utc(windows.definition.valid_from)

    # --- Hours -------------------------------------------------------------
    now = _aware_utc(now) or datetime.now(UTC)
    summary.hours_warnings.extend(wt.coverage_warnings(
        session, location=location, window_start=window_start,
        period_start=period_start, period_end=period_end, now=now,
    ))

    by_employee: dict[int, list[m.Shift]] = {}
    for shift in wt.load_location_shifts(session, location_id=location.id, window_start=window_start, window_end=window_end):
        by_employee.setdefault(shift.employee_id, []).append(shift)

    rows: dict[int, EmployeeSummaryRow] = {}
    threshold_seconds = float(OVERTIME_WEEKLY_THRESHOLD_HOURS * _SECONDS_PER_HOUR)
    for employee_id, shifts in by_employee.items():
        intervals, issues = wt.employee_intervals(shifts, window_start=window_start, window_end=window_end)
        in_period = wt.shifts_in_period(shifts, period_start=period_start, period_end=period_end)
        worked, overtime = wt.count_hours(
            intervals, period_start=period_start, period_end=period_end,
            weeks=weeks, threshold_seconds=threshold_seconds,
        )
        if worked == 0 and not issues:
            continue  # only a week-context Shift before the period: not a row
        row = EmployeeSummaryRow(employee_id=employee_id, display_name=None,
                                 worked_seconds=worked, overtime_seconds=overtime, issues=issues,
                                 home_location_fallback_shifts=sum(1 for sh in in_period if sh.location_id is None))
        summary.shifts_counted += len(in_period)
        rows[employee_id] = row
        summary.issues.extend(issues)

    # --- Tips --------------------------------------------------------------
    payable = _resolve_finalized_tips(session, summary, location)
    for employee_id, amount in payable.items():
        row = rows.setdefault(employee_id, EmployeeSummaryRow(employee_id=employee_id, display_name=None))
        row.tips_payable_minor = amount
        row.has_tip_entitlement = True
    if summary.tips_status == TIPS_AVAILABLE:
        for row in rows.values():
            if row.tips_payable_minor is None:
                row.tips_payable_minor = 0  # finalized, and nothing was assigned to this person

    # --- Names (display only; rows are keyed by Employee id) -----------------
    if rows:
        for employee in session.scalars(select(m.Employee).where(m.Employee.id.in_(list(rows)))).all():
            rows[employee.id].display_name = employee.display_name
    summary.rows = sorted(rows.values(), key=lambda r: ((r.display_name or "").split()[1:] or [""], r.display_name or "", r.employee_id))
    return summary
