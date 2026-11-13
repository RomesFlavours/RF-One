"""Clover acquisition jobs — how an acquisition is STARTED, never how Clover
data is acquired (CLOVER_ACQUISITION_JOBS_001).

RF-One has three ways to acquire Clover data. All three run the one,
unchanged acquisition engine (`acquisition.import_clover_period`), the one
Location-scoped lock, and the one `IngestionRun` history:

| Mode                | Window                                              | Trigger                     |
|---------------------|-----------------------------------------------------|-----------------------------|
| Live Sync           | min(last successful sync, now - recent window) → now | a loop, when enabled        |
| Sync Now            | last successful sync → now                          | a person, from any RF-One area |
| Historical Backfill | the dates a person chose                            | a person, for recovery      |

This module owns the part that is the same for every manual trigger:

1. **Accept** (`request_sync_now` / `request_historical_backfill`): refuse if
   an acquisition is already QUEUED/RUNNING for the Location (the existing
   lock, taken here with status QUEUED so the refusal holds from the
   moment a job is accepted), work out the window, record the job, commit,
   hand it to a launcher, and return at once. A web page calling this never
   waits for Clover.
2. **Run** (`execute_job`, in a process of its own): QUEUED -> RUNNING,
   heartbeat, `import_clover_period(..., ingestion_run=<this job>)`, then
   COMPLETE / PARTIAL / FAILED exactly as the engine has always decided.

Sync Now is a central Clover function, not a Tips one: any RF-One area
(Tips, Sales, Payroll, ...) resolves its own Location and calls
`request_sync_now(session, location_id=...)`. There is no per-area sync.

Last successful synchronization (`get_last_successful_sync_point`): the
latest `source_window_end` of a Sync Now or Live Sync run that ended
COMPLETE or PARTIAL. A FAILED run never moves it, so the next attempt
starts again from the same point and nothing is skipped. PARTIAL counts as
successful for the same reason it always has for the Live Sync checkpoint
(`_finalize_import_run`): the window's own Payments/Refunds scans
succeeded; a failed scan is FAILED, never PARTIAL. Until a Location has
ever been synchronized, the end of its latest successful Historical
Backfill is the starting point; a Location with neither must be
backfilled first. A Historical Backfill run later never moves the sync
point — a backfill of an old period must not rewind it.

The launcher is how "a process of its own" is obtained. The default,
`SubprocessLauncher`, starts `python -m <this module> --run-id N` detached
from the web worker, so closing the page, a request timeout, or a web
worker being recycled cannot stop the job. `ThreadLauncher` runs the job in
a background thread of the current process (tests). `EcsLauncher`
starts the job as a one-off AWS ECS Fargate task of the application image —
used on AWS, because App Runner throttles a container's CPU whenever it is
not serving a request and so cannot host work that must continue after
the page is closed. Chosen with `RFONE_CLOVER_JOB_LAUNCHER` (`subprocess`
default, `thread`, or `ecs`).

A process that dies (container replaced, killed) leaves its run QUEUED or
RUNNING with no heartbeat; `acquisition._reap_if_stale` — the existing
recovery mechanism — marks it FAILED within minutes and frees the Location.
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from .... import models as m
from ....ingestion.common import utc_now
from .acquisition import (
    ACTIVE_STATUSES,
    MODE_BACKFILL,
    MODE_LIVE_SYNC,
    MODE_SYNC_NOW,
    STATUS_QUEUED,
    STATUS_RUNNING,
    CloverReadClient,
    ImportAlreadyRunningError,
    _acquire_import_lock,
    _acquisition_lock_key,
    _aware_utc,
    _is_stale,
    _resolve_clover_merchant,
    _safe_error_summary,
    import_clover_period,
    reap_stale_acquisition_run,
)

UTC = timezone.utc
LOG = logging.getLogger("clover_acquisition_jobs")

SUCCESS_STATUSES = ("COMPLETE", "PARTIAL")
# Runs whose successful end IS a synchronization point.
SYNC_POINT_MODES = (MODE_SYNC_NOW, MODE_LIVE_SYNC)
# The modes a person sees in the acquisition history.
HISTORY_MODES = (MODE_BACKFILL, MODE_SYNC_NOW, MODE_LIVE_SYNC)
# The Correction Poller's per-cycle row (`correction_sync.MODE_CORRECTION`,
# spelled here to keep this module free of that import). It runs about
# every minute, so the history lists only its latest finished cycle and its
# recent failed ones — never one row a minute burying Sync Now and Backfill
# (CORRECTION_POLLER_ACTIVATION_001).
MODE_CORRECTION = "CORRECTION"
CORRECTION_FAILURES_IN_HISTORY = 10

HEARTBEAT_INTERVAL = timedelta(seconds=30)

# Live Sync's recent safety window: how far back each cycle re-reads so an
# Order still open, a Payment arriving just after, or a very recent
# correction is not missed. Not a deep historical re-scan.
DEFAULT_LIVE_SYNC_RECENT_WINDOW = timedelta(hours=2)
LIVE_SYNC_WINDOW_ENV = "RFONE_CLOVER_LIVE_SYNC_WINDOW_MINUTES"
# Live Sync is prepared, not switched on: it only counts as enabled when the
# deployment says so explicitly (CLOVER_ACQUISITION_JOBS_001 §19).
LIVE_SYNC_ENABLED_ENV = "RFONE_CLOVER_LIVE_SYNC_ENABLED"
# An enabled Live Sync whose last successful cycle is older than this is
# reported as not actually running.
LIVE_SYNC_ACTIVE_WITHIN = timedelta(minutes=10)

LAUNCHER_ENV = "RFONE_CLOVER_JOB_LAUNCHER"

_DATA_STORE_DIR = Path(__file__).resolve().parents[4]


class NoSyncStartingPointError(RuntimeError):
    """Sync Now was requested for a Location that has never been
    synchronized nor backfilled — there is no point to synchronize from."""


class NotACloverLocationError(ValueError):
    """The Location is not Clover-sourced with a resolved external id."""


class JobLaunchError(RuntimeError):
    """The job was accepted but its process could not be started. The job
    has already been marked FAILED and the Location's lock released."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def live_sync_recent_window() -> timedelta:
    """The configurable Live Sync safety window (default 2 hours)."""
    raw = os.environ.get(LIVE_SYNC_WINDOW_ENV)
    if raw:
        try:
            minutes = int(raw)
            if minutes > 0:
                return timedelta(minutes=minutes)
        except ValueError:
            LOG.warning("%s=%r is not a positive integer — using the default.", LIVE_SYNC_WINDOW_ENV, raw)
    return DEFAULT_LIVE_SYNC_RECENT_WINDOW


def live_sync_enabled() -> bool:
    return os.environ.get(LIVE_SYNC_ENABLED_ENV, "").strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Synchronization point and windows
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SyncPoint:
    at: datetime
    # "SYNC" — the end of a successful Sync Now / Live Sync run.
    # "BACKFILL" — no synchronization yet; the end of the latest
    # successful Historical Backfill is used as the starting point.
    basis: str


def _max_successful_window_end(session: Session, *, location_id: int, modes: tuple[str, ...]) -> datetime | None:
    value = session.scalar(
        select(func.max(m.IngestionRun.source_window_end)).where(
            m.IngestionRun.location_id == location_id,
            m.IngestionRun.status.in_(SUCCESS_STATUSES),
            m.IngestionRun.resource_type.is_(None),
            m.IngestionRun.acquisition_mode.in_(modes),
        )
    )
    return _aware_utc(value) if value is not None else None


def get_last_successful_sync_point(session: Session, *, location_id: int) -> SyncPoint | None:
    """See the module docstring. `None` when the Location has neither a
    successful synchronization nor a successful Historical Backfill."""
    at = _max_successful_window_end(session, location_id=location_id, modes=SYNC_POINT_MODES)
    if at is not None:
        return SyncPoint(at=at, basis="SYNC")
    at = _max_successful_window_end(session, location_id=location_id, modes=(MODE_BACKFILL,))
    if at is not None:
        return SyncPoint(at=at, basis="BACKFILL")
    return None


def compute_sync_now_window(
    session: Session, *, location_id: int, now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Last successful synchronization -> now. Raises
    `NoSyncStartingPointError` if there is no starting point."""
    now = now or utc_now()
    point = get_last_successful_sync_point(session, location_id=location_id)
    if point is None:
        raise NoSyncStartingPointError(
            "RF-One has no completed synchronization or Historical Backfill for this location yet, "
            "so there is no point to synchronize from. Run a Historical Backfill first."
        )
    return point.at, now


def compute_live_sync_window(
    session: Session, *, location_id: int, now: datetime | None = None,
    recent_window: timedelta | None = None,
) -> tuple[datetime, datetime]:
    """now - recent window -> now, reaching further back only when the last
    successful synchronization is older than that (a Live Sync that was
    stopped catches up once, from where it stopped, instead of silently
    skipping the gap)."""
    now = now or utc_now()
    recent_start = now - (recent_window or live_sync_recent_window())
    point = get_last_successful_sync_point(session, location_id=location_id)
    if point is not None and point.at < recent_start:
        return point.at, now
    return recent_start, now


# ---------------------------------------------------------------------------
# Launchers
# ---------------------------------------------------------------------------

Launcher = Callable[[int], None]


class SubprocessLauncher:
    """Starts the job in a detached OS process of its own (default).

    The database URL is handed over through the child's environment, never
    its command line, so it never appears in a process listing. The child
    inherits stdout/stderr, so its log lines reach the same log stream as
    the web app's (e.g. App Runner application logs)."""

    def __init__(self, database_url: str):
        self._database_url = database_url

    def __call__(self, run_id: int) -> None:
        env = dict(os.environ)
        env["RFONE_DATABASE_URL"] = self._database_url
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(_DATA_STORE_DIR), env.get("PYTHONPATH")]))
        kwargs: dict = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(  # noqa: S603 — fixed interpreter + module, run id is an int
            [sys.executable, "-m", "rfone_data_store.technical.connectors.clover.acquisition_jobs",
             "--run-id", str(int(run_id))],
            cwd=str(_DATA_STORE_DIR), env=env, stdin=subprocess.DEVNULL, close_fds=True, **kwargs,
        )


class ThreadLauncher:
    """Runs the job in a background thread of the current process. Used by
    tests; `threads` lets a test wait for completion."""

    def __init__(self, session_factory: sessionmaker[Session], client: CloverReadClient | None = None):
        self._session_factory = session_factory
        self._client = client
        self.threads: list[threading.Thread] = []

    def __call__(self, run_id: int) -> None:
        thread = threading.Thread(
            target=execute_job, args=(self._session_factory, run_id), kwargs={"client": self._client},
            name=f"clover-acquisition-job-{run_id}", daemon=True,
        )
        self.threads.append(thread)
        thread.start()

    def join(self, timeout: float = 30.0) -> None:
        for thread in self.threads:
            thread.join(timeout)


