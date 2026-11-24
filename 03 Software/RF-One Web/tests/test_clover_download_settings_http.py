#!/usr/bin/env python
"""HTTP-level test for Settings > Clover download (CLOVER_ACQUISITION_ENGINE_001).
A throwaway SQLite database migrated to head before `app.py` is imported,
Werkzeug's test client, `main()` returning an exit code. Never touches AWS,
Clover or any real database."""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import datetime, time, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.normpath(os.path.join(BASE_DIR, ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="rfoneweb_clover_download_http_test_")
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
from rfone_data_store import operational_acquisition as oa  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
UTC = timezone.utc


def extract_csrf(html: bytes) -> str:
    match = CSRF_RE.search(html.decode("utf-8"))
    assert match, "csrf_token not found in response HTML"
    return match.group(1)


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        if not condition:
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    try:
        with SessionFactory() as s:
            source = s.query(m.SourceSystem).filter_by(code="CLOVER").first()
            if source is None:
                source = m.SourceSystem(code="CLOVER", name="Clover", active=True)
                s.add(source)
                s.flush()
            ids = {}
            for name, merchant_id, active in (("Rome's Flavours - WP", "WPM", True), ("Rome's Flavours - MD", "MDM", False)):
                merchant = m.Merchant(source_system_id=source.id, source_merchant_id=merchant_id, name=name, active=active)
                s.add(merchant)
                s.flush()
                location = m.Location(merchant_id=merchant.id, source_system_id=source.id, source_location_id=merchant_id,
                                      name=name, timezone="America/New_York", operating_day_cutoff_time=time(4, 0),
                                      active=active)
                s.add(location)
                s.flush()
                ids[name] = location.id
            wp = ids["Rome's Flavours - WP"]
            s.add(m.OperationalAcquisitionRequest(
                location_id=wp, kind="SCHEDULED", status="COMPLETE", requested_at=datetime(2026, 11, 22, 5, tzinfo=UTC),
                scheduled_local_date=datetime(2026, 11, 22).date(), finished_at=datetime(2026, 11, 22, 5, 2, tzinfo=UTC),
                coverage_start=datetime(2026, 11, 21, 5, tzinfo=UTC), coverage_end=datetime(2026, 11, 22, 5, tzinfo=UTC)))
            s.add(m.OperationalAcquisitionRequest(
                location_id=wp, kind="SCHEDULED", status="FAILED", requested_at=datetime(2026, 11, 23, 5, tzinfo=UTC),
                scheduled_local_date=datetime(2026, 11, 23).date(), finished_at=datetime(2026, 11, 23, 5, 1, tzinfo=UTC),
                outcome="New records: 401 Unauthorized"))
            admin_id = account_service.create_account(s, username="RFone", display_name="Pino Miraglia",
                                                      password="AdminPass123!", status="ACTIVE", is_admin=True).id
            account_service.create_account(s, username="plain", display_name="Plain User", password="PlainPass123!",
                                           status="ACTIVE", is_admin=False)
            s.commit()

        plain = web_app.app.test_client()
        csrf = extract_csrf(plain.get("/login").data)
        plain.post("/login", data={"username": "plain", "password": "PlainPass123!", "csrf_token": csrf})
        refused = plain.get("/admin/clover-download")
        check("a non-administrator cannot open the page", refused.status_code in (302, 403), str(refused.status_code))

        client = web_app.app.test_client()
        csrf = extract_csrf(client.get("/login").data)
        client.post("/login", data={"username": "RFone", "password": "AdminPass123!", "csrf_token": csrf})
        home = client.get("/")
        check("Home > Settings links to Clover download", b'href="/admin/clover-download"' in home.data)

        page = client.get("/admin/clover-download")
        html = page.data.decode("utf-8")
        check("page renders", page.status_code == 200, str(page.status_code))
        check("initial time is 00:00", 'value="00:00"' in html)
        check("contextual help link and modal are present", "clover-download" in html and "How this page works" in html)
        check("breadcrumb present", "breadcrumb" in html)
        check("both sites listed, MD marked inactive", "Rome&#39;s Flavours - MD" in html and "inactive: not downloaded" in html)
        check("WP last attempt failed with its reason", "Failed" in html and "401 Unauthorized" in html)
        check("WP last success and coverage come from the COMPLETE download only",
              "11/22/2026" in html or "2026-11-22" in html or "Nov 22" in html, html[html.find("Status by site"):][:1500])
        check("Live is off", ">off<" in html)

        bad = client.post("/admin/clover-download", data={"run_time": "25:99", "csrf_token": extract_csrf(page.data)},
                          follow_redirects=True)
        check("an invalid time is refused", b"Enter a valid time" in bad.data)
        no_csrf = client.post("/admin/clover-download", data={"run_time": "03:30"})
        check("CSRF is required", no_csrf.status_code in (400, 403), str(no_csrf.status_code))
        ok = client.post("/admin/clover-download", data={"run_time": "03:30", "csrf_token": extract_csrf(client.get("/admin/clover-download").data)},
                         follow_redirects=True)
        check("time saved", b"Ordinary download set to 03:30" in ok.data and b'value="03:30"' in ok.data)
        with SessionFactory() as s:
            schedule = oa.get_schedule(s)
            check("schedule stored with the account that changed it",
                  schedule.run_time == time(3, 30) and schedule.timezone == "America/New_York"
                  and schedule.updated_by_account_id == admin_id)
        os.environ["RFONE_UI_LANGUAGE"] = "it"
        try:
            it_page = client.get("/admin/clover-download").data.decode("utf-8")
            it_home = client.get("/").data.decode("utf-8")
        finally:
            os.environ.pop("RFONE_UI_LANGUAGE", None)
        check("Italian: page, help button and modal close label",
              "Orario dello scarico ordinario" in it_page and "Come funziona questa pagina" in it_page
              and 'aria-label="Chiudi"' in it_page)
        check("Italian: Home link", "Scarico Clover</strong>" in it_home)
    finally:
        print(f"\n{len(passed)} passed, {len(failed)} failed.")
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
