#!/usr/bin/env python
"""HTTP-level verification for Historical Backfill's "From date" prefill:
must default to the latest operational `Order.business_date` already on
file for the Restaurant's Clover Location(s) - never `created_at`/
`modified_at` (ingestion/sync timestamps) - inserted as the exact value
(never advanced by a day), left editable, and left blank (with a message)
when no Business Date data exists yet. "Through date" must never be
affected.

Mirrors this repo's own throwaway-SQLite + Flask-test-client convention.
Never touches AWS or any production database.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="tips_backfill_prefill_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"

_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as tips_app  # noqa: E402
from rfone_data_store import models as m  # noqa: E402

UTC = timezone.utc


def main() -> int:
    checks_passed: list[str] = []
    checks_failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        if condition:
            checks_passed.append(description)
        else:
            checks_failed.append(description)
            print(f"FAILED: {description}" + (f" ({detail})" if detail else ""))

    try:
        client = tips_app.app.test_client()

        # -----------------------------------------------------------------
        # No Restaurant at all yet: unaffected by this change (pre-existing
        # "No Restaurant exists" message), From date stays empty.
        # -----------------------------------------------------------------
        resp = client.get("/")
        check("with no Restaurant, the page still opens (200)", resp.status_code == 200)
        check(
            "with no Restaurant, From date has no value and no Business-Date message is shown",
            b'id="from_date" name="from_date" value=""' in resp.data
            and b"No Clover Business Date on file" not in resp.data,
        )

        # -----------------------------------------------------------------
        # A Restaurant exists, but zero Orders: From date stays blank, with
        # the required helpful message.
        # -----------------------------------------------------------------
        with tips_app.SessionFactory() as s:
            merchant = m.Merchant(name="Verification Merchant")
            s.add(merchant)
            s.flush()
            location = m.Location(merchant_id=merchant.id, name="Verification Location")
            s.add(location)
            s.flush()
            restaurant = m.Restaurant(name="Verification Restaurant", default_currency="USD")
            s.add(restaurant)
            s.flush()
            s.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
            s.commit()
            location_id = location.id

        resp = client.get("/")
        check(
            "with a Restaurant but zero Orders, From date is blank and the helpful message is shown",
            b'id="from_date" name="from_date" value=""' in resp.data
            and b"No Clover Business Date on file yet for this Restaurant" in resp.data,
        )

        # -----------------------------------------------------------------
        # Orders exist with different business_date/created_at values -
        # the prefill must use the MAX(business_date), never created_at.
        # -----------------------------------------------------------------
        with tips_app.SessionFactory() as s:
            # Deliberately: the Order with the LATEST created_at has an
            # EARLIER business_date than another Order - proves the
            # ingestion timestamp is never used for this prefill.
            s.add(m.Order(
                location_id=location_id, created_at=datetime(2026, 9, 5, tzinfo=UTC),
                business_date=date(2026, 9, 9),
            ))
            s.add(m.Order(
                location_id=location_id, created_at=datetime(2026, 9, 10, tzinfo=UTC),
                business_date=date(2026, 9, 6),
            ))
            # An Order with no resolved Business Date yet must never break
            # or skew the MAX computation.
            s.add(m.Order(
                location_id=location_id, created_at=datetime(2026, 9, 11, tzinfo=UTC),
                business_date=None,
            ))
            s.commit()

        resp = client.get("/")
        check(
            "From date is prefilled with the MAX(business_date) = 2026-09-09, "
            "not the latest created_at (2026-09-11) and not advanced by a day",
            b'id="from_date" name="from_date" value="2026-09-09"' in resp.data,
        )
        check(
            "the 'no data' message is gone now that a Business Date exists",
            b"No Clover Business Date on file" not in resp.data,
        )
        check(
            "the From date field remains a normal, editable input (not readonly/disabled)",
            b'id="from_date"' in resp.data and b'id="from_date" name="from_date" value="2026-09-09" readonly' not in resp.data
            and b'id="from_date" name="from_date" value="2026-09-09" disabled' not in resp.data,
        )

        # -----------------------------------------------------------------
        # An explicit from_date in the URL (e.g. the redirect after running
        # a Backfill) is respected, never overridden by the prefill.
        # -----------------------------------------------------------------
        resp = client.get("/?from_date=2026-01-15&through_date=2026-01-20")
        check(
            "an explicit from_date query parameter is never overridden by the Business-Date prefill",
            b'id="from_date" name="from_date" value="2026-01-15"' in resp.data,
        )
        check(
            "Through date remains driven only by its own query parameter, unaffected by this change",
            b'id="through_date" name="through_date" value="2026-01-20"' in resp.data,
        )

        # An explicit, empty from_date (e.g. a manually edited URL) is also
        # respected as an explicit choice, never re-filled.
        resp = client.get("/?from_date=&through_date=")
        check(
            "an explicit empty from_date is respected as a deliberate choice, not re-prefilled",
            b'id="from_date" name="from_date" value=""' in resp.data,
        )

    finally:
        for suffix in ("", "-wal", "-shm", "-journal"):
            candidate = _TEST_DB_PATH + suffix
            if os.path.exists(candidate):
                try:
                    os.remove(candidate)
                except OSError:
                    pass

    print()
    print(f"{len(checks_passed)} passed, {len(checks_failed)} failed.")
    if checks_failed:
        print("FAILED CHECKS:")
        for c in checks_failed:
            print(" -", c)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