class EcsLauncher:
    """Starts the job as a one-off AWS ECS Fargate task running the
    application image with `python -m <this module> --run-id N` (see
    `03 Software/Infrastructure/deploy/clover-acquisition-job/`). The task
    has its own CPU and lifetime, independent of the web service, and gets
    the database and Clover credentials from its own task definition
    (Secrets Manager) — this launcher hands over only the run id.

    Configuration (environment): `RFONE_CLOVER_JOB_ECS_CLUSTER`,
    `RFONE_CLOVER_JOB_ECS_TASK_DEFINITION`, `RFONE_CLOVER_JOB_ECS_SUBNETS`
    and `RFONE_CLOVER_JOB_ECS_SECURITY_GROUPS` (comma-separated),
    `RFONE_CLOVER_JOB_ECS_CONTAINER` (default `clover-acquisition-job`),
    `RFONE_CLOVER_JOB_ECS_PUBLIC_IP` (`ENABLED` default — the task reaches
    Clover through the subnet's internet gateway)."""

    def __init__(self, *, cluster: str, task_definition: str, subnets: list[str], security_groups: list[str],
                 container: str = "clover-acquisition-job", assign_public_ip: str = "ENABLED",
                 region_name: str | None = None):
        self._cluster = cluster
        self._task_definition = task_definition
        self._subnets = subnets
        self._security_groups = security_groups
        self._container = container
        self._assign_public_ip = assign_public_ip
        self._region_name = region_name or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")

    @classmethod
    def from_environment(cls) -> "EcsLauncher":
        def required(name: str) -> str:
            value = os.environ.get(name, "").strip()
            if not value:
                raise RuntimeError(f"{LAUNCHER_ENV}=ecs requires {name}.")
            return value

        def split(value: str) -> list[str]:
            return [part.strip() for part in value.split(",") if part.strip()]

        return cls(
            cluster=required("RFONE_CLOVER_JOB_ECS_CLUSTER"),
            task_definition=required("RFONE_CLOVER_JOB_ECS_TASK_DEFINITION"),
            subnets=split(required("RFONE_CLOVER_JOB_ECS_SUBNETS")),
            security_groups=split(required("RFONE_CLOVER_JOB_ECS_SECURITY_GROUPS")),
            container=os.environ.get("RFONE_CLOVER_JOB_ECS_CONTAINER", "clover-acquisition-job"),
            assign_public_ip=os.environ.get("RFONE_CLOVER_JOB_ECS_PUBLIC_IP", "ENABLED"),
        )

    def __call__(self, run_id: int) -> None:
        import boto3  # lazily: only a deployment that uses ECS needs AWS credentials
        from botocore.config import Config

        # Short, bounded timeouts: this call runs inside the web request that
        # accepted the job. If ECS cannot be reached, the request must fail
        # in seconds (the job is then marked FAILED) — never hang until the
        # web server kills it, which is exactly the failure this replaces.
        config = Config(connect_timeout=5, read_timeout=15, retries={"max_attempts": 2, "mode": "standard"})
        response = boto3.client("ecs", region_name=self._region_name, config=config).run_task(
            cluster=self._cluster, taskDefinition=self._task_definition, launchType="FARGATE", count=1,
            networkConfiguration={"awsvpcConfiguration": {
                "subnets": self._subnets, "securityGroups": self._security_groups,
                "assignPublicIp": self._assign_public_ip,
            }},
            overrides={"containerOverrides": [{
                "name": self._container,
                "command": ["python", "-m", "rfone_data_store.technical.connectors.clover.acquisition_jobs",
                            "--run-id", str(int(run_id))],
            }]},
            startedBy=f"rfone-clover-job-{int(run_id)}",
        )
        if response.get("failures") or not response.get("tasks"):
            raise RuntimeError(f"ECS could not start the task: {response.get('failures')}")


def default_launcher(session: Session) -> Launcher:
    """The launcher configured for this deployment (`RFONE_CLOVER_JOB_LAUNCHER`)."""
    choice = os.environ.get(LAUNCHER_ENV, "subprocess").strip().lower()
    if choice == "ecs":
        return EcsLauncher.from_environment()
    if choice == "thread":
        from ....database import create_session_factory

        return ThreadLauncher(create_session_factory(session.get_bind()))
    return SubprocessLauncher(session.get_bind().url.render_as_string(hide_password=False))


# ---------------------------------------------------------------------------
# Accepting a job
# ---------------------------------------------------------------------------


