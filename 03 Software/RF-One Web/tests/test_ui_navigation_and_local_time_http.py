#!/usr/bin/env python
"""UI_NAVIGATION_AND_LOCAL_TIME_001 — RF-One UI Rules on RF-One Web.

Proves:
  A. the shared formatter: local time (America/New_York, EDT/EST), "UTC"
     only when a Location has no timezone, "Surname I." names;
  B. the Clover Acquisition page shows no UTC time: every time is the
     Location's local time, noted once; people as "Surname I.";
  C. a Sync Now posted from the Tips tab (`return_to=tips`) goes through
     the SAME route, gates and central service: one job, requested by the
     person, and the person lands back on the Tips tab; a second one while
     the first runs is refused (no duplicate) and also lands back on Tips;
     a request without a session creates nothing;
  D. the breadcrumb: RF-One > Clover Acquisition from Home, RF-One > Tips >
     Clover Acquisition when opened from Tips, every upper level a link;
  E. no RF-One Web template keeps a generic "Home" back link, and every
     sub-page tested renders the breadcrumb;
  F. the Tips Domain card points at Tips on the same host (`/tips/`).

Throwaway SQLite; a recording launcher stands in for Fargate. Never
touches AWS or Clover.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import datetime, time as dtime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_ui_navigation_http_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "http-test-secret"
os.environ.pop("RFONE_TIPS_URL", None)
os.environ.pop("RFONE_CLOVER_LIVE_SYNC_ENABLED", None)

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from domain_registry import DOMAINS  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from rfone_data_store import display_format  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
HOST = "https://rfone.example"
PASSWORD = "a-long-enough-test-password"
UTC = timezone.utc
SYNC_END_UTC = datetime(2026, 9, 26, 18, 5, tzinfo=UTC)  # 14:05 EDT


class RecordingLauncher:
    def __init__(self) -> None:
        self.run_ids: list[int] = []

    def __call__(self, run_id: int) -> None:
        self.run_ids.append(run_id)


def csrf(html: bytes) -> str | None:
    match = CSRF_RE.search(html.decode("utf-8"))
    return match.group(1) if match else None


def login(client, username: str):
    page = client.get("/login", base_url=HOST)
    return client.post("/login", base_url=HOST,
                       data={"username": username, "password": PASSWORD, "csrf_token": csrf(page.data)})


def job_count() -> int:
    with SessionFactory() as s:
        return s.scalar(select(func.count()).select_from(m.IngestionRun))


def crumbs(html: str) -> str:
    found = re.search(r'<nav class="breadcrumb".*?</nav>', html, re.S)
    return found.group(0) if found else ""


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    # ---- A: the shared formatter ---------------------------------------------
    fmt = display_format
    check("A: summer instant in Winter Park local time, EDT",
          fmt.local_datetime(SYNC_END_UTC, "America/New_York", with_zone=True) == "2026-09-26 14:05 EDT")
    check("A: winter instant in EST",
          fmt.local_datetime(datetime(2026, 1, 10, 18, 5, tzinfo=UTC), "America/New_York", with_zone=True)
          == "2026-01-10 13:05 EST")
    check("A: a naive stored timestamp is read as UTC",
          fmt.local_datetime(datetime(2026, 9, 26, 18, 5), "America/New_York") == "2026-09-26 14:05")
    check("A: no timezone configured -> the UTC instant, labelled UTC (never guessed)",
          fmt.local_datetime(SYNC_END_UTC, None, with_zone=True) == "2026-09-26 18:05 UTC"
          and fmt.zone_label(None) == "UTC" and fmt.zone_label("America/New_York") == "America/New_York")
    check("A: names as 'Surname I.'",
          fmt.employee_short_name("Tatiana Ceban") == "Ceban T." and fmt.employee_short_name("Andrew Muller") == "Muller A."
          and fmt.employee_short_name("Maria De Luca") == "De Luca M." and fmt.employee_short_name("Emilia") == "Emilia"
          and fmt.employee_short_name(None) == "-")

    with SessionFactory() as s:
        source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
        s.add(source_system)
        s.flush()
        merchant = m.Merchant(source_system_id=source_system.id, source_merchant_id="NAV-M", name="Nav Merchant")
        s.add(merchant)
        s.flush()
        location = m.Location(merchant_id=merchant.id, source_system_id=source_system.id, source_location_id="NAV-M",
                              name="Winter Park Test", currency="USD", timezone="America/New_York",
                              operating_day_cutoff_time=dtime(4, 0))
        s.add(location)
        s.flush()
        restaurant = m.Restaurant(name="Nav Restaurant", default_currency="USD")
        s.add(restaurant)
        s.flush()
        s.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
        operator = account_service.create_account(s, username="nav-operator", display_name="Tatiana Ceban",
                                                  password=PASSWORD, is_admin=True)
        s.flush()
        for code in ("CLOVER_ACQUISITION", "TIPS", "BANK", "COMPENSATION"):
            account_service.set_domain_access(s, account_id=operator.id, domain_code=code, enabled=True, role_code=None)
        s.add(m.IngestionRun(source_system_id=source_system.id, location_id=location.id, status="COMPLETE",
                             acquisition_mode="SYNC_NOW", started_at=SYNC_END_UTC - timedelta(minutes=3),
                             queued_at=SYNC_END_UTC - timedelta(minutes=4), finished_at=SYNC_END_UTC,
                             source_window_start=SYNC_END_UTC - timedelta(days=1), source_window_end=SYNC_END_UTC,
                             requested_by_account_id=operator.id,
                             notes=f"CLOVER_ACQUISITION mode=SYNC_NOW location_id={location.id}; COMPLETE"))
        s.commit()
        operator_id = operator.id

    launcher = RecordingLauncher()
    web_app.clover_job_launcher = launcher

    # ---- C (anonymous first): nothing is created ------------------------------
    anon = web_app.app.test_client()
    before = job_count()
    resp = anon.post("/clover-acquisition/sync-now", base_url=HOST, data={"return_to": "tips", "csrf_token": "x"})
    check("C: without a session the Tips-originated Sync Now is refused, back to login then to the Tips tab",
          resp.status_code == 302 and "/login" in resp.headers["Location"] and "next=/tips/" in resp.headers["Location"],
          resp.headers.get("Location", ""))
    check("C: ... and nothing was created or launched", job_count() == before and launcher.run_ids == [])

    client = web_app.app.test_client()
    login(client, "nav-operator")

    # ---- B: the full page -------------------------------------------------------
    page = client.get("/clover-acquisition", base_url=HOST).get_data(as_text=True)
    check("B: the page shows no UTC time", "UTC" not in page)
    check("B: last completed synchronization in local time (14:05 EDT)", "2026-09-26 14:05 EDT" in page)
    check("B: history times are local (started 14:02, ended 14:05), never 18:0x",
          "2026-09-26 14:02" in page and "2026-09-26 14:05" in page and "18:05" not in page and "18:02" not in page)
    check("B: the zone is stated once for the page", "Winter Park Test local time (America/New_York)" in page)
    check("B: people as 'Surname I.' (signed in as, requested by)",
          "Signed in as <strong>Ceban T.</strong>" in page and "<td>Ceban T.</td>" in page
          and "Tatiana Ceban" not in page)

    # ---- D: breadcrumb ------------------------------------------------------------
    nav = crumbs(page)
    check("D: from Home the path is RF-One > Clover Acquisition, with no Tips level",
          '<a href="/">RF-One</a>' in nav and '<span aria-current="page">Clover Acquisition</span>' in nav
          and "Tips" not in nav)
    check("D: the generic Home link is gone", "&larr; Home" not in page)
    from_tips = client.get("/clover-acquisition?from=tips", base_url=HOST).get_data(as_text=True)
    nav = crumbs(from_tips)
    check("D: opened from Tips the path is RF-One > Tips > Clover Acquisition, each upper level clickable",
          '<a href="/">RF-One</a>' in nav and '<a href="/tips/">Tips</a>' in nav
          and '<span aria-current="page">Clover Acquisition</span>' in nav)
    check("D: opened from Tips, the page's own forms keep the path", from_tips.count('name="from" value="tips"') == 2)

    # ---- C: Sync Now from the Tips tab ---------------------------------------------
    token = csrf(page.encode("utf-8"))
    before = job_count()
    resp = client.post("/clover-acquisition/sync-now", base_url=HOST,
                       data={"csrf_token": token, "return_to": "tips"})
    check("C: Sync Now from the Tips tab is accepted and returns to the Tips tab",
          resp.status_code == 302 and resp.headers["Location"] == "/tips/", resp.headers.get("Location", ""))
    with SessionFactory() as s:
        new_runs = list(s.scalars(select(m.IngestionRun).where(m.IngestionRun.status.in_(("QUEUED", "RUNNING")))))
    check("C: exactly one job, by the central service, requested by the signed-in person",
          job_count() == before + 1 and len(new_runs) == 1 and new_runs[0].acquisition_mode == "SYNC_NOW"
          and new_runs[0].requested_by_account_id == operator_id and launcher.run_ids == [new_runs[0].id])
    check("C: the Sync Now window starts at the last completed synchronization (no dates asked)",
          display_format.to_local(new_runs[0].source_window_start, None) == SYNC_END_UTC)
    with client.session_transaction(base_url=HOST) as sess:
        flashes = sess.get("_flashes", [])
    check("C: the outcome waits in the shared session for the Tips tab",
          any(cat == "info" and "accepted and started" in msg and "Ceban T." in msg for cat, msg in flashes), str(flashes))
    resp = client.post("/clover-acquisition/sync-now", base_url=HOST,
                       data={"csrf_token": token, "return_to": "tips"})
    with client.session_transaction(base_url=HOST) as sess:
        flashes = sess.get("_flashes", [])
    check("C: a second Sync Now while one runs is refused, no duplicate job, back on the Tips tab",
          resp.headers.get("Location") == "/tips/" and job_count() == before + 1 and len(launcher.run_ids) == 1
          and any(cat == "error" and "already in progress" in msg for cat, msg in flashes))
    resp = client.post("/clover-acquisition/sync-now", base_url=HOST, data={"return_to": "tips"})
    check("C: without the CSRF token it is refused (400) — Tips cannot bypass the gate", resp.status_code == 400)

    # ---- G: Historical Backfill dates are LOCAL civil days --------------------------
    # Release the running Sync Now first (the one-job lock is unchanged).
    with SessionFactory() as s:
        for run in s.scalars(select(m.IngestionRun).where(m.IngestionRun.status.in_(("QUEUED", "RUNNING")))):
            run.status, run.lock_key, run.finished_at = "COMPLETE", None, datetime.now(UTC)
        s.commit()
    page = client.get("/clover-acquisition", base_url=HOST).get_data(as_text=True)
    check("G: the Backfill form says the dates are whole local days",
          "Whole local days" in page and "America/New_York" in page)
    resp = client.post("/clover-acquisition/backfill", base_url=HOST,
                       data={"csrf_token": token, "from_date": "2026-09-20", "through_date": "2026-09-26"})
    with SessionFactory() as s:
        backfill = s.scalars(select(m.IngestionRun).where(m.IngestionRun.acquisition_mode == "BACKFILL")
                             .order_by(m.IngestionRun.id.desc())).first()
    check("G: 20-26 Sept = 20 Sept 00:00 EDT (04:00Z) -> 26 Sept 23:59:59 EDT (27 Sept 03:59:59Z)",
          backfill is not None
          and display_format.to_local(backfill.source_window_start, None) == datetime(2026, 9, 20, 4, 0, tzinfo=UTC)
          and display_format.to_local(backfill.source_window_end, None) == datetime(2026, 9, 27, 3, 59, 59, tzinfo=UTC),
          f"{backfill.source_window_start if backfill else None} -> {backfill.source_window_end if backfill else None}")
    history = client.get("/clover-acquisition", base_url=HOST).get_data(as_text=True)
    check("G: the history shows the chosen local days, not a 4-hour shift",
          "2026-09-20 00:00 &rarr; 2026-09-26 23:59" in history)

    # ---- E: every sub-page shows its path ----------------------------------------------
    templates_dir = os.path.join(APP_DIR, "templates")
    leftovers = [f for f in os.listdir(templates_dir)
                 if "&larr; Home" in open(os.path.join(templates_dir, f), encoding="utf-8").read()
                 or "RF-One Home<" in open(os.path.join(templates_dir, f), encoding="utf-8").read()]
    check("E: no RF-One Web template keeps a generic Home link", not leftovers, str(leftovers))
    for path, current in (("/admin/accounts", "Accounts"), ("/admin/legal-entities", "Legal Entities"),
                          ("/admin/organization", "Organization"), ("/profile", "Profile"),
                          ("/tips/runs", "Saved periods"), ("/compensation", "Compensation"),
                          ("/bank", "Import &amp; Instruments")):
        html = client.get(path, base_url=HOST).get_data(as_text=True)
        nav = crumbs(html)
        check(f"E: {path} shows RF-One > ... > {current}",
              '<a href="/">RF-One</a>' in nav and f'<span aria-current="page">{current}</span>' in nav, nav[:200])
    html = client.get("/tips/runs", base_url=HOST).get_data(as_text=True)
    check("E: RF-One > Tips > Saved periods — Tips is a clickable level", '<a href="/tips/">Tips</a>' in crumbs(html))

    # ---- F: Tips on the same host ----------------------------------------------------
    tips = next(d for d in DOMAINS if d.code == "TIPS")
    check("F: the Tips Domain card points at /tips/ on the same host", tips.link == "/tips/", tips.link)

    print(f"UI navigation and local time HTTP tests: {'SUCCESS' if not failed else 'FAILURE'} "
          f"({len(passed)} passed, {len(failed)} failed)")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
