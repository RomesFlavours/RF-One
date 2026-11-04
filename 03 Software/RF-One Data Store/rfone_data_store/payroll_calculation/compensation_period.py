"""Who is in a Compensation Preparation Run, and with how many hours.

Product Owner decision (Compensation from real hours): a person is in a
`CompensationPreparationRun` when they worked — when they have Clover Shifts
in the run's period at a Location belonging to the run's Legal Entity. An
`EmployeeCompensationTerm` is NEVER a condition for being in the run: it is
only the source of the hourly wage, and a missing wage is shown as MISSING,
never a reason to drop the person.

    Shift -> Location -> RestaurantLocation -> Restaurant.legal_entity_id

The run's period is read as an INCLUSIVE range of Business Dates
(`period_start`'s date to `period_end`'s date), turned into instants by each
Location's own timezone and operating-day cutoff, exactly like the Period
Summary. Hours are counted by the shared `worked_time` module: per Employee
and per Workweek, the first 40 hours are Regular Hours and the rest are
Overtime Hours; the 40 restart every Workweek; Total = Regular + Overtime.
RF-One counts overtime HOURS only — their monetary value stays with the
Payroll Provider (`COMPENSATION_AND_INCOME_COMPOSITION_001.md` §8), and its
absence is never reported as a problem with the hours.

Two statuses are kept apart, per person:

  * Hours: COMPLETE, or INCOMPLETE with the reason — the person's own
    open/invalid/overlapping Shifts, an overtime split that cannot be made
    (no Workweek, ...), or a Shift history starting too late at a Location
    they worked at. Every Location-wide note is also stated once for the
    run (`hours_warnings`).
  * Compensation data: COMPLETE, or INCOMPLETE with the reason (hourly wage
    missing, more than one rate, Tips not available, ...).

A period that has not ended yet makes the whole run PROVISIONAL (stated
once) without making anyone's hours incomplete; an acquired Shift history
that starts after the period begins DOES make the hours of everyone who
worked at that Location INCOMPLETE, because real hours may be missing.

SALARIED people are listed apart (`RunHours.salaried`), from their
Compensation Term, with or without Shifts: Regular/Overtime never apply to a
salary, and Shift hours are informational only.

A Restaurant with no `legal_entity_id`, or a Location linked to no
Restaurant, is never silently skipped: its Shifts in the period are counted
and reported as not attributable to any Legal Entity. Nothing here writes to
the database or guesses an association. Read-only; recomputed on every call.
READY FOR PAYMENT is deliberately not modeled yet."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..tips.distribution_engine import business_date_window_utc
from . import compensation as compensation_helpers
from . import incentives as incentives_service
from . import period_summary as period_summary_service
from . import worked_time as wt

UTC = timezone.utc

HOURS_COMPLETE = "HOURS_COMPLETE"
HOURS_INCOMPLETE = "HOURS_INCOMPLETE"
DATA_COMPLETE = "COMPENSATION_DATA_COMPLETE"
DATA_INCOMPLETE = "COMPENSATION_DATA_INCOMPLETE"

_THRESHOLD_SECONDS = float(wt.OVERTIME_WEEKLY_THRESHOLD_HOURS * wt.SECONDS_PER_HOUR)


# ---------------------------------------------------------------------------
# Result shapes
# ---------------------------------------------------------------------------


@dataclass
class UnattributedHours:
    """Shifts in the period that no Legal Entity can claim, and why."""
    location_id: int
    location_name: str | None
    restaurant_id: int | None
    restaurant_name: str | None
    reason: str
    shifts: int
    employees: int


@dataclass
class PersonRow:
    employee_id: int
    display_name: str | None
    worked_seconds: float = 0.0
    overtime_seconds: float | None = 0.0   # None: the overtime split is not available
    location_names: list[str] = field(default_factory=list)
    hours_issues: list[wt.ShiftIssue] = field(default_factory=list)
    hours_reasons: list[str] = field(default_factory=list)
    hourly_terms: list[m.EmployeeCompensationTerm] = field(default_factory=list)
    salaried_terms: list[m.EmployeeCompensationTerm] = field(default_factory=list)
    bonus: Decimal | None = None           # Recognized Incentive; None: nothing entered
    tips: Decimal | None = None            # None: not available
    data_reasons: list[str] = field(default_factory=list)

    @property
    def total_hours(self) -> Decimal:
        return wt.hours(self.worked_seconds)

    @property
    def overtime_hours(self) -> Decimal | None:
        return None if self.overtime_seconds is None else wt.hours(self.overtime_seconds)

    @property
    def regular_hours(self) -> Decimal | None:
        # Derived from the two rounded figures so Regular + Overtime == Total exactly.
        overtime = self.overtime_hours
        return None if overtime is None else self.total_hours - overtime

    @property
    def hourly_rates(self) -> list[Decimal]:
        return sorted({
            (Decimal(t.hourly_rate_minor) / 100).quantize(Decimal("0.01")) for t in self.hourly_terms
        })

    @property
    def hourly_wage(self) -> Decimal | None:
        """The wage when exactly one hourly rate applies; None otherwise."""
        rates = self.hourly_rates
        return rates[0] if len(rates) == 1 else None

    @property
    def hours_status(self) -> str:
        return HOURS_INCOMPLETE if self.hours_reasons else HOURS_COMPLETE

    @property
    def data_status(self) -> str:
        return DATA_INCOMPLETE if self.data_reasons else DATA_COMPLETE


@dataclass
class SalariedRow:
    """A person paid on a SALARIED Compensation Term for this Legal Entity
    and period. Listed whether or not they have Shifts: Regular/Overtime
    never apply to a salary, and any Shift hours are informational only."""
    employee_id: int
    display_name: str | None
    terms: list[m.EmployeeCompensationTerm] = field(default_factory=list)
    informational_hours: Decimal | None = None   # None: no Shift in the period


@dataclass
class RunHours:
    run_id: int
    legal_entity_id: int
    first_business_date: date
    last_business_date: date
    rows: list[PersonRow] = field(default_factory=list)
    salaried: list[SalariedRow] = field(default_factory=list)
    # The period has not ended yet: every figure is provisional, but the
    # hours acquired so far are complete as hours (never HOURS INCOMPLETE
    # for this reason alone).
    provisional: bool = False
    # Why some or all hours of this Legal Entity cannot be computed (no
    # Restaurant linked, unconfigured Location, ...).
    problems: list[str] = field(default_factory=list)
    hours_warnings: list[str] = field(default_factory=list)
    unattributed: list[UnattributedHours] = field(default_factory=list)
    tips_available: bool = False
    tips_unavailable_reason: str = ""
    location_names: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Compensation Terms — the source of the wage, never of inclusion
# ---------------------------------------------------------------------------


def _naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None) if value.tzinfo is not None else value


def effective_terms(
    session: Session, run: m.CompensationPreparationRun, *, compensation_basis: str,
    employee_ids: list[int] | None = None,
) -> list[m.EmployeeCompensationTerm]:
    """Every `EmployeeCompensationTerm` of the given basis for this run's
    Legal Entity that is effective at some point during the run's period."""
    query = select(m.EmployeeCompensationTerm).where(
        m.EmployeeCompensationTerm.legal_entity_id == run.legal_entity_id,
        m.EmployeeCompensationTerm.compensation_basis == compensation_basis,
    )
    if employee_ids is not None:
        query = query.where(m.EmployeeCompensationTerm.employee_id.in_(employee_ids))
    period_start, period_end = _naive(run.period_start), _naive(run.period_end)
    active = []
    for term in session.scalars(query).all():
        valid_from = _naive(term.valid_from)
        valid_to = _naive(term.valid_to) if term.valid_to is not None else period_end
        if valid_from < period_end and valid_to > period_start:
            active.append(term)
    return active


