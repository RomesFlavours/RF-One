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
module only decides WHEN to ATTEMPT, never whether the attempt succeeds.

TASK_TIPS_RECONCILIATION_AND_PAYMENT_CONTROL_001 §4 — the Payment loop's
tick additionally drives the THREE decided Tips payment modes end to end:

    MANUAL                       — never touched by this module at all; a
                                    human starts the cycle AND Approves & Pays
                                    it (Tips/app.py's Payment Control).
    AUTOMATIC + WITH_APPROVAL     — `run_due_payment_cycle_starts` opens the
                                    cycle when due; a human still Approves &
                                    Pays it (unchanged, pre-existing behavior).
    AUTOMATIC + WITHOUT_APPROVAL  — `run_due_payment_cycle_starts` opens the
                                    cycle when due, and `run_due_payment_
                                    cycle_auto_approvals` (called every tick,
                                    independently of whether a NEW cycle just
                                    opened) Approves & Pays any currently OPEN
                                    cycle for that Restaurant AS SOON AS it
                                    becomes READY — never before, and never by
                                    bypassing the Authority or Payment
                                    Readiness gates, which `approve_and_pay_
                                    cycle` re-checks unconditionally for the
                                    SYSTEM Acting Identity exactly as for a
                                    human one."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .. import acting_identity_service
from .. import models as m
from ..technical.connectors.mercury.client import MercuryClient, MercuryConnectorError
from . import payment_cycle_service as cycle_svc
from . import payment_readiness as readiness_svc
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


@dataclass
class DueAutoApprovalOutcome:
    restaurant_id: int
    cycle_id: int
    approved: bool
    reason: str | None


def run_due_payment_cycle_auto_approvals(
    session: Session, *, now: datetime | None = None, client: MercuryClient | None = None,
) -> list[DueAutoApprovalOutcome]:
    """One tick of the AUTO WITHOUT APPROVAL path (module docstring above):
    for every Restaurant configured `mode=AUTOMATIC, auto_approval_mode=
    WITHOUT_APPROVAL` with a currently OPEN Payment Cycle, attempts Approve &
    Pay using the stable SYSTEM Acting Identity (`acting_identity_service.
    get_or_create_system_identity`) — never a bare bypass: `approve_and_pay_
    cycle` re-checks Authority (a TIPS/APPROVE_AND_PAY `AuthorityGrant` that
    Restaurant must have explicitly granted the SYSTEM identity — Core 09
    §5.1 "AI-Authorized Execution... strictly within explicit Delegated
    Authority") and Payment Readiness exactly as for a human-triggered
    Approve & Pay. A NOT READY or unauthorized outcome is reported in the
    returned outcome and simply retried next tick — never raised as an
    error here (task §3); a persistently-failing readiness raises Attention
    via the SAME mechanism the Web Payment Control route uses, never a
    Tips-specific one.

    `client` — same dependency-injection shape `approve_and_pay_cycle`
    itself already takes: defaults to a real `MercuryClient()` (sandbox,
    per that class's own default), overridable in tests with a fake — one
    client per tick, shared by every Restaurant approved in it, exactly
    like a real deployment would (one Mercury sandbox account per
    environment today)."""
    now = now or datetime.now(UTC)
    client = client or MercuryClient()
    outcomes: list[DueAutoApprovalOutcome] = []
    for restaurant_id in _all_restaurant_ids(session):
        config = sched_svc.get_payment_schedule_effective_at(session, restaurant_id=restaurant_id, at=now)
        if (
            config is None or config.mode != m.TIPS_SCHEDULE_MODE_AUTOMATIC
            or config.auto_approval_mode != m.TIPS_PAYMENT_AUTO_APPROVAL_MODE_WITHOUT_APPROVAL
        ):
            continue
        cycle = cycle_svc.get_open_cycle(session, restaurant_id)
        if cycle is None:
            continue

        readiness = readiness_svc.describe_payment_readiness(session, restaurant_id, now=now)
        if not readiness.ready:
            cycle_svc.maybe_raise_attention_for_payment_readiness(session, restaurant_id=restaurant_id, readiness=readiness)
            session.commit()
            outcomes.append(
                DueAutoApprovalOutcome(restaurant_id=restaurant_id, cycle_id=cycle.id, approved=False, reason=readiness.reason)
            )
            continue

        try:
            source_account_id = cycle_svc.resolve_source_account_id(session, restaurant_id, client)
            if source_account_id is None:
                outcomes.append(
                    DueAutoApprovalOutcome(
                        restaurant_id=restaurant_id, cycle_id=cycle.id, approved=False,
                        reason="no Mercury sandbox source account configured or available",
                    )
                )
                continue
            system_identity = acting_identity_service.get_or_create_system_identity(session)
            cycle_svc.approve_and_pay_cycle(
                session, cycle=cycle, acting_identity=system_identity, client=client, source_account_id=source_account_id,
            )
            session.commit()
            outcomes.append(DueAutoApprovalOutcome(restaurant_id=restaurant_id, cycle_id=cycle.id, approved=True, reason=None))
        except cycle_svc.ApproveAndPayError as exc:
            session.rollback()
            outcomes.append(
                DueAutoApprovalOutcome(restaurant_id=restaurant_id, cycle_id=cycle.id, approved=False, reason=str(exc))
            )
        except MercuryConnectorError as exc:
            session.rollback()
            outcomes.append(
                DueAutoApprovalOutcome(
                    restaurant_id=restaurant_id, cycle_id=cycle.id, approved=False,
                    reason=f"Mercury sandbox connector error: {exc}",
                )
            )
    return outcomes


def run_payment_tick(session: Session, *, now: datetime | None = None, client: MercuryClient | None = None) -> list:
    """The Payment loop's actual per-tick entry point: starts any due
    cycles, THEN attempts auto-approval for any Restaurant configured
    WITHOUT_APPROVAL — in that order, so a cycle started on THIS tick can
    also be auto-approved on the SAME tick if it happens to already be
    READY (never waits an extra full interval for no reason)."""
    now = now or datetime.now(UTC)
    start_outcomes = run_due_payment_cycle_starts(session, now=now)
    approval_outcomes = run_due_payment_cycle_auto_approvals(session, now=now, client=client)
    return [*start_outcomes, *approval_outcomes]


def _run_forever(
    session_factory: sessionmaker[Session], *, loop: str, interval_seconds: float,
) -> None:  # pragma: no cover — thin process loop, exercised via run_due_* directly in tests
    LOG.info("Starting Tips %s scheduler loop (interval=%.0fs).", loop, interval_seconds)
    runner = run_due_calculations if loop == "calculation" else run_payment_tick
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

    runner = run_due_calculations if args.loop == "calculation" else run_payment_tick
    if args.once:
        with session_factory() as session:
            outcomes = runner(session)
            LOG.info("Tips %s scheduler tick: %d Restaurant(s) triggered.", args.loop, len(outcomes))
        return 0

    _run_forever(session_factory, loop=args.loop, interval_seconds=args.interval_seconds)
    return 0  # unreachable — _run_forever loops until killed


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
