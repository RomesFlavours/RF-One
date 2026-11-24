"""The shared RF-One Clover acquisition engine (CLOVER_ACQUISITION_ENGINE_001,
Product Owner 2026-11-22).

ONE engine downloads Clover data for every site into the RF-One operational
database. Applications never call the connector: they ask this module.

* **Ordinary download.** One common daily time for every site, set in RF-One
  Settings > Clover download (`get_schedule` / `set_schedule`; initial value
  00:00 America/New_York). At that time, for EVERY active, configured Clover
  site, the engine downloads new records and updates with that site's own
  merchant identity and credentials. One request row per site and date
  (`OperationalAcquisitionRequest`, SCHEDULED) holds that site's outcome; a
  site that fails never stops the other. A download missed while the engine
  was stopped runs as soon as it starts again (same day); the next download
  always starts from the end of the site's last COMPLETE one, so a failed day
  is downloaded again.
* **Coverage.** Only a COMPLETE download records the period it covered
  (`coverage_start`/`coverage_end`). `describe_site_status` gives, per site,
  the last outcome, the last successful download and the covered period.
* **Live download.** Off in ordinary conditions. It starts only when an
  authorized RF-One function asks (`request_live`: an RF-One account holding
  the CLOVER_ACQUISITION access for those sites), uses the same engine, and is
  limited to the requested sites and data (orders, payments, refunds). It
  stops by itself when the request ends or expires.

Execution: `python -m rfone_data_store.operational_acquisition` runs one worker
thread per active site, so a slow or failing site never delays another.
"""

from __future__ import annotations

import argparse
import logging
import signal
import threading
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .ingestion.common import utc_now
from .technical.connectors.clover.acquisition import active_clover_location_ids
from .technical.connectors.clover.correction_sync import ALL_RESOURCES

UTC = timezone.utc
LOG = logging.getLogger("rfone_operational_acquisition")

CLOVER_ACQUISITION_ACCESS_CODE = "CLOVER_ACQUISITION"
DEFAULT_RUN_TIME = time(0, 0)
DEFAULT_TIMEZONE = "America/New_York"
LIVE_INTERVAL = timedelta(seconds=30)
LIVE_MAX_DURATION = timedelta(hours=12)
# Each ordinary download re-reads this much before the end of the previous one
# (Clover write-then-read latency). Upserts make the overlap harmless.
SCHEDULED_OVERLAP = timedelta(minutes=5)
DEFAULT_TICK_SECONDS = 5.0
# A running ordinary download is leased: renewed every minute, taken over by another
# instance only after ten minutes without renewal.
LEASE_DURATION = timedelta(minutes=10)
LEASE_RENEWAL = timedelta(minutes=1)
# The full-scope acquisitions whose COMPLETE window may start a site's first ordinary download
# (see `_starting_acquisitions`). Live Sync is not full scope and never counts.
COMPLETE_STARTING_MODES = ("SYNC_NOW", "BACKFILL")
LOCATION_REFRESH_INTERVAL = timedelta(minutes=1)

ClientFactory = Callable[[int], object] | None


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# The common schedule (Settings > Clover download)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Schedule:
    run_time: time
    timezone: str
    updated_at: datetime | None = None
    updated_by_account_id: int | None = None

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def local_date(self, now: datetime) -> date:
        return _aware(now).astimezone(self.zone).date()

    def due_at(self, local_date: date) -> datetime:
        """The UTC instant of the ordinary download of `local_date`."""
        return datetime.combine(local_date, self.run_time, tzinfo=self.zone).astimezone(UTC)

    def next_run(self, now: datetime) -> datetime:
        today = self.local_date(now)
        due = self.due_at(today)
        return due if due > _aware(now) else self.due_at(today + timedelta(days=1))



