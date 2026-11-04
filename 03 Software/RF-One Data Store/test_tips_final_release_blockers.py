#!/usr/bin/env python
"""Tips release blockers T1-T3 (BANK_FINAL_RELEASE_BLOCKERS_001).

T1  ONE persisted calculation: `calculation_run_service.save_calculation_run`,
    over the Location's Business Day (America/New_York, 04:00 cutoff, Order
    Open Time) — reached by "Run Calculation Now", the scheduler and
    "Calculate and save this period" alike. The Calculate Tips preview
    persists nothing.
T2  Only a FINAL run's entitlements are payable; a Business Date can sit in
    one FINAL run only, so it is never paid twice.
T3  Clover's fee-line `percentage` is scaled down x10000 to the canonical
    percent, which fits the PostgreSQL `Numeric(7,4)` column.

Runs on a disposable database. Never touches AWS, Clover or Mercury.
"""

from __future__ import annotations

import inspect
import sys
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

from rfone_data_store import models as m
from rfone_data_store import rfone_account_service as account_service
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    resolve_test_database_url,
    run_migrations_to_head,
)
from rfone_data_store.technical.connectors.clover import mapping as clover_mapping
from rfone_data_store.tips import calculation_run_service as run_svc
from rfone_data_store.tips import distribution_engine as engine_svc
from rfone_data_store.tips import payment_cycle_service as cycle_svc
from rfone_data_store.tips import payout_process as payout_svc
from rfone_data_store.tips import readiness as readiness_svc
from rfone_data_store.tips import schedule_service as sched_svc
from rfone_data_store.tips import scheduler
from rfone_data_store.tips_scheduler_validation import _build_fixture

TIPS_APP = Path(__file__).resolve().parent.parent / "Tips" / "app.py"
DAY = date(2026, 5, 3)          # EDT: the Business Day runs 08:00 UTC May 3 -> 08:00 UTC May 4


