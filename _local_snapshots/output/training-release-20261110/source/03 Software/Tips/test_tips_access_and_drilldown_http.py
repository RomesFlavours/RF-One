#!/usr/bin/env python
"""TIPS_ACCESS_AND_DRILLDOWN_001 — the RF-One login in front of every Tips
page, the Calculate Tips order drill-down, and Configuration highlighted on
New/Edit Role.

Proves:

  1. without an RF-One session, every Tips page and action sends the person
     to RF-One's login (coming back to the page asked for) and shows no
     data; a revoked session (password changed) is refused the same way;
  2. with the session, every Tips tab and sub-page answers 200;
  3. the session is RF-One Web's own: a person who logs in through RF-One
     Web's real /login opens Tips with no second login, and RF-One Web still
     recognises them afterwards;
  4. only the intended technical endpoints stay public (stylesheet, logo,
     the public dish guide, Training's own area);
  5. the order drill-down answers 200 — an Order distributed to a Host, an
     Order with no eligible Host, an Order with a Tip, an Order with
     Gratuity — its figures match the calculation, and it writes nothing;
  6. New Role and Edit Role keep the Configuration tab highlighted.

Throwaway SQLite + Flask test clients. Never touches AWS or Clover.

Usage:
    python test_tips_access_and_drilldown_http.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="tips_access_drilldown_http_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
# One signing secret for both apps: the shared-session contract.
os.environ["RFONE_FLASK_SECRET_KEY"] = "tips-access-drilldown-test-secret"
HOST = "https://rfone.example.test"
os.environ["RFONE_WEB_BASE_URL"] = HOST

_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as tips_app  # noqa: E402
from tips_test_session import sign_in  # noqa: E402
from sqlalchemy import func, inspect, select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store import rfone_account_service as account_service  # noqa: E402
from rfone_data_store.business_date import resolve_and_persist_order_business_date  # noqa: E402
from rfone_data_store.tips import distribution_engine as engine  # noqa: E402
from rfone_data_store.tips import distribution_rule_service as rule_svc  # noqa: E402

UTC = timezone.utc
NY = ZoneInfo("America/New_York")
DAY = date(2026, 9, 20)
PASSWORD = "a-long-enough-test-password"
WINDOW = "start_at=2026-09-20T04:00&end_at=2026-09-21T04:00"


def local(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=NY).astimezone(UTC)


# RF-One Web runs in its own process: it and Training both ship a module
# named `auth`, so the two apps cannot share one interpreter. Same database,
# same secret — exactly the shared-session contract.
_WEB_SCRIPT = r"""
import os, re, sys
web_dir = sys.argv[1]
sys.path.insert(0, web_dir)
sys.path.insert(0, os.path.join(web_dir, "..", "RF-One Data Store"))
import app as web
c = web.app.test_client()
host, action = sys.argv[2], sys.argv[3]
if action == "login":
    page = c.get("/login", base_url=host).get_data(as_text=True)
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    r = c.post("/login", base_url=host, data={"username": sys.argv[4], "password": sys.argv[5], "csrf_token": csrf})
    cookie = re.search(r"session=([^;]+)", r.headers.get("Set-Cookie", ""))
    print(r.status_code, cookie.group(1) if cookie else "")
else:
    c.set_cookie("session", sys.argv[4], domain=host.split("//", 1)[1])
    r = c.get("/", base_url=host)
    print(r.status_code, r.headers.get("Location", ""))
"""


def rfone_web(*args: str) -> list[str]:
    web_dir = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Web"))
    out = subprocess.run([sys.executable, "-c", _WEB_SCRIPT, web_dir, HOST, *args],
                         capture_output=True, text=True, env=os.environ.copy(), check=True).stdout
    return out.strip().splitlines()[-1].split(" ", 1)


def row_counts() -> dict[str, int]:
    with tips_app.SessionFactory() as s:
        tables = inspect(s.get_bind()).get_table_names()
        return {t: s.scalar(select(func.count()).select_from(m.Base.metadata.tables[t]))
                for t in tables if t in m.Base.metadata.tables}


def main() -> int:
    sys.stdout.reconfigure(errors="replace")
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    # ---- fixture: one Server, two Hosts on shift 17:00-22:00, a 10% rule ----
    with tips_app.SessionFactory() as s:
        source = m.SourceSystem(code="CLOVER", name="Clover", active=True)
        s.add(source)
        s.flush()
        merchant = m.Merchant(source_system_id=source.id, source_merchant_id="AD-MERCH", name="AD Merchant")
        s.add(merchant)
        s.flush()
        location = m.Location(merchant_id=merchant.id, source_system_id=source.id, source_location_id="AD-LOC",
                              name="Winter Park Test", currency="USD", timezone="America/New_York",
                              operating_day_cutoff_time=time(4, 0))
        s.add(location)
        s.flush()
        restaurant = m.Restaurant(name="AD Test Restaurant", default_currency="USD")
        s.add(restaurant)
        s.flush()
        s.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
        area = m.OperationalArea(restaurant_id=restaurant.id, name="FOH")
        role_server = m.RestaurantRole(restaurant_id=restaurant.id, name="Server")
        role_host = m.RestaurantRole(restaurant_id=restaurant.id, name="Host")
        s.add_all([area, role_server, role_host])
        s.flush()

        def employee(source_id, name, role):
            e = m.Employee(location_id=location.id, source_system_id=source.id, source_employee_id=source_id,
                           display_name=name, system_role="EMPLOYEE")
            s.add(e)
            s.flush()
            s.add(m.EmployeeAssignment(employee_id=e.id, restaurant_id=restaurant.id, operational_area_id=area.id,
                                       restaurant_role_id=role.id, valid_from=local(DAY, 0) - timedelta(days=300),
                                       valid_to=None, assignment_source="MANUAL"))
            return e

        server = employee("AD-SRV", "Meagan Messick", role_server)
        host_a = employee("AD-HA", "Andrew Muller", role_host)
        for h in (host_a,):
            s.add(m.Shift(employee_id=h.id, source_system_id=source.id, location_id=location.id,
                          source_shift_id=f"SH-{h.id}", clock_in=local(DAY, 17), clock_out=local(DAY, 22)))
        rule = rule_svc.create_rule(
            s, restaurant_id=restaurant.id, source_role_id=role_server.id, recipient_role_id=role_host.id,
            calculation_base=m.CALC_BASE_VOLUNTARY_TIP, rate=Decimal("10.0000"),
            effective_from=local(DAY, 0) - timedelta(days=300), created_by="tester",
        )
        s.flush()
        counter = {"n": 0}

        def order(at, tip, gratuity=0):
            counter["n"] += 1
            o = m.Order(location_id=location.id, source_system_id=source.id, source_order_id=f"AD-O{counter['n']}",
                        employee_id=server.id, source_employee_id=server.source_employee_id, created_at=at,
                        state="locked", payment_state="PAID", currency="USD", total=10000)
            s.add(o)
            s.flush()
            p = m.Payment(order_id=o.id, source_system_id=source.id, source_payment_id=f"AD-P{counter['n']}",
                          employee_id=server.id, source_employee_id=server.source_employee_id, created_at=at,
                          amount=10000, result="SUCCESS", currency="USD")
            s.add(p)
            s.flush()
            s.add(m.PaymentTip(payment_id=p.id, amount=tip, source_present=True))
            if gratuity:
                s.add(m.OrderFee(order_id=o.id, source_system_id=source.id, source_line_item_id=f"FEE-{o.id}",
                                 fee_type="SERVICE_CHARGE", name_raw="Gratuity", amount=gratuity))
            s.flush()
            resolve_and_persist_order_business_date(s, o.id)
            return o.id

        with_host = order(local(DAY, 18), 2000)                 # a Host on shift -> distributed
        no_host = order(local(DAY, 12), 1500)                   # lunch, no Host on shift -> Server keeps 100%
        with_gratuity = order(local(DAY, 19), 1000, gratuity=1800)
        role_id = role_host.id
        rule_id = rule.id
        restaurant_id = restaurant.id
        editor = account_service.create_account(s, username="ad-editor", display_name="Ad Editor", password=PASSWORD)
        s.commit()
        account = (editor.id, editor.session_version)

        start = datetime.combine(DAY, time(4, 0), tzinfo=NY).astimezone(UTC)
        result = engine.calculate_tips(s, restaurant_id=restaurant_id, period_start=start,
                                       period_end=start + timedelta(days=1))
        expected = {oid: engine.get_order_drilldown(s, result, oid) for oid in (with_host, no_host, with_gratuity)}
        s.rollback()

    pages = ["/tips/", "/tips/calculate-tips", "/tips/tips-runs", "/tips/payment-control", "/tips/configuration",
             "/tips/host-audit", "/tips/roles", "/tips/roles/new", f"/tips/roles/{role_id}/edit",
             f"/tips/distribution-rules/{rule_id}", f"/tips/calculate-tips/order/{with_host}?{WINDOW}",
             "/tips/host-audit/export.csv", "/tips/distribution-rules", "/tips/tips-configuration"]

    # ---- 1. signed out -> RF-One login ---------------------------------------
    anon = tips_app.app.test_client()
    for path in pages:
        resp = anon.get(path, base_url=HOST)
        location = resp.headers.get("Location", "")
        check(f"1. signed out, GET {path} -> RF-One login, back to the same page",
              resp.status_code == 302 and location.startswith(f"{HOST}/login?next=")
              and "Messick" not in resp.get_data(as_text=True), f"{resp.status_code} {location}")
    resp = anon.get("/tips/configuration?x=1", base_url=HOST)
    check("1. the page asked for (query included) is where login returns",
          resp.headers.get("Location") == f"{HOST}/login?next=%2Ftips%2Fconfiguration%3Fx%3D1", resp.headers.get("Location"))
    before = row_counts()
    for path in ("/tips/calculate-tips/run", "/tips/calculate-tips/consolidate", "/tips/payment-control/start-cycle",
                 "/tips/distribution-rules/new", "/tips/roles/new", "/tips/tips-configuration/validation-mode"):
        resp = anon.post(path, base_url=HOST, data={})
        check(f"1. signed out, POST {path} -> RF-One login, nothing done",
              resp.status_code == 302 and resp.headers["Location"] == f"{HOST}/login?next=%2Ftips%2F",
              f"{resp.status_code} {resp.headers.get('Location')}")
    check("1. the refused POSTs wrote nothing", row_counts() == before)

    revoked = tips_app.app.test_client()
    sign_in(revoked, (account[0], account[1] + 1), HOST)   # an older session version = password changed since
    resp = revoked.get("/tips/configuration", base_url=HOST)
    check("1. a revoked session is refused like no session", resp.status_code == 302
          and resp.headers["Location"].startswith(f"{HOST}/login"))

    # ---- 2. signed in -> 200 ---------------------------------------------------
    client = tips_app.app.test_client()
    sign_in(client, account, HOST)
    for path in pages:
        resp = client.get(path, base_url=HOST)
        # A former URL, or the CSV export without its parameters, redirects —
        # never to the login.
        ok = resp.status_code == 200 or (resp.status_code in (301, 302)
                                         and not resp.headers.get("Location", "").startswith(f"{HOST}/login"))
        check(f"2. signed in, GET {path} -> {resp.status_code}", ok)

    # ---- 3. the session is RF-One Web's own --------------------------------------
    status, cookie = rfone_web("login", "ad-editor", PASSWORD)
    check("3. RF-One Web's real /login issues the session cookie", status == "302" and bool(cookie), status)
    shared = tips_app.app.test_client()
    # Werkzeug's test client replaces a hand-written Cookie header with its
    # own jar, so the browser's cookie is placed in the jar.
    shared.set_cookie("session", cookie, domain=HOST.split("//", 1)[1])
    resp = shared.get("/tips/calculate-tips", base_url=HOST)
    check("3. that cookie opens Tips directly — no second login", resp.status_code == 200, str(resp.status_code))
    status, location = (rfone_web("home", cookie) + [""])[:2]
    check("3. back on RF-One Web Home with the same cookie, still signed in", status == "200", f"{status} {location}")

    # ---- 4. technical endpoints stay public ----------------------------------------
    check("4. the stylesheet is public (the login redirect itself needs none, but pages do)",
          anon.get("/tips/static/css/rf-one.css", base_url=HOST).status_code == 200)
    check("4. the public dish guide stays public", anon.get("/tips/training/menu", base_url=HOST).status_code == 200)
    training = anon.get("/tips/training/login", base_url=HOST)
    check("4. Training keeps its own login (not redirected to RF-One's)",
          training.status_code == 200 or not training.headers.get("Location", "").startswith(f"{HOST}/login"))
    check("4. an unknown path is still a plain 404", anon.get("/tips/no-such-page", base_url=HOST).status_code == 404)

    # ---- 5. the order drill-down -------------------------------------------------
    before = row_counts()
    for label, oid in (("distributed to a Host", with_host), ("no eligible Host", no_host),
                       ("with Gratuity", with_gratuity)):
        resp = client.get(f"/tips/calculate-tips/order/{oid}?{WINDOW}", base_url=HOST)
        html = resp.get_data(as_text=True)
        exp = expected[oid]
        check(f"5. drill-down, {label}: 200", resp.status_code == 200, str(resp.status_code))
        check(f"5. drill-down, {label}: Voluntary Tip and Gratuity as calculated",
              f"${exp['voluntary_tip_minor'] / 100:.2f}" in html and f"${exp['gratuity_minor'] / 100:.2f}" in html)
        allocated = sum(a.allocated_amount_minor for a in exp["allocations"])
        check(f"5. drill-down, {label}: allocations as calculated (${allocated / 100:.2f})",
              all(f"${a.allocated_amount_minor / 100:.2f}" in html for a in exp["allocations"]))
        check(f"5. drill-down, {label}: Service Owner shown as 'Messick M.'", "Messick M." in html)
    host_html = client.get(f"/tips/calculate-tips/order/{with_host}?{WINDOW}", base_url=HOST).get_data(as_text=True)
    check("5. the Host who received the tip-out is named ('Muller A.', $2.00)",
          "Muller A." in host_html and "$2.00" in host_html)
    nohost_html = client.get(f"/tips/calculate-tips/order/{no_host}?{WINDOW}", base_url=HOST).get_data(as_text=True)
    check("5. no eligible Host is stated, nothing allocated", "no eligible recipient" in nohost_html
          and sum(a.allocated_amount_minor for a in expected[no_host]["allocations"]) == 0)
    check("5. the drill-downs wrote nothing", row_counts() == before)

    # ---- 6. Configuration highlighted on New/Edit Role ------------------------------
    for path in ("/tips/roles/new", f"/tips/roles/{role_id}/edit"):
        bar = re.search(r'<div class="nav-tabs">(.*?)</div>',
                        client.get(path, base_url=HOST).get_data(as_text=True), re.S).group(1)
        check(f"6. {path}: Configuration is the highlighted tab",
              re.findall(r'class="active">([^<]+)</a>', bar) == ["Configuration"])

    print()
    print(f"Tips access and drill-down HTTP tests: {'SUCCESS' if not failed else 'FAILURE'} "
          f"({len(passed)} passed, {len(failed)} failed)")
    try:
        os.remove(_TEST_DB_PATH)
    except OSError:
        pass
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
