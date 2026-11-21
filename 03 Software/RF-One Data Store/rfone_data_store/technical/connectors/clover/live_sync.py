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

Window (CLOVER_ACQUISITION_JOBS_001 §5): each cycle re-reads only a small
recent window — now minus 2 hours by default, configurable — so Orders
still open, Payments arriving just after, and very recent corrections are
caught. It is not a deep historical re-scan; see `compute_next_sync_window`.

Not active until enabled: nothing starts this loop automatically. It is to
be switched on (and `RFONE_CLOVER_LIVE_SYNC_ENABLED` set, so the pages say
so) when the Product Owner decides the platform is ready (Cognito).

Idempotency: every cycle reuses the exact same upsert-by-source-identity
primitives as Backfill — a repeated or overlapping poll can only refresh
existing rows from Clover's current values, never duplicate them.

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

from sqlalchemy.orm import Session, sessionmaker

from .acquisition import (
    ImportAlreadyRunningError,
    ImportSummary,
    MODE_LIVE_SYNC,
    CloverReadClient,
    _resolve_clover_merchant,
    active_clover_location_ids,
    import_clover_period,
    location_is_active,
)
from .acquisition_jobs import compute_live_sync_window

UTC = timezone.utc
LOG = logging.getLogger("clover_live_sync")

DEFAULT_POLL_INTERVAL_SECONDS = 15.0


def compute_next_sync_window(
    session: Session, *, location_id: int, now: datetime | None = None,
    recent_window: timedelta | None = None,
) -> tuple[datetime, datetime] | None:
    """`[period_start, period_end]` for the next Live Sync cycle
    (CLOVER_ACQUISITION_JOBS_001 §5).

    `period_end` is always `now`. `period_start` is `now - recent window`
    (default 2 hours, `RFONE_CLOVER_LIVE_SYNC_WINDOW_MINUTES`): every cycle
    re-reads that small recent window so Orders still open, Payments that
    arrive just after, and very recent corrections are not missed — never a
    deep historical re-scan. Only when the last successful synchronization
    is older than that window (Live Sync was stopped) does the cycle start
    from that point instead, catching up once rather than skipping the gap.
    The rule itself lives in `acquisition_jobs.compute_live_sync_window`,
    shared with Sync Now's own "last successful synchronization".

    Returns `None` if `location_id` is not a Clover-sourced Location at all
    (the caller should skip it, not error)."""
    if _resolve_clover_merchant(session, location_id) is None:
        return None
    return compute_live_sync_window(session, location_id=location_id, now=now, recent_window=recent_window)


def run_live_sync_cycle(
    session: Session, *, location_id: int, client: CloverReadClient | None = None, now: datetime | None = None,
) -> ImportSummary | None:
    """One Live Sync cycle for one Location. Returns the `ImportSummary` on
    success, or `None` if the cycle was skipped (not a Clover-sourced
    Location, or another acquisition — Backfill or Live Sync — is already
    RUNNING for this Location right now). A skip is never an error: the
    next cycle simply tries again with a fresh, still-correct window."""
    if _resolve_clover_merchant(session, location_id) is not None and not location_is_active(session, location_id):
        LOG.info("location_id=%s is not active — no Live Sync until it is activated.", location_id)
        return None
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


def _cycle_locations(session_factory: sessionmaker[Session], location_ids: list[int] | None) -> list[int]:
    """Fixed `--location-id` list, or every active Clover Location re-read each
    cycle (`--all-active-locations`, CLOVER_MULTISITE_001)."""
    if location_ids is not None:
        return list(location_ids)
    with session_factory() as session:
        return active_clover_location_ids(session)


def _run_one_location(session_factory: sessionmaker[Session], location_id: int) -> None:
    """One Location's cycle in its own session and transaction."""
    try:
        with session_factory() as session:
            summary = run_live_sync_cycle(session, location_id=location_id)
            if summary is not None:
                session.commit()
                LOG.info(
                    "location_id=%s cycle complete: payments=%d orders=%d shifts=%d refunds=%d errors=%d",
                    location_id,
                    summary.payments_imported + summary.payments_updated,
                    summary.orders_imported + summary.orders_updated,
                    summary.shifts_imported, summary.refunds_found, len(summary.errors),
                )
    except Exception:  # noqa: BLE001 — one bad cycle must never kill the loop
        LOG.exception("Unhandled error in Live Sync cycle for location_id=%s — will retry next interval.", location_id)


def _run_forever(
    session_factory: sessionmaker[Session], *, location_ids: list[int] | None, interval_seconds: float,
) -> None:  # pragma: no cover — thin process loop, exercised via run_live_sync_cycle directly in tests
    LOG.info("Starting Clover Live Sync loop for %s (interval=%.0fs).",
             f"location_id(s)={location_ids}" if location_ids is not None else "all active Clover Locations",
             interval_seconds)
    while True:
        try:
            for location_id in _cycle_locations(session_factory, location_ids):
                _run_one_location(session_factory, location_id)
        except Exception:  # noqa: BLE001 — one bad cycle must never kill the loop
            LOG.exception("Unhandled error in Live Sync cycle — will retry next interval.")
        time.sleep(interval_seconds)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover — thin CLI wrapper
    from ....database import create_configured_engine, create_session_factory, get_database_url, prepare_new_private_database

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--location-id", type=int, action="append",
                        help="A Clover Location to synchronize; repeat for several. Inactive Locations are skipped.")
    target.add_argument("--all-active-locations", action="store_true",
                        help="Synchronize every active Clover Location, re-read each cycle (CLOVER_MULTISITE_001).")
    parser.add_argument("--interval-seconds", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)
    parser.add_argument(
        "--once", action="store_true",
        help="Run a single cycle and exit, instead of looping forever — for cron/Task Scheduler-driven "
        "invocation rather than a long-running daemon.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    db_url = get_database_url()
    prepare_new_private_database(db_url)  # never migrates an existing database (MIGRATIONS.md)
    engine = create_configured_engine(db_url)
    session_factory = create_session_factory(engine)

    location_ids = None if args.all_active_locations else args.location_id
    if args.once:
        for location_id in _cycle_locations(session_factory, location_ids):
            _run_one_location(session_factory, location_id)
        return 0

    _run_forever(session_factory, location_ids=location_ids, interval_seconds=args.interval_seconds)
    return 0  # unreachable — _run_forever loops until killed


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