def get_schedule(session: Session) -> Schedule:
    row = session.scalars(select(m.OperationalAcquisitionSchedule).order_by(m.OperationalAcquisitionSchedule.id)).first()
    if row is None:  # the migration seeds the row; a model-built database starts from the same value
        return Schedule(DEFAULT_RUN_TIME, DEFAULT_TIMEZONE)
    return Schedule(row.run_time, row.timezone, _aware(row.updated_at), row.updated_by_account_id)


def set_schedule(session: Session, *, run_time: time, timezone_name: str | None = None,
                 account_id: int | None = None) -> Schedule:
    """Changes the common daily time. Flushes; the caller commits. A download
    already done today is not repeated: the new time applies from the next
    download not yet run."""
    current = get_schedule(session)
    timezone_name = (timezone_name or current.timezone).strip()
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Unknown timezone {timezone_name!r}.") from exc
    run_time = run_time.replace(second=0, microsecond=0, tzinfo=None)
    row = session.scalars(select(m.OperationalAcquisitionSchedule).order_by(m.OperationalAcquisitionSchedule.id)).first()
    if row is None:
        row = m.OperationalAcquisitionSchedule(run_time=run_time, timezone=timezone_name)
        session.add(row)
    row.run_time, row.timezone = run_time, timezone_name
    row.updated_by_account_id = account_id
    row.updated_at = utc_now()
    session.flush()
    return get_schedule(session)


# ---------------------------------------------------------------------------
# Live requests (what authorized functions call)
# ---------------------------------------------------------------------------


class LiveRequestNotAuthorized(PermissionError):
    pass


def _authorize_live(session: Session, account, location_ids: list[int]) -> None:
    from . import rfone_web_session

    if account is None or not rfone_web_session.account_may_enter_domain(session, account, CLOVER_ACQUISITION_ACCESS_CODE):
        raise LiveRequestNotAuthorized("A Live download needs an RF-One account with the Clover Acquisition access.")
    try:
        from . import site_selection
    except ImportError:  # a release without per-company site scope: the access covers every Clover site
        allowed = set(active_clover_location_ids(session))
    else:
        allowed = {site.location_id
                   for site in site_selection.sites_for_account(session, account, CLOVER_ACQUISITION_ACCESS_CODE)}
    refused = [location_id for location_id in location_ids if location_id not in allowed]
    if refused:
        raise LiveRequestNotAuthorized(f"The account may not download these sites: {refused}.")


def request_live(
    session: Session, *, account, application: str, location_ids, live_until: datetime,
    resources=ALL_RESOURCES, now: datetime | None = None,
) -> list[m.OperationalAcquisitionRequest]:
    """An authorized RF-One function (`application`, acting for `account`)
    needs live data of `location_ids`, limited to `resources`, until
    `live_until`. One ACTIVE request per site. Flushes; the caller commits.
    Raises `LiveRequestNotAuthorized` / `ValueError`; nothing is written then."""
    now = _aware(now or utc_now())
    application = (application or "").strip().upper()
    if not application:
        raise ValueError("The requesting RF-One function must be named.")
    location_ids = sorted(set(location_ids or ()))
    if not location_ids:
        raise ValueError("A Live download needs at least one site.")
    asked = set(resources or ())
    if not asked or asked - set(ALL_RESOURCES):
        raise ValueError(f"Choose the data among {ALL_RESOURCES}.")
    resources = tuple(r for r in ALL_RESOURCES if r in asked)
    live_until = _aware(live_until)
    if live_until <= now or live_until - now > LIVE_MAX_DURATION:
        raise ValueError(f"A Live download lasts between now and {LIVE_MAX_DURATION} from now.")
    _authorize_live(session, account, location_ids)
    clover = set(active_clover_location_ids(session))
    inactive = [location_id for location_id in location_ids if location_id not in clover]
    if inactive:
        raise ValueError(f"These sites are not active Clover sites: {inactive}.")
    rows = []
    for location_id in location_ids:
        row = m.OperationalAcquisitionRequest(
            location_id=location_id, kind=m.ACQUISITION_REQUEST_LIVE, status=m.ACQUISITION_REQUEST_ACTIVE,
            requested_by_application=application, requested_by_account_id=account.id, requested_at=now,
            resources=",".join(resources), live_until=live_until,
        )
        session.add(row)
        rows.append(row)
    session.flush()
    return rows


