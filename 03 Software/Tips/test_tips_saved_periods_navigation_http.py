#!/usr/bin/env python
"""TIPS_AWS_FINALIZATION_WORKFLOW_001 — standalone Tips leads to RF-One Web
for finalization, and cannot finalize anything itself.

The ONE human finalization path is RF-One Web's `/tips/runs/<run_id>`.
Saved Periods (`/tips-runs`) and the saved report (`/tips-runs/<id>`) link
to the SAME run there through `RFONE_WEB_BASE_URL`; without it, they say
navigation is not configured instead of rendering a broken link. The old
local `POST /tips-runs/<id>/validate` route and form are gone.

Eight CALCULATED runs of one period are saved so runs 7 and 8 exist, as on
AWS. Throwaway SQLite; never touches AWS, Clover or Mercury.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="tips_saved_periods_nav_test_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_FLASK_SECRET_KEY"] = "tips-saved-periods-nav-test-secret"
os.environ.pop("RFONE_WEB_BASE_URL", None)

_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as tips_app  # noqa: E402
import rfone_web_link  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402
from rfone_data_store.tips import calculation_run_service as run_svc  # noqa: E402
from rfone_data_store.tips_scheduler_validation import _build_fixture, _make_order_with_tip  # noqa: E402

DAY = date(2026, 5, 3)
BASE = "https://rfone.example.test"
CSRF = "shared-rfone-csrf-token"


def set_base(value: str | None) -> None:
    if value is None:
        os.environ.pop("RFONE_WEB_BASE_URL", None)
    else:
        os.environ["RFONE_WEB_BASE_URL"] = value


def hrefs(html: str) -> list[str]:
    return re.findall(r'href="([^"]*)"', html)


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}"
              + ("" if condition or not detail else f" ({detail})"))

    try:
        with tips_app.SessionFactory() as s:
            restaurant, location, source_system, employee = _build_fixture(s, suffix="NAV")
            _make_order_with_tip(s, location=location, source_system=source_system, employee=employee,
                                 business_date=DAY, order_suffix="NAV-1")
            run_ids = []
            for _ in range(8):
                run, reason = run_svc.save_calculation_run(
                    s, restaurant_id=restaurant.id, first_business_date=DAY, last_business_date=DAY,
                )
                assert run is not None, reason
                run_ids.append(run.id)
            validator = account_service.create_account(
                s, username="nav-validator", display_name="NAV Validator", password="a-long-enough-password",
            )
            s.flush()
            account_service.set_domain_access(s, account_id=validator.id, domain_code="TIPS",
                                              enabled=True, role_code=None)
            s.commit()
            validator_id, validator_version = validator.id, validator.session_version
        assert run_ids[6] == 7 and run_ids[7] == 8, run_ids

        def state(run_id: int) -> str:
            with tips_app.SessionFactory() as s:
                return s.get(m.TipDistributionCalculationRun, run_id).state

        client = tips_app.app.test_client()

        # --- configured -------------------------------------------------
        set_base(BASE)
        page = client.get("/tips-runs").get_data(as_text=True)
        web_links = [h for h in hrefs(page) if h.startswith(BASE)]
        check("1. /tips-runs renders an RF-One Web action for every saved run",
              sorted(web_links) == sorted(f"{BASE}/tips/runs/{i}" for i in run_ids)
              and page.count(">Review / Finalize in RF-One</a>") == len(run_ids),
              f"{web_links}")
        check("2. run 7 links exactly to <base>/tips/runs/7",
              f'href="{BASE}/tips/runs/7"' in page)
        check("3. run 8 links exactly to <base>/tips/runs/8",
              f'href="{BASE}/tips/runs/8"' in page)

        detail_ok = True
        for run_id in (1, 7, 8):
            detail = client.get(f"/tips-runs/{run_id}").get_data(as_text=True)
            links = [h for h in hrefs(detail) if h.startswith(BASE)]
            detail_ok = detail_ok and links == [f"{BASE}/tips/runs/{run_id}"] \
                and "Open in RF-One Web for validation/finalization" in detail
        check("4. the detail page for run N links exactly to <base>/tips/runs/N (N = 1, 7, 8)", detail_ok)

        set_base(BASE + "/")
        slash_list = client.get("/tips-runs").get_data(as_text=True)
        slash_detail = client.get("/tips-runs/7").get_data(as_text=True)
        check("5. a trailing slash on RFONE_WEB_BASE_URL does not create //tips/runs",
              "//tips/runs" not in slash_list.replace("https://", "")
              and "//tips/runs" not in slash_detail.replace("https://", "")
              and f'href="{BASE}/tips/runs/7"' in slash_detail)

        # --- not configured, or configured unsafely ---------------------
        unsafe_ok = True
        for value in (None, "", "   ", "rfone.example.test", "javascript:alert(1)",
                      "https://user:pw@rfone.example.test", f"{BASE}/?csrf_token=x", f"{BASE}#frag"):
            set_base(value)
            listing = client.get("/tips-runs").get_data(as_text=True)
            detail = client.get("/tips-runs/7").get_data(as_text=True)
            unsafe_ok = unsafe_ok \
                and "/tips/runs/" not in listing and "/tips/runs/" not in detail \
                and "RF-One Web navigation is not configured" in listing \
                and "RF-One Web navigation is not configured" in detail \
                and "Review / Finalize in RF-One" in listing  # the explanation still names the action
        check("6. RFONE_WEB_BASE_URL absent or unsafe (credentials, query, fragment, no scheme): "
              "no external link, a clear configuration message", unsafe_ok)

        # --- no local finalization path ---------------------------------
        set_base(BASE)
        rules = [r.rule for r in tips_app.app.url_map.iter_rules()]
        signed_in = tips_app.app.test_client()
        with signed_in.session_transaction() as sess:
            sess[shared_session.SESSION_ACCOUNT_KEY] = validator_id
            sess[shared_session.SESSION_VERSION_KEY] = validator_version
            sess[shared_session.SESSION_CSRF_KEY] = CSRF
        anon_post = client.post("/tips-runs/7/validate", data={"csrf_token": CSRF})
        authz_post = signed_in.post("/tips-runs/7/validate", data={"csrf_token": CSRF})
        check("7. standalone Tips has no local finalization POST route: 404/405 even for an "
              "authorized RF-One session with a valid token, runs stay CALCULATED",
              not any(r.endswith("/validate") and r.startswith("/tips-runs") for r in rules)
              and anon_post.status_code in (404, 405) and authz_post.status_code in (404, 405)
              and all(state(i) == m.TIPS_RUN_STATE_CALCULATED for i in run_ids),
              f"{anon_post.status_code}/{authz_post.status_code}")

        authz_detail = signed_in.get("/tips-runs/7").get_data(as_text=True)
        check("8. no local Validate form, even for an authorized RF-One session",
              "<form" not in authz_detail and 'method="post"' not in authz_detail.lower()
              and "Validate this period as" not in authz_detail and 'name="csrf_token"' not in authz_detail)

        check("security: RF-One Web links carry no token, credentials or query",
              all("?" not in h and "@" not in h and "csrf" not in h.lower() and "session" not in h.lower()
                  for h in hrefs(page) + hrefs(authz_detail) if h.startswith(BASE)))

        check("11. Saved Periods content is otherwise unchanged",
              all(text in page for text in (
                  "Saved Periods", "<th>Run</th>", "<th>Business Dates</th>",
                  "<th>Total Tips + Gratuity</th>", "<th>Total Employee Entitlements</th>",
                  "<th>Control</th>", "<th>State</th>", "<th>Approved by</th>", "<th>Calculated</th>",
                  f"{DAY} &rarr; {DAY}", "CALCULATED", "Only a FINAL period is a Payroll source.",
              ))
              and all(f'href="/tips-runs/{i}"' in page for i in run_ids))

    finally:
        set_base(None)
        tips_app._engine.dispose()
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
