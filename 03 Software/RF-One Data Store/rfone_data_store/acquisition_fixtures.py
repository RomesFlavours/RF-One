"""Validation/test fixtures only — never imported by production code (CLOVER_ACQUISITION_ENGINE_001).

Tips readiness asks the shared Clover acquisition engine whether the nightly download is done for every active
Clover site (`operational_acquisition.describe_nightly_download`). Suites that need it record such a download the
way the engine would have.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from . import models as m
from .ingestion.common import utc_now
from .operational_acquisition import _aware, get_schedule, latest_due_date
from .technical.connectors.clover.acquisition import active_clover_location_ids


def record_nightly_download(session, *, location_id: int, now: datetime | None = None,
                            status: str = m.ACQUISITION_REQUEST_COMPLETE) -> m.OperationalAcquisitionRequest:
    """The nightly download of `location_id` already due at `now` (default: the current moment). Flushes."""
    now = _aware(now or utc_now())
    schedule = get_schedule(session)
    day = latest_due_date(schedule, now)
    due = schedule.due_at(day)
    done = status == m.ACQUISITION_REQUEST_COMPLETE
    row = m.OperationalAcquisitionRequest(
        location_id=location_id, kind=m.ACQUISITION_REQUEST_SCHEDULED, status=status,
        requested_at=due, scheduled_local_date=day, started_at=due, finished_at=due,
        coverage_start=due - timedelta(days=1) if done else None, coverage_end=due if done else None,
        outcome="synthetic test download",
    )
    session.add(row)
    session.flush()
    return row


def cover_every_active_site(session, *, now: datetime | None = None) -> None:
    """The nightly download already due at `now`, COMPLETE for every active Clover site. Flushes."""
    for location_id in active_clover_location_ids(session):
        record_nightly_download(session, location_id=location_id, now=now)