def main() -> int:
    passed: list[str] = []
    failed: list[str] = []

    def check(description: str, condition: bool, detail: str = "") -> None:
        (passed if condition else failed).append(description)
        print(f"  {'PASS' if condition else 'FAIL'}  {description}"
              + ("" if condition or not detail else f" ({detail})"))

    url = resolve_test_database_url("tips_final_release_blockers")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)
    try:
        with create_session_factory(engine)() as s:
            restaurant, location, source_system, employee = _build_fixture(s, suffix="FRB")
            n = [0]

            def order_at(opened_utc: datetime, tip_minor: int, business_date: date = DAY) -> None:
                n[0] += 1
                order = m.Order(
                    location_id=location.id, source_system_id=source_system.id,
                    source_order_id=f"FRB-ORDER-{n[0]}", employee_id=employee.id,
                    source_employee_id=employee.source_employee_id, created_at=opened_utc,
                    business_date=business_date, state="locked", payment_state="PAID",
                    currency="USD", total=10000,
                )
                s.add(order)
                s.flush()
                payment = m.Payment(
                    order_id=order.id, source_system_id=source_system.id,
                    source_payment_id=f"FRB-PAY-{n[0]}", employee_id=employee.id,
                    source_employee_id=employee.source_employee_id, created_at=opened_utc,
                    amount=10000, result="SUCCESS", currency="USD",
                )
                s.add(payment)
                s.flush()
                s.add(m.PaymentTip(payment_id=payment.id, amount=tip_minor, source_present=True))
                s.commit()

            # Three orders of ONE Business Day (May 3, New York):
            order_at(datetime(2026, 5, 3, 15, 0, tzinfo=UTC), 1000)   # 11:00 EDT May 3
            order_at(datetime(2026, 5, 4, 2, 0, tzinfo=UTC), 2000)    # 22:00 EDT May 3 — UTC says May 4
            order_at(datetime(2026, 5, 4, 7, 0, tzinfo=UTC), 4000)    # 03:00 EDT May 4, before the cutoff

            validator = account_service.create_account(
                s, username="frb-validator", display_name="FRB Validator",
                password="a-long-enough-test-password", is_admin=False,
            )
            s.commit()

            def entitlements_of(run) -> int:
                return s.scalar(select(func.coalesce(func.sum(m.TipEntitlement.gross_amount_minor), 0))
                                .where(m.TipEntitlement.calculation_run_id == run.id))

            # ---- 1. manual and scheduler share ONE service -------------------
            calls: list[tuple] = []
            original = run_svc.save_calculation_run

            def spy(session, **kwargs):
                calls.append((kwargs["first_business_date"], kwargs["last_business_date"]))
                return original(session, **kwargs)

            run_svc.save_calculation_run = spy
            try:
                manual = payout_svc.run_calculation_now(s, restaurant_id=restaurant.id)
                s.commit()
            finally:
                run_svc.save_calculation_run = original
            app_source = TIPS_APP.read_text(encoding="utf-8")
            check("1. Run Calculation Now persists through save_calculation_run, the service "
                  "'Calculate and save this period' calls; the scheduler calls Run Calculation Now",
                  manual.ran and calls == [(DAY, DAY)]
                  and "run_svc.save_calculation_run(" in app_source
                  and "payout_svc.run_calculation_now(" in inspect.getsource(scheduler.run_due_calculations)
                  and "run_tip_distribution_calculation" not in inspect.getsource(payout_svc)
                  and "populate_entitlements_for_run" not in app_source,
                  detail=str(calls))
            run = manual.calculation_run

            # ---- 2, 3. the Business Day window -------------------------------
            expected_start = datetime(2026, 5, 3, 8, 0, tzinfo=UTC)
            expected_end = datetime(2026, 5, 4, 8, 0, tzinfo=UTC)

            def aware(dt):
                return dt if dt.tzinfo else dt.replace(tzinfo=UTC)

            check("2. the persisted window is the Location's Business Day: America/New_York, 04:00 cutoff",
                  aware(run.period_start) == expected_start and aware(run.period_end) == expected_end
                  and run.timezone_name == "America/New_York"
                  and run.operating_day_cutoff_time == time(4, 0)
                  and readiness_svc.business_date_period(DAY, location) == (expected_start, expected_end),
                  detail=f"{run.period_start} -> {run.period_end}")
            check("3. no UTC-midnight boundary: the 22:00 and 03:00 EDT orders (May 4 in UTC) count on "
                  "May 3 by Order Open Time",
                  entitlements_of(run) == 7000, detail=str(entitlements_of(run)))
            midnight_runs = s.scalar(select(func.count(m.TipDistributionCalculationRun.id)).where(
                m.TipDistributionCalculationRun.restaurant_id == restaurant.id,
                m.TipDistributionCalculationRun.period_start == datetime(2026, 5, 3, tzinfo=UTC)))
            check("3b. no persisted run for the Restaurant starts at UTC midnight", midnight_runs == 0)

            # ---- 5. the preview persists nothing -----------------------------
            runs_before = s.scalar(select(func.count(m.TipDistributionCalculationRun.id)))
            ents_before = s.scalar(select(func.count(m.TipEntitlement.id)))
            preview = engine_svc.calculate_tips_for_business_dates(
                s, restaurant_id=restaurant.id, first_business_date=DAY, last_business_date=DAY,
            )
            s.commit()
            check("5. the stateless preview persists no run and no entitlement",
                  not preview.blocked_reason
                  and s.scalar(select(func.count(m.TipDistributionCalculationRun.id))) == runs_before
                  and s.scalar(select(func.count(m.TipEntitlement.id))) == ents_before)

            # ---- 7. a CALCULATED run is not payable --------------------------
            check("7. an unvalidated (CALCULATED) run's entitlements are excluded from payment",
                  run.state == m.TIPS_RUN_STATE_CALCULATED
                  and cycle_svc.get_unpaid_entitlements(s, restaurant.id) == []
                  and cycle_svc.start_payment_cycle(s, restaurant_id=restaurant.id, triggered_by="MANUAL") is None)
            s.rollback()

            # ---- 6. "Calculate and save this period" -------------------------
            # One order of the NEXT Business Day, opened after the cutoff.
            order_at(datetime(2026, 5, 4, 9, 0, tzinfo=UTC), 8000, date(2026, 5, 4))  # 05:00 EDT May 4
            saved, _ = run_svc.save_calculation_run(
                s, restaurant_id=restaurant.id, first_business_date=DAY, last_business_date=DAY,
            )
            s.commit()
            check("6. 'Calculate and save this period' uses the same engine and window: same figures "
                  "(the 05:00 EDT May 4 order excluded), same Business Day, a validatable CALCULATED run — not a second engine's answer",
                  saved.id != run.id and entitlements_of(saved) == entitlements_of(run) == 7000
                  and aware(saved.period_start) == aware(run.period_start)
                  and aware(saved.period_end) == aware(run.period_end)
                  and saved.state == m.TIPS_RUN_STATE_CALCULATED,
                  detail=f"{entitlements_of(saved)}/{entitlements_of(run)} {saved.period_start}/{run.period_start} {saved.state}")

            # ---- 8, 9. FINAL payable, superseded not -------------------------
            final, reason = run_svc.validate_run(s, run_id=saved.id, account_id=validator.id)
            s.commit()
            payable = cycle_svc.get_unpaid_entitlements(s, restaurant.id)
            check("8. the FINAL (validated) run's entitlements are payable",
                  final is not None and payable and all(e.calculation_run_id == saved.id for e in payable),
                  detail=reason)
            check("9. the superseded, never-final run's entitlements are not payable",
                  all(e.calculation_run_id != run.id for e in payable))

            # ---- 4, 10. one payable population per Business Date -------------
            refused, refusal = run_svc.validate_run(s, run_id=run.id, account_id=validator.id)
            s.rollback()
            wide, _ = run_svc.save_calculation_run(
                s, restaurant_id=restaurant.id,
                first_business_date=DAY, last_business_date=date(2026, 5, 4),
            )
            wide_refused, wide_refusal = run_svc.validate_run(s, run_id=wide.id, account_id=validator.id)
            s.commit()
            check("4. the same Business Date cannot have two payable entitlement populations: a second "
                  "run for it is refused finalization",
                  refused is None and "final" in refusal.lower(), detail=refusal)
            check("4b. ...including a run whose range only OVERLAPS the final one",
                  wide_refused is None and wide.state == m.TIPS_RUN_STATE_CALCULATED, detail=wide_refusal)
            cycle = cycle_svc.start_payment_cycle(s, restaurant_id=restaurant.id, triggered_by="MANUAL")
            s.commit()
            instructions = list(s.scalars(select(m.TipPaymentInstruction).where(
                m.TipPaymentInstruction.payment_cycle_id == cycle.id)))
            check("10. two runs for the same Business Date cannot both be paid: the cycle carries the "
                  "FINAL run's amount once",
                  len(instructions) == 1 and instructions[0].amount_minor == 7000
                  and cycle_svc.get_unpaid_entitlements(s, restaurant.id) == [],
                  detail=str([i.amount_minor for i in instructions]))

            # Scheduler: the automatic path reaches the SAME service.
            restaurant2, location2, source2, employee2 = _build_fixture(s, suffix="FRB2")
            s.add(m.Order(
                location_id=location2.id, source_system_id=source2.id, source_order_id="FRB2-O1",
                employee_id=employee2.id, source_employee_id=employee2.source_employee_id,
                created_at=datetime(2026, 5, 3, 15, tzinfo=UTC), business_date=DAY, state="locked",
                payment_state="PAID", currency="USD", total=10000,
            ))
            s.commit()
            now = datetime(2026, 5, 4, 23, 0, tzinfo=UTC)
            from datetime import timedelta
            sched_svc.set_calculation_schedule(
                s, restaurant_id=restaurant2.id, mode="AUTOMATIC", interval_days=1,
                execution_time=time(22, 0), anchor_date=DAY, effective_from=now - timedelta(days=2),
            )
            s.commit()
            calls.clear()
            run_svc.save_calculation_run = spy
            try:
                outcomes = [o for o in scheduler.run_due_calculations(s, now=now)
                            if o.restaurant_id == restaurant2.id]
                s.commit()
            finally:
                run_svc.save_calculation_run = original
            check("1b. the scheduler's calculation goes through the same save_calculation_run",
                  len(outcomes) == 1 and outcomes[0].result.ran and calls == [(DAY, DAY)],
                  detail=str(calls))

            # ---- 11. Clover fee percentage ------------------------------------
            fee = clover_mapping.map_order_fee({"id": "F1", "name": "Service Charge", "price": 1800,
                                                "percentage": 180000})
            column = m.OrderFee.__table__.c.percentage.type if hasattr(m, "OrderFee") else None
            fits = fee["percentage"] is not None and abs(fee["percentage"]) < Decimal(10) ** (
                (column.precision - column.scale) if column is not None else 3)
            check("11. Clover fee percentage 180000 maps to 18 percent, which fits Numeric(7,4) "
                  "(PostgreSQL rejects the raw value)",
                  fee["percentage"] == Decimal("18") and fits
                  and clover_mapping.map_order_fee({"id": "F2", "price": 5})["percentage"] is None,
                  detail=str(fee["percentage"]))
    finally:
        engine.dispose()

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
