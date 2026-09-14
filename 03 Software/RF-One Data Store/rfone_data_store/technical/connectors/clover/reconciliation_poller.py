"""Correction/Reconciliation Poller
(CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md §3-§4).

The required complement to Live Sync (`live_sync.py`), never an
alternative to it: Live Sync only ever revisits records CREATED inside its
own short recent window, so a correction to a record whose `createdTime`
has already scrolled out of that window (a line item voided later, a
payment refunded the next day, an employee reassignment corrected after
the shift, card tips finalizing after `Payment.createdTime`) is
structurally invisible to it, no matter how long it keeps running. This
module closes that gap by polling the SAME `acquisition.import_clover_period()`
fetch/mapping/upsert/concurrency-guard path Live Sync and Historical
Backfill already use, filtered by Clover's `modifiedTime` instead of
`createdTime` (`acquisition.MODE_RECONCILIATION`) — a rolling window over a
DIFFERENT time field, not a wider or slower one, so it eventually catches
every correction regardless of the corrected record's original age. Reuses
the exact same canonical RF-One Data Store — no second database, no Clover
event ledger, no full POS history (doc §1, §3, §8, §11).

Mirrors `live_sync.py`'s own shape deliberately (`compute_next_*_window` /
`run_*_cycle` / `_run_forever` / `main`) — no new scheduling primitive.

Modification Cursor (doc §4): tracked as the latest COMPLETE/PARTIAL
`IngestionRun` whose own `mode == MODE_RECONCILIATION` for this Location —
a SEPARATE cursor track from Live Sync's/Backfill's `createdTime`-window
lineage (which `live_sync.compute_next_sync_window` reads regardless of
mode). The two cursors must never be conflated: a Live Sync/Backfill run
advancing far into the future says nothing about how recently corrections
were last checked, and vice versa.

Location-scoped, not Restaurant-scoped, for the identical reason
`live_sync.py` is: this connector has no concept of Restaurant. Concurrency:
reuses `import_clover_period()`'s own Location-scoped lock — a Reconciliation
cycle and a concurrent Live Sync cycle/Backfill for the same Location can
never write at the same time; a cycle that finds the lock busy simply skips
and retries next tick (cheap, frequent, and safe — see `live_sync.py`'s own
docstring for the identical rationale)."""

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
    MODE_RECONCILIATION,
    CloverReadClient,
    _resolve_clover_merchant,
    import_clover_period,
)

UTC = timezone.utc
LOG = logging.getLogger("clover_reconciliation_poller")

# CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md §3 — "recommended ~60
# seconds, configurable per deployment."
DEFAULT_POLL_INTERVAL_SECONDS = 60.0
# First-ever Reconciliation cycle for a Location (no prior RECONCILIATION-
# mode run at all): starts this far back. Wider than Live Sync's own initial
# lookback (1 hour) because a correction can legitimately surface against a
# record from further back than an hour ago (e.g. "a payment refunded the
# next day") the very first time this poller ever runs for a Location;
# subsequent cycles resume from the checkpoint exactly like Live Sync does,
# so this wide value is paid only once per Location, not every cycle.
DEFAULT_INITIAL_LOOKBACK = timedelta(hours=24)
# Mirrors Live Sync's own overlap buffer rationale exactly (a record whose
# modification settles moments after a prior cycle's fetch must still be
# reliably captured on the very next cycle) — safe by construction, since
# re-checking a slightly wider window than strictly needed can only refresh
# rows via the existing idempotent upsert, never duplicate them.
DEFAULT_OVERLAP_BUFFER = timedelta(minutes=2)


def compute_next_reconciliation_window(
    session: Session, *, location_id: int, now: datetime | None = None,
    initial_lookback: timedelta = DEFAULT_INITIAL_LOOKBACK, overlap_buffer: timedelta = DEFAULT_OVERLAP_BUFFER,
) -> tuple[datetime, datetime] | None:
    """`[period_start, period_end)` for the next Reconciliation cycle —
    the Modification Cursor. `period_end` is always `now`; `period_start`
    resumes from the last COMPLETE/PARTIAL run whose own `mode ==
    MODE_RECONCILIATION` for this Location (never a Live Sync/Backfill run —
    those advance a DIFFERENT cursor, doc §4), minus `overlap_buffer`. On
    the very first Reconciliation cycle ever for this Location, starts from
    `now - initial_lookback` instead. Returns `None` if `location_id` is
    not a Clover-sourced Location at all (the caller should skip it, not
    error) — identical contract to `live_sync.compute_next_sync_window`."""
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
            m.IngestionRun.mode == MODE_RECONCILIATION,
            m.IngestionRun.status.in_(("COMPLETE", "PARTIAL")),
            m.IngestionRun.source_window_end.is_not(None),
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


def run_reconciliation_cycle(
    session: Session, *, location_id: int, client: CloverReadClient | None = None, now: datetime | None = None,
) -> ImportSummary | None:
    """One Reconciliation cycle for one Location. Returns the `ImportSummary`
    on success, or `None` if the cycle was skipped (not a Clover-sourced
    Location, or another acquisition — Backfill, Live Sync, or Reconciliation
    itself — is already RUNNING for this Location right now). A skip is
    never an error: the next cycle simply tries again with a fresh, still-
    correct window — identical contract to `live_sync.run_live_sync_cycle`."""
    window = compute_next_reconciliation_window(session, location_id=location_id, now=now)
    if window is None:
        LOG.info("location_id=%s is not a Clover-sourced Location — skipping this cycle.", location_id)
        return None
    period_start, period_end = window

    try:
        return import_clover_period(
            session, location_id=location_id, period_start=period_start, period_end=period_end,
            client=client, mode=MODE_RECONCILIATION,
        )
    except ImportAlreadyRunningError:
        LOG.info(
            "location_id=%s: another Clover acquisition is already running — skipping this Reconciliation "
            "cycle, will retry next interval.", location_id,
        )
        return None


def _run_forever(
    session_factory: sessionmaker[Session], *, location_id: int, interval_seconds: float,
) -> None:  # pragma: no cover — thin process loop, exercised via run_reconciliation_cycle directly in tests
    LOG.info(
        "Starting Clover Correction/Reconciliation Poller loop for location_id=%s (interval=%.0fs).",
        location_id, interval_seconds,
    )
    while True:
        try:
            with session_factory() as session:
                summary = run_reconciliation_cycle(session, location_id=location_id)
                if summary is not None:
                    session.commit()
                    LOG.info(
                        "Reconciliation cycle complete: payments=%d orders=%d refunds=%d errors=%d",
                        summary.payments_imported + summary.payments_updated,
                        summary.orders_imported + summary.orders_updated,
                        summary.refunds_found, len(summary.errors),
                    )
        except Exception:  # noqa: BLE001 — one bad cycle must never kill the loop
            LOG.exception("Unhandled error in Reconciliation cycle — will retry next interval.")
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
            summary = run_reconciliation_cycle(session, location_id=args.location_id)
            if summary is not None:
                session.commit()
                LOG.info(
                    "Reconciliation cycle complete: payments=%d orders=%d refunds=%d errors=%d",
                    summary.payments_imported + summary.payments_updated,
                    summary.orders_imported + summary.orders_updated,
                    summary.refunds_found, len(summary.errors),
                )
        return 0

    _run_forever(session_factory, location_id=args.location_id, interval_seconds=args.interval_seconds)
    return 0  # unreachable — _run_forever loops until killed


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
