"""Automated synthetic tests for `technical.connectors.clover.acquisition_jobs`
(CLOVER_ACQUISITION_JOBS_001) — how Clover acquisitions are started, windowed
and tracked. The acquisition engine itself is exercised unchanged.

Own disposable database, `_FullCoverageFakeCloverClient` (never contacts
Clover), jobs executed either deterministically (`execute_job` called by the
test after a recording launcher accepted the job) or in a real separate OS
process (`SubprocessLauncher`, scenario "separate process" — arranged so the
engine returns before any Clover call is possible).
"""

from __future__ import annotations

import time
from datetime import datetime, time as dtime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .clover_acquisition_validation import ValidationResult, _FakeResult
from .historical_backfill_extractor_validation import _FullCoverageFakeCloverClient
from .ingestion.common import utc_now
from .technical.connectors.clover import acquisition as acq
from .technical.connectors.clover import acquisition_jobs as jobs

UTC = timezone.utc


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


class _RecordingLauncher:
    """Accepts jobs without starting them, so a test can observe QUEUED and
    then run the job itself, deterministically."""

    def __init__(self) -> None:
        self.run_ids: list[int] = []

    def __call__(self, run_id: int) -> None:
        self.run_ids.append(run_id)


class _FailingPaymentsClient(_FullCoverageFakeCloverClient):
    """Clover answers the Payments scan with an error — the window was never
    scanned, so the engine must end the run FAILED."""

    def get(self, path: str, params: dict[str, Any] | None = None) -> _FakeResult:
        if path.endswith("/payments"):
            return _FakeResult(ok=False, error="simulated Clover outage", status_code=503)
        return super().get(path, params)


def run_validation(session_factory: sessionmaker[Session], *, database_url: str | None = None) -> ValidationResult:
    result = ValidationResult(success=True)
    _test_no_starting_point(session_factory, result)
    _test_backfill_lifecycle_window_and_business_date(session_factory, result)
    _test_sync_now_success_and_failure(session_factory, result)
    _test_concurrent_acquisition_refused(session_factory, result)
    _test_existing_orders_updated_not_duplicated(session_factory, result)
    _test_launch_failure_releases_lock(session_factory, result)
    _test_stale_detection(session_factory, result)
    _test_live_sync_status_not_active_by_default(session_factory, result)
    _test_ecs_launcher_request(result)
    if database_url is not None and database_url.startswith("sqlite"):
        _test_separate_process(session_factory, database_url, result)
    return result


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


def _fixture(session: Session, merchant: str) -> tuple[m.Location, _FullCoverageFakeCloverClient]:
    source_system = session.scalars(select(m.SourceSystem).filter_by(code="CLOVER")).first()
    if source_system is None:
        source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
        session.add(source_system)
        session.flush()
    merchant_row = m.Merchant(source_system_id=source_system.id, source_merchant_id=merchant, name=f"Jobs {merchant}")
    session.add(merchant_row)
    session.flush()
    location = m.Location(
        merchant_id=merchant_row.id, source_system_id=source_system.id, source_location_id=merchant,
        name=f"Jobs {merchant}", currency="USD", timezone="America/New_York", operating_day_cutoff_time=dtime(4, 0),
    )
    session.add(location)
    session.commit()

    client = _FullCoverageFakeCloverClient(merchant_id=merchant)
    client.employees = [{"id": f"{merchant}-EMP", "name": "Alice", "role": "EMPLOYEE"}]
    return location, client


def _add_order(client: _FullCoverageFakeCloverClient, merchant: str, n: int, at: datetime, tip: int) -> None:
    order_id, payment_id = f"{merchant}-O{n}", f"{merchant}-P{n}"
    client.orders_by_id[order_id] = {
        "id": order_id, "employee": {"id": f"{merchant}-EMP"}, "createdTime": _ms(at), "modifiedTime": _ms(at),
        "state": "locked", "paymentState": "PAID", "currency": "USD", "total": 5000, "lineItems": {"elements": []},
    }
    client.payments = [p for p in client.payments if p["id"] != payment_id] + [{
        "id": payment_id, "order": {"id": order_id}, "employee": {"id": f"{merchant}-EMP"},
        "amount": 5000, "taxAmount": 0, "tipAmount": tip, "createdTime": _ms(at), "modifiedTime": _ms(at),
        "result": "SUCCESS",
    }]


