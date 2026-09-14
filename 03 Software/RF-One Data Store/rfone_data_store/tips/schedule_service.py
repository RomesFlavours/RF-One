"""Tips Configuration — Calculation Schedule and Payment Schedule
(TASK_TIPS_COMPLETE_001 §2/§3).

Two independent, Restaurant-scoped, effective-dated configurations:
`TipsCalculationScheduleConfig` (WHEN to calculate) and `TipsPaymentSchedule
Config` (WHEN to pay out). Neither is inferred from the other — a
Restaurant may calculate daily while paying out weekly, or any other
combination (§2's own explicit principle). Mirrors the existing effective-
dating discipline already established by `distribution_rule_service.
create_new_version` and `payroll/payment_execution.py`'s `approved_provider_
at`: never overwrite a prior configuration row, close its `valid_to` and
insert a new one; resolve "what applies right now" by picking the
most-recently-started row whose `[valid_from, valid_to)` window contains the
instant in question.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m

UTC = timezone.utc


class ScheduleConfigError(ValueError):
    """A malformed configuration call — always a caller bug (e.g. AUTOMATIC
    mode with no `interval_days`), never a normal outcome."""


def _validate(*, mode: str, interval_days: int | None) -> None:
    if mode not in m.TIPS_SCHEDULE_MODES:
        raise ScheduleConfigError(f"Invalid mode {mode!r} — must be one of {m.TIPS_SCHEDULE_MODES}.")
    if mode == m.TIPS_SCHEDULE_MODE_AUTOMATIC:
        if interval_days is None or interval_days <= 0:
            raise ScheduleConfigError("mode=AUTOMATIC requires a strictly positive interval_days ('every N days').")


def _effective_at(rows: list, at: datetime):
    """Most-recently-started row whose `[valid_from, valid_to)` window
    contains `at` — same tie-break rule `payroll/payment_execution.py`'s
    `approved_provider_at` already establishes for this exact shape."""
    candidates = [
        r for r in rows
        if _aware(r.valid_from) <= at and (r.valid_to is None or at < _aware(r.valid_to))
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda r: _aware(r.valid_from))


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# Calculation Schedule
# ---------------------------------------------------------------------------


def get_calculation_schedule_effective_at(
    session: Session, *, restaurant_id: int, at: datetime | None = None,
) -> m.TipsCalculationScheduleConfig | None:
    at = at or datetime.now(UTC)
    rows = list(
        session.scalars(
            select(m.TipsCalculationScheduleConfig).where(
                m.TipsCalculationScheduleConfig.restaurant_id == restaurant_id,
            )
        )
    )
    return _effective_at(rows, at)


def set_calculation_schedule(
    session: Session, *, restaurant_id: int, mode: str, interval_days: int | None = None,
    execution_time: time | None = None, anchor_date: date | None = None,
    effective_from: datetime | None = None, created_by: str | None = None,
) -> m.TipsCalculationScheduleConfig:
    """Closes the currently-effective row (if any) at `effective_from` and
    inserts a new one — never overwrites history (task §8)."""
    _validate(mode=mode, interval_days=interval_days)
    effective_from = effective_from or datetime.now(UTC)

    current = get_calculation_schedule_effective_at(session, restaurant_id=restaurant_id, at=effective_from)
    if current is not None:
        current.valid_to = effective_from

    config = m.TipsCalculationScheduleConfig(
        restaurant_id=restaurant_id, mode=mode, interval_days=interval_days, execution_time=execution_time,
        anchor_date=anchor_date, valid_from=effective_from, valid_to=None, created_by=created_by,
    )
    session.add(config)
    session.flush()
    return config


# ---------------------------------------------------------------------------
# Payment Schedule
# ---------------------------------------------------------------------------


def get_payment_schedule_effective_at(
    session: Session, *, restaurant_id: int, at: datetime | None = None,
) -> m.TipsPaymentScheduleConfig | None:
    at = at or datetime.now(UTC)
    rows = list(
        session.scalars(
            select(m.TipsPaymentScheduleConfig).where(
                m.TipsPaymentScheduleConfig.restaurant_id == restaurant_id,
            )
        )
    )
    return _effective_at(rows, at)


def set_payment_schedule(
    session: Session, *, restaurant_id: int, mode: str, interval_days: int | None = None,
    execution_time: time | None = None, anchor_date: date | None = None,
    mercury_source_account_id: str | None = None, effective_from: datetime | None = None,
    created_by: str | None = None,
) -> m.TipsPaymentScheduleConfig:
    _validate(mode=mode, interval_days=interval_days)
    effective_from = effective_from or datetime.now(UTC)

    current = get_payment_schedule_effective_at(session, restaurant_id=restaurant_id, at=effective_from)
    if current is not None:
        current.valid_to = effective_from

    config = m.TipsPaymentScheduleConfig(
        restaurant_id=restaurant_id, mode=mode, interval_days=interval_days, execution_time=execution_time,
        anchor_date=anchor_date, mercury_source_account_id=mercury_source_account_id,
        valid_from=effective_from, valid_to=None, created_by=created_by,
    )
    session.add(config)
    session.flush()
    return config


# ---------------------------------------------------------------------------
# "Is this cycle due yet" — shared by both scheduler loops (calculation and
# payment), since the "every N days, execution_time, anchor_date" arithmetic
# is identical for both; only WHAT gets triggered differs.
# ---------------------------------------------------------------------------


def is_due(
    *, mode: str, interval_days: int | None, execution_time: time | None, anchor_date: date | None,
    now: datetime, last_triggered_at: datetime | None,
) -> bool:
    """True if an AUTOMATIC schedule's next occurrence has arrived and has
    not already been handled. `anchor_date` defaults to `now`'s own date
    when unset (task §3's "se necessario" — a config that never specified
    one still behaves deterministically, anchored to whenever it was first
    evaluated due, not to a fabricated "day one" of the whole system).

    Never a wall-clock-only check (Core 2.0 §5, "Time is just an event," the
    same discipline `tips/readiness.py` already applies): due-ness is
    "has the next scheduled instant already passed, AND has nothing already
    handled it" — `last_triggered_at` (the caller's own record of when this
    Restaurant's schedule last actually ran) is what prevents re-triggering
    every time the scheduler polls within the same due window."""
    if mode != m.TIPS_SCHEDULE_MODE_AUTOMATIC:
        return False
    if interval_days is None or interval_days <= 0:
        return False

    anchor = anchor_date or now.date()
    exec_time = execution_time or time(0, 0)
    days_since_anchor = (now.date() - anchor).days
    if days_since_anchor < 0:
        return False  # anchor is in the future — no occurrence has happened yet.

    cycles_elapsed = days_since_anchor // interval_days
    most_recent_due_date = anchor + timedelta(days=cycles_elapsed * interval_days)
    most_recent_due_at = datetime.combine(most_recent_due_date, exec_time, tzinfo=UTC)
    if most_recent_due_at > now:
        return False

    if last_triggered_at is not None and _aware(last_triggered_at) >= most_recent_due_at:
        return False
    return True