def _enqueue(
    session: Session, *, location_id: int, mode: str, period_start: datetime, period_end: datetime,
    launcher: Launcher | None, requested_by_account_id: int | None,
) -> m.IngestionRun:
    merchant = _resolve_clover_merchant(session, location_id)
    if merchant is None:
        raise NotACloverLocationError(f"location_id={location_id} is not a Clover-sourced Location.")
    source_system_id, _merchant_id = merchant

    # Raises ImportAlreadyRunningError when the Location's lock is held
    # (after reaping it first if its holder is stale) — the existing guard.
    run = _acquire_import_lock(
        session, location_id=location_id, source_system_id=source_system_id,
        period_start=period_start, period_end=period_end, mode=mode, status=STATUS_QUEUED,
    )
    run_id = run.id
    # CLOVER_ACQUISITION_IDENTITY_001 — who asked, recorded on the job
    # before anything is launched (the caller has already authenticated
    # and authorized that account).
    if requested_by_account_id is not None:
        run.requested_by_account_id = requested_by_account_id
        session.commit()
    try:
        (launcher or default_launcher(session))(run_id)
    except Exception as exc:  # noqa: BLE001 — never leave an accepted job holding the lock
        session.rollback()
        run = session.get(m.IngestionRun, run_id)
        if run is not None and run.status == STATUS_QUEUED:
            _mark_failed(run, f"Could not start the acquisition process: {_safe_error_summary(exc)}")
            session.commit()
        raise JobLaunchError(_safe_error_summary(exc)) from exc
    return run


def request_sync_now(
    session: Session, *, location_id: int, launcher: Launcher | None = None, now: datetime | None = None,
    requested_by_account_id: int | None = None,
) -> m.IngestionRun:
    """Accept a Sync Now job for `location_id` and start it; returns the
    QUEUED run immediately. Raises `ImportAlreadyRunningError`,
    `NoSyncStartingPointError`, `NotACloverLocationError` or
    `JobLaunchError`.

    This service does not authenticate anyone: a caller exposed to people
    (RF-One Web) must establish and authorize the account BEFORE calling,
    and passes it as `requested_by_account_id`."""
    if _resolve_clover_merchant(session, location_id) is None:
        raise NotACloverLocationError(f"location_id={location_id} is not a Clover-sourced Location.")
    # "Already in progress" is the answer that matters while a job runs —
    # even the first Backfill that will create the starting point. The lock
    # taken in `_enqueue` remains the authoritative guard.
    recover_stale_run(session, location_id=location_id)
    if get_active_run(session, location_id=location_id) is not None:
        raise ImportAlreadyRunningError(f"An import is already in progress for location_id={location_id}.")
    period_start, period_end = compute_sync_now_window(session, location_id=location_id, now=now)
    return _enqueue(
        session, location_id=location_id, mode=MODE_SYNC_NOW,
        period_start=period_start, period_end=period_end, launcher=launcher,
        requested_by_account_id=requested_by_account_id,
    )


def request_historical_backfill(
    session: Session, *, location_id: int, period_start: datetime, period_end: datetime,
    launcher: Launcher | None = None, requested_by_account_id: int | None = None,
) -> m.IngestionRun:
    """Accept a Historical Backfill job for exactly `[period_start,
    period_end]` and start it; returns the QUEUED run immediately. Same
    exceptions as `request_sync_now`, less `NoSyncStartingPointError`."""
    if period_end < period_start:
        raise ValueError("The end of a Historical Backfill period must not be before its start.")
    return _enqueue(
        session, location_id=location_id, mode=MODE_BACKFILL,
        period_start=period_start, period_end=period_end, launcher=launcher,
        requested_by_account_id=requested_by_account_id,
    )


# ---------------------------------------------------------------------------
# Running a job (in its own process)
# ---------------------------------------------------------------------------


def _mark_failed(run: m.IngestionRun, message: str) -> None:
    run.status = "FAILED"
    run.finished_at = utc_now()
    run.lock_key = None
    run.error_summary = message[:2000]
    run.notes = f"{run.notes or ''} | FAILED: {message}"[:4000]


class _Heartbeat:
    """Refreshes `heartbeat_at` on its own connection every
    `HEARTBEAT_INTERVAL` while the job runs. A missed beat (e.g. SQLite's
    single writer busy with the job itself) is harmless; only prolonged
    silence makes the run stale."""

    def __init__(self, session_factory: sessionmaker[Session], run_id: int):
        self._session_factory = session_factory
        self._run_id = run_id
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name=f"clover-job-heartbeat-{run_id}", daemon=True)

    def __enter__(self) -> "_Heartbeat":
        self._thread.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.wait(HEARTBEAT_INTERVAL.total_seconds()):
            try:
                with self._session_factory() as session:
                    session.execute(
                        update(m.IngestionRun)
                        .where(m.IngestionRun.id == self._run_id, m.IngestionRun.status == STATUS_RUNNING)
                        .values(heartbeat_at=utc_now())
                    )
                    session.commit()
            except Exception:  # noqa: BLE001 — a missed beat must never disturb the job
                LOG.debug("Heartbeat for run %s skipped.", self._run_id, exc_info=True)