def end_live(session: Session, *, request_ids, now: datetime | None = None) -> None:
    """The function no longer needs live data. Flushes; the caller commits."""
    for request_id in request_ids:
        request = session.get(m.OperationalAcquisitionRequest, request_id)
        if request is not None and request.kind == m.ACQUISITION_REQUEST_LIVE \
                and request.status == m.ACQUISITION_REQUEST_ACTIVE:
            request.status = m.ACQUISITION_REQUEST_ENDED
            request.finished_at = _aware(now or utc_now())
    session.flush()


# ---------------------------------------------------------------------------
# Per-site status
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SiteStatus:
    location_id: int
    name: str
    active: bool
    last_attempt: m.OperationalAcquisitionRequest | None
    last_success: m.OperationalAcquisitionRequest | None
    covered_from: datetime | None
    covered_through: datetime | None
    live_active: bool = False
    timezone: str | None = None


def describe_site_status(session: Session, location_id: int) -> SiteStatus:
    """The ordinary download of one site: last outcome, last successful
    download, and the continuous period covered by COMPLETE downloads up to
    it. Read-only."""
    location = session.get(m.Location, location_id)
    R = m.OperationalAcquisitionRequest
    scheduled = (R.location_id == location_id, R.kind == m.ACQUISITION_REQUEST_SCHEDULED)
    last_attempt = session.scalars(
        select(R).where(*scheduled, R.status.in_((m.ACQUISITION_REQUEST_COMPLETE, m.ACQUISITION_REQUEST_FAILED,
                                                  m.ACQUISITION_REQUEST_RUNNING)))
        .order_by(R.id.desc())).first()
    complete = session.scalars(
        select(R).where(*scheduled, R.status == m.ACQUISITION_REQUEST_COMPLETE, R.coverage_end.is_not(None))
        .order_by(R.coverage_end.desc())).all()
    covered_from = covered_through = None
    if complete:
        covered_through = _aware(complete[0].coverage_end)
        covered_from = _aware(complete[0].coverage_start)
        for row in complete[1:]:
            if _aware(row.coverage_end) >= covered_from:
                covered_from = min(covered_from, _aware(row.coverage_start))
            else:
                break
    live = session.scalar(select(R.id).where(R.location_id == location_id, R.kind == m.ACQUISITION_REQUEST_LIVE,
                                             R.status == m.ACQUISITION_REQUEST_ACTIVE).limit(1))
    return SiteStatus(
        location_id=location_id, name=location.name if location else str(location_id),
        active=location_id in set(active_clover_location_ids(session)),
        last_attempt=last_attempt, last_success=complete[0] if complete else None,
        covered_from=covered_from, covered_through=covered_through, live_active=live is not None,
        timezone=location.timezone if location else None,
    )


def _starting_acquisitions(session: Session, location_id: int) -> list[m.IngestionRun]:
    """The COMPLETE full-scope acquisitions a site's ordinary downloads may
    start from: a Historical Backfill at any time; a Sync Now only if it
    started before the site's first ordinary download was recorded. A Sync Now
    run by the engine itself counts only through its own download's outcome
    (a download that imported new records and then failed on updates never
    becomes a starting point or coverage)."""
    R = m.OperationalAcquisitionRequest
    first_request = _aware(session.scalar(select(func.min(R.requested_at)).where(
        R.location_id == location_id, R.kind == m.ACQUISITION_REQUEST_SCHEDULED)))
    runs = session.scalars(select(m.IngestionRun).where(
        m.IngestionRun.location_id == location_id, m.IngestionRun.status == "COMPLETE",
        m.IngestionRun.resource_type.is_(None), m.IngestionRun.source_window_end.is_not(None),
        m.IngestionRun.acquisition_mode.in_(COMPLETE_STARTING_MODES))).all()
    return [run for run in runs if run.acquisition_mode == "BACKFILL" or first_request is None
            or _aware(run.started_at) < first_request]


