"""Central on-demand Clover data freshness service
(TECHNICAL_CONNECTORS_STRUCTURE_001 / CLOVER_DATA_ACQUISITION_ARCHITECTURE_001).

RULE: any Clover-dependent RF-One module (Tips, and in the future Server
Copilot, Server Performance, Sales, etc.) that needs Clover data for a given
Location/date range must call `ensure_clover_data_fresh()` below rather than
call `acquisition.import_clover_period()` — or the Clover API — directly.
This is the one place that decides whether a fetch is actually needed, so
every caller gets the same "already imported? skip; otherwise import, then
proceed" behavior instead of re-implementing its own check.

This is an on-demand, synchronous service only: it never starts Live Sync,
never schedules anything, and introduces no new process. It reuses the
exact same `acquisition.import_clover_period()` fetch/mapping/upsert/
concurrency-guard path Historical Backfill and Live Sync already share —
there is still only one Clover ingestion implementation in this codebase.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .... import models as m
from .acquisition import (
    CloverReadClient,
    ImportSummary,
    MODE_BACKFILL,
    _resolve_clover_merchant,
    import_clover_period,
)

UTC = timezone.utc

STATUS_ALREADY_FRESH = "ALREADY_FRESH"
STATUS_REFRESHED = "REFRESHED"


@dataclass(frozen=True)
class FreshnessResult:
    """The small result `ensure_clover_data_fresh()` returns.

    `summary` is the underlying `ImportSummary` when a fetch actually ran
    (`status == STATUS_REFRESHED`), or `None` when nothing needed fetching
    (`status == STATUS_ALREADY_FRESH`)."""

    status: str
    period_start: datetime
    period_end: datetime
    summary: ImportSummary | None = None


def _aware_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _is_range_covered(
    session: Session, *, location_id: int, source_system_id: int, period_start: datetime, period_end: datetime,
) -> bool:
    """True if this Location's own COMPLETE/PARTIAL Clover acquisition runs
    (Historical Backfill or Live Sync — both populate `IngestionRun.
    source_window_start`/`source_window_end` identically) already cover
    `[period_start, period_end]` end-to-end, with no gap. A single run
    covering the whole range, or several runs whose windows chain/overlap
    with no hole between them, both count as covered."""
    runs = session.scalars(
        select(m.IngestionRun)
        .where(
            m.IngestionRun.location_id == location_id,
            m.IngestionRun.source_system_id == source_system_id,
            m.IngestionRun.status.in_(("COMPLETE", "PARTIAL")),
            m.IngestionRun.source_window_start.is_not(None),
            m.IngestionRun.source_window_end.is_not(None),
        )
        .order_by(m.IngestionRun.source_window_start)
    ).all()

    covered_up_to = period_start
    for run in runs:
        start = _aware_utc(run.source_window_start)
        end = _aware_utc(run.source_window_end)
        if start > covered_up_to:
            break  # a gap starts here; later runs (sorted by start) can't close it
        if end > covered_up_to:
            covered_up_to = end
        if covered_up_to >= period_end:
            return True
    return covered_up_to >= period_end


def ensure_clover_data_fresh(
    session: Session, *, location_id: int, from_date: datetime, through_date: datetime,
    client: CloverReadClient | None = None,
) -> FreshnessResult:
    """Ensures Clover data for `location_id` is available/up to date in the
    canonical database for `[from_date, through_date]`, then returns.

    Freshness check: see `_is_range_covered` — already-recorded COMPLETE/
    PARTIAL acquisition runs for this Location must cover the requested
    range with no gap. If so, returns immediately with `STATUS_ALREADY_FRESH`
    and calls Clover for nothing.

    Otherwise, calls the existing `acquisition.import_clover_period()` for
    exactly the requested `[from_date, through_date]` (mode=BACKFILL, so
    catalog/reference data is refreshed too) and waits for it to complete —
    `import_clover_period` is synchronous, so by the time this returns the
    import has already finished. Commits the session afterwards (matching
    every existing caller of `import_clover_period`, e.g.
    `run_clover_historical_backfill.py`) so the caller can rely on the data
    being durably persisted. Nothing is committed for `STATUS_ALREADY_FRESH`,
    since nothing was written.

    Raises `ValueError` if `location_id` is not a Clover-sourced Location.
    Propagates `ImportAlreadyRunningError` unchanged if another acquisition
    is already RUNNING for this Location — this service does not retry or
    queue on the caller's behalf.
    """
    merchant = _resolve_clover_merchant(session, location_id)
    if merchant is None:
        raise ValueError(f"location_id={location_id} is not a Clover-sourced Location.")
    source_system_id, _merchant_id = merchant

    if _is_range_covered(
        session, location_id=location_id, source_system_id=source_system_id,
        period_start=from_date, period_end=through_date,
    ):
        return FreshnessResult(status=STATUS_ALREADY_FRESH, period_start=from_date, period_end=through_date)

    summary = import_clover_period(
        session, location_id=location_id, period_start=from_date, period_end=through_date,
        client=client, mode=MODE_BACKFILL,
    )
    session.commit()
    return FreshnessResult(
        status=STATUS_REFRESHED, period_start=from_date, period_end=through_date, summary=summary,
    )
