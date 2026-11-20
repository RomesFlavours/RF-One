#!/usr/bin/env python
"""CLOVER_ACQUISITION_IDENTITY_001 — the standalone Tips app starts no Clover
acquisition. On AWS it cannot see the RF-One login (another hostname), so
Sync Now and Historical Backfill live in RF-One Web behind that login.

Proves: the former action URLs are refused with no effect (no job row);
the Tips page offers no start button and no job history; it links to RF-One
Web's Clover Acquisition when RFONE_WEB_BASE_URL is set, and says plainly
that navigation is not configured when it is not.

Throwaway SQLite + Flask test client. Never touches AWS or Clover.

Usage:
    python test_clover_acquisition_moved_http.py
"""

from __future__ import annotations

import os
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="tips_clover_moved_http_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"

_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as tips_app  # noqa: E402
from tips_test_session import signed_in_client  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402


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
        merchant = m.Merchant(name="Moved Merchant", source_system_id=source_system.id, source_merchant_id="MOVED")
        s.add(merchant)
        s.flush()
        location = m.Location(merchant_id=merchant.id, name="Moved Location", source_system_id=source_system.id,
                              source_location_id="MOVED", currency="USD")
        s.add(location)
        s.flush()
        restaurant = m.Restaurant(name="Moved Restaurant", default_currency="USD")
        s.add(restaurant)
        s.flush()
        s.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
        s.commit()

    web = signed_in_client(tips_app)
    for path, data in (("/historical-backfill", {"from_date": "2026-09-01", "through_date": "2026-09-02"}),
                       ("/clover-acquisition/sync-now", {})):
        resp = web.post(path, data=data)
        check(f"POST {path} on the Tips host is refused (no such action)", resp.status_code in (404, 405),
              f"status={resp.status_code}")
    check("GET /clover-acquisition/status.json is not served by Tips",
          web.get("/clover-acquisition/status.json").status_code == 404)
    with tips_app.SessionFactory() as s:
        check("no acquisition job was created", s.scalar(select(func.count()).select_from(m.IngestionRun)) == 0)

    os.environ.pop("RFONE_WEB_BASE_URL", None)
    page = web.get("/")
    check("the Tips page opens", page.status_code == 200)
    check("the Tips page has no Sync Now / Backfill button and no job history",
          b">Sync Now</button>" not in page.data and b"Run Historical Backfill" not in page.data
          and b"Acquisition history" not in page.data)
    check("without RFONE_WEB_BASE_URL the page says plainly that navigation is not configured",
          b"RFONE_WEB_BASE_URL is not set" in page.data)

    os.environ["RFONE_WEB_BASE_URL"] = "https://rfone-web.example"
    page = web.get("/")
    check("with RFONE_WEB_BASE_URL the page links to RF-One Web's Clover Acquisition (opened from Tips)",
          b'href="https://rfone-web.example/clover-acquisition?from=tips"' in page.data)

    print(f"Clover acquisition moved (Tips) HTTP tests: {'SUCCESS' if not failed else 'FAILURE'} "
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
