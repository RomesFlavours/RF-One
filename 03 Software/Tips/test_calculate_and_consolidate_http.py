#!/usr/bin/env python
"""CALCULATE_AND_CONSOLIDATE_001 — Calculate Tips reduced to two actions.

Proves:

  1. the page is linear: period + Calculate, Totals, Employee Entitlements,
     Consolidate; no "Run Calculation Now", no "Close this period", no
     second pair of dates;
  2. Calculate gives the same figures as before (the former default window,
     one Business Day from cutoff to cutoff) and as the engine itself, and
     writes nothing;
  3. Consolidate saves the period shown, with the result shown, into Saved
     Periods, without asking for dates again;
  4. afterwards the page says "Period consolidated MM/DD/YYYY → MM/DD/YYYY"
     and offers no Consolidate button; posting again saves nothing;
  5. a result that changed after it was shown is not consolidated;
  6. the AUDIT review mode is a small indicator, not a card;
  7. a multi-day range and the drill-down's former window link work.

Throwaway SQLite + Flask test client. Never touches AWS or Clover.

Usage:
    python test_calculate_and_consolidate_http.py
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix=".db", prefix="tips_calc_consolidate_http_")
os.close(_TEST_DB_FD)
os.remove(_TEST_DB_PATH)
os.environ["RFONE_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"
os.environ["RFONE_FLASK_SECRET_KEY"] = "tips-calc-consolidate-test-secret"

_DATA_STORE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "RF-One Data Store"))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import run_migrations_to_head  # noqa: E402
run_migrations_to_head(os.environ["RFONE_DATABASE_URL"])

import app as tips_app  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from rfone_data_store import models as m  # noqa: E402
from rfone_data_store.business_date import resolve_and_persist_order_business_date  # noqa: E402
from rfone_data_store.tips import distribution_engine as engine  # noqa: E402
from rfone_data_store.tips import distribution_rule_service as rule_svc  # noqa: E402

UTC = timezone.utc
NY = ZoneInfo("America/New_York")
DAY1 = date(2026, 9, 20)
DAY2 = date(2026, 9, 21)


def local(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=NY).astimezone(UTC)


def run_count() -> int:
    with tips_app.SessionFactory() as s:
        return s.scalar(select(func.count()).select_from(m.TipDistributionCalculationRun))


def figures(result, rows):
    totals = engine.build_operational_totals(result, rows)
    return (
        totals.voluntary_minor, totals.gratuity_minor, totals.total_employee_entitlements_minor,
        totals.control_difference_minor,
        sorted((r.employee_id, r.final_entitlement_minor) for r in rows),
    )


def main() -> int:
    sys.stdout.reconfigure(errors="replace")  # a Windows console cannot print "→"
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}" + ("" if condition or not detail else f" ({detail})"))

    with tips_app.SessionFactory() as s:
        source = m.SourceSystem(code="CLOVER", name="Clover", active=True)
        s.add(source)
        s.flush()
        merchant = m.Merchant(source_system_id=source.id, source_merchant_id="CC-MERCH", name="CC Merchant")
        s.add(merchant)
        s.flush()
        location = m.Location(
            merchant_id=merchant.id, source_system_id=source.id, source_location_id="CC-LOC",
            name="Winter Park Test", currency="USD", timezone="America/New_York", operating_day_cutoff_time=time(4, 0),
        )
        s.add(location)
        s.flush()
        restaurant = m.Restaurant(name="CC Test Restaurant", default_currency="USD")
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
                                       restaurant_role_id=role.id, valid_from=local(DAY1, 0) - timedelta(days=300),
                                       valid_to=None, assignment_source="MANUAL"))
            return e

        server = employee("CC-SRV", "Tatiana Ceban", role_server)
        host_a = employee("CC-HA", "Alessia Martini", role_host)
        host_b = employee("CC-HB", "Luis Espinoza", role_host)
        for day in (DAY1, DAY2):
            for h in (host_a, host_b):
                s.add(m.Shift(employee_id=h.id, source_system_id=source.id, location_id=location.id,
                              source_shift_id=f"SH-{h.id}-{day}", clock_in=local(day, 17), clock_out=local(day, 22)))
        rule_svc.create_rule(
            s, restaurant_id=restaurant.id, source_role_id=role_server.id, recipient_role_id=role_host.id,
            calculation_base=m.CALC_BASE_VOLUNTARY_TIP, rate=Decimal("10.0000"),
            effective_from=local(DAY1, 0) - timedelta(days=300), created_by="tester",
        )
        s.flush()
        counter = {"n": 0}

        def order(at, tip, total=10000, gratuity=0):
            counter["n"] += 1
            o = m.Order(location_id=location.id, source_system_id=source.id, source_order_id=f"CC-O{counter['n']}",
                        employee_id=server.id, source_employee_id=server.source_employee_id, created_at=at,
                        state="locked", payment_state="OPEN", currency="USD", total=total)
            s.add(o)
            s.flush()
            p = m.Payment(order_id=o.id, source_system_id=source.id, source_payment_id=f"CC-P{counter['n']}",
                          employee_id=server.id, source_employee_id=server.source_employee_id, created_at=at,
                          amount=total, result="SUCCESS", currency="USD")
            s.add(p)
            s.flush()
            s.add(m.PaymentTip(payment_id=p.id, amount=tip, source_present=True))
            if gratuity:
                s.add(m.OrderFee(order_id=o.id, source_system_id=source.id, source_line_item_id=f"FEE-{o.id}",
                                 fee_type="SERVICE_CHARGE", name_raw="Gratuity", amount=gratuity))
            s.flush()
            resolve_and_persist_order_business_date(s, o.id)
            return o

        order(local(DAY1, 18), 2000)
        order(local(DAY1, 19, 30), 1500, total=12000, gratuity=1800)
        order(local(DAY2, 1), 700)          # 01:00 on the 21st still belongs to Business Date the 20th
        order(local(DAY2, 20), 3000)
        s.commit()
        restaurant_id = restaurant.id

        # What the page showed before this change: one Business Day as the
        # window cutoff -> cutoff, through the engine's plain calculate_tips.
        old_start = datetime.combine(DAY1, time(4, 0), tzinfo=NY).astimezone(UTC)
        old = engine.calculate_tips(s, restaurant_id=restaurant_id, period_start=old_start,
                                    period_end=old_start + timedelta(days=1))
        before_figures = figures(old, engine.build_employee_review(s, old))
        new = engine.calculate_tips_for_business_dates(s, restaurant_id=restaurant_id,
                                                       first_business_date=DAY1, last_business_date=DAY1)
        engine_figures = figures(new, engine.build_employee_review(s, new))
        s.rollback()

    client = tips_app.app.test_client()
    runs_before = run_count()
    html = client.get(f"/calculate-tips?from_date={DAY1}&through_date={DAY1}").get_data(as_text=True)

    # ---- 1. Linear page, two actions -------------------------------------
    marks = ['id="calculate"', 'id="totals"', 'id="entitlements"', 'id="consolidate"']
    pos = [html.find(x) for x in marks]
    check("1. period+Calculate, Totals, Employee Entitlements, Consolidate — in that order",
          min(pos) >= 0 and pos == sorted(pos), str(pos))
    check("1. From and Through inputs, one Calculate button",
          'id="from_date"' in html and 'id="through_date"' in html and html.count(">Calculate</button>") == 1)
    check("1. no 'Run Calculation Now'", "Run Calculation Now" not in html)
    check("1. no 'Close this period' and no second pair of dates",
          "Close this period" not in html and "First Business Date" not in html and "first_business_date" not in html)
    consolidate_card = html[html.index('id="consolidate"'):]
    check("1. one Consolidate button, carrying the period only as hidden values",
          consolidate_card.count("<button") == 1 and 'type="date"' not in consolidate_card
          and f'name="from_date" value="{DAY1}"' in consolidate_card)
    check("1. result status reads CALCULATED, period 09/20/2026 → 09/20/2026",
          "CALCULATED" in html and "09/20/2026 → 09/20/2026" in html)

    # ---- 2. Same figures -------------------------------------------------
    check("2. the Business Date calculation equals the former cutoff-to-cutoff window",
          before_figures == engine_figures, f"{before_figures} vs {engine_figures}")
    vol, grat, ent, diff, per_emp = engine_figures
    money = lambda c: "${:,.2f}".format(c / 100)  # noqa: E731
    for label, value in (("Voluntary Tips", vol), ("Gratuity", grat), ("Total Tips + Gratuity", vol + grat),
                         ("Total Employee Entitlements", ent), ("Control Difference", diff)):
        found = re.search(r'<div class="label">' + re.escape(label) + r'</div><div class="value">([^<]*)</div>', html)
        check(f"2. Totals: {label} = {money(value)}", found and found.group(1) == money(value),
              found.group(1) if found else "missing")
    entitlements = html[html.index('id="entitlements"'):html.index('id="consolidate"')]
    check("2. every employee's entitlement shown as the engine computes it",
          all(money(a) in entitlements for _, a in per_emp) and len(per_emp) == 3, str(per_emp))
    check("2. employees as 'Surname I.'", "Ceban T." in entitlements and "Martini A." in entitlements)
    check("2. Calculate wrote nothing", run_count() == runs_before)

    # ---- 3. Consolidate --------------------------------------------------
    fp = re.search(r'name="fingerprint" value="([^"]*)"', html).group(1)
    resp = client.post("/calculate-tips/consolidate",
                       data={"from_date": str(DAY1), "through_date": str(DAY1), "fingerprint": fp})
    check("3. Consolidate returns to the same period", resp.status_code == 302
          and f"from_date={DAY1}" in resp.headers.get("Location", ""), resp.headers.get("Location", ""))
    check("3. exactly one Saved Period created", run_count() == runs_before + 1)
    with tips_app.SessionFactory() as s:
        run = s.scalars(select(m.TipDistributionCalculationRun).order_by(m.TipDistributionCalculationRun.id.desc())).first()
        saved = (run.voluntary_total_minor, run.gratuity_total_minor, run.control_difference_minor,
                 sorted((e.employee_id, e.payable_amount_minor) for e in
                        s.scalars(select(m.TipEntitlement).where(m.TipEntitlement.calculation_run_id == run.id))))
        run_id, run_dates = run.id, (run.first_business_date, run.last_business_date)
    check("3. saved for the period shown", run_dates == (DAY1, DAY1), str(run_dates))
    check("3. saved with the result shown (totals and every employee)",
          saved == (vol, grat, diff, per_emp), f"{saved}")
    history = client.get("/tips-runs").get_data(as_text=True)
    check("3. the period appears in Saved Periods", f"/tips-runs/{run_id}" in history)

    # ---- 4. After Consolidate --------------------------------------------
    after = client.get(f"/calculate-tips?from_date={DAY1}&through_date={DAY1}").get_data(as_text=True)
    check("4. 'Period consolidated 09/20/2026 → 09/20/2026' is shown",
          "Period consolidated 09/20/2026 → 09/20/2026" in after and "CONSOLIDATED" in after)
    check("4. no Consolidate button any more", 'id="consolidate-btn"' not in after)
    check("4. it links to the Saved Period", f"/tips-runs/{run_id}" in after)
    client.post("/calculate-tips/consolidate",
                data={"from_date": str(DAY1), "through_date": str(DAY1), "fingerprint": fp})
    check("4. posting the same result again saves nothing", run_count() == runs_before + 1)

    # ---- 5. A result that changed after it was shown ---------------------
    two_day = client.get(f"/calculate-tips?from_date={DAY1}&through_date={DAY2}").get_data(as_text=True)
    stale_fp = re.search(r'name="fingerprint" value="([^"]*)"', two_day).group(1)
    with tips_app.SessionFactory() as s:  # a Sync lands a new tipped Order on the 21st
        srv = s.scalars(select(m.Employee).where(m.Employee.source_employee_id == "CC-SRV")).one()
        loc = s.scalars(select(m.Location)).first()
        o = m.Order(location_id=loc.id, source_system_id=loc.source_system_id, source_order_id="CC-LATE",
                    employee_id=srv.id, source_employee_id="CC-SRV", created_at=local(DAY2, 21), state="locked",
                    payment_state="OPEN", currency="USD", total=5000)
        s.add(o)
        s.flush()
        p = m.Payment(order_id=o.id, source_system_id=loc.source_system_id, source_payment_id="CC-PLATE",
                      employee_id=srv.id, source_employee_id="CC-SRV", created_at=local(DAY2, 21), amount=5000,
                      result="SUCCESS", currency="USD")
        s.add(p)
        s.flush()
        s.add(m.PaymentTip(payment_id=p.id, amount=900, source_present=True))
        resolve_and_persist_order_business_date(s, o.id)
        s.commit()
    resp = client.post("/calculate-tips/consolidate",
                       data={"from_date": str(DAY1), "through_date": str(DAY2), "fingerprint": stale_fp})
    check("5. a result that changed after it was shown is not consolidated", run_count() == runs_before + 1)
    msg = client.get(resp.headers["Location"]).get_data(as_text=True)
    check("5. the person is told why", "changed after you calculated it" in msg)

    # ---- 6. AUDIT is a small indicator -----------------------------------
    check("6. AUDIT shown as a small indicator linking to the Host audit",
          "Audit mode" in html and "check Hosts" in html and "Review mode is <strong>AUDIT</strong>" not in html)

    # ---- 7. Multi-day and the former window link -------------------------
    fresh_two = client.get(f"/calculate-tips?from_date={DAY1}&through_date={DAY2}").get_data(as_text=True)
    check("7. a two-day range calculates and shows 09/20/2026 → 09/21/2026",
          "09/20/2026 → 09/21/2026" in fresh_two and 'id="consolidate-btn"' in fresh_two)
    legacy = client.get("/calculate-tips?start_at=2026-09-20T04:00&end_at=2026-09-21T04:00").get_data(as_text=True)
    check("7. the drill-down's former window link opens Business Date 09/20/2026",
          f'id="from_date" name="from_date" value="{DAY1}"' in legacy and "Period consolidated 09/20/2026" in legacy)
    check("7. no UTC and no Clover employee id on the page", "UTC" not in html and "CC-SRV" not in html)

    print()
    print(f"Calculate and Consolidate HTTP tests: {'SUCCESS' if not failed else 'FAILURE'} "
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