# ---------------------------------------------------------------------------
# The run's hours
# ---------------------------------------------------------------------------


def run_business_dates(run: m.CompensationPreparationRun) -> tuple[date, date]:
    return wt.aware_utc(run.period_start).date(), wt.aware_utc(run.period_end).date()


def _location_names(session: Session, ids: set[int]) -> dict[int, str | None]:
    if not ids:
        return {}
    return {loc.id: loc.name for loc in session.scalars(select(m.Location).where(m.Location.id.in_(ids))).all()}


def _unattributed(
    session: Session, *, location: m.Location, restaurant: m.Restaurant | None, reason: str,
    first: date, last: date,
) -> UnattributedHours | None:
    """Shifts of the period at a Location no Legal Entity can claim."""
    if location.timezone and location.operating_day_cutoff_time:
        start, end = business_date_window_utc(location, first, last)
    else:  # no Business Date configuration: a plain UTC day range, only to count
        start = datetime(first.year, first.month, first.day, tzinfo=UTC)
        end = datetime(last.year, last.month, last.day, tzinfo=UTC) + timedelta(days=1)
    shifts = wt.load_location_shifts(session, location_id=location.id, window_start=start, window_end=end)
    counted = wt.shifts_in_period(shifts, period_start=start, period_end=end)
    if not counted:
        return None
    return UnattributedHours(
        location_id=location.id, location_name=location.name,
        restaurant_id=restaurant.id if restaurant else None,
        restaurant_name=restaurant.name if restaurant else None,
        reason=reason, shifts=len(counted), employees=len({s.employee_id for s in counted}),
    )