def execute_job(
    session_factory: sessionmaker[Session], run_id: int, *, client: CloverReadClient | None = None,
) -> str | None:
    """Run one accepted job to completion. Returns the run's final status,
    or `None` if the run was not QUEUED (already started or finished — a
    job is never executed twice)."""
    with session_factory() as session:
        claimed = session.execute(
            update(m.IngestionRun)
            .where(m.IngestionRun.id == run_id, m.IngestionRun.status == STATUS_QUEUED)
            .values(status=STATUS_RUNNING, started_at=utc_now(), heartbeat_at=utc_now())
        ).rowcount
        session.commit()
        if claimed != 1:
            LOG.warning("Acquisition job %s is not QUEUED — not executing it.", run_id)
            return None

        run = session.get(m.IngestionRun, run_id)
        run.notes = f"CLOVER_ACQUISITION mode={run.acquisition_mode} location_id={run.location_id}; RUNNING"
        session.commit()
        LOG.info(
            "Acquisition job %s started: mode=%s location_id=%s window=%s -> %s",
            run_id, run.acquisition_mode, run.location_id, run.source_window_start, run.source_window_end,
        )

        try:
            with _Heartbeat(session_factory, run_id):
                summary = import_clover_period(
                    session, location_id=run.location_id,
                    period_start=_aware_utc(run.source_window_start), period_end=_aware_utc(run.source_window_end),
                    client=client, mode=run.acquisition_mode, ingestion_run=run,
                )
                session.commit()
        except Exception:  # noqa: BLE001 — the engine already recorded FAILED and released the lock
            LOG.exception("Acquisition job %s failed.", run_id)
            session.rollback()
            run = session.get(m.IngestionRun, run_id)
            if run is not None and run.status in ACTIVE_STATUSES:
                _mark_failed(run, "The acquisition process stopped unexpectedly.")
                session.commit()
            return run.status if run is not None else None

        session.refresh(run)
        if run.status in ACTIVE_STATUSES:
            # The engine returned without resolving the run (e.g. the
            # Location stopped being Clover-sourced after the job was
            # accepted) — never leave it holding the lock.
            _mark_failed(run, "; ".join(summary.errors) or "The acquisition did not run.")
            session.commit()
        LOG.info(
            "Acquisition job %s finished: status=%s orders=%s payments=%s shifts=%s",
            run_id, run.status, run.orders_processed, run.payments_processed, run.shifts_processed,
        )
        return run.status


# ---------------------------------------------------------------------------
# Reading the history
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LiveSyncStatus:
    enabled: bool
    active: bool
    last_update: datetime | None
    recent_window: timedelta


def get_active_run(session: Session, *, location_id: int) -> m.IngestionRun | None:
    """The job currently holding this Location's lock (QUEUED or RUNNING)."""
    return session.scalars(
        select(m.IngestionRun).where(
            m.IngestionRun.lock_key == _acquisition_lock_key(location_id),
            m.IngestionRun.status.in_(ACTIVE_STATUSES),
        )
    ).first()


def recover_stale_run(session: Session, *, location_id: int) -> int | None:
    """The existing recovery (`reap_stale_acquisition_run`): a run holding
    the lock with no sign of life is marked FAILED. Safe to call on every
    page view — a live run is never touched."""
    return reap_stale_acquisition_run(session, location_id=location_id)


