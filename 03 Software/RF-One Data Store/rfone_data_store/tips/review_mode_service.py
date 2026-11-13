"""Tips Review Mode — AUDIT vs AUTOMATIC (HOST_TIP_AUDIT_001 §9/§10/§11).

A Restaurant-scoped, purely operational/UI toggle: whether the Host Tip
Audit/Explain report is surfaced prominently right after a calculation
(AUDIT), or the calculation flow proceeds without requiring it to be opened
(AUTOMATIC — the report itself remains permanently available on demand
either way). This NEVER changes what the Tip Distribution Engine computes —
there is exactly one calculation engine (`tips/distribution_engine.py`),
untouched by this module.

Reuses the existing `TipsCalculationScheduleConfig` table (`tips/
schedule_service.py`) rather than introducing a new configuration
subsystem — `review_mode` lives there as a plain, in-place-mutable column,
deliberately NOT part of that table's own effective-dating discipline (see
the column's own comment in `models.py`): a schedule change is a fact worth
a permanent historical record, but "which UI emphasis is currently on" is
not.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .. import models as m
from . import schedule_service as sched_svc

UTC = timezone.utc


def get_review_mode(session: Session, *, restaurant_id: int, at: datetime | None = None) -> str:
    """The Restaurant's current Review Mode. Defaults to `TIPS_REVIEW_MODE_
    AUDIT` — the task-mandated safe default — whenever no Calculation
    Schedule has ever been configured for this Restaurant, or one exists but
    has never had a Review Mode explicitly set. Never silently resolves to
    AUTOMATIC."""
    config = sched_svc.get_calculation_schedule_effective_at(session, restaurant_id=restaurant_id, at=at)
    if config is None or not config.review_mode:
        return m.TIPS_REVIEW_MODE_AUDIT
    return config.review_mode


def set_review_mode(
    session: Session, *, restaurant_id: int, review_mode: str, created_by: str | None = None,
) -> m.TipsCalculationScheduleConfig:
    """Sets the Restaurant's current Review Mode, in place — never creates a
    new `TipsCalculationScheduleConfig` version for this alone (see the
    column's own comment). If no Calculation Schedule row exists yet for
    this Restaurant, bootstraps the minimal safe one (`mode=MANUAL`, no
    automatic cadence) rather than requiring the operator to configure a
    full calculation schedule just to set a review-workflow preference —
    MANUAL is the strictest, already-the-de-facto behavior whenever no
    schedule has ever been configured (task §11's own instruction: introduce
    only what is necessary)."""
    if review_mode not in m.TIPS_REVIEW_MODES:
        raise ValueError(f"Invalid review_mode {review_mode!r} — must be one of {m.TIPS_REVIEW_MODES}.")

    config = sched_svc.get_calculation_schedule_effective_at(session, restaurant_id=restaurant_id)
    if config is None:
        config = m.TipsCalculationScheduleConfig(
            restaurant_id=restaurant_id, mode=m.TIPS_SCHEDULE_MODE_MANUAL, interval_days=None,
            valid_from=datetime.now(UTC), valid_to=None, created_by=created_by,
        )
        session.add(config)

    config.review_mode = review_mode
    session.flush()
    return config
