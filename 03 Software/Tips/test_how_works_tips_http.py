#!/usr/bin/env python
"""Contextual help ("How … works" modal) on every Tips page.

Every operational Tips page declares its own help section: the layout
renders the link (``data-how-works="<section>"``) in the Tips menu and ONE
help dialog (``id="rf-help-dialog"``) containing that page's own section
(``id="help-<section>"``). The Tips entry page (Clover Acquisition tab) says
"How Tips works"; every other page says "How this page works".

Throwaway SQLite + Flask test client. Never touches AWS, Clover or Mercury
(no payment connector is configured, so Payment Control makes no call).

Usage:
    python test_how_works_tips_http.py
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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="tips_how_works_http_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_FLASK_SECRET_KEY"] = "tips-how-works-test-secret"
os.environ.pop("RFONE_WEB_BASE_URL", None)

_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as tips_app  # noqa: E402
from tips_test_session import signed_in_client  # noqa: E402
from sqlalchemy import select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store.tips import calculation_run_service as run_svc  # noqa: E402
from rfone_data_store.tips_scheduler_validation import _build_fixture, _make_order_with_tip  # noqa: E402

DAY = date(2026, 5, 3)
WINDOW = "start_at=2026-05-03T04:00&end_at=2026-05-04T04:00"
HOME_LABEL = "How Tips works"
PAGE_LABEL = "How this page works"


def visible_text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    try:
        with tips_app.SessionFactory() as s:
            restaurant, location, source_system, employee = _build_fixture(s, suffix="HW")
            order = _make_order_with_tip(s, location=location, source_system=source_system, employee=employee,
                                         business_date=DAY, order_suffix="HW-1")
            run, reason = run_svc.save_calculation_run(
                s, restaurant_id=restaurant.id, first_business_date=DAY, last_business_date=DAY,
            )
            assert run is not None, reason
            s.commit()
            role_id = s.scalars(select(m.RestaurantRole.id)).first()
            rule_id = s.scalars(select(m.TipDistributionRule.id)).first()
            order_id, run_id, employee_id = order.id, run.id, employee.id

        client = signed_in_client(tips_app)
        pages = [
            ("/", "tips-home", HOME_LABEL),
            (f"/calculate-tips?{WINDOW}", "tips-calculate", PAGE_LABEL),
            (f"/host-audit?{WINDOW}", "tips-host-audit", PAGE_LABEL),
            (f"/host-audit?employee_id={employee_id}&{WINDOW}", "tips-host-audit", PAGE_LABEL),
            (f"/calculate-tips/order/{order_id}?{WINDOW}", "tips-order-drilldown", PAGE_LABEL),
            ("/tips-runs", "tips-saved-periods", PAGE_LABEL),
            (f"/tips-runs/{run_id}", "tips-saved-period", PAGE_LABEL),
            ("/historical-tip-payments", "tips-historical-paid", PAGE_LABEL),
            ("/payment-control", "tips-payment-control", PAGE_LABEL),
            ("/configuration", "tips-configuration", PAGE_LABEL),
            (f"/distribution-rules/{rule_id}", "tips-rule-detail", PAGE_LABEL),
            ("/roles", "tips-roles", PAGE_LABEL),
            ("/roles/new", "tips-role-form", PAGE_LABEL),
            (f"/roles/{role_id}/edit", "tips-role-form", PAGE_LABEL),
        ]
        for path, section, label in pages:
            resp = client.get(path)
            html = resp.get_data(as_text=True)
            check(f"{path}: 200", resp.status_code == 200, str(resp.status_code))
            check(f"{path}: link opens section {section}", f'data-how-works="{section}"' in html)
            check(f"{path}: the page's own section is in the dialog", f'id="help-{section}"' in html)
            check(f"{path}: label '{label}'", f">{label}</button>" in html)
            check(f"{path}: exactly one help dialog", html.count('id="rf-help-dialog"') == 1,
                  str(html.count('id="rf-help-dialog"')))
            body = html[html.find(f'id="help-{section}"'):html.find("</section>", html.find(f'id="help-{section}"'))]
            check(f"{path}: the section explains the page (>= 300 visible characters)",
                  len(visible_text(body)) >= 300, str(len(visible_text(body))))
            check(f"{path}: the help link sits in the Tips menu",
                  re.search(r'<div class="nav-tabs">.*?data-how-works=', html, re.S) is not None)

        # The role form's help follows the page's own mode.
        new_role = client.get("/roles/new").get_data(as_text=True)
        edit_role = client.get(f"/roles/{role_id}/edit").get_data(as_text=True)
        check("role form: create mode explains Create Role", "<dt>Create Role</dt>" in new_role)
        check("role form: edit mode explains Save changes", "<dt>Save changes</dt>" in edit_role)

        # Signed out, no page (nor its help) is shown.
        anon = tips_app.app.test_client()
        resp = anon.get("/configuration")
        check("signed out: no help is served", resp.status_code in (302, 401)
              and 'id="rf-help-dialog"' not in resp.get_data(as_text=True), str(resp.status_code))
    finally:
        try:
            tips_app._engine.dispose()
        except Exception:
            pass
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass

    print()
    print(f"Tips How Works HTTP tests: {'SUCCESS' if not failed else 'FAILURE'} "
          f"({len(passed)} passed, {len(failed)} failed)")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