def list_acquisition_runs(session: Session, *, location_id: int, limit: int = 20) -> list[m.IngestionRun]:
    """The one acquisition history: Sync Now, Historical Backfill and Live
    Sync runs, plus the Correction Poller's latest finished cycle and its
    recent failed cycles, newest first."""
    base = select(m.IngestionRun).where(
        m.IngestionRun.location_id == location_id,
        m.IngestionRun.resource_type.is_(None),
        m.IngestionRun.notes.like("CLOVER_ACQUISITION%"),
    )
    runs = list(session.scalars(
        base.where(or_(m.IngestionRun.acquisition_mode.in_(HISTORY_MODES), m.IngestionRun.acquisition_mode.is_(None)))
        .order_by(m.IngestionRun.id.desc()).limit(limit)
    ))
    corrections = base.where(m.IngestionRun.acquisition_mode == MODE_CORRECTION)
    latest = session.scalars(
        corrections.where(m.IngestionRun.status.not_in(ACTIVE_STATUSES)).order_by(m.IngestionRun.id.desc()).limit(1)
    ).all()
    failed = session.scalars(
        corrections.where(m.IngestionRun.status == "FAILED")
        .order_by(m.IngestionRun.id.desc()).limit(CORRECTION_FAILURES_IN_HISTORY)
    ).all()
    merged = {run.id: run for run in [*runs, *latest, *failed]}
    return sorted(merged.values(), key=lambda run: run.id, reverse=True)


def correction_cycle_resources(session: Session, cycle: m.IngestionRun) -> list[m.IngestionRun]:
    """The Orders/Payments/Refunds cursor rows one Correction cycle wrote —
    what it scanned (window) and how each resource ended. They are created
    after the cycle's own row and before it finished, while it held the
    Location's lock, so no other acquisition's rows can fall in between."""
    if cycle.acquisition_mode != MODE_CORRECTION:
        return []
    query = select(m.IngestionRun).where(
        m.IngestionRun.location_id == cycle.location_id,
        m.IngestionRun.resource_type.is_not(None),
        m.IngestionRun.id > cycle.id,
    )
    if cycle.finished_at is not None:
        query = query.where(m.IngestionRun.started_at <= cycle.finished_at)
    return list(session.scalars(query.order_by(m.IngestionRun.id).limit(3)))


def describe_live_sync(session: Session, *, location_id: int, now: datetime | None = None) -> LiveSyncStatus:
    now = now or utc_now()
    last = session.scalar(
        select(func.max(m.IngestionRun.finished_at)).where(
            m.IngestionRun.location_id == location_id,
            m.IngestionRun.acquisition_mode == MODE_LIVE_SYNC,
            m.IngestionRun.status.in_(SUCCESS_STATUSES),
        )
    )
    last = _aware_utc(last) if last is not None else None
    enabled = live_sync_enabled()
    active = enabled and last is not None and last >= now - LIVE_SYNC_ACTIVE_WITHIN
    return LiveSyncStatus(enabled=enabled, active=active, last_update=last, recent_window=live_sync_recent_window())


def run_is_stale(run: m.IngestionRun) -> bool:
    return run.status in ACTIVE_STATUSES and _is_stale(run)


# ---------------------------------------------------------------------------
# Process entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:  # pragma: no cover — thin process wrapper
    from ....database import create_configured_engine, create_session_factory, get_database_url

    parser = argparse.ArgumentParser(description="Run one accepted Clover acquisition job.")
    parser.add_argument("--run-id", type=int, required=True)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    engine = create_configured_engine(get_database_url())
    try:
        status = execute_job(create_session_factory(engine), args.run_id)
    finally:
        engine.dispose()
    return 0 if status in SUCCESS_STATUSES else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


__all__ = [
    "ImportAlreadyRunningError", "JobLaunchError", "NoSyncStartingPointError", "NotACloverLocationError",
    "EcsLauncher", "SubprocessLauncher", "ThreadLauncher", "SyncPoint", "LiveSyncStatus",
    "compute_live_sync_window", "compute_sync_now_window", "describe_live_sync", "execute_job",
    "correction_cycle_resources", "get_active_run", "get_last_successful_sync_point", "list_acquisition_runs",
    "recover_stale_run",
    "request_historical_backfill", "request_sync_now", "run_is_stale",
]