@dataclass(frozen=True)
class DataCoverage:
    ready: bool
    reason: str


def latest_due_date(schedule: Schedule, now: datetime) -> date:
    """The local date of the latest ordinary download already due at `now`."""
    today = schedule.local_date(now)
    return today if _aware(now) >= schedule.due_at(today) else today - timedelta(days=1)


def describe_nightly_download(session: Session, *, now: datetime | None = None) -> DataCoverage:
    """Whether the latest nightly (ordinary) download already due completed
    for EVERY active Clover site. Product Owner 2026-11-23: once the nightly
    download is done, Tips are ready to be processed; Tips wait for every
    active site (people work at several restaurants, tips are summed per
    person). An inactive site is not required. Read-only."""
    now = _aware(now or utc_now())
    location_ids = active_clover_location_ids(session)
    if not location_ids:
        # Same rule as before the engine: without any Clover-sourced site there is no Clover data to wait for.
        return DataCoverage(True, "no active Clover site: no Clover data to wait for")
    day = latest_due_date(get_schedule(session), now)
    R = m.OperationalAcquisitionRequest
    for location_id in location_ids:
        status = session.scalar(select(R.status).where(
            R.location_id == location_id, R.kind == m.ACQUISITION_REQUEST_SCHEDULED, R.scheduled_local_date == day))
        if status != m.ACQUISITION_REQUEST_COMPLETE:
            location = session.get(m.Location, location_id)
            return DataCoverage(False, f"{location.name if location else location_id}: the nightly Clover download "
                                       f"of {day.isoformat()} has not completed ({status or 'not started'})")
    return DataCoverage(True, f"the nightly Clover download of {day.isoformat()} completed for every active site")


def clover_site_location_ids(session: Session) -> list[int]:
    """Every Clover site (active or not), for the status page."""
    rows = session.execute(
        select(m.Location.id).join(m.SourceSystem, m.SourceSystem.id == m.Location.source_system_id)
        .where(m.SourceSystem.code == "CLOVER", m.Location.source_location_id.is_not(None))
        .order_by(m.Location.id)).scalars().all()
    return list(rows)


# ---------------------------------------------------------------------------
# The engine: one worker per site
# ---------------------------------------------------------------------------