@dataclass
class _LocationContext:
    location: m.Location
    restaurant_id: int
    period_start: datetime
    period_end: datetime
    windows: wt.WorkweekWindows
    coverage: wt.Coverage

    @property
    def key(self) -> tuple:
        weeks = tuple(self.windows.weeks) if self.windows.weeks is not None else None
        return (self.period_start, self.period_end, weeks)


def _merge(intervals: list[tuple[datetime, datetime]]) -> tuple[list[tuple[datetime, datetime]], bool]:
    """Union of intervals from several Locations; True when two overlapped."""
    merged: list[tuple[datetime, datetime]] = []
    overlapped = False
    for start, end in sorted(intervals):
        if merged and start < merged[-1][1]:
            overlapped = True
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged, overlapped


def build_run_hours(
    session: Session, run: m.CompensationPreparationRun, *, now: datetime | None = None,
) -> RunHours:
    """Never raises for a data condition: every gap is stated on the result."""
    first, last = run_business_dates(run)
    result = RunHours(run.id, run.legal_entity_id, first, last)
    now = wt.aware_utc(now) or datetime.now(UTC)

    # --- Which Locations belong to this Legal Entity -----------------------
    restaurants = list(session.scalars(
        select(m.Restaurant).where(m.Restaurant.legal_entity_id == run.legal_entity_id).order_by(m.Restaurant.name)
    ).all())
    links = list(session.scalars(
        select(m.RestaurantLocation).where(m.RestaurantLocation.restaurant_id.in_([r.id for r in restaurants]))
        .order_by(m.RestaurantLocation.id)
    ).all()) if restaurants else []
    if not restaurants:
        result.problems.append(
            "No Restaurant is linked to this Legal Entity (Restaurant.legal_entity_id), so no Shift can be "
            "attributed to it. Link the Restaurant to its Legal Entity; RF-One never guesses it."
        )
    for restaurant in restaurants:
        if not any(link.restaurant_id == restaurant.id for link in links):
            result.problems.append(f"Restaurant {restaurant.name!r} has no Location: no Shift can be read for it.")

    contexts: list[_LocationContext] = []
    seen_locations: set[int] = set()
    for link in links:
        if link.location_id in seen_locations:
            continue
        seen_locations.add(link.location_id)
        location = session.get(m.Location, link.location_id)
        result.location_names.append(location.name)
        missing = [n for n, v in (("timezone", location.timezone),
                                  ("operating-day cutoff", location.operating_day_cutoff_time)) if not v]
        if missing:
            result.problems.append(
                f"Location {location.name!r} has no {' and no '.join(missing)} configured: its Shifts cannot "
                "be turned into Business Dates and are not counted. No default is ever assumed."
            )
            continue
        period_start, period_end = business_date_window_utc(location, first, last)
        windows = wt.workweek_windows(
            session, restaurant_id=link.restaurant_id, location=location,
            first_business_date=first, last_business_date=last, period_start=period_start,
        )
        coverage = wt.coverage(
            session, location=location, window_start=windows.window_start,
            period_start=period_start, period_end=period_end, now=now,
        )
        # A period still open is stated once for the whole run (PROVISIONAL),
        # never as a per-Location or per-person hours problem.
        result.provisional = result.provisional or coverage.period_open
        result.hours_warnings.extend(
            f"{location.name}: {w}" for w in coverage.messages if not w.startswith("The period has not ended yet")
        )
        contexts.append(_LocationContext(location, link.restaurant_id, period_start, period_end, windows, coverage))

    # --- Hours that no Legal Entity can claim -------------------------------
    for restaurant in session.scalars(select(m.Restaurant).where(m.Restaurant.legal_entity_id.is_(None))).all():
        for link in session.scalars(
            select(m.RestaurantLocation).where(m.RestaurantLocation.restaurant_id == restaurant.id)
        ).all():
            found = _unattributed(
                session, location=session.get(m.Location, link.location_id), restaurant=restaurant,
                reason="Restaurant has no Legal Entity (Restaurant.legal_entity_id is empty)",
                first=first, last=last,
            )
            if found:
                result.unattributed.append(found)
    linked_locations = select(m.RestaurantLocation.location_id)
    for location in session.scalars(select(m.Location).where(m.Location.id.not_in(linked_locations))).all():
        found = _unattributed(
            session, location=location, restaurant=None, reason="Location is linked to no Restaurant",
            first=first, last=last,
        )
        if found:
            result.unattributed.append(found)

    # --- Per Employee, per Location ----------------------------------------
    per_employee: dict[int, list[tuple[_LocationContext, list, list]]] = {}
    for ctx in contexts:
        by_employee: dict[int, list[m.Shift]] = {}
        for shift in wt.load_location_shifts(
            session, location_id=ctx.location.id, window_start=ctx.windows.window_start, window_end=ctx.period_end,
        ):
            by_employee.setdefault(shift.employee_id, []).append(shift)
        for employee_id, shifts in by_employee.items():
            intervals, issues = wt.employee_intervals(
                shifts, window_start=ctx.windows.window_start, window_end=ctx.period_end,
            )
            per_employee.setdefault(employee_id, []).append((ctx, intervals, issues))

    rows: dict[int, PersonRow] = {}
    for employee_id, parts in per_employee.items():
        issues = [i for _, _, part_issues in parts for i in part_issues]
        worked_parts = []
        for ctx, intervals, _ in parts:
            worked, _ = wt.count_hours(
                intervals, period_start=ctx.period_start, period_end=ctx.period_end,
                weeks=None, threshold_seconds=_THRESHOLD_SECONDS,
            )
            worked_parts.append((ctx, intervals, worked))
        active = [p for p in worked_parts if p[2] > 0]
        if not active and not issues:
            continue  # only a week-context Shift before the period: not in the run

        row = PersonRow(employee_id=employee_id, display_name=None, hours_issues=issues)
        row.hours_reasons.extend(i.detail for i in issues)
        involved = active or worked_parts[:1]
        row.location_names = sorted({ctx.location.name for ctx, _, _ in involved})

        if len({ctx.key for ctx, _, _ in involved}) == 1:
            ctx = involved[0][0]
            intervals, overlapped = _merge([iv for _, part, _ in involved for iv in part])
            if overlapped:
                row.hours_reasons.append(
                    "Shifts at two Locations overlap in time: the overlapping time is counted once."
                )
            worked, overtime = wt.count_hours(
                intervals, period_start=ctx.period_start, period_end=ctx.period_end,
                weeks=ctx.windows.weeks, threshold_seconds=_THRESHOLD_SECONDS,
            )
            row.worked_seconds = worked
            if ctx.windows.weeks is None:
                row.overtime_seconds = None
                row.hours_reasons.append(f"Overtime hours not available: {ctx.windows.unavailable_reason}")
            else:
                row.overtime_seconds = overtime
        else:
            row.worked_seconds = sum(worked for _, _, worked in involved)
            row.overtime_seconds = None
            row.hours_reasons.append(
                "Overtime hours not available: this person worked at Locations of this Legal Entity with "
                "different Business Date or Workweek settings, so one Workweek cannot be applied."
            )
        # The acquired Shift history starts too late at a Location this person
        # worked at: real hours of theirs may be missing.
        for ctx, _, _ in involved:
            if ctx.coverage.history_starts_after_period:
                row.hours_reasons.append(
                    f"Shift history starts after the beginning of the period ({ctx.location.name})."
                )
            elif ctx.coverage.history_starts_late:
                row.hours_reasons.append(
                    f"Shift history starts after the beginning of the period's first Workweek "
                    f"({ctx.location.name}): overtime hours may be understated."
                )
        rows[employee_id] = row

    # --- Names --------------------------------------------------------------
    if rows:
        for employee in session.scalars(select(m.Employee).where(m.Employee.id.in_(list(rows)))).all():
            rows[employee.id].display_name = employee.display_name

    # --- Compensation data: wage, bonus, tips --------------------------------
    employee_ids = list(rows)
    if employee_ids:
        for term in effective_terms(session, run, compensation_basis=compensation_helpers.HOURLY,
                                    employee_ids=employee_ids):
            rows[term.employee_id].hourly_terms.append(term)
    # SALARIED: listed from the Compensation Term, with or without Shifts,
    # separately from the hourly logic. A person holding only SALARIED terms
    # is not an hourly row; Shift hours, if any, are informational.
    salaried: dict[int, SalariedRow] = {}
    for term in effective_terms(session, run, compensation_basis=compensation_helpers.SALARIED):
        entry = salaried.setdefault(term.employee_id, SalariedRow(term.employee_id, None))
        entry.terms.append(term)
        if term.employee_id in rows:
            rows[term.employee_id].salaried_terms.append(term)
            entry.informational_hours = rows[term.employee_id].total_hours
    for employee_id, entry in salaried.items():
        if employee_id in rows and not rows[employee_id].hourly_terms:
            entry.display_name = rows.pop(employee_id).display_name
    missing_names = [e for e in salaried if salaried[e].display_name is None]
    if missing_names:
        for employee in session.scalars(select(m.Employee).where(m.Employee.id.in_(missing_names))).all():
            salaried[employee.id].display_name = employee.display_name
    result.salaried = sorted(salaried.values(), key=lambda r: (r.display_name or "", r.employee_id))
    for row in rows.values():
        contributions = incentives_service.list_incentive_contributions(
            session, calculation_run_id=run.id, employee_id=row.employee_id,
        )
        if contributions:
            row.bonus = incentives_service.calculate_recognized_incentive(contributions)

    _resolve_tips(session, result, contexts, rows)

    for row in rows.values():
        if not row.hourly_terms:
            row.data_reasons.append(
                "Hourly wage missing: no HOURLY Compensation Term for this Legal Entity in this period."
            )
        elif len(row.hourly_rates) > 1:
            row.data_reasons.append(
                "More than one hourly rate applies, and Clover Shifts do not say which hours belong to "
                "which function."
            )
        if not result.tips_available:
            row.data_reasons.append(f"Tips not available: {result.tips_unavailable_reason}")

    result.rows = sorted(
        rows.values(),
        key=lambda r: ((r.display_name or "").split()[1:] or [""], r.display_name or "", r.employee_id),
    )
    return result


