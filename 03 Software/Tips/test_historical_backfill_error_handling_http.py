#!/usr/bin/env python
"""Regression test for "Diagnose Historical Backfill 500 Error": a real
failure from `import_clover_period()` (missing/invalid Clover credentials,
a network error, an unexpected API response, or any other exception) must
surface as a controlled, user-facing flash message + redirect — never a
raw, unhandled 500 Internal Server Error.

Root cause: `run_historical_backfill()` in app.py only caught
`ImportAlreadyRunningError`; any other exception from
`import_clover_period()` (which deliberately re-raises after releasing its
own lock/marking the IngestionRun FAILED — see that function's own
`except Exception as exc: ...; raise`) propagated straight through Flask.

Mirrors this repo's own throwaway-SQLite + Flask-test-client convention.
Never touches AWS, App Runner, or any production database, and never makes
a real Clover API call (import_clover_period is monkeypatched).

Usage:
    python test_historical_backfill_error_handling_http.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="tips_backfill_error_test_")
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
from rfone_data_store.technical.connectors.clover.acquisition import (  # noqa: E402
    ImportAlreadyRunningError, ImportSummary,
)

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

    original_import_clover_period = tips_app.import_clover_period

    try:
        client = tips_app.app.test_client()

        # A Restaurant with a real Clover-sourced Location, so the route
        # gets past its own "no Restaurant"/"no Location" guards and
        # actually reaches the import_clover_period() call this task's bug
        # lives around.
        with tips_app.SessionFactory() as s:
            merchant = m.Merchant(name="Error Handling Test Merchant")
            s.add(merchant)
            s.flush()
            source_system = s.query(m.SourceSystem).filter_by(code="CLOVER").first()
            if source_system is None:
                source_system = m.SourceSystem(code="CLOVER", name="Clover")
                s.add(source_system)
                s.flush()
            location = m.Location(
                merchant_id=merchant.id, name="Error Handling Test Location",
                source_system_id=source_system.id, source_location_id="error-handling-test-loc",
            )
            s.add(location)
            s.flush()
            restaurant = m.Restaurant(name="Error Handling Test Restaurant", default_currency="USD")
            s.add(restaurant)
            s.flush()
            s.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
            s.commit()

        # -----------------------------------------------------------------
        # A generic exception (stands in for a missing/invalid Clover
        # credential, a network failure, or any other real failure) must
        # produce a controlled redirect, never a raw 500.
        # -----------------------------------------------------------------
        def _raise_generic(*args, **kwargs):
            raise RuntimeError("simulated Clover failure: connection refused")

        tips_app.import_clover_period = _raise_generic
        try:
            resp = client.post(
                "/historical-backfill", data={"from_date": "2026-09-01", "through_date": "2026-09-07"}
            )
            check(
                "a real import_clover_period() failure redirects (never a raw 500)",
                resp.status_code in (302, 303),
                detail=f"status={resp.status_code}",
            )

            resp2 = client.post(
                "/historical-backfill",
                data={"from_date": "2026-09-01", "through_date": "2026-09-07"},
                follow_redirects=True,
            )
            check(
                "the redirected page opens cleanly (200), not a 500",
                resp2.status_code == 200,
                detail=f"status={resp2.status_code}",
            )
            check(
                "a controlled, user-facing error message is shown, naming the failure type",
                b"Historical Backfill failed" in resp2.data and b"RuntimeError" in resp2.data,
            )
            check(
                "the raw exception message reaches the user (transparency), never a stack trace",
                b"simulated Clover failure" in resp2.data and b"Traceback" not in resp2.data,
            )
        finally:
            tips_app.import_clover_period = original_import_clover_period

        # -----------------------------------------------------------------
        # A ConfigError-shaped failure (the realistic missing-env-var case)
        # behaves the same way -- controlled, not a 500.
        # -----------------------------------------------------------------
        class SimulatedConfigError(Exception):
            pass

        def _raise_config_error(*args, **kwargs):
            raise SimulatedConfigError(
                "Missing or empty required configuration: CLOVER_MERCHANT_ID, CLOVER_API_TOKEN."
            )

        tips_app.import_clover_period = _raise_config_error
        try:
            resp = client.post(
                "/historical-backfill",
                data={"from_date": "2026-09-01", "through_date": "2026-09-07"},
                follow_redirects=True,
            )
            check(
                "a missing-Clover-config-shaped failure is also controlled, not a 500",
                resp.status_code == 200 and b"Historical Backfill failed" in resp.data,
                detail=f"status={resp.status_code}",
            )
        finally:
            tips_app.import_clover_period = original_import_clover_period

        # -----------------------------------------------------------------
        # No regression: ImportAlreadyRunningError keeps its own specific,
        # pre-existing message (not swallowed by the new generic handler).
        # -----------------------------------------------------------------
        def _raise_already_running(*args, **kwargs):
            raise ImportAlreadyRunningError("already running")

        tips_app.import_clover_period = _raise_already_running
        try:
            resp = client.post(
                "/historical-backfill",
                data={"from_date": "2026-09-01", "through_date": "2026-09-07"},
                follow_redirects=True,
            )
            check(
                "ImportAlreadyRunningError still gets its own specific message (no regression)",
                resp.status_code == 200 and b"already in progress" in resp.data,
            )
            check(
                "the generic failure handler's message is not shown for this specific case",
                b"Historical Backfill failed" not in resp.data,
            )
        finally:
            tips_app.import_clover_period = original_import_clover_period

        # -----------------------------------------------------------------
        # No regression: a normal, successful run still flashes its summary.
        # -----------------------------------------------------------------
        def _raise_nothing(session, *, location_id, period_start, period_end, mode):
            return ImportSummary(location_id=location_id, period_start=period_start, period_end=period_end)

        tips_app.import_clover_period = _raise_nothing
        try:
            resp = client.post(
                "/historical-backfill",
                data={"from_date": "2026-09-01", "through_date": "2026-09-07"},
                follow_redirects=True,
            )
            check(
                "a successful run still opens cleanly and is not treated as a failure",
                resp.status_code == 200 and b"Historical Backfill failed" not in resp.data,
            )
        finally:
            tips_app.import_clover_period = original_import_clover_period
    finally:
        tips_app.import_clover_period = original_import_clover_period
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass

    total = len(checks_passed) + len(checks_failed)
    if not checks_failed:
        print(f"Historical Backfill error-handling tests: SUCCESS ({len(checks_passed)}/{total} checks passed)")
        return 0
    print(f"Historical Backfill error-handling tests: FAILURE ({len(checks_passed)} passed, {len(checks_failed)} failed)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
