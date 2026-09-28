#!/usr/bin/env python
"""IMPORTED_CLOVER_DATA_CONTROL_001 — the Tips "Imported Clover data" page as
a control tool, to hold next to Clover's Orders and Transactions reports.

Proves:

  1. the page order: period, Orders summary, Transactions summary, Orders
     detail, Transactions detail, then the other existing details;
  2. Orders: All / Completed / Incomplete / Incomplete order value, judged by
     balance (successful Payments against the Order total), never by the
     Clover state text (`OPEN` on every Order of this merchant);
  3. Transactions: Payments total and Number of payments over successful
     Payments only (a FAILED attempt counts in nothing), Voluntary Tips and
     Gratuity shown apart, their sum, and Taxes and Fees without Gratuity;
  4. a split Order's Gratuity is counted once, and equals what the Tips
     engine counts for that Order;
  5. local civil days (America/New_York) and local times, never UTC;
  6. employees as "Surname I.", never a Clover id;
  7. a period with no data shows zeros, no error;
  8. read-only: nothing is written, and "/" accepts no POST.

Throwaway SQLite + Flask test client. Never touches AWS or Clover.

Usage:
    python test_imported_clover_data_control_http.py
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

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="tips_imported_control_http_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_FLASK_SECRET_KEY"] = "tips-imported-control-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as tips_app  # noqa: E402
from tips_test_session import signed_in_client  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store.tips import distribution_engine as engine_svc  # noqa: E402

UTC = timezone.utc
DAY = datetime(2026, 9, 26, 16, 0, tzinfo=UTC)  # 12:00 EDT
TABLES = (m.Order, m.Payment, m.PaymentTip, m.OrderFee, m.Shift, m.IngestionRun)


def table_counts() -> dict:
    with tips_app.SessionFactory() as s:
        return {t.__tablename__: s.scalar(select(func.count()).select_from(t)) for t in TABLES}


def tile(html: str, label: str) -> str | None:
    match = re.search(r'<div class="label">' + re.escape(label) + r'</div><div class="value">([^<]*)</div>', html)
    return match.group(1) if match else None


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with tips_app.SessionFactory() as s:
        source = m.SourceSystem(code="CLOVER", name="Clover", active=True)
        s.add(source)
        s.flush()
        merchant = m.Merchant(source_system_id=source.id, source_merchant_id="CTRL-MERCH", name="Control Merchant")
        s.add(merchant)
        s.flush()
        location = m.Location(
            merchant_id=merchant.id, source_system_id=source.id, source_location_id="CTRL-LOC",
            name="Winter Park Test", currency="USD", timezone="America/New_York", operating_day_cutoff_time=time(4, 0),
        )
        s.add(location)
        s.flush()
        restaurant = m.Restaurant(name="Control Test Restaurant", default_currency="USD")
        s.add(restaurant)
        s.flush()
        s.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
        emp = m.Employee(location_id=location.id, source_system_id=source.id, source_employee_id="CLOVEREMPCTRL1",
                         display_name="Tatiana Ceban", system_role="EMPLOYEE")
        s.add(emp)
        s.flush()

        def order(oid, total, at, **extra):
            o = m.Order(location_id=location.id, source_system_id=source.id, source_order_id=oid,
                        employee_id=emp.id, source_employee_id=emp.source_employee_id, created_at=at,
                        state="locked", payment_state="OPEN", currency="USD", total=total, **extra)
            s.add(o)
            s.flush()
            return o

        def payment(o, pid, amount, at, *, result="SUCCESS", tip=None, tax=None):
            p = m.Payment(order_id=o.id, source_system_id=source.id, source_payment_id=pid, employee_id=emp.id,
                          source_employee_id=emp.source_employee_id, created_at=at, amount=amount, result=result,
                          tax_amount_source=tax, currency="USD")
            s.add(p)
            s.flush()
            if tip is not None:
                s.add(m.PaymentTip(payment_id=p.id, amount=tip, source_present=True))
            return p

        def gratuity(o, amount):
            s.add(m.OrderFee(order_id=o.id, source_system_id=source.id, source_line_item_id=f"FEE-{o.source_order_id}",
                             fee_type="SERVICE_CHARGE", name_raw="Gratuity", note_raw="Service Charge", amount=amount))

        # O1: paid in one Payment, 9.00 gratuity, 5.00 tip.
        o1 = order("CTRL-O1", 5900, DAY)
        payment(o1, "CTRL-P1", 5900, DAY + timedelta(minutes=30), tip=500, tax=300)
        gratuity(o1, 900)
        # O2: split across two Payments, 15.00 gratuity counted once.
        o2 = order("CTRL-O2", 10000, DAY + timedelta(hours=1))
        payment(o2, "CTRL-P2A", 6000, DAY + timedelta(hours=1, minutes=40), tip=300, tax=360)
        payment(o2, "CTRL-P2B", 4000, DAY + timedelta(hours=1, minutes=41), tip=200, tax=240)
        gratuity(o2, 1500)
        # O3: only a FAILED attempt — Incomplete, and nothing counted.
        o3 = order("CTRL-O3", 3000, DAY + timedelta(hours=2))
        payment(o3, "CTRL-P3F", 3000, DAY + timedelta(hours=2, minutes=5), result="FAIL", tip=400, tax=180)
        # O4: partially paid, tip field absent from source.
        o4 = order("CTRL-O4", 4000, DAY + timedelta(hours=3))
        payment(o4, "CTRL-P4", 1000, DAY + timedelta(hours=3, minutes=5), tax=60)
        # O5: 02:30Z on 27 Sept = 22:30 EDT on 26 Sept — the LOCAL 26th.
        late_at = datetime(2026, 9, 27, 2, 30, tzinfo=UTC)
        o5 = order("CTRL-O5", 2000, late_at)
        payment(o5, "CTRL-P5", 2000, late_at + timedelta(minutes=5), tip=0, tax=120)
        s.commit()
        engine_o2 = engine_svc._order_gross_tip_components(s, s.get(m.Order, o2.id))

    before = table_counts()
    client = signed_in_client(tips_app)
    html = client.get("/?from_date=2026-09-26&through_date=2026-09-26").get_data(as_text=True)

    # ---- 1. Page order --------------------------------------------------
    marks = ['id="from_date"', 'id="orders-summary"', 'id="transactions-summary"',
             "<h2>Orders detail</h2>", "<h2>Transactions detail</h2>", "<h2>Imported Shifts"]
    positions = [html.find(x) for x in marks]
    check("1. period, Orders, Transactions, Orders detail, Transactions detail, other details — in that order",
          all(p >= 0 for p in positions) and positions == sorted(positions), str(positions))

    # ---- 2. Orders summary ----------------------------------------------
    check("2. All orders = 5 (the 22:30 EDT Order included)", tile(html, "All orders") == "5", tile(html, "All orders"))
    check("2. Completed orders = 3 (by balance, although every Order says OPEN)",
          tile(html, "Completed orders") == "3", tile(html, "Completed orders"))
    check("2. Incomplete orders = 2 (failed-only and partially paid)",
          tile(html, "Incomplete orders") == "2", tile(html, "Incomplete orders"))
    check("2. Incomplete order value = $70.00", tile(html, "Incomplete order value") == "$70.00",
          tile(html, "Incomplete order value"))
    orders_detail = html[html.index("<h2>Orders detail</h2>"):html.index("<h2>Transactions detail</h2>")]
    check("2. Payment State reads as Clover's report (Paid / Open / Partially paid), never the raw OPEN",
          "Partially paid" in orders_detail and ">Open<" in orders_detail and "OPEN" not in orders_detail)

    # ---- 3. Transactions summary ----------------------------------------
    expect = {
        "Payments total": "$189.00", "Number of payments": "5", "Voluntary Tips": "$10.00",
        "Gratuity": "$24.00", "Total Tips + Gratuity": "$34.00", "Taxes and Fees": "$10.80",
    }
    for label, value in expect.items():
        check(f"3. {label} = {value}", tile(html, label) == value, tile(html, label))
    check("3. the failed attempt is named as not counted", "1 failed not counted" in html)
    check("3. no generic 'Tips' tile that could mix tips and gratuity",
          tile(html, "Tips") is None and tile(html, "Tips + Gratuity") is None)

    # ---- 4. Gratuity once, same as the Tips engine -----------------------
    tx_detail = html[html.index("<h2>Transactions detail</h2>"):html.index("<h2>Imported Shifts")]
    check("4. the split Order's $15.00 gratuity appears once in the Transactions detail",
          tx_detail.count("$15.00") == 1, str(tx_detail.count("$15.00")))
    check("4. the Tips engine counts the same for that Order (tip $5.00, gratuity $15.00)",
          engine_o2 == (500, 1500), str(engine_o2))
    check("4. Transactions detail names the Order of each Payment", "CTRL-O2" in tx_detail)

    # ---- 5. Local days and times ----------------------------------------
    check("5. no UTC on the page", "UTC" not in html)
    check("5. the 22:30 EDT Payment shows in local time", "22:35" in tx_detail)
    next_day = client.get("/?from_date=2026-09-27&through_date=2026-09-27").get_data(as_text=True)
    check("5. the 22:30 EDT Order does not fall on the next local day", tile(next_day, "All orders") == "0")

    # ---- 6. Names --------------------------------------------------------
    check("6. employee shown as 'Ceban T.'", "Ceban T." in html)
    check("6. no Clover employee id on the page", "CLOVEREMPCTRL1" not in html)

    # ---- 7. Zero data ----------------------------------------------------
    resp = client.get("/?from_date=2026-01-01&through_date=2026-01-02")
    empty = resp.get_data(as_text=True)
    check("7. an empty period renders (200)", resp.status_code == 200, str(resp.status_code))
    zeros = {"All orders": "0", "Completed orders": "0", "Incomplete orders": "0", "Incomplete order value": "$0.00",
             "Payments total": "$0.00", "Number of payments": "0", "Voluntary Tips": "$0.00", "Gratuity": "$0.00",
             "Total Tips + Gratuity": "$0.00", "Taxes and Fees": "$0.00"}
    check("7. every summary figure shows zero", all(tile(empty, k) == v for k, v in zeros.items()),
          str({k: tile(empty, k) for k in zeros}))
    fresh = client.get("/").get_data(as_text=True)
    check("7. no period chosen yet: no summary figures, a prompt instead",
          tile(fresh, "All orders") is None and "Select a From/Through date above." in fresh)

    # ---- 8. Read-only ----------------------------------------------------
    check("8. nothing written by any of these reads", table_counts() == before, f"{before} -> {table_counts()}")
    check("8. '/' accepts no POST", client.post("/?from_date=2026-09-26&through_date=2026-09-26").status_code == 405)

    print()
    print(f"Imported Clover data control HTTP tests: {'SUCCESS' if not failed else 'FAILURE'} "
          f"({len(passed)} passed, {len(failed)} failed)")
    return 0 if not failed else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        try:
            os.remove(_TEST_DB_PATH)
        except OSError:
            pass