def _resolve_tips(
    session: Session, result: RunHours, contexts: list[_LocationContext], rows: dict[int, PersonRow],
) -> None:
    """FINAL Tips per Restaurant of this Legal Entity, through the Period
    Summary's own rule (whole FINAL runs covering every date exactly once;
    otherwise not available — never zero, never prorated)."""
    if not contexts:
        result.tips_unavailable_reason = "no configured Location of this Legal Entity to read them for."
        return
    payable: dict[int, int] = {}
    seen_restaurants: set[int] = set()
    for ctx in contexts:
        if ctx.restaurant_id in seen_restaurants:
            continue
        seen_restaurants.add(ctx.restaurant_id)
        stub = period_summary_service.PeriodSummary(
            location_id=ctx.location.id, location_name=ctx.location.name, restaurant_id=ctx.restaurant_id,
            first_business_date=result.first_business_date, last_business_date=result.last_business_date,
        )
        amounts = period_summary_service.resolve_finalized_tips(session, stub, ctx.location)
        result.hours_warnings.extend(f"{ctx.location.name}: {w}" for w in stub.hours_warnings)
        if stub.tips_status != period_summary_service.TIPS_AVAILABLE:
            result.tips_unavailable_reason = f"{ctx.location.name}: {stub.tips_unavailable_reason}"
            return
        for employee_id, amount in amounts.items():
            payable[employee_id] = payable.get(employee_id, 0) + amount
    result.tips_available = True
    for row in rows.values():
        row.tips = (Decimal(payable.get(row.employee_id, 0)) / 100).quantize(Decimal("0.01"))