@dataclass
class LocationWorker:
    """Everything the engine does for ONE site. `tick` performs at most one
    download and returns its outcome (or None when nothing was due).

    Each worker has its own `instance_id`. An ordinary download is claimed
    with a lease (`claimed_by`, `lease_until`) that the running worker renews
    while it works; another instance may take it over only once the lease has
    expired, and only the worker still holding the claim records the outcome."""

    session_factory: sessionmaker[Session]
    location_id: int
    client_factory: ClientFactory = None
    last_live_cycle_at: datetime | None = None
    instance_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def _client(self):
        return self.client_factory(self.location_id) if self.client_factory else None

    def recover_interrupted(self, now: datetime | None = None) -> None:
        """A download whose lease has expired (its engine stopped) becomes
        PENDING again. A download still leased by a live instance is left alone."""
        now = _aware(now or utc_now())
        R = m.OperationalAcquisitionRequest
        with self.session_factory() as session:
            session.execute(
                update(R).execution_options(synchronize_session=False).where(R.location_id == self.location_id, R.status == m.ACQUISITION_REQUEST_RUNNING,
                                or_(R.lease_until.is_(None), R.lease_until < now))
                .values(status=m.ACQUISITION_REQUEST_PENDING, claimed_by=None, lease_until=None)
            )
            session.commit()

    def _ensure_day(self, session: Session, local_date: date, now: datetime) -> None:
        R = m.OperationalAcquisitionRequest
        exists = session.scalar(select(R.id).where(
            R.location_id == self.location_id, R.kind == m.ACQUISITION_REQUEST_SCHEDULED,
            R.scheduled_local_date == local_date))
        if exists is not None:
            return
        session.add(R(location_id=self.location_id, kind=m.ACQUISITION_REQUEST_SCHEDULED,
                      status=m.ACQUISITION_REQUEST_PENDING, requested_at=now, scheduled_local_date=local_date))
        try:
            session.commit()
        except IntegrityError:  # another instance recorded this day first
            session.rollback()

    def _ensure_scheduled(self, session: Session, now: datetime) -> None:
        """Today's download once its time has come; before that, yesterday's
        download if it was missed (the engine was stopped at that time)."""
        schedule = get_schedule(session)
        today = schedule.local_date(now)
        if now >= schedule.due_at(today):
            self._ensure_day(session, today, now)
        else:
            self._ensure_day(session, today - timedelta(days=1), now)

    def _claim_scheduled(self, session: Session, now: datetime) -> m.OperationalAcquisitionRequest | None:
        R = m.OperationalAcquisitionRequest
        candidate = session.scalars(select(R).where(
            R.location_id == self.location_id, R.kind == m.ACQUISITION_REQUEST_SCHEDULED,
            or_(R.status == m.ACQUISITION_REQUEST_PENDING,
                and_(R.status == m.ACQUISITION_REQUEST_RUNNING, R.lease_until < now))).order_by(R.id)).first()
        if candidate is None:
            return None
        claimed = session.execute(
            update(R).execution_options(synchronize_session=False).where(R.id == candidate.id, or_(
                R.status == m.ACQUISITION_REQUEST_PENDING,
                and_(R.status == m.ACQUISITION_REQUEST_RUNNING, R.lease_until < now)))
            .values(status=m.ACQUISITION_REQUEST_RUNNING, started_at=now, attempts=R.attempts + 1,
                    claimed_by=self.instance_id, lease_until=now + LEASE_DURATION)
        ).rowcount
        session.commit()
        if claimed != 1:
            return None
        session.refresh(candidate)
        return candidate

    def _scheduled_start(self, session: Session) -> datetime | None:
        """The end of this site's last COMPLETE ordinary download, minus the
        overlap; else the end of the site's last starting acquisition
        (`_starting_acquisitions`) — never one that ended PARTIAL or FAILED,
        nor the import of an ordinary download that failed. None = no
        starting point."""
        R = m.OperationalAcquisitionRequest
        last_end = session.scalar(select(R.coverage_end).where(
            R.location_id == self.location_id, R.kind == m.ACQUISITION_REQUEST_SCHEDULED,
            R.status == m.ACQUISITION_REQUEST_COMPLETE, R.coverage_end.is_not(None))
            .order_by(R.coverage_end.desc()).limit(1))
        if last_end is not None:
            return _aware(last_end) - SCHEDULED_OVERLAP
        ends = [_aware(run.source_window_end) for run in _starting_acquisitions(session, self.location_id)]
        return max(ends) if ends else None

    def _renew_lease(self, request_id: int, stop: threading.Event) -> None:
        while not stop.wait(LEASE_RENEWAL.total_seconds()):
            try:
                with self.session_factory() as session:
                    R = m.OperationalAcquisitionRequest
                    session.execute(update(R).execution_options(synchronize_session=False).where(R.id == request_id, R.claimed_by == self.instance_id,
                                                    R.status == m.ACQUISITION_REQUEST_RUNNING)
                                    .values(lease_until=utc_now() + LEASE_DURATION))
                    session.commit()
            except Exception:  # noqa: BLE001 — a missed renewal is retried; only a long silence expires the lease
                LOG.warning("location_id=%s: lease renewal of download %s failed — will retry.",
                            self.location_id, request_id)

    def _run_scheduled(self, session: Session, request: m.OperationalAcquisitionRequest,
                       now: datetime) -> shared_cycle.CycleOutcome:
        from .technical.connectors.clover import shared_cycle  # only the engine process downloads
        request_id = request.id
        start = self._scheduled_start(session)
        session.commit()  # hold no transaction while Clover is read
        stop = threading.Event()
        renewer = threading.Thread(target=self._renew_lease, args=(request_id, stop), daemon=True,
                                   name=f"acquisition-lease-{request_id}")
        renewer.start()
        try:
            outcome = shared_cycle.run_location_cycle(
                session, location_id=self.location_id, trigger=shared_cycle.TRIGGER_SCHEDULED, start=start,
                client=self._client(), now=now, session_factory=self.session_factory,
            )
        finally:
            stop.set()
            renewer.join(timeout=5)
        session.rollback()  # nothing of the download is pending; start the bookkeeping clean
        R = m.OperationalAcquisitionRequest
        done = outcome.status == shared_cycle.OUTCOME_COMPLETE
        if outcome.status == shared_cycle.OUTCOME_BUSY:
            values = dict(status=m.ACQUISITION_REQUEST_PENDING, claimed_by=None, lease_until=None)
        else:
            values = dict(
                status=m.ACQUISITION_REQUEST_COMPLETE if done else m.ACQUISITION_REQUEST_FAILED,
                finished_at=utc_now(), claimed_by=None, lease_until=None,
                coverage_start=outcome.coverage_start if done else None,
                coverage_end=outcome.coverage_end if done else None,
            )
        values["outcome"] = outcome.summary
        if outcome.ingestion_run_id is not None:
            values["ingestion_run_id"] = outcome.ingestion_run_id
        # Only the worker still holding the claim records the outcome.
        recorded = session.execute(update(R).execution_options(synchronize_session=False).where(
            R.id == request_id, R.claimed_by == self.instance_id, R.status == m.ACQUISITION_REQUEST_RUNNING
        ).values(**values)).rowcount
        session.commit()
        if recorded != 1:
            LOG.warning("location_id=%s: download %s was taken over by another instance; its outcome (%s) is "
                        "not recorded.", self.location_id, request_id, outcome.status)
        else:
            LOG.info("location_id=%s ordinary download %s: %s — %s", self.location_id, request_id,
                     outcome.status, outcome.summary)
        return outcome

    def _live_requests(self, session: Session, now: datetime) -> list[m.OperationalAcquisitionRequest]:
        R = m.OperationalAcquisitionRequest
        active = session.scalars(select(R).where(
            R.location_id == self.location_id, R.kind == m.ACQUISITION_REQUEST_LIVE,
            R.status == m.ACQUISITION_REQUEST_ACTIVE).order_by(R.id)).all()
        alive = []
        for request in active:
            until = _aware(request.live_until)
            if until is None or until <= now:
                request.status = m.ACQUISITION_REQUEST_ENDED
                request.finished_at = now
            else:
                alive.append(request)
        session.commit()
        return alive

    def tick(self, now: datetime | None = None) -> shared_cycle.CycleOutcome | None:
        from .technical.connectors.clover import shared_cycle  # only the engine process downloads
        now = _aware(now or utc_now())
        with self.session_factory() as session:
            self._ensure_scheduled(session, now)
            request = self._claim_scheduled(session, now)
            if request is not None:
                return self._run_scheduled(session, request, now)
            live = self._live_requests(session, now)
            if not live:
                self.last_live_cycle_at = None  # Live off: the next request starts at once
                return None
            if self.last_live_cycle_at is not None and now - self.last_live_cycle_at < LIVE_INTERVAL:
                return None
            self.last_live_cycle_at = now
            wanted = set()
            for request in live:
                wanted.update((request.resources or "").split(","))
            resources = tuple(r for r in ALL_RESOURCES if r in wanted)
            request_ids = [request.id for request in live]
            session.commit()
            outcome = shared_cycle.run_location_cycle(
                session, location_id=self.location_id, trigger=shared_cycle.TRIGGER_LIVE, resources=resources,
                client=self._client(), now=now, session_factory=self.session_factory,
            )
            session.rollback()
            for request_id in request_ids:
                request = session.get(m.OperationalAcquisitionRequest, request_id)
                request.outcome = f"{now.isoformat()} {outcome.status}: {outcome.summary}"[:4000]
            session.commit()
            LOG.info("location_id=%s Live download (%s): %s — %s", self.location_id, ",".join(resources),
                     outcome.status, outcome.summary)
            return outcome


