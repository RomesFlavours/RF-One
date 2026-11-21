"""Worked time from Clover Shifts — the one shared definition of "how many
hours did this person work, and how many of them were past 40 in a
Workweek".

Extracted unchanged from the Compensation Period Summary
(`period_summary.py`, COMPENSATION_PERIOD_SUMMARY_001) so the Period Summary
and the Compensation Run (`compensation_period.py`) count hours with the
same code, never with two copies that can drift apart:

  * The official times of a Shift are its manager override when present,
    else the raw clock-in/out (the empirically confirmed Clover rule,
    `Clover Data Explorer/clover_explorer/export_clock.py`). Clover has no
    break record: no break is deducted from inside a Shift.
  * A Shift counts at a Location when it carries that Location, or carries
    none and its Employee's home Location is that one (`Shift.location_id`
    docstring). Shifts are never modified: a Shift crossing a boundary is
    split in memory only.
  * Open, invalid and overlapping Shifts are reported as `ShiftIssue`s,
    never silently counted or dropped; overlapping time is counted once.
  * A Workweek is 7 Business Dates starting on the Restaurant's configured
    weekday (`workweek.py`), so it begins at the operating-day cutoff, like
    every Business Date. Inside each Workweek, hours past the threshold, in
    chronological order, are overtime hours; weeks are never netted.

This is an HOURS count only. The monetary/statutory overtime treatment
stays with the Payroll Provider (`OVERTIME_RULE_MATRIX_001.md`,
`COMPENSATION_AND_INCOME_COMPOSITION_001.md` §8)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from ..tips.distribution_engine import business_date_window_utc
from . import workweek as workweek_service

UTC = timezone.utc

# The Product Owner's rule: hours past 40 in one Workweek are overtime hours.
OVERTIME_WEEKLY_THRESHOLD_HOURS = Decimal("40")

ISSUE_OPEN = "OPEN"
ISSUE_INVALID = "INVALID"
ISSUE_OVERLAP = "OVERLAP"
ISSUE_NO_CLOCK_IN = "NO_CLOCK_IN"

_HOURS = Decimal("0.01")
SECONDS_PER_HOUR = Decimal(3600)


def aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def hours(seconds: float | int | Decimal) -> Decimal:
    return (Decimal(str(seconds)) / SECONDS_PER_HOUR).quantize(_HOURS, rounding=ROUND_HALF_UP)


def overlap_seconds(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> float:
    start, end = max(a_start, b_start), min(a_end, b_end)
    return max(0.0, (end - start).total_seconds())


@dataclass
class ShiftIssue:
    employee_id: int
    shift_id: int
    kind: str
    detail: str
    started_at: datetime | None = None


def week_first_date(business_date: date, start_weekday: int) -> date:
    return business_date - timedelta(days=(business_date.weekday() - start_weekday) % 7)


# ---------------------------------------------------------------------------
# Shifts
# ---------------------------------------------------------------------------


def official_interval(shift: m.Shift) -> tuple[datetime | None, datetime | None]:
    """Manager override when present, else the raw clock event."""
    start = aware_utc(shift.override_in_time or shift.clock_in)
    end = aware_utc(shift.override_out_time or shift.clock_out)
    return start, end


def load_location_shifts(
    session: Session, *, location_id: int, window_start: datetime, window_end: datetime,
) -> list[m.Shift]:
    """Shifts that may touch [window_start, window_end) at this Location.

    The SQL filter is deliberately wide (a day of margin on the raw
    clock-in, open Shifts included); the exact test on the official
    interval happens in Python."""
    margin = timedelta(days=1)
    return list(session.scalars(
        select(m.Shift)
        .join(m.Employee, m.Employee.id == m.Shift.employee_id)
        .where(
            (m.Shift.location_id == location_id)
            | (m.Shift.location_id.is_(None) & (m.Employee.location_id == location_id)),
            func.coalesce(m.Shift.override_in_time, m.Shift.clock_in) < window_end + margin,
            (func.coalesce(m.Shift.override_out_time, m.Shift.clock_out).is_(None)
             & (func.coalesce(m.Shift.override_in_time, m.Shift.clock_in) >= window_start - margin))
            | (func.coalesce(m.Shift.override_out_time, m.Shift.clock_out) > window_start - margin),
        )
        .order_by(m.Shift.employee_id, m.Shift.id)
    ).all())


def shift_history_bounds(session: Session, location_id: int) -> tuple[datetime | None, datetime | None]:
    first, last = session.execute(
        select(func.min(m.Shift.clock_in), func.max(m.Shift.clock_in))
        .join(m.Employee, m.Employee.id == m.Shift.employee_id)
        .where(
            (m.Shift.location_id == location_id)
            | (m.Shift.location_id.is_(None) & (m.Employee.location_id == location_id)),
        )
    ).one()
    return aware_utc(first), aware_utc(last)


def shifts_in_period(
    shifts: list[m.Shift], *, period_start: datetime, period_end: datetime,
) -> list[m.Shift]:
    """The valid, closed Shifts whose official interval touches the period."""
    return [
        shift for shift in shifts
        if (bounds := official_interval(shift))[0] is not None and bounds[1] is not None
        and bounds[1] > bounds[0] and bounds[0] < period_end and bounds[1] > period_start
    ]


# ---------------------------------------------------------------------------
# Hours
# ---------------------------------------------------------------------------


def employee_intervals(
    shifts: list[m.Shift], *, window_start: datetime, window_end: datetime,
) -> tuple[list[tuple[datetime, datetime]], list[ShiftIssue]]:
    """Countable official intervals for ONE Employee inside the window, plus
    what could not be counted. Overlapping Shifts are merged (never counted
    twice) and reported."""
    intervals: list[tuple[datetime, datetime, int]] = []
    issues: list[ShiftIssue] = []
    for shift in shifts:
        start, end = official_interval(shift)
        if start is None:
            issues.append(ShiftIssue(shift.employee_id, shift.id, ISSUE_NO_CLOCK_IN, "Shift has no clock-in time."))
            continue
        if end is None:
            # Open since shortly before the window or inside it: it may hold
            # hours of this window that nobody can count yet.
            if window_start - timedelta(days=1) <= start < window_end:
                issues.append(ShiftIssue(
                    shift.employee_id, shift.id, ISSUE_OPEN,
                    "Shift is still open (no clock-out): its hours are not counted.", start,
                ))
            continue
        if end <= start:
            if start < window_end and end > window_start:
                issues.append(ShiftIssue(
                    shift.employee_id, shift.id, ISSUE_INVALID,
                    "Clock-out is not after clock-in: the Shift is not counted.", start,
                ))
            continue
        if end <= window_start or start >= window_end:
            continue
        intervals.append((start, end, shift.id))

    intervals.sort()
    merged: list[tuple[datetime, datetime]] = []
    for start, end, shift_id in intervals:
        if merged and start < merged[-1][1]:
            issues.append(ShiftIssue(
                shifts[0].employee_id, shift_id, ISSUE_OVERLAP,
                "Shift overlaps the previous Shift: the overlapping time is counted once.", start,
            ))
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    clipped = [(max(s, window_start), min(e, window_end)) for s, e in merged]
    return [(s, e) for s, e in clipped if e > s], issues


def count_hours(
    intervals: list[tuple[datetime, datetime]], *,
    period_start: datetime, period_end: datetime,
    weeks: list[tuple[datetime, datetime]] | None, threshold_seconds: float,
) -> tuple[float, float]:
    """(worked seconds inside the period, overtime seconds inside the period).

    For each Workweek, hours are accumulated chronologically from the
    week's start; the part of each interval past the threshold is overtime.
    Only the part of both that falls inside the period is returned."""
    worked = sum(overlap_seconds(s, e, period_start, period_end) for s, e in intervals)
    if weeks is None:
        return worked, 0.0
    overtime = 0.0
    for week_start, week_end in weeks:
        cumulative = 0.0
        for start, end in intervals:
            piece_start, piece_end = max(start, week_start), min(end, week_end)
            if piece_end <= piece_start:
                continue
            duration = (piece_end - piece_start).total_seconds()
            regular = max(0.0, min(duration, threshold_seconds - cumulative))
            overtime_start = piece_start + timedelta(seconds=regular)
            overtime += overlap_seconds(overtime_start, piece_end, period_start, period_end)
            cumulative += duration
    return worked, overtime


# ---------------------------------------------------------------------------
# Workweeks and coverage of the acquired Shift history
# ---------------------------------------------------------------------------


@dataclass
class WorkweekWindows:
    """The Workweek windows covering a Business Date range at one Location.

    `weeks is None` means overtime cannot be split, and `unavailable_reason`
    says why; worked hours are still countable. `window_start` is where
    Shifts must be read from: the start of the first Workweek when the range
    starts mid-week (earlier hours of that week count towards the 40)."""
    weeks: list[tuple[datetime, datetime]] | None
    window_start: datetime
    unavailable_reason: str = ""
    definition: m.WorkweekDefinition | None = None


def workweek_windows(
    session: Session, *, restaurant_id: int, location: m.Location,
    first_business_date: date, last_business_date: date, period_start: datetime,
) -> WorkweekWindows:
    definition = workweek_service.effective_workweek_definition(session, restaurant_id, period_start)
    if definition is None:
        return WorkweekWindows(
            None, period_start, "No Workweek start is configured for this Restaurant (Settings > Workweek).",
        )
    week_first = week_first_date(first_business_date, definition.start_weekday)
    weeks = []
    while week_first <= last_business_date:
        weeks.append(business_date_window_utc(location, week_first, week_first + timedelta(days=6)))
        week_first += timedelta(days=7)
    other = workweek_service.effective_workweek_definition(session, restaurant_id, weeks[-1][1] - timedelta(seconds=1))
    if other is None or other.id != definition.id:
        return WorkweekWindows(
            None, period_start,
            "The Workweek start changes inside this period; choose a period on one side of the change.",
            definition,
        )
    return WorkweekWindows(weeks, weeks[0][0], "", definition)


@dataclass
class Coverage:
    """What the acquired Shift history can and cannot vouch for in a window.

    The conditions are kept apart because they mean different things:
    `history_starts_late` means real hours may be missing; `period_open`
    only means more hours may still come. `messages` is the human wording,
    in a stable order."""
    no_history: bool = False
    history_starts_late: bool = False
    # True when the history starts after the period itself, not merely
    # after the start of its first (partial) Workweek.
    history_starts_after_period: bool = False
    period_open: bool = False
    latest_shift_stale: bool = False
    messages: list[str] = field(default_factory=list)


def coverage(
    session: Session, *, location: m.Location, window_start: datetime,
    period_start: datetime, period_end: datetime, now: datetime,
) -> Coverage:
    result = Coverage()
    history_first, history_last = shift_history_bounds(session, location.id)
    if history_first is None:
        result.no_history = True
        result.messages.append("No Clover Shift has been acquired for this Location.")
        return result
    if window_start < history_first:
        result.history_starts_late = True
        result.history_starts_after_period = period_start < history_first
        which = "the start of the first Workweek" if window_start < period_start else "the start of the period"
        result.messages.append(
            f"Acquired Shifts start at {history_first.isoformat()} (UTC), after {which}: "
            "earlier hours are unknown, so totals may be understated."
        )
    if period_end > now:
        result.period_open = True
        result.messages.append("The period has not ended yet: hours are still accruing.")
    elif history_last is not None and history_last < period_end - timedelta(days=1):
        result.latest_shift_stale = True
        result.messages.append(
            f"The latest acquired Shift starts at {history_last.isoformat()} (UTC), more than a day "
            "before the period ends: later Shifts may not have been acquired yet."
        )
    return result


def coverage_warnings(
    session: Session, *, location: m.Location, window_start: datetime,
    period_start: datetime, period_end: datetime, now: datetime,
) -> list[str]:
    """What the acquired Shift history cannot vouch for in this window:
    nothing acquired, history starting late, period not over, or Shifts
    possibly not acquired yet."""
    return coverage(
        session, location=location, window_start=window_start,
        period_start=period_start, period_end=period_end, now=now,
    ).messages
