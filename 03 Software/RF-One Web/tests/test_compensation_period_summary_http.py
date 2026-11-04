#!/usr/bin/env python
"""HTTP-level test for the Compensation Period Summary and Settings >
Workweek (COMPENSATION_PERIOD_SUMMARY_001). Same convention as
`test_compensation_v1_http.py`: a throwaway SQLite database created before
`app.py` is imported, migrated explicitly, Werkzeug's test client, `main()`
returning an exit code. Never touches AWS or any real database."""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_period_summary_http_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_WEB_TEST_SECRET_KEY"] = "http-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as web_app  # noqa: E402
from db import SessionFactory  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
NY = ZoneInfo("America/New_York")
UTC = timezone.utc


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found in response HTML"
    return match.group(1)


def _local(day: date, hour: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=NY).astimezone(UTC)


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        if not condition:
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    week1, week2 = date(2026, 9, 7), date(2026, 9, 14)
    try:
        with SessionFactory() as s:
            legal_entity = m.LegalEntity(legal_name="Summary LLC", status="ACTIVE")
            merchant = m.Merchant(name="Summary Merchant")
            s.add_all([legal_entity, merchant])
            s.flush()
            location = m.Location(merchant_id=merchant.id, name="Rome's Flavours - WP",
                                  timezone="America/New_York", operating_day_cutoff_time=time(4, 0))
            s.add(location)
            s.flush()
            restaurant = m.Restaurant(name="Rome's Flavours - WP", legal_entity_id=legal_entity.id)
            s.add(restaurant)
            s.flush()
            s.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
            # The seed migration ran before this Restaurant existed, so it has
            # no Workweek yet — exactly what Settings > Workweek must show.
            ceban = m.Employee(location_id=location.id, display_name="Tatiana Ceban")
            host = m.Employee(location_id=location.id, display_name="Andrew Muller")
            s.add_all([ceban, host])
            s.flush()
            for offset in range(5):
                for day, hours in ((week1, 9), (week2, 7)):
                    start = _local(day + timedelta(days=offset), 10)
                    s.add(m.Shift(employee_id=ceban.id, clock_in=start, clock_out=start + timedelta(hours=hours)))
            run = m.TipDistributionCalculationRun(
                restaurant_id=restaurant.id, period_start=_local(week1, 4), period_end=_local(week2 + timedelta(days=7), 4),
                status="COMPLETE", state=m.TIPS_RUN_STATE_FINAL, first_business_date=week1,
                last_business_date=week2 + timedelta(days=6), timezone_name="America/New_York",
                operating_day_cutoff_time=time(4, 0), control_difference_minor=0, finalized_at=datetime.now(UTC),
            )
            s.add(run)
            s.flush()
            s.add(m.TipEntitlement(calculation_run_id=run.id, restaurant_id=restaurant.id, employee_id=host.id,
                                   gross_amount_minor=0, outbound_amount_minor=0, inbound_amount_minor=4200,
                                   payable_amount_minor=4200))
            admin = account_service.create_account(
                s, username="RFone", display_name="Pino Miraglia", password="AdminPass123!",
                status="ACTIVE", is_admin=True,
            )
            s.commit()
            admin_id, restaurant_id, location_id, run_id = admin.id, restaurant.id, location.id, run.id

        client = web_app.app.test_client()
        csrf = extract_csrf(client.get("/login").data)
        client.post("/login", data={"username": "RFone", "password": "AdminPass123!", "csrf_token": csrf})
        csrf = extract_csrf(client.get(f"/admin/accounts/{admin_id}/access").data)
        client.post(f"/admin/accounts/{admin_id}/access",
                    data={"enabled_COMPENSATION": "on", "enabled_TIPS": "on", "csrf_token": csrf})

        home = client.get("/")
        check("Home > Settings links to Workweek", b'href="/admin/workweek"' in home.data)
        comp = client.get("/compensation")
        check("Compensation links to the Period Summary", b'href="/compensation/period-summary"' in comp.data)

        page = client.get("/compensation/period-summary")
        check("summary form renders with the busy indicator and breadcrumb",
              page.status_code == 200 and b"rf-one-busy.js" in page.data and b"breadcrumb" in page.data)

        query = f"/compensation/period-summary?location_id={location_id}&first_business_date={week1}&last_business_date={week2 + timedelta(days=6)}"
        resp = client.get(query)
        html = resp.data.decode("utf-8")
        check("without a Workweek, overtime is stated as not available", "Overtime hours not available" in html, html[:0])
        check("hours are still shown (80.00)", "80.00" in html)

        workweek_page = client.get("/admin/workweek")
        check("Workweek setting shows 'not configured'", b"not configured" in workweek_page.data)
        csrf = extract_csrf(workweek_page.data)
        bad = client.post(f"/admin/workweek/{restaurant_id}",
                          data={"start_weekday": "0", "effective_business_date": "2026-09-08", "csrf_token": csrf},
                          follow_redirects=True)
        check("an effective date not on the start weekday is refused", b"must fall on the new start day" in bad.data)
        csrf = extract_csrf(client.get("/admin/workweek").data)
        ok = client.post(f"/admin/workweek/{restaurant_id}",
                         data={"start_weekday": "0", "effective_business_date": "2026-01-05", "csrf_token": csrf},
                         follow_redirects=True)
        check("Workweek set to Monday from a Monday Business Date", b"starts on Monday" in ok.data)

        html = client.get(query).data.decode("utf-8")
        row_ceban = re.search(r"Tatiana C\.(?:(?!</td>).)*</td>\s*<td>([^<]+)</td>\s*<td>([^<]+)</td>\s*<td>(.*?)</td>", html, re.S)
        check("employee shown as 'Tatiana C.' (first name + surname initial) with 80.00 worked and 5.00 overtime",
              bool(row_ceban) and row_ceban.group(1) == "80.00" and row_ceban.group(2) == "5.00",
              row_ceban.groups() if row_ceban else "row missing")
        check("hours-only employee gets $0.00 from a finalized period (a real zero)",
              bool(row_ceban) and "$0.00" in row_ceban.group(3))
        check("tips-only employee is a row with $42.00", "Andrew M." in html and "$42.00" in html)
        check("Surname-first format is not used on this page", "Ceban T." not in html and "Muller A." not in html)
        check("home-Location attribution is visible (10 of 10 Shifts)", "10 of 10 Shifts" in html and "home Location &times;10" in html)
        check("the FINAL run used is linked", f'href="/tips/runs/{run_id}"' in html)
        check("Bonus is 'to be defined'", "to be defined" in html)
        check("settings used are displayed", "America/New_York" in html and "04:00" in html and "Monday" in html)

        partial = client.get(
            f"/compensation/period-summary?location_id={location_id}&first_business_date={week1}&last_business_date={week2}"
        ).data.decode("utf-8")
        check("a period cutting the FINAL run shows tips as not available",
              "not available" in partial and "$42.00" not in partial)
    finally:
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = _TEST_DB_PATH + suffix
            if os.path.exists(candidate):
                try:
                    os.remove(candidate)
                except OSError:
                    pass

    print()
    print(f"{len(passed)} passed, {len(failed)} failed.")
    if failed:
        print("FAILED CHECKS:")
        for c in failed:
            print(" -", c)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
