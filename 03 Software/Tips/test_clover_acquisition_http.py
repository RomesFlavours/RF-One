#!/usr/bin/env python
"""HTTP test of the Clover acquisition page (CLOVER_ACQUISITION_JOBS_001):
Sync Now and Historical Backfill are accepted and return at once, the job
continues on its own (QUEUED -> RUNNING -> COMPLETE / FAILED), a second
acquisition is refused while one is in progress, and the page shows the
job history and Live Sync as NOT ACTIVE.

Replaces `test_historical_backfill_error_handling_http.py`, which tested
the acquisition failing INSIDE the request — no longer possible: a failing
acquisition now ends as a FAILED job in the history, never a 500.

Throwaway SQLite + Flask test client + a fake, GET-only Clover client whose
Payments scan can be held open, so "the page returned while the job is
still RUNNING" is observed, not assumed. Never touches AWS or Clover.

Usage:
    python test_clover_acquisition_http.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from datetime import datetime, time as dtime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="tips_clover_acquisition_http_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ.pop("RFONE_CLOVER_LIVE_SYNC_ENABLED", None)

_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as tips_app  # noqa: E402
from sqlalchemy import select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store.clover_acquisition_validation import _FakeResult  # noqa: E402
from rfone_data_store.historical_backfill_extractor_validation import _FullCoverageFakeCloverClient  # noqa: E402
from rfone_data_store.technical.connectors.clover.acquisition_jobs import ThreadLauncher  # noqa: E402

UTC = timezone.utc
MERCHANT = "HTTP-JOBS"


class _GatedClient(_FullCoverageFakeCloverClient):
    """Holds the Payments scan until `gate` is set; can fail it instead."""

    def __init__(self) -> None:
        super().__init__(merchant_id=MERCHANT)
        self.gate = threading.Event()
        self.fail_payments = False
        at = datetime(2026, 9, 2, 1, 30, tzinfo=UTC)
        ms = int(at.timestamp() * 1000)
        self.employees = [{"id": "E1", "name": "Alice", "role": "EMPLOYEE"}]
        self.orders_by_id["O1"] = {
            "id": "O1", "employee": {"id": "E1"}, "createdTime": ms, "modifiedTime": ms, "state": "locked",
            "paymentState": "PAID", "currency": "USD", "total": 5000, "lineItems": {"elements": []},
        }
        self.payments = [{
            "id": "P1", "order": {"id": "O1"}, "employee": {"id": "E1"}, "amount": 5000, "taxAmount": 0,
            "tipAmount": 700, "createdTime": ms, "modifiedTime": ms, "result": "SUCCESS",
        }]

    def get(self, path, params=None):
        if path.endswith("/payments"):
            self.gate.wait(30)
            if self.fail_payments:
                return _FakeResult(ok=False, error="simulated Clover outage", status_code=503)
        return super().get(path, params)


def _wait_for(predicate, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return False


def _run(run_id: int) -> m.IngestionRun:
    with tips_app.SessionFactory() as s:
        return s.get(m.IngestionRun, run_id)


def _latest_run_id() -> int | None:
    with tips_app.SessionFactory() as s:
        return s.scalar(select(m.IngestionRun.id).order_by(m.IngestionRun.id.desc()).limit(1))


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        if not condition:
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    with tips_app.SessionFactory() as s:
        source_system = m.SourceSystem(code="CLOVER", name="Clover")
        s.add(source_system)
        s.flush()
        merchant = m.Merchant(name="HTTP Jobs Merchant", source_system_id=source_system.id, source_merchant_id=MERCHANT)
        s.add(merchant)
        s.flush()
        location = m.Location(
            merchant_id=merchant.id, name="HTTP Jobs Location", source_system_id=source_system.id,
            source_location_id=MERCHANT, currency="USD", timezone="America/New_York",
            operating_day_cutoff_time=dtime(4, 0),
        )
        s.add(location)
        s.flush()
        restaurant = m.Restaurant(name="HTTP Jobs Restaurant", default_currency="USD")
        s.add(restaurant)
        s.flush()
        s.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
        s.commit()

    clover = _GatedClient()
    launcher = ThreadLauncher(tips_app.SessionFactory, client=clover)
    tips_app.clover_job_launcher = launcher
    web = tips_app.app.test_client()

    page = web.get("/")
    check("the page opens", page.status_code == 200, f"status={page.status_code}")
    check("the page offers Sync Now and Historical Backfill as two separate actions",
          b">Sync Now</button>" in page.data and b">Run Historical Backfill</button>" in page.data)
    check("Live Sync is shown as NOT ACTIVE", b"NOT ACTIVE" in page.data)
    check("Sync Now is unavailable until a starting point exists (never synced, never backfilled)",
          b'id="sync-now-btn" disabled' in page.data)

    # --- A / F / H: Historical Backfill returns at once, job continues ----
    t0 = time.monotonic()
    resp = web.post("/historical-backfill", data={"from_date": "2026-09-01", "through_date": "2026-09-03"})
    elapsed = time.monotonic() - t0
    check("A: Run Historical Backfill returns immediately (redirect, not a wait)",
          resp.status_code in (302, 303) and elapsed < 3.0, f"status={resp.status_code} elapsed={elapsed:.2f}s")
    backfill_id = _latest_run_id()
    check("H: the Backfill job is RUNNING while Clover is still being read",
          _wait_for(lambda: _run(backfill_id).status == "RUNNING"))
    run = _run(backfill_id)
    check("F: the job covers exactly the chosen dates (through the end of the Through day)",
          run.source_window_start.strftime("%Y-%m-%d %H:%M:%S") == "2026-09-01 00:00:00"
          and run.source_window_end.strftime("%Y-%m-%d %H:%M:%S") == "2026-09-03 23:59:59")

    page = web.get("/")
    check("the page is usable during the job and shows it in progress",
          page.status_code == 200 and b"Acquisition in progress" in page.data and b"RUNNING" in page.data)
    status = web.get("/clover-acquisition/status.json").get_json()
    check("the status endpoint reports the running job", status["active_run_id"] == backfill_id)

    # --- E: second acquisition refused ------------------------------------
    resp = web.post("/clover-acquisition/sync-now", follow_redirects=True)
    check("E: Sync Now while a Backfill is RUNNING is refused, with a clear message",
          resp.status_code == 200 and b"already in progress" in resp.data)
    resp = web.post("/historical-backfill", data={"from_date": "2026-09-04", "through_date": "2026-09-05"},
                    follow_redirects=True)
    check("E: a second Backfill while one is RUNNING is refused", b"already in progress" in resp.data)
    check("E: no second job was recorded", _latest_run_id() == backfill_id)

    clover.gate.set()
    check("H: the Backfill job ends COMPLETE on its own", _wait_for(lambda: _run(backfill_id).status == "COMPLETE"))
    page = web.get("/")
    check("the history shows the completed Backfill with its counts",
          b"Historical Backfill" in page.data and b"COMPLETE" in page.data and b"Acquisition in progress" not in page.data)
    with tips_app.SessionFactory() as s:
        order = s.scalars(select(m.Order).filter_by(source_order_id="O1")).one()
        check("I: the acquired Order has its operating day", str(order.business_date) == "2026-09-01")

    # --- B / D: Sync Now, no dates, window from last successful point ----
    clover.gate.clear()
    t0 = time.monotonic()
    resp = web.post("/clover-acquisition/sync-now")
    elapsed = time.monotonic() - t0
    sync_id = _latest_run_id()
    check("B: Sync Now takes no dates and returns immediately",
          resp.status_code in (302, 303) and elapsed < 3.0 and sync_id != backfill_id)
    run = _run(sync_id)
    check("B: Sync Now's window starts at the last successful acquisition (end of the Backfill)",
          run.acquisition_mode == "SYNC_NOW"
          and run.source_window_start.strftime("%Y-%m-%d %H:%M:%S") == "2026-09-03 23:59:59")
    clover.gate.set()
    check("D: Sync Now ends COMPLETE", _wait_for(lambda: _run(sync_id).status == "COMPLETE"))
    sync_end = _run(sync_id).source_window_end

    # --- C: failed Sync Now does not advance the point --------------------
    clover.gate.set()
    clover.fail_payments = True
    web.post("/clover-acquisition/sync-now")
    failed_id = _latest_run_id()
    check("H: a Sync Now whose Clover scan fails ends FAILED", _wait_for(lambda: _run(failed_id).status == "FAILED"))
    check("C: the failed Sync Now started from the previous successful point",
          _run(failed_id).source_window_start == sync_end)
    page = web.get("/")
    check("a failed job is shown in the history with its error — never an Internal Server Error",
          page.status_code == 200 and b"FAILED" in page.data and b"simulated Clover outage" in page.data)
    clover.fail_payments = False
    web.post("/clover-acquisition/sync-now")
    retry_id = _latest_run_id()
    check("C: the next Sync Now starts again from the same successful point",
          _run(retry_id).source_window_start == sync_end)
    _wait_for(lambda: _run(retry_id).status == "COMPLETE")
    launcher.join()

    print(f"Clover acquisition HTTP tests: {'SUCCESS' if not failed else 'FAILURE'} "
          f"({len(passed)} passed, {len(failed)} failed)")
    return 0 if not failed else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        try:
            tips_app._engine.dispose()
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass
