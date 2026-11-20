#!/usr/bin/env python
"""UI_NAVIGATION_AND_LOCAL_TIME_001 — the Tips "Clover Acquisition" tab.

Tips and RF-One Web are published on ONE host (RF-One Web at `/`, Tips at
`/tips/`), so the RF-One session reaches Tips. Proves:

  1. the tab shows the last completed synchronization in the Location's
     LOCAL time (America/New_York, EDT) and never in UTC;
  2. a signed-in account holding CLOVER_ACQUISITION sees Sync Now as a form
     posting to RF-One Web's ONE Sync Now action (`/clover-acquisition/
     sync-now`), carrying the session's own RF-One CSRF token and
     `return_to=tips`; Tips itself has no Sync Now route and creates no job;
  3. without the access, or signed out, there is no button (a sign-in link
     coming back to the Tips tab instead);
  4. a job in progress shows "Sync in progress" and disables the button;
  5. employees are shown as "Surname I.", never as Clover ids;
  6. the breadcrumb RF-One > Tips > <tab> [> detail], each level clickable,
     replaces the generic back links;
  7. served under `/tips/`, every link carries the prefix, and the session
     cookie Tips re-issues keeps RF-One Web's attributes (Secure, HttpOnly,
     SameSite=Lax, Path=/).

Throwaway SQLite + Flask test client. Never touches AWS or Clover.

Usage:
    python test_clover_acquisition_tab_http.py
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import datetime, time, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="tips_clover_tab_http_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_FLASK_SECRET_KEY"] = "tips-clover-tab-test-secret"
BASE = "https://rfone.example.test"
os.environ["RFONE_WEB_BASE_URL"] = BASE

_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as tips_app  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store import rfone_web_session as shared_session  # noqa: E402

UTC = timezone.utc
HOST = "https://rfone.example.test"
# 18:05 UTC on 2026-09-26 is 14:05 EDT in Winter Park.
SYNC_END_UTC = datetime(2026, 9, 26, 18, 5, tzinfo=UTC)
ORDER_AT_UTC = datetime(2026, 9, 26, 22, 40, tzinfo=UTC)  # 18:40 EDT


def sign_in(client, account) -> None:
    """The cookie RF-One Web's `auth.log_in` issues: the same two shared keys."""
    with client.session_transaction(base_url=HOST) as sess:
        sess[shared_session.SESSION_ACCOUNT_KEY] = account[0]
        sess[shared_session.SESSION_VERSION_KEY] = account[1]


def job_count() -> int:
    with tips_app.SessionFactory() as s:
        return s.scalar(select(func.count()).select_from(m.IngestionRun))


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with tips_app.SessionFactory() as s:
        source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
        s.add(source_system)
        s.flush()
        merchant = m.Merchant(source_system_id=source_system.id, source_merchant_id="TAB-MERCH", name="Tab Merchant")
        s.add(merchant)
        s.flush()
        location = m.Location(
            merchant_id=merchant.id, source_system_id=source_system.id, source_location_id="TAB-LOC",
            name="Winter Park Test", currency="USD", timezone="America/New_York",
            operating_day_cutoff_time=time(4, 0),
        )
        s.add(location)
        s.flush()
        restaurant = m.Restaurant(name="Tab Test Restaurant", default_currency="USD")
        s.add(restaurant)
        s.flush()
        s.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
        employee = m.Employee(location_id=location.id, source_system_id=source_system.id,
                              source_employee_id="CLOVEREMP9XYZ", display_name="Tatiana Ceban", system_role="EMPLOYEE")
        s.add(employee)
        s.flush()
        order = m.Order(location_id=location.id, source_system_id=source_system.id, source_order_id="TAB-ORDER-1",
                        employee_id=employee.id, source_employee_id=employee.source_employee_id,
                        created_at=ORDER_AT_UTC, state="locked", payment_state="PAID", currency="USD", total=5000)
        s.add(order)
        s.flush()
        s.add(m.Payment(order_id=order.id, source_system_id=source_system.id, source_payment_id="TAB-PAY-1",
                        employee_id=employee.id, source_employee_id=employee.source_employee_id,
                        created_at=ORDER_AT_UTC, amount=5000, result="SUCCESS", currency="USD"))
        # 02:30Z on 27 Sept is 22:30 EDT on 26 Sept: it belongs to the LOCAL 26th.
        late = m.Order(location_id=location.id, source_system_id=source_system.id, source_order_id="TAB-ORDER-LATE",
                       employee_id=employee.id, source_employee_id=employee.source_employee_id,
                       created_at=datetime(2026, 9, 27, 2, 30, tzinfo=UTC), state="locked", payment_state="PAID",
                       currency="USD", total=1000)
        s.add(late)
        # The last completed synchronization.
        s.add(m.IngestionRun(source_system_id=source_system.id, location_id=location.id, status="COMPLETE",
                             acquisition_mode="SYNC_NOW", started_at=SYNC_END_UTC - timedelta(minutes=3),
                             finished_at=SYNC_END_UTC, source_window_start=SYNC_END_UTC - timedelta(days=1),
                             source_window_end=SYNC_END_UTC))
        operator = account_service.create_account(s, username="tab-operator", display_name="Andrew Muller",
                                                  password="a-long-enough-test-password")
        tips_only = account_service.create_account(s, username="tab-tips-only", display_name="Tips Only",
                                                   password="a-long-enough-test-password")
        s.flush()
        account_service.set_domain_access(s, account_id=operator.id, domain_code="CLOVER_ACQUISITION",
                                          enabled=True, role_code=None)
        account_service.set_domain_access(s, account_id=tips_only.id, domain_code="TIPS", enabled=True,
                                          role_code=None)
        s.commit()
        operator_acc = (operator.id, operator.session_version)
        tips_only_acc = (tips_only.id, tips_only.session_version)
        location_id, source_system_id = location.id, source_system.id
    jobs_before = job_count()

    # ---- 1 / 2: signed in with the access, served under /tips/ -------------
    client = tips_app.app.test_client()
    sign_in(client, operator_acc)
    resp = client.get("/tips/", base_url=HOST)
    html = resp.get_data(as_text=True)
    card = html[html.index('id="clover-acquisition"'):html.index("Imported Clover data")]
    check("1. the tab opens under /tips/", resp.status_code == 200)
    check("1. Last update is shown in the Location's local time (14:05 EDT, not 18:05 UTC)",
          "Last update:" in card and "2026-09-26 14:05 EDT" in card and "18:05" not in card, card[:300])
    check("1. no UTC time anywhere on the tab", "UTC" not in html)
    action = re.search(r'<form method="post" action="([^"]+)"', card)
    check("2. Sync Now posts to RF-One Web's ONE Sync Now action",
          action is not None and action.group(1) == f"{BASE}/clover-acquisition/sync-now",
          action.group(1) if action else "no form")
    with client.session_transaction(base_url=HOST) as sess:
        session_token = sess.get(shared_session.SESSION_CSRF_KEY)
    check("2. the form carries the session's own RF-One CSRF token",
          session_token is not None and f'name="csrf_token" value="{session_token}"' in card)
    check("2. the form asks to come back to the Tips tab", 'name="return_to" value="tips"' in card)
    check("2. Sync Now is enabled (no job running, a sync point exists)",
          re.search(r'<button type="submit" id="sync-now-btn"\s*>Sync Now</button>', card) is not None)
    check("2. 'Open Clover Acquisition' is offered, optional",
          f'href="{BASE}/clover-acquisition?from=tips"' in card and ">Open Clover Acquisition<" in card)
    visible = re.sub(r"<script.*?</script>|<[^>]+>", " ", card, flags=re.S)
    check("2. the tab carries no technical explanation of acquisitions",
          "Fargate" not in visible and "ECS" not in visible and "lock" not in visible.lower(), visible)
    for path in ("/tips/clover-acquisition/sync-now", "/clover-acquisition/sync-now", "/tips/historical-backfill"):
        r = client.post(path, base_url=HOST, data={"csrf_token": session_token})
        check(f"2. Tips has no Sync Now of its own: POST {path} is refused", r.status_code in (404, 405))
    check("2. opening the tab and the refused POSTs created no job", job_count() == jobs_before)

    # ---- 7: prefix and cookie ------------------------------------------------
    check("7. links on the tab carry the /tips prefix",
          'href="/tips/configuration"' in html and 'href="/tips/"' in html)
    set_cookie = resp.headers.get("Set-Cookie", "")
    check("7. the re-issued session cookie keeps RF-One Web's attributes",
          all(flag in set_cookie for flag in ("Secure", "HttpOnly", "SameSite=Lax", "Path=/")), set_cookie)
    check("7. the service's own address (no prefix) still serves the tab",
          client.get("/", base_url=HOST).status_code == 200)

    # ---- 5: employees as "Surname I." ---------------------------------------
    data = client.get("/tips/?from_date=2026-09-26&through_date=2026-09-27", base_url=HOST).get_data(as_text=True)
    check("5. employees shown as 'Ceban T.'", data.count("<td>Ceban T.</td>") >= 2)
    check("5. the Clover employee id is never shown", "CLOVEREMP9XYZ" not in data)
    check("5. Order/Payment times shown in local time (18:40, not 22:40)",
          "2026-09-26 18:40" in data and "22:40" not in data)

    # ---- 8: the date filter uses LOCAL civil days --------------------------------
    day26 = client.get("/tips/?from_date=2026-09-26&through_date=2026-09-26", base_url=HOST).get_data(as_text=True)
    day27 = client.get("/tips/?from_date=2026-09-27&through_date=2026-09-27", base_url=HOST).get_data(as_text=True)
    check("8. an order at 22:30 EDT on 26 Sept is listed under 26 Sept (local day)", "TAB-ORDER-LATE" in day26)
    check("8. ... and not under 27 Sept, although it is 27 Sept in UTC", "TAB-ORDER-LATE" not in day27)

    # ---- 3: without the access / signed out ---------------------------------
    other = tips_app.app.test_client()
    sign_in(other, tips_only_acc)
    page = other.get("/tips/", base_url=HOST).get_data(as_text=True)
    check("3. without the Clover Acquisition access: no Sync Now button, a plain note instead",
          'id="sync-now-btn"' not in page and "requires the Clover Acquisition access" in page)
    # TIPS_ACCESS_AND_DRILLDOWN_001 — signed out, the tab is not shown at all:
    # RF-One's login, coming back to the Tips tab.
    anon = tips_app.app.test_client()
    resp_anon = anon.get("/tips/", base_url=HOST)
    page = resp_anon.get_data(as_text=True)
    check("3. signed out: sent to RF-One's login, coming back to the Tips tab",
          resp_anon.status_code == 302 and resp_anon.headers["Location"] == f"{BASE}/login?next=%2Ftips%2F",
          f"{resp_anon.status_code} {resp_anon.headers.get('Location')}")
    check("3. signed out: no data on the response", "2026-09-26 14:05 EDT" not in page and 'id="sync-now-btn"' not in page)

    # ---- 4: a job in progress -------------------------------------------------
    with tips_app.SessionFactory() as s:
        now = datetime.now(UTC)
        s.add(m.IngestionRun(source_system_id=source_system_id, location_id=location_id, status="RUNNING",
                             acquisition_mode="SYNC_NOW", started_at=now, queued_at=now, heartbeat_at=now,
                             lock_key=f"CLOVER_ACQUISITION:{location_id}", requested_by_account_id=operator_acc[0],
                             source_window_start=SYNC_END_UTC, source_window_end=now))
        s.commit()
    page = client.get("/tips/", base_url=HOST).get_data(as_text=True)
    check("4. a running job shows 'Sync in progress' with who asked, as 'Surname I.'",
          "Sync in progress" in page and "requested by Muller A." in page)
    check("4. the button is disabled while a job runs",
          re.search(r'id="sync-now-btn"\s+disabled', page) is not None)

    # ---- 6: breadcrumbs -------------------------------------------------------
    crumbs = re.search(r'<nav class="breadcrumb".*?</nav>', html, re.S).group(0)
    check("6. the tab shows RF-One > Tips > Clover Acquisition, upper levels clickable",
          f'<a href="{BASE}/">RF-One</a>' in crumbs and '<a href="/tips/">Tips</a>' in crumbs
          and '<span aria-current="page">Clover Acquisition</span>' in crumbs)
    rules = client.get("/tips/configuration", base_url=HOST).get_data(as_text=True)
    check("6. a tab page: RF-One > Tips > Configuration",
          '<span aria-current="page">Configuration</span>' in rules)
    roles = client.get("/tips/roles/new", base_url=HOST).get_data(as_text=True)
    check("6. a deeper page: RF-One > Tips > Configuration > Roles > New Role, every upper level clickable",
          '<a href="/tips/configuration">Configuration</a>' in roles
          and '<a href="/tips/roles">Roles</a>' in roles and '<span aria-current="page">New Role</span>' in roles)
    templates_dir = os.path.join(BASE_DIR, "templates")
    leftovers = [f for f in os.listdir(templates_dir)
                 if re.search(r"&larr; (Back to|All saved|Home)", open(os.path.join(templates_dir, f), encoding="utf-8").read())]
    check("6. no Tips template keeps a generic back link", not leftovers, str(leftovers))

    print(f"Tips Clover Acquisition tab HTTP tests: {'SUCCESS' if not failed else 'FAILURE'} "
          f"({len(passed)} passed, {len(failed)} failed)")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
