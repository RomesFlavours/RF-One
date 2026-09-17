"""Workweek evaluation-window helper (relocated from
`rfone_data_store/payroll/schedule.py` by explicit Product Owner decision).

`WorkweekDefinition` (see `models.py`) is used by RF-One Compensation /
Rule Matrix to define the evaluation window a future Overtime Evaluator must
use — never by the Administration/Payroll domain's own `PayrollSchedule`/
`PayrollRun` cadence, which remains a purely administrative processing
schedule (`01 Domains/Shared Domains/Administration/Payroll/Payroll Schedule
and Period.md`). Ownership of the Workweek boundary therefore belongs to
Compensation / Compensation Rules / Rule Matrix, not to Administration/
Payroll, even though `WorkweekDefinition`'s physical table
(`workweek_definitions`) is unchanged and the Administration/Payroll package
may still read it for its own scheduling purposes.

Deliberately absent from this module, by design (same boundary
`payroll/schedule.py` already established): any function that computes
overtime, or that treats a BIWEEKLY Payroll Period's total hours as an
80-hour threshold. Overtime determination is delegated to a future
jurisdiction/labor-rule layer (the Rule Matrix's future Overtime Evaluator —
see `OVERTIME_RULE_MATRIX_001.md`) operating on Workweek-scoped worked time,
never on Payroll-Period-scoped totals. Behavior is unchanged by this move —
only the module's location and import path changed.
"""

from __future__ import annotations

from datetime import datetime, timedelta


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