def _worker_loop(worker: LocationWorker, stop: threading.Event, tick_seconds: float) -> None:
    worker.recover_interrupted()
    while not stop.is_set():
        try:
            worker.tick()
        except Exception:  # noqa: BLE001 — one site's error never stops its worker or another site
            LOG.exception("location_id=%s: unexpected error — will retry.", worker.location_id)
        stop.wait(tick_seconds)


def run_service(
    session_factory: sessionmaker[Session], *, location_ids: list[int] | None = None,
    tick_seconds: float = DEFAULT_TICK_SECONDS, stop: threading.Event | None = None,
    client_factory: ClientFactory = None,
) -> None:
    """Runs until `stop` is set: one worker thread per site — the fixed
    `location_ids`, or every active Clover site re-read each minute so
    activating a site needs no restart."""
    stop = stop or threading.Event()
    workers: dict[int, tuple[threading.Thread, threading.Event]] = {}
    while not stop.is_set():
        try:
            if location_ids is not None:
                wanted = set(location_ids)
            else:
                with session_factory() as session:
                    wanted = set(active_clover_location_ids(session))
            for location_id in sorted(wanted - set(workers)):
                own_stop = threading.Event()
                worker = LocationWorker(session_factory, location_id, client_factory=client_factory)
                thread = threading.Thread(target=_worker_loop, args=(worker, own_stop, tick_seconds),
                                          name=f"acquisition-location-{location_id}", daemon=True)
                thread.start()
                workers[location_id] = (thread, own_stop)
                LOG.info("location_id=%s: worker started.", location_id)
            for location_id in sorted(set(workers) - wanted):
                workers.pop(location_id)[1].set()
                LOG.info("location_id=%s: no longer active — worker stopped.", location_id)
        except Exception:  # noqa: BLE001 — the supervisor never dies on a transient database error
            LOG.exception("Could not refresh the list of sites — will retry.")
        stop.wait(LOCATION_REFRESH_INTERVAL.total_seconds())
    for _thread, own_stop in workers.values():
        own_stop.set()
    for thread, _ in workers.values():
        thread.join(timeout=150)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover — thin process wrapper
    from .database import create_configured_engine, create_session_factory, get_database_url, prepare_new_private_database

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--location-id", type=int, action="append",
                        help="Serve only this site; repeat for several. Default: every active Clover site.")
    parser.add_argument("--tick-seconds", type=float, default=DEFAULT_TICK_SECONDS)
    parser.add_argument("--once", action="store_true", help="Do the work due now for each site once, then exit.")
    parser.add_argument("--skip-migrations", action="store_true",
                        help="Never prepares a database; without it only a brand-new private SQLite file is created.")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(threadName)s %(message)s")
    url = get_database_url()
    if not args.skip_migrations:
        prepare_new_private_database(url)
    session_factory = create_session_factory(create_configured_engine(url))
    if args.once:
        with session_factory() as session:
            ids = args.location_id or active_clover_location_ids(session)
        threads = []
        for location_id in ids:
            worker = LocationWorker(session_factory, location_id)
            worker.recover_interrupted()
            thread = threading.Thread(target=worker.tick, name=f"acquisition-location-{location_id}")
            thread.start()
            threads.append(thread)
        for thread in threads:
            thread.join()
        return 0
    stop = threading.Event()
    try:
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
    except ValueError:
        pass
    run_service(session_factory, location_ids=args.location_id, tick_seconds=args.tick_seconds, stop=stop)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
