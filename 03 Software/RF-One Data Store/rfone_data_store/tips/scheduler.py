"""Tips automatic scheduler — TWO independent loops, Calculation and
Payment (TASK_TIPS_COMPLETE_001 §16: "Calculation e Payment devono avere
scheduler separati"). Mirrors the existing `technical.connectors.clover.
live_sync._run_forever` shape (a testable `run_due_*` function wrapped by a
thin, uncovered `_run_forever`/`main` process loop) — no new scheduling
primitive, no cron/celery dependency introduced.

Neither loop hardcodes a cadence: each iterates every Restaurant that has an
AUTOMATIC `TipsCalculationScheduleConfig`/`TipsPaymentScheduleConfig`
effective right now, and asks `schedule_service.is_due(...)` whether THAT
Restaurant's own configured "every N days" occurrence has arrived and not
already been handled (task §3/§16's explicit "NON hardcodare"). A Restaurant
with no AUTOMATIC configuration is simply never triggered here — it relies
entirely on manual "Run Calculation Now"/"Start Payment Cycle Now" (task
§15).

Calculation due-ness never itself bypasses `payout_process.run_calculation_
now`'s own Clover-readiness/already-calculated checks (task §5) — this
module only decides WHEN to ATTEMPT, never whether the attempt succeeds."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .. import models as m
from . import payment_cycle_service as cycle_svc
from . import payout_process as payout_svc
from . import schedule_service as sched_svc

UTC = timezone.utc
LOG = logging.getLogger("tips_scheduler")

DEFAULT_POLL_INTERVAL_SECONDS = 300.0


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _all_restaurant_ids(session: Session) -> list[int]:
    return list(session.scalars(select(m.Restaurant.id)))


def _last_calculation_at(session: Session, restaurant_id: int) -> datetime | None:
    started_at = session.scalars(
        select(m.TipDistributionCalculationRun.started_at)
        .where(m.TipDistributionCalculationRun.restaurant_id == restaurant_id)
        .order_by(m.TipDistributionCalculationRun.id.desc())
        .limit(1)
    ).first()
    return _aware(started_at) if started_at is not None else None


def _last_payment_cycle_at(session: Session, restaurant_id: int) -> datetime | None:
    started_at = session.scalars(
        select(m.TipPaymentCycle.started_at)
        .where(m.TipPaymentCycle.restaurant_id == restaurant_id)
        .order_by(m.TipPaymentCycle.id.desc())
        .limit(1)
    ).first()
    return _aware(started_at) if started_at is not None else None


@dataclass
class DueCalculationOutcome:
    restaurant_id: int
    result: "payout_svc.CalculationRunResult"


def run_due_calculations(session: Session, *, now: datetime | None = None) -> list[DueCalculationOutcome]:
    """One tick of the Calculation scheduler: for every Restaurant with an
    AUTOMATIC `TipsCalculationScheduleConfig` effective at `now` whose
    configured cadence is due, calls `payout_process.run_calculation_now`
    (which itself re-checks Clover readiness/already-calculated — this
    function never assumes due == safe to calculate)."""
    now = now or datetime.now(UTC)
    outcomes: list[DueCalculationOutcome] = []
    for restaurant_id in _all_restaurant_ids(session):
        config = sched_svc.get_calculation_schedule_effective_at(session, restaurant_id=restaurant_id, at=now)
        if config is None or config.mode != m.TIPS_SCHEDULE_MODE_AUTOMATIC:
            continue
        due = sched_svc.is_due(
            mode=config.mode, interval_days=config.interval_days, execution_time=config.execution_time,
            anchor_date=config.anchor_date, now=now, last_triggered_at=_last_calculation_at(session, restaurant_id),
        )
        if not due:
            continue
        result = payout_svc.run_calculation_now(session, restaurant_id=restaurant_id)
        session.commit()
        outcomes.append(DueCalculationOutcome(restaurant_id=restaurant_id, result=result))
    return outcomes


@dataclass
class DuePaymentCycleOutcome:
    restaurant_id: int
    cycle: "m.TipPaymentCycle | None"


def run_due_payment_cycle_starts(session: Session, *, now: datetime | None = None) -> list[DuePaymentCycleOutcome]:
    """One tick of the Payment scheduler: for every Restaurant with an
    AUTOMATIC `TipsPaymentScheduleConfig` effective at `now` whose configured
    cadence is due, STARTS (aggregates) a new Payment Cycle — it never
    Approves & Pays it (task §14's authority gate is never bypassed by
    automation; Approve & Pay always requires an explicit, authorized human
    action, even when the Cycle itself opened automatically)."""
    now = now or datetime.now(UTC)
    outcomes: list[DuePaymentCycleOutcome] = []
    for restaurant_id in _all_restaurant_ids(session):
        config = sched_svc.get_payment_schedule_effective_at(session, restaurant_id=restaurant_id, at=now)
        if config is None or config.mode != m.TIPS_SCHEDULE_MODE_AUTOMATIC:
            continue
        due = sched_svc.is_due(
            mode=config.mode, interval_days=config.interval_days, execution_time=config.execution_time,
            anchor_date=config.anchor_date, now=now, last_triggered_at=_last_payment_cycle_at(session, restaurant_id),
        )
        if not due:
            continue
        cycle = cycle_svc.start_payment_cycle(
            session, restaurant_id=restaurant_id, now=now, triggered_by=m.TIP_PAYMENT_CYCLE_TRIGGER_AUTOMATIC,
        )
        session.commit()
        outcomes.append(DuePaymentCycleOutcome(restaurant_id=restaurant_id, cycle=cycle))
    return outcomes


def _run_forever(
    session_factory: sessionmaker[Session], *, loop: str, interval_seconds: float,
) -> None:  # pragma: no cover — thin process loop, exercised via run_due_* directly in tests
    LOG.info("Starting Tips %s scheduler loop (interval=%.0fs).", loop, interval_seconds)
    runner = run_due_calculations if loop == "calculation" else run_due_payment_cycle_starts
    while True:
        try:
            with session_factory() as session:
                outcomes = runner(session)
                if outcomes:
                    LOG.info("Tips %s scheduler tick: %d Restaurant(s) triggered.", loop, len(outcomes))
        except Exception:  # noqa: BLE001 — one bad tick must never kill the loop
            LOG.exception("Unhandled error in Tips %s scheduler tick — will retry next interval.", loop)
        time.sleep(interval_seconds)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover — thin CLI wrapper
    from ..database import create_configured_engine, create_session_factory, get_database_url, run_migrations_to_head

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--loop", choices=("calculation", "payment"), required=True)
    parser.add_argument("--interval-seconds", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)
    parser.add_argument(
        "--once", action="store_true",
        help="Run a single tick and exit, instead of looping forever — for cron/Task Scheduler-driven "
        "invocation rather than a long-running daemon.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    db_url = get_database_url()
    run_migrations_to_head(db_url)
    engine = create_configured_engine(db_url)
    session_factory = create_session_factory(engine)

    runner = run_due_calculations if args.loop == "calculation" else run_due_payment_cycle_starts
    if args.once:
        with session_factory() as session:
            outcomes = runner(session)
            LOG.info("Tips %s scheduler tick: %d Restaurant(s) triggered.", args.loop, len(outcomes))
        return 0

    _run_forever(session_factory, loop=args.loop, interval_seconds=args.interval_seconds)
    return 0  # unreachable — _run_forever loops until killed


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