def _run_job(session_factory: sessionmaker[Session], run_id: int, client: Any) -> m.IngestionRun:
    jobs.execute_job(session_factory, run_id, client=client)
    with session_factory() as s:
        return s.get(m.IngestionRun, run_id)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def _test_no_starting_point(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    with session_factory() as s:
        location, _client = _fixture(s, "JOBS0")
        try:
            jobs.request_sync_now(s, location_id=location.id, launcher=_RecordingLauncher())
            refused = False
        except jobs.NoSyncStartingPointError:
            refused = True
        result.check("Sync Now on a never-synchronized, never-backfilled location is refused with a clear reason", refused)
        result.check(
            "the refused Sync Now left no job and no lock behind",
            jobs.get_active_run(s, location_id=location.id) is None,
        )


def _test_backfill_lifecycle_window_and_business_date(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    with session_factory() as s:
        location, client = _fixture(s, "JOBS1")
        start, end = datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 9, 3, 23, 59, 59, tzinfo=UTC)
        _add_order(client, "JOBS1", 1, datetime(2026, 9, 2, 1, 30, tzinfo=UTC), tip=700)  # 21:30 NY on 9/1
        launcher = _RecordingLauncher()

        t0 = time.monotonic()
        run = jobs.request_historical_backfill(
            s, location_id=location.id, period_start=start, period_end=end, launcher=launcher,
        )
        elapsed = time.monotonic() - t0
        result.check("A: accepting a Historical Backfill returns immediately (no acquisition inside the call)",
                     elapsed < 2.0 and client.calls == [])
        result.check("H: an accepted job is QUEUED and was handed to the launcher",
                     run.status == "QUEUED" and launcher.run_ids == [run.id] and run.queued_at is not None)
        result.check("F: the job records exactly the chosen period",
                     acq._aware_utc(run.source_window_start) == start and acq._aware_utc(run.source_window_end) == end)
        result.check("the job's type is recorded as a column (BACKFILL)", run.acquisition_mode == "BACKFILL")

    seen_running: list[str] = []

    class _ObservingClient(type(client)):
        pass

    def _observe(path: str, params: Any = None, _orig=client.get):
        if not seen_running:
            with session_factory() as s2:
                seen_running.append(s2.get(m.IngestionRun, run.id).status)
        return _orig(path, params)

    client.get = _observe  # type: ignore[method-assign]
    final = _run_job(session_factory, run.id, client)
    result.check("H: while the acquisition works, the job is RUNNING", seen_running == ["RUNNING"])
    result.check("H: the job ends COMPLETE and releases the lock",
                 final.status == "COMPLETE" and final.lock_key is None and final.finished_at is not None)
    result.check("the job history records orders/payments/shifts processed",
                 final.orders_processed == 1 and final.payments_processed == 1 and final.shifts_processed == 0)
    payments_call = next(p for path, p in client.calls if path.endswith("/payments") and p and "filter" in p)
    result.check("F: Clover was asked for exactly the chosen period",
                 payments_call["filter"] == [f"createdTime>={_ms(start)}", f"createdTime<={_ms(end)}"])
    with session_factory() as s:
        order = s.scalars(select(m.Order).filter_by(source_order_id="JOBS1-O1")).one()
        result.check("I: the acquired Order leaves with its operating day (21:30 New York -> 2026-09-01)",
                     str(order.business_date) == "2026-09-01")
    result.check("a job that already ran is never executed a second time",
                 jobs.execute_job(session_factory, run.id, client=client) is None)


def _test_sync_now_success_and_failure(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    with session_factory() as s:
        location, client = _fixture(s, "JOBS2")
        backfill_end = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)
        bf = jobs.request_historical_backfill(
            s, location_id=location.id, period_start=datetime(2026, 9, 9, tzinfo=UTC), period_end=backfill_end,
            launcher=_RecordingLauncher(),
        )
        location_id = location.id
    _run_job(session_factory, bf.id, client)

    now1 = datetime(2026, 9, 10, 12, 30, tzinfo=UTC)
    with session_factory() as s:
        point = jobs.get_last_successful_sync_point(s, location_id=location_id)
        result.check("before any sync, the latest successful Backfill's end is the starting point",
                     point is not None and point.at == backfill_end and point.basis == "BACKFILL")
        failing = _FailingPaymentsClient(merchant_id="JOBS2")
        run = jobs.request_sync_now(s, location_id=location_id, launcher=_RecordingLauncher(), now=now1)
        result.check("B: Sync Now needs no dates — its window is last successful sync -> now (08:00 -> 12:30)",
                     acq._aware_utc(run.source_window_start) == backfill_end
                     and acq._aware_utc(run.source_window_end) == now1 and run.acquisition_mode == "SYNC_NOW")
    failed = _run_job(session_factory, run.id, failing)
    result.check("H: a Sync Now whose Clover scan fails ends FAILED, lock released, error recorded",
                  failed.status == "FAILED" and failed.lock_key is None and bool(failed.error_summary))
    with session_factory() as s:
        point = jobs.get_last_successful_sync_point(s, location_id=location_id)
        result.check("C: a FAILED Sync Now does not move the last successful sync (still 08:00)",
                     point.at == backfill_end)
        now2 = datetime(2026, 9, 10, 12, 45, tzinfo=UTC)
        retry = jobs.request_sync_now(s, location_id=location_id, launcher=_RecordingLauncher(), now=now2)
        result.check("C: the next Sync Now starts again from 08:00 — nothing is skipped",
                     acq._aware_utc(retry.source_window_start) == backfill_end)
    ok = _run_job(session_factory, retry.id, client)
    with session_factory() as s:
        point = jobs.get_last_successful_sync_point(s, location_id=location_id)
        result.check("D: a COMPLETE Sync Now moves the sync point to the end of its window (12:45)",
                     ok.status == "COMPLETE" and point.at == now2 and point.basis == "SYNC")
        later_backfill = jobs.request_historical_backfill(
            s, location_id=location_id, period_start=datetime(2026, 8, 1, tzinfo=UTC),
            period_end=datetime(2026, 8, 2, tzinfo=UTC), launcher=_RecordingLauncher(),
        )
    _run_job(session_factory, later_backfill.id, client)
    with session_factory() as s:
        result.check("a later Backfill of an old period never rewinds the sync point",
                     jobs.get_last_successful_sync_point(s, location_id=location_id).at == now2)


def _test_concurrent_acquisition_refused(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    with session_factory() as s:
        location, client = _fixture(s, "JOBS3")
        first = jobs.request_historical_backfill(
            s, location_id=location.id, period_start=datetime(2026, 9, 1, tzinfo=UTC),
            period_end=datetime(2026, 9, 2, tzinfo=UTC), launcher=_RecordingLauncher(),
        )
        refused = []
        for request in (
            lambda: jobs.request_sync_now(s, location_id=location.id, launcher=_RecordingLauncher()),
            lambda: jobs.request_historical_backfill(
                s, location_id=location.id, period_start=datetime(2026, 9, 3, tzinfo=UTC),
                period_end=datetime(2026, 9, 4, tzinfo=UTC), launcher=_RecordingLauncher(),
            ),
        ):
            try:
                request()
                refused.append(False)
            except (jobs.ImportAlreadyRunningError, jobs.NoSyncStartingPointError):
                refused.append(True)
        result.check("E: while an acquisition is QUEUED, a second Sync Now or Backfill for the same location is refused",
                     refused == [True, True])
        live = jobs.get_active_run(s, location_id=location.id)
        result.check("E: the job already in progress is the one shown", live is not None and live.id == first.id)
        count = s.scalar(select(func.count()).select_from(m.IngestionRun).where(m.IngestionRun.location_id == location.id))
        result.check("E: no second job was recorded", count == 1)
        location_id = location.id
    _run_job(session_factory, first.id, client)
    with session_factory() as s:
        again = jobs.request_sync_now(s, location_id=location_id, launcher=_RecordingLauncher())
        result.check("E: once the first is COMPLETE, a new acquisition can start", again.status == "QUEUED")


def _test_existing_orders_updated_not_duplicated(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    with session_factory() as s:
        location, client = _fixture(s, "JOBS4")
        location_id = location.id
    at = datetime(2026, 9, 5, 18, 0, tzinfo=UTC)
    _add_order(client, "JOBS4", 1, at, tip=500)
    window = dict(period_start=datetime(2026, 9, 5, tzinfo=UTC), period_end=datetime(2026, 9, 5, 23, 59, tzinfo=UTC))
    with session_factory() as s:
        first = jobs.request_historical_backfill(s, location_id=location_id, launcher=_RecordingLauncher(), **window)
    _run_job(session_factory, first.id, client)

    _add_order(client, "JOBS4", 1, at, tip=900)  # tip adjusted in Clover afterwards
    with session_factory() as s:
        second = jobs.request_historical_backfill(s, location_id=location_id, launcher=_RecordingLauncher(), **window)
    _run_job(session_factory, second.id, client)
    with session_factory() as s:
        orders = s.scalars(select(m.Order).filter_by(source_order_id="JOBS4-O1")).all()
        payments = s.scalars(select(m.Payment).filter_by(source_payment_id="JOBS4-P1")).all()
        tip = s.get(m.PaymentTip, payments[0].id) if payments else None
        result.check("G: re-acquiring an Order already present updates it — still exactly one Order and one Payment",
                     len(orders) == 1 and len(payments) == 1)
        result.check("G: the Tip is updated to Clover's current value (5.00 -> 9.00)", tip is not None and tip.amount == 900)


def _test_launch_failure_releases_lock(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    def _broken_launcher(run_id: int) -> None:
        raise OSError("simulated: cannot start process")

    with session_factory() as s:
        location, _client = _fixture(s, "JOBS5")
        try:
            jobs.request_historical_backfill(
                s, location_id=location.id, period_start=datetime(2026, 9, 1, tzinfo=UTC),
                period_end=datetime(2026, 9, 2, tzinfo=UTC), launcher=_broken_launcher,
            )
            raised = False
        except jobs.JobLaunchError:
            raised = True
        run = s.scalars(select(m.IngestionRun).where(m.IngestionRun.location_id == location.id)).one()
        result.check("a job whose process cannot be started is reported, marked FAILED and frees the location",
                     raised and run.status == "FAILED" and run.lock_key is None and "cannot start" in (run.error_summary or ""))


def _test_stale_detection(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    now = utc_now()
    with session_factory() as s:
        location, _client = _fixture(s, "JOBS6")
        run = m.IngestionRun(
            source_system_id=location.source_system_id, location_id=location.id, status="RUNNING",
            started_at=now - timedelta(hours=2), heartbeat_at=now - timedelta(seconds=20),
            lock_key=acq._acquisition_lock_key(location.id), acquisition_mode="BACKFILL",
            notes="CLOVER_ACQUISITION mode=BACKFILL",
        )
        s.add(run)
        s.commit()
        result.check("a long Backfill (2h) that is still heartbeating is NOT treated as dead",
                     jobs.recover_stale_run(s, location_id=location.id) is None)
        run.heartbeat_at = now - timedelta(minutes=10)
        s.commit()
        reaped = jobs.recover_stale_run(s, location_id=location.id)
        s.refresh(run)
        result.check("a RUNNING job silent for 10 minutes is recovered as FAILED by the existing mechanism",
                     reaped == run.id and run.status == "FAILED" and run.lock_key is None)

        queued = m.IngestionRun(
            source_system_id=location.source_system_id, location_id=location.id, status="QUEUED",
            started_at=now - timedelta(minutes=20), queued_at=now - timedelta(minutes=20),
            lock_key=acq._acquisition_lock_key(location.id), acquisition_mode="SYNC_NOW",
            notes="CLOVER_ACQUISITION mode=SYNC_NOW",
        )
        s.add(queued)
        s.commit()
        reaped = jobs.recover_stale_run(s, location_id=location.id)
        s.refresh(queued)
        result.check("a job QUEUED for 20 minutes (its process never started) is recovered as FAILED",
                     reaped == queued.id and queued.status == "FAILED")


def _test_live_sync_status_not_active_by_default(session_factory: sessionmaker[Session], result: ValidationResult) -> None:
    import os

    previous = os.environ.pop(jobs.LIVE_SYNC_ENABLED_ENV, None)
    try:
        with session_factory() as s:
            location, _client = _fixture(s, "JOBS7")
            status = jobs.describe_live_sync(s, location_id=location.id)
            result.check("Live Sync is reported NOT ACTIVE unless explicitly enabled",
                         status.enabled is False and status.active is False)
            result.check("Live Sync's recent window defaults to 2 hours",
                         status.recent_window == timedelta(hours=2))
    finally:
        if previous is not None:
            os.environ[jobs.LIVE_SYNC_ENABLED_ENV] = previous


def _test_ecs_launcher_request(result: ValidationResult) -> None:
    """The AWS launcher asks ECS for exactly one Fargate task running this
    job and nothing else; an ECS refusal is surfaced, never swallowed. A
    fake boto3 client — no AWS call."""
    import boto3

    calls: list[dict[str, Any]] = []
    configs: list[Any] = []
    answers = [{"tasks": [{"taskArn": "arn:task/1"}], "failures": []}, {"tasks": [], "failures": [{"reason": "RESOURCE"}]}]

    class _FakeEcs:
        def run_task(self, **kwargs: Any) -> dict[str, Any]:
            calls.append(kwargs)
            return answers[len(calls) - 1]

    original = boto3.client
    boto3.client = lambda service, **kw: (configs.append(kw.get("config")), _FakeEcs())[1]  # type: ignore[assignment]
    try:
        launcher = jobs.EcsLauncher(
            cluster="c", task_definition="td", subnets=["s1", "s2"], security_groups=["sg"], region_name="us-east-1",
        )
        launcher(42)
        request = calls[0]
        result.check(
            "ECS launcher: one Fargate task, public IP for Clover, the job's security group, run id 42 only",
            request["launchType"] == "FARGATE" and request["count"] == 1
            and request["networkConfiguration"]["awsvpcConfiguration"] == {
                "subnets": ["s1", "s2"], "securityGroups": ["sg"], "assignPublicIp": "ENABLED"}
            and request["overrides"]["containerOverrides"][0]["command"][-2:] == ["--run-id", "42"],
        )
        try:
            launcher(43)
            surfaced = False
        except RuntimeError:
            surfaced = True
        result.check("ECS launcher: a task ECS refuses to start is reported as an error", surfaced)
        config = configs[0]
        result.check(
            "ECS launcher: bounded timeouts (connect 5s, read 15s, 2 attempts) — an unreachable ECS fails "
            "the request in seconds, never hangs it until the web server kills it",
            config is not None and config.connect_timeout == 5 and config.read_timeout == 15
            and config.retries == {"max_attempts": 2, "mode": "standard"},
        )
    finally:
        boto3.client = original  # type: ignore[assignment]


def _test_separate_process(session_factory: sessionmaker[Session], database_url: str, result: ValidationResult) -> None:
    """The real default launcher: the job is picked up and resolved by a
    separate OS process. The Location stops being Clover-sourced after the
    job is accepted, so the engine returns before any client is created —
    no Clover call is possible."""
    with session_factory() as s:
        location, _client = _fixture(s, "JOBS8")
        run = jobs.request_historical_backfill(
            s, location_id=location.id, period_start=datetime(2026, 9, 1, tzinfo=UTC),
            period_end=datetime(2026, 9, 2, tzinfo=UTC), launcher=_RecordingLauncher(),
        )
        location.source_location_id = None
        s.commit()

    t0 = time.monotonic()
    jobs.SubprocessLauncher(database_url)(run.id)
    launch_time = time.monotonic() - t0
    final = None
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        with session_factory() as s:
            final = s.get(m.IngestionRun, run.id)
            if final.status not in ("QUEUED", "RUNNING"):
                break
        time.sleep(0.5)
    result.check("A: starting the separate process returns at once", launch_time < 2.0)
    result.check("a separate OS process picked the job up and resolved it (FAILED: nothing to acquire), lock released",
                 final is not None and final.status == "FAILED" and final.lock_key is None
                 and "Clover-sourced" in (final.error_summary or ""))
