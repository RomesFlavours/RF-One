#!/usr/bin/env python
"""CLOVER_ACQUISITION_IDENTITY_001 — manual Clover acquisitions (Sync Now,
Historical Backfill) may be started only by a signed-in RF-One account
holding the CLOVER_ACQUISITION access, through RF-One Web's real login.

Proves:
  A. unauthenticated: the page sends the person to the normal RF-One login
     with a plain message; Sync Now and Backfill are refused; no job, no
     launch;
  B. a direct POST without a session (even carrying a made-up CSRF token)
     is refused server-side;
  C. signed in WITHOUT the access (BANK only): refused (403); no job, no launch;
     signed in WITH the access but without CSRF: refused (400), no job;
  D. signed in WITH the access: Backfill and Sync Now accepted, each job
     records the requesting account, the page shows "Requested by";
  E. opening the page (and its status poll) never creates a job;
  F. a second acquisition while one is in progress is still refused;
  G. after signing in, the person is returned to Clover Acquisition, and
     `next` can never point to another host;
  H. Home shows Clover Acquisition only to accounts holding the access.

Throwaway SQLite database; a recording launcher stands in for Fargate and a
fake GET-only Clover client runs the one accepted job. Never touches AWS or
Clover.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import datetime, time as dtime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_clover_acquisition_http_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "http-test-secret"
os.environ.pop("RFONE_CLOVER_LIVE_SYNC_ENABLED", None)

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.historical_backfill_extractor_validation import _FullCoverageFakeCloverClient  # noqa: E402
from rfone_data_store.technical.connectors.clover import acquisition_jobs as jobs  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
HOST = "https://rfone-web.example"
PASSWORD = "a-long-enough-test-password"
MERCHANT = "IDENT-MERCH-1"


class RecordingLauncher:
    """Stands in for Fargate: records every launch, starts nothing."""

    def __init__(self) -> None:
        self.run_ids: list[int] = []

    def __call__(self, run_id: int) -> None:
        self.run_ids.append(run_id)


def csrf(html: bytes) -> str | None:
    match = CSRF_RE.search(html.decode("utf-8"))
    return match.group(1) if match else None


def login(client, username: str, next_path: str | None = None):
    page = client.get("/login" + (f"?next={next_path}" if next_path else ""), base_url=HOST)
    data = {"username": username, "password": PASSWORD, "csrf_token": csrf(page.data)}
    if next_path:
        data["next"] = next_path
    return client.post("/login", base_url=HOST, data=data)


def job_count() -> int:
    with SessionFactory() as s:
        return s.scalar(select(func.count()).select_from(m.IngestionRun))


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with SessionFactory() as s:
        source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
        s.add(source_system)
        s.flush()
        merchant = m.Merchant(source_system_id=source_system.id, source_merchant_id=MERCHANT, name="Identity Merchant")
        s.add(merchant)
        s.flush()
        location = m.Location(
            merchant_id=merchant.id, source_system_id=source_system.id, source_location_id=MERCHANT,
            name="Identity Test Location", currency="USD", timezone="America/New_York",
            operating_day_cutoff_time=dtime(4, 0),
        )
        s.add(location)
        s.flush()
        restaurant = m.Restaurant(name="Identity Test Restaurant", default_currency="USD")
        s.add(restaurant)
        s.flush()
        s.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
        operator = account_service.create_account(s, username="clover-operator", display_name="Clover Operator",
                                                  password=PASSWORD)
        bank_only = account_service.create_account(s, username="bank-only", display_name="Bank Only",
                                                   password=PASSWORD)
        s.flush()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="CLOVER_ACQUISITION",
                                          enabled=True, role_code=None)
        account_service.set_domain_access(s, account_id=bank_only.id, domain_code="BANK", enabled=True,
                                          role_code=None)
        s.commit()
        operator_id = operator.id

    launcher = RecordingLauncher()
    web_app.clover_job_launcher = launcher

    # ---- A / B: unauthenticated -------------------------------------------
    anon = web_app.app.test_client()
    resp = anon.get("/clover-acquisition", base_url=HOST)
    check("A: an unauthenticated visitor is sent to the normal RF-One login, with the way back",
          resp.status_code == 302 and "/login" in resp.headers["Location"]
          and "next=/clover-acquisition" in resp.headers["Location"], resp.headers.get("Location", ""))
    page = anon.get(resp.headers["Location"], base_url=HOST)
    check("A: the login page explains, in plain words, why",
          b"Please sign in to RF-One to use Clover Acquisition" in page.data and b"Clover" in page.data
          and b'name="next" value="/clover-acquisition"' in page.data)
    for path, data in (("/clover-acquisition/sync-now", {}),
                       ("/clover-acquisition/backfill", {"from_date": "2026-09-01", "through_date": "2026-09-02"})):
        resp = anon.post(path, base_url=HOST, data=data)
        check(f"A: unauthenticated POST {path} is refused (sent to login)",
              resp.status_code == 302 and "/login" in resp.headers["Location"])
    raw = web_app.app.test_client()
    resp = raw.post("/clover-acquisition/sync-now", base_url=HOST, data={"csrf_token": "made-up"})
    check("B: a direct request without any session, with a made-up CSRF token, is refused server-side",
          resp.status_code == 302 and "/login" in resp.headers["Location"])
    check("B: the status endpoint answers 401 without a session",
          raw.get("/clover-acquisition/status.json", base_url=HOST).status_code == 401)
    check("A/B: no job was created and nothing was launched", job_count() == 0 and launcher.run_ids == [])

    # ---- C: signed in without the access -----------------------------------
    bank = web_app.app.test_client()
    login(bank, "bank-only")
    home = bank.get("/", base_url=HOST)
    check("H: Home does not offer Clover Acquisition to an account without the access",
          home.status_code == 200 and b"Clover Acquisition" not in home.data)
    token = csrf(home.data)
    check("C: the page is refused (403) to a signed-in account without the access",
          bank.get("/clover-acquisition", base_url=HOST).status_code == 403)
    for path, data in (("/clover-acquisition/sync-now", {"csrf_token": token}),
                       ("/clover-acquisition/backfill",
                        {"csrf_token": token, "from_date": "2026-09-01", "through_date": "2026-09-02"})):
        check(f"C: POST {path} refused (403) without the access",
              bank.post(path, base_url=HOST, data=data).status_code == 403)
    check("C: the status endpoint answers 403 without the access",
          bank.get("/clover-acquisition/status.json", base_url=HOST).status_code == 403)
    check("C: no job was created and nothing was launched", job_count() == 0 and launcher.run_ids == [])

    # ---- G: back to the requested function after signing in ---------------
    op = web_app.app.test_client()
    resp = login(op, "clover-operator", next_path="/clover-acquisition")
    check("G: after signing in, the person returns to Clover Acquisition",
          resp.status_code == 302 and resp.headers["Location"].endswith("/clover-acquisition"),
          resp.headers.get("Location", ""))
    evil = web_app.app.test_client()
    resp = login(evil, "clover-operator", next_path="//evil.example/steal")
    check("G: `next` can never send a person to another host",
          resp.status_code == 302 and "evil.example" not in resp.headers["Location"], resp.headers.get("Location", ""))
    home = op.get("/", base_url=HOST)
    check("H: Home offers Clover Acquisition to an account holding the access",
          b"Clover Acquisition" in home.data and b"/clover-acquisition" in home.data)

    # ---- E: opening the page never creates a job --------------------------
    for _ in range(3):
        page = op.get("/clover-acquisition", base_url=HOST)
        op.get("/clover-acquisition/status.json", base_url=HOST)
    check("E: opening the page and polling its status create no job and launch nothing",
          page.status_code == 200 and job_count() == 0 and launcher.run_ids == [])
    check("the page recognises the signed-in RF-One person",
          b"Signed in as <strong>Operator C.</strong>" in page.data)
    check("Live Sync is shown NOT ACTIVE", b"NOT ACTIVE" in page.data)

    # ---- C': CSRF still required for an authorized account -----------------
    resp = op.post("/clover-acquisition/sync-now", base_url=HOST, data={})
    check("C: an authorized POST without CSRF is refused (400), no job", resp.status_code == 400 and job_count() == 0)

    # ---- D: Backfill accepted, requester recorded --------------------------
    token = csrf(page.data)
    resp = op.post("/clover-acquisition/backfill", base_url=HOST,
                   data={"csrf_token": token, "from_date": "2026-09-01", "through_date": "2026-09-02"})
    with SessionFactory() as s:
        backfill = s.scalars(select(m.IngestionRun).order_by(m.IngestionRun.id.desc())).first()
    check("D: Historical Backfill accepted and returned at once (redirect)",
          resp.status_code == 302 and backfill is not None and backfill.status == "QUEUED"
          and launcher.run_ids == [backfill.id])
    check("D: the Backfill job records the requesting RF-One account",
          backfill.requested_by_account_id == operator_id)
    check("D: the Backfill keeps its date logic (From 00:00:00 through 23:59:59 of the Through day)",
          backfill.source_window_start.strftime("%Y-%m-%d %H:%M:%S") == "2026-09-01 00:00:00"
          and backfill.source_window_end.strftime("%Y-%m-%d %H:%M:%S") == "2026-09-02 23:59:59")
    page = op.get("/clover-acquisition", base_url=HOST)
    check("D: the page shows who requested the job in progress",
          b"requested by Operator C." in page.data and b"Acquisition in progress" in page.data)

    # ---- F: concurrent acquisition still refused ---------------------------
    resp = op.post("/clover-acquisition/sync-now", base_url=HOST, data={"csrf_token": token}, follow_redirects=True)
    check("F: Sync Now while the Backfill is in progress is refused, with a clear message",
          b"already in progress" in resp.data and job_count() == 1 and launcher.run_ids == [backfill.id])

    # The accepted job runs (fake Clover), then Sync Now is accepted.
    clover = _FullCoverageFakeCloverClient(merchant_id=MERCHANT)
    jobs.execute_job(SessionFactory, backfill.id, client=clover)
    resp = op.post("/clover-acquisition/sync-now", base_url=HOST, data={"csrf_token": token})
    with SessionFactory() as s:
        sync = s.scalars(select(m.IngestionRun).order_by(m.IngestionRun.id.desc())).first()
        backfill_status = s.get(m.IngestionRun, backfill.id).status
    check("D: Sync Now accepted after the Backfill COMPLETE, requester recorded",
          backfill_status == "COMPLETE" and resp.status_code == 302 and sync.acquisition_mode == "SYNC_NOW"
          and sync.requested_by_account_id == operator_id and launcher.run_ids == [backfill.id, sync.id])
    page = op.get("/clover-acquisition", base_url=HOST)
    history = page.data.decode("utf-8")
    check("D: the history shows 'Requested by' with the person's RF-One name for both jobs",
          "<th>Requested by</th>" in history and history.count("<td>Operator C.</td>") == 2)

    print(f"Clover acquisition identity HTTP tests: {'SUCCESS' if not failed else 'FAILURE'} "
          f"({len(passed)} passed, {len(failed)} failed)")
    return 0 if not failed else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass
