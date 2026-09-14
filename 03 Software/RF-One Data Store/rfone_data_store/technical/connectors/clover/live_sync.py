"""Near-real-time Clover data acquisition — Live Sync
(TECHNICAL_CONNECTORS_STRUCTURE_001 / CLOVER_DATA_ACQUISITION_ARCHITECTURE_001).

The operational path Tips, and in the future Server Copilot, Server
Performance, Sales, and other Domains read already-ingested Clover facts
from. Polls a short, recent, automatically-advancing window using the SAME
`acquisition.import_clover_period()` fetch/mapping/upsert/concurrency-guard
primitives Historical Backfill uses — never a second ingestion system.

Location-scoped, not Restaurant-scoped: this connector has no concept of
Restaurant. A Domain caller resolves which `location_id` it needs synced
(e.g. Tips resolves its Restaurant's own Location via `RestaurantLocation`)
and passes that in; this module never performs that resolution itself.

Why polling, not webhooks: this repository has no public HTTPS endpoint to
receive Clover webhook callbacks, and none is registered/configured anywhere
in this codebase (verified — no webhook receiver exists). Standing one up is
an infrastructure/deployment decision (a publicly reachable endpoint, Clover
App webhook registration, signature verification) outside the scope of a
code-only change, so this module implements the "lightweight incremental
polling" fallback. It is deliberately built so that, whenever webhook
infrastructure exists, a webhook handler can call the exact same
`import_clover_period(..., mode=MODE_LIVE_SYNC)` per affected Order/Payment
without any change to the acquisition logic itself — only the trigger
(a poll tick vs. an inbound webhook call) would differ.

Latency ("seconds, not minutes"): with a short poll interval (default 15s)
and a narrow, checkpoint-advancing window, a Payment/Order change is
typically visible in RF-One within one interval of it settling on Clover.

Idempotency: every cycle reuses the exact same upsert-by-source-identity
primitives as Backfill, and always includes a small overlap buffer in its
window — a repeated or overlapping poll can only refresh existing rows from
Clover's current values, never duplicate them.

Concurrency: a cycle uses the SAME Location-scoped `IngestionRun.lock_key`
Backfill uses — a manual Backfill and a Live Sync cycle can never write
concurrently. A cycle that finds the lock busy is not an error: it logs and
waits for the next tick (cycles are frequent and cheap; missing one because
a Backfill is mid-flight is immaterial — the next cycle's window absorbs
it).
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .... import models as m
from .acquisition import (
    ImportAlreadyRunningError,
    ImportSummary,
    MODE_LIVE_SYNC,
    CloverReadClient,
    _resolve_clover_merchant,
    import_clover_period,
)

UTC = timezone.utc
LOG = logging.getLogger("clover_live_sync")

DEFAULT_POLL_INTERVAL_SECONDS = 15.0
# First-ever cycle (no prior acquisition run at all for this Location):
# starts this far back rather than the dawn of time. Anything older is
# Historical Backfill's job, not Live Sync's.
DEFAULT_INITIAL_LOOKBACK = timedelta(hours=1)
# Every cycle's window starts this far BEFORE the prior cycle's own
# period_end — never a razor's edge — tolerating Clover write-then-read
# latency/clock skew so a Payment that finalizes moments after a prior
# cycle's fetch is still reliably captured on the very next cycle. Safe by
# construction: re-touching a slightly wider window than strictly needed can
# only refresh rows via the existing idempotent upsert, never duplicate them.
DEFAULT_OVERLAP_BUFFER = timedelta(minutes=2)


def compute_next_sync_window(
    session: Session, *, location_id: int, now: datetime | None = None,
    initial_lookback: timedelta = DEFAULT_INITIAL_LOOKBACK, overlap_buffer: timedelta = DEFAULT_OVERLAP_BUFFER,
) -> tuple[datetime, datetime] | None:
    """`[period_start, period_end)` for the next Live Sync cycle.
    `period_end` is always `now`; `period_start` resumes from the last
    COMPLETE/PARTIAL acquisition run's own `source_window_end` (Backfill OR
    a prior Live Sync cycle — both populate this identically, so a manual
    Backfill through yesterday naturally advances Live Sync's own
    checkpoint too) minus `overlap_buffer`. On the very first cycle ever for
    this Location, starts from `now - initial_lookback` instead. Returns
    `None` if `location_id` is not a Clover-sourced Location at all (the
    caller should skip it, not error)."""
    now = now or datetime.now(UTC)
    merchant = _resolve_clover_merchant(session, location_id)
    if merchant is None:
        return None
    source_system_id, _merchant_id = merchant

    last_run = session.scalars(
        select(m.IngestionRun)
        .where(
            m.IngestionRun.location_id == location_id,
            m.IngestionRun.source_system_id == source_system_id,
            m.IngestionRun.status.in_(("COMPLETE", "PARTIAL")),
            m.IngestionRun.source_window_end.is_not(None),
            # The Live Cursor is the whole-Location Backfill/Live Sync
            # checkpoint only — the Correction/Reconciliation Poller's own
            # per-resource Modification Cursor rows (`resource_type` set,
            # correction_sync.py) must never be mistaken for it.
            m.IngestionRun.resource_type.is_(None),
        )
        .order_by(m.IngestionRun.id.desc())
        .limit(1)
    ).first()

    if last_run is not None and last_run.source_window_end is not None:
        checkpoint = last_run.source_window_end
        checkpoint = checkpoint if checkpoint.tzinfo is not None else checkpoint.replace(tzinfo=UTC)
        period_start = checkpoint - overlap_buffer
    else:
        period_start = now - initial_lookback

    return period_start, now


def run_live_sync_cycle(
    session: Session, *, location_id: int, client: CloverReadClient | None = None, now: datetime | None = None,
) -> ImportSummary | None:
    """One Live Sync cycle for one Location. Returns the `ImportSummary` on
    success, or `None` if the cycle was skipped (not a Clover-sourced
    Location, or another acquisition — Backfill or Live Sync — is already
    RUNNING for this Location right now). A skip is never an error: the
    next cycle simply tries again with a fresh, still-correct window."""
    window = compute_next_sync_window(session, location_id=location_id, now=now)
    if window is None:
        LOG.info("location_id=%s is not a Clover-sourced Location — skipping this cycle.", location_id)
        return None
    period_start, period_end = window

    try:
        return import_clover_period(
            session, location_id=location_id, period_start=period_start, period_end=period_end,
            client=client, mode=MODE_LIVE_SYNC,
        )
    except ImportAlreadyRunningError:
        LOG.info(
            "location_id=%s: another Clover acquisition is already running — skipping this cycle, "
            "will retry next interval.", location_id,
        )
        return None


def _run_forever(
    session_factory: sessionmaker[Session], *, location_id: int, interval_seconds: float,
) -> None:  # pragma: no cover — thin process loop, exercised via run_live_sync_cycle directly in tests
    LOG.info("Starting Clover Live Sync loop for location_id=%s (interval=%.0fs).", location_id, interval_seconds)
    while True:
        try:
            with session_factory() as session:
                summary = run_live_sync_cycle(session, location_id=location_id)
                if summary is not None:
                    session.commit()
                    LOG.info(
                        "Cycle complete: payments=%d orders=%d shifts=%d refunds=%d errors=%d",
                        summary.payments_imported + summary.payments_updated,
                        summary.orders_imported + summary.orders_updated,
                        summary.shifts_imported, summary.refunds_found, len(summary.errors),
                    )
        except Exception:  # noqa: BLE001 — one bad cycle must never kill the loop
            LOG.exception("Unhandled error in Live Sync cycle — will retry next interval.")
        time.sleep(interval_seconds)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover — thin CLI wrapper
    from ....database import create_configured_engine, create_session_factory, get_database_url, run_migrations_to_head

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--location-id", type=int, required=True)
    parser.add_argument("--interval-seconds", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)
    parser.add_argument(
        "--once", action="store_true",
        help="Run a single cycle and exit, instead of looping forever — for cron/Task Scheduler-driven "
        "invocation rather than a long-running daemon.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    db_url = get_database_url()
    run_migrations_to_head(db_url)
    engine = create_configured_engine(db_url)
    session_factory = create_session_factory(engine)

    if args.once:
        with session_factory() as session:
            summary = run_live_sync_cycle(session, location_id=args.location_id)
            if summary is not None:
                session.commit()
                LOG.info(
                    "Cycle complete: payments=%d orders=%d shifts=%d refunds=%d errors=%d",
                    summary.payments_imported + summary.payments_updated,
                    summary.orders_imported + summary.orders_updated,
                    summary.shifts_imported, summary.refunds_found, len(summary.errors),
                )
        return 0

    _run_forever(session_factory, location_id=args.location_id, interval_seconds=args.interval_seconds)
    return 0  # unreachable — _run_forever loops until killed


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
