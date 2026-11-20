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

COMPENSATION_PERIOD_SUMMARY_001 adds the shared SETTING side of the same
concept here, where the concept already lives: which `WorkweekDefinition`
is in force for a Restaurant at an instant, and recording a new start day
(effective-dated, never overwriting history). The Workweek start is a
general Restaurant setting, edited in RF-One Settings, and every consumer
reads it from here — the Compensation Period Summary is only its first
reader, not its owner. Counting the hours above a weekly threshold (an
hours quantity, never a monetary overtime result) lives in
`period_summary.py`, not in this module.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m

UTC = timezone.utc

WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _aware_utc(value: datetime) -> datetime:
    """Persisted datetimes are UTC; SQLite drops `tzinfo` on reload (see
    `engine._as_naive_utc`). Treat a naive value as already-UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def workweek_definitions_for(session: Session, restaurant_id: int) -> list[m.WorkweekDefinition]:
    """Every `WorkweekDefinition` of a Restaurant, oldest first (history)."""
    return list(session.scalars(
        select(m.WorkweekDefinition)
        .where(m.WorkweekDefinition.restaurant_id == restaurant_id)
        .order_by(m.WorkweekDefinition.valid_from, m.WorkweekDefinition.id)
    ).all())


def effective_workweek_definition(
    session: Session, restaurant_id: int, at: datetime,
) -> m.WorkweekDefinition | None:
    """The `WorkweekDefinition` in force for this Restaurant at instant `at`
    (`valid_from <= at < valid_to`), or None when none is configured. Never
    a default: an unconfigured Workweek is reported, not assumed."""
    at = _aware_utc(at)
    for definition in reversed(workweek_definitions_for(session, restaurant_id)):
        starts = _aware_utc(definition.valid_from)
        ends = _aware_utc(definition.valid_to) if definition.valid_to is not None else None
        if starts <= at and (ends is None or at < ends):
            return definition
    return None


def set_workweek_start(
    session: Session, *, restaurant_id: int, start_weekday: int, effective_from: datetime,
    notes: str | None = None,
) -> m.WorkweekDefinition:
    """Record a new Workweek start day from `effective_from` onwards.

    History is never rewritten: the definition in force at `effective_from`
    is closed at that instant and a new one opens. A change dated before
    the latest existing definition is refused, because it would silently
    re-cut weeks that are already history."""
    if not 0 <= start_weekday <= 6:
        raise ValueError("start_weekday must be 0 (Monday) .. 6 (Sunday)")
    effective_from = _aware_utc(effective_from)
    existing = workweek_definitions_for(session, restaurant_id)
    if existing and effective_from <= _aware_utc(existing[-1].valid_from):
        raise ValueError(
            "A new Workweek start must take effect after the latest existing one "
            f"({_aware_utc(existing[-1].valid_from).date()}); history is never rewritten."
        )
    current = effective_workweek_definition(session, restaurant_id, effective_from)
    if current is not None:
        if current.start_weekday == start_weekday:
            raise ValueError(f"The Workweek already starts on {WEEKDAY_NAMES[start_weekday]}.")
        current.valid_to = effective_from
    definition = m.WorkweekDefinition(
        restaurant_id=restaurant_id, start_weekday=start_weekday,
        valid_from=effective_from, valid_to=None, notes=notes,
    )
    session.add(definition)
    session.flush()
    return definition


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
