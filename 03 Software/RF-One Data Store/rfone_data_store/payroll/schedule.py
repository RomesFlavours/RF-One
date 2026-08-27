"""Payroll Schedule / Payroll Period / Workweek helpers (TASK_PAYROLL_001).

`PayrollSchedule`, `PayrollPeriod` and `Workweek` are structurally independent
concepts — see `01 Domains/Administration/Payroll/Payroll Schedule and
Period.md`. This module holds only the pure helpers that demonstrate/exercise
that independence.

Deliberately absent from this module, by design (task §7-8, "Jurisdiction /
labor-rule boundary"): any function that computes overtime, or that treats a
BIWEEKLY Payroll Period's total hours as an 80-hour threshold. Overtime
determination is delegated to a future jurisdiction/labor-rule layer
operating on Workweek-scoped worked time, never on Payroll-Period-scoped
totals. `test_payroll_engine.py` asserts this module exposes no such
function at all, rather than merely asserting a formula is "correct."
"""

from __future__ import annotations

from datetime import datetime, timedelta

SCHEDULE_TYPES: tuple[str, ...] = ("WEEKLY", "BIWEEKLY", "MONTHLY")


def validate_schedule_type(schedule_type: str) -> None:
    if schedule_type not in SCHEDULE_TYPES:
        raise ValueError(
            f"Unsupported PayrollSchedule schedule_type: {schedule_type!r}. "
            f"Supported: {SCHEDULE_TYPES}"
        )


def workweeks_within_period(
    period_start: datetime, period_end: datetime, start_weekday: int
) -> list[tuple[datetime, datetime]]:
    """Return the [start, end) Workweek intervals intersecting
    [period_start, period_end), anchored to `start_weekday` (0=Monday,
    matching `date.weekday()`).

    Pure calendar computation, independent of any `PayrollSchedule` —
    it makes no BIWEEKLY-specific assumption about how many Workweeks a
    Period contains; it only walks the calendar from the nearest Workweek
    boundary at or before `period_start`. For Rome's Flavours' current
    configuration (Monday-anchored Workweek, a Monday-to-Sunday-inclusive
    14-day BIWEEKLY Period), this returns exactly two full 7-day intervals.
    """
    if period_end <= period_start:
        raise ValueError("period_end must be after period_start")
    if not 0 <= start_weekday <= 6:
        raise ValueError("start_weekday must be 0 (Monday) .. 6 (Sunday)")

    days_since_boundary = (period_start.weekday() - start_weekday) % 7
    cursor = (period_start - timedelta(days=days_since_boundary)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    intervals: list[tuple[datetime, datetime]] = []
    while cursor < period_end:
        next_cursor = cursor + timedelta(days=7)
        overlap_start = max(cursor, period_start)
        overlap_end = min(next_cursor, period_end)
        if overlap_start < overlap_end:
            intervals.append((overlap_start, overlap_end))
        cursor = next_cursor
    return intervals
