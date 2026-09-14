#!/usr/bin/env python
"""End-to-end UI checks for the Tips Payment Control page
(TASK_TIPS_RECONCILIATION_AND_PAYMENT_CONTROL_001 §5-§8).

Unlike every other `test_*.py` in this directory, this one exercises the
REAL Flask app (`03 Software/Tips/app.py`) via its own `test_client()` —
proving the actual rendered HTML, not just the service layer underneath it.
Seeds a disposable SQLite database directly via SQLAlchemy, then points the
Flask app's own `RFONE_DATABASE_URL` at that same file before importing it,
so both this script and the Flask app operate on identical data.

Checks:
  - desktop render: the Payment Control page renders successfully and shows
    the mobile-first summary/READY status/instructions table.
  - responsive structure: the viewport meta tag and the `.responsive-table`/
    `.stat-grid` CSS hooks are present — the CSS itself is exercised
    visually by a real browser, not by this script; what a Python test CAN
    prove is that the responsive markup/hooks actually ship in the response.
  - deep link: `/payment-control/cycle/<id>` resolves the CORRECT Payment
    Cycle/Restaurant, independent of `_default_restaurant()`.
  - detail view: the per-payee Business Date breakdown (gross/outbound/
    inbound/payable) renders with the correct figures.
  - no sensitive banking data (full account/routing number, token, secret)
    ever appears in the rendered HTML.

Never contacts Clover or Mercury production; the Mercury sandbox client
call this route makes is expected to fail cleanly (no `MERCURY_SANDBOX_
API_TOKEN` in this test environment) and is tolerated via `connector_error`,
exactly as the app itself already handles it.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

_DATA_STORE_DIR = os.path.dirname(os.path.abspath(__file__))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import (  # noqa: E402
    cleanup_disposable_test_database_url, create_configured_engine, create_session_factory,
    redact_database_url, resolve_test_database_url, run_migrations_to_head,
)

UTC = timezone.utc


@dataclass
class ValidationResult:
    success: bool = True
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)

    def check(self, description: str, condition: bool) -> None:
        if condition:
            self.checks_passed.append(description)
        else:
            self.checks_failed.append(description)
            self.success = False


def _seed(session_factory, *, now: datetime) -> tuple[int, int, int]:
    """Returns (restaurant_id, cycle_id, other_restaurant_cycle_id) —
    TWO independent Restaurants/Cycles, so the deep-link test can prove it
    resolves the RIGHT one, never merely "the" (single, default) one."""
    from rfone_data_store import authority_service, models as m

    with session_factory() as session:
        def build_restaurant(suffix: str):
            source_system = session.query(m.SourceSystem).filter_by(code="CLOVER").first()
            if source_system is None:
                source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
                session.add(source_system)
                session.flush()
            merchant = m.Merchant(source_system_id=source_system.id, source_merchant_id=f"UI-{suffix}", name="UI Test Merchant")
            session.add(merchant)
            session.flush()
            location = m.Location(
                merchant_id=merchant.id, source_system_id=source_system.id, source_location_id=f"UI-{suffix}",
                name="UI Test Location", currency="USD",
            )
            session.add(location)
            session.flush()
            restaurant = m.Restaurant(name=f"UI Test Restaurant {suffix}", default_currency="USD")
            session.add(restaurant)
            session.flush()
            session.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
            session.flush()

            fresh = now - timedelta(seconds=10)
            session.add(m.IngestionRun(
                source_system_id=source_system.id, location_id=location.id, started_at=fresh, finished_at=fresh,
                status="COMPLETE", mode="LIVE_SYNC", source_window_start=fresh - timedelta(minutes=1), source_window_end=fresh,
                notes="CLOVER_ACQUISITION mode=LIVE_SYNC",
            ))
            session.add(m.IngestionRun(
                source_system_id=source_system.id, location_id=location.id, started_at=fresh, finished_at=fresh,
                status="COMPLETE", mode="RECONCILIATION", source_window_start=fresh - timedelta(minutes=1), source_window_end=fresh,
                notes="CLOVER_ACQUISITION mode=RECONCILIATION",
            ))

            role = m.RestaurantRole(restaurant_id=restaurant.id, name="Server")
            session.add(role)
            session.flush()
            employee = m.Employee(
                location_id=location.id, source_system_id=source_system.id, source_employee_id=f"UI-EMP-{suffix}",
                display_name=f"UI Test Server {suffix}", system_role="EMPLOYEE",
            )
            session.add(employee)
            session.flush()
            session.add(m.EmployeeExternalPaymentAccount(
                employee_id=employee.id, provider="MERCURY", provider_recipient_id=f"SECRET-RECIPIENT-{suffix}-DO-NOT-LEAK",
                is_active=True,
            ))

            cycle = m.TipPaymentCycle(
                restaurant_id=restaurant.id, period_start=now - timedelta(days=2), period_end=now,
                status=m.TIP_PAYMENT_CYCLE_STATUS_OPEN, triggered_by="MANUAL", notes="UI test cycle",
            )
            session.add(cycle)
            session.flush()
            instruction = m.TipPaymentInstruction(
                payment_cycle_id=cycle.id, employee_id=employee.id, amount_minor=5500, status="READY",
            )
            session.add(instruction)
            session.flush()

            run = m.TipDistributionCalculationRun(
                restaurant_id=restaurant.id, period_start=now - timedelta(days=2), period_end=now - timedelta(days=1),
                status="COMPLETE",
            )
            session.add(run)
            session.flush()
            session.add(m.TipEntitlement(
                calculation_run_id=run.id, restaurant_id=restaurant.id, business_date=date(2026, 9, 10),
                employee_id=employee.id, gross_amount_minor=6000, outbound_amount_minor=1000,
                inbound_amount_minor=500, payable_amount_minor=5500, tip_payment_instruction_id=instruction.id,
            ))

            approver = m.ActingIdentity(kind="HUMAN_USER", display_name=f"UI Approver {suffix}", is_active=True)
            session.add(approver)
            session.flush()
            authority_service.grant_authority(
                session, actor=approver, domain="TIPS", action="APPROVE_AND_PAY",
                scope_type=m.SCOPE_RESTAURANT, scope_id=restaurant.id,
            )
            session.commit()
            return restaurant.id, cycle.id

        restaurant_a_id, cycle_a_id = build_restaurant("A")
        restaurant_b_id, cycle_b_id = build_restaurant("B")
        return restaurant_a_id, cycle_a_id, cycle_b_id


def main() -> int:
    result = ValidationResult()
    now = datetime.now(UTC)

    url = resolve_test_database_url("tips_payment_control_ui")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)
    session_factory = create_session_factory(engine)

    try:
        restaurant_a_id, cycle_a_id, cycle_b_id = _seed(session_factory, now=now)

        os.environ["RFONE_DATABASE_URL"] = url
        tips_dir = os.path.normpath(os.path.join(_DATA_STORE_DIR, "..", "Tips"))
        if tips_dir not in sys.path:
            sys.path.insert(0, tips_dir)
        import app as tips_app  # noqa: E402  (Tips/app.py — imported AFTER RFONE_DATABASE_URL is set)

        client = tips_app.app.test_client()

        # --- desktop / structural render (test 15/16) ---
        resp = client.get("/payment-control")
        result.check("Payment Control GET / returns 200", resp.status_code == 200)
        html = resp.get_data(as_text=True)
        result.check("the base template ships a mobile viewport meta tag", 'name="viewport"' in html)
        result.check("the mobile-first summary stat grid is present", 'class="stat-grid"' in html)
        result.check("the READY/NOT READY status line is present", 'class="status-line' in html)
        result.check(
            "the Payment Instructions table opts into the responsive (table -> card) CSS technique",
            'class="responsive-table"' in html,
        )
        result.check("Approve & Pay control is present and labeled clearly", "Approve &amp; Pay" in html or "Approve & Pay" in html)

        # --- deep link (test 17) ---
        resp_a = client.get(f"/payment-control/cycle/{cycle_a_id}")
        html_a = resp_a.get_data(as_text=True)
        result.check(
            "deep link to Cycle A's id resolves Cycle A's own Restaurant/Cycle — not the default one",
            resp_a.status_code == 200 and f"#{cycle_a_id}" in html_a and "UI Test Restaurant A" in html_a,
        )
        resp_b = client.get(f"/payment-control/cycle/{cycle_b_id}")
        html_b = resp_b.get_data(as_text=True)
        # Scoped to the Payment Control CONTENT card only — the shared
        # site-wide header brand name intentionally still reflects this
        # pilot app's single `_default_restaurant()` convention (unrelated
        # to Payment Control's own correctness) everywhere else in this app;
        # what must never leak between Restaurants is the actual Payment
        # Control page CONTENT this route renders.
        content_b = html_b.split('id="content-start"', 1)[-1] if 'id="content-start"' in html_b else html_b
        result.check(
            "a DIFFERENT deep link (Cycle B) resolves Cycle B's own Restaurant/Cycle content, not A's",
            resp_b.status_code == 200 and f"#{cycle_b_id}" in content_b and "UI Test Restaurant B" in content_b
            and "UI Test Restaurant A" not in content_b,
        )
        result.check("the deep-link view marks itself as such", "deep link" in html_a.lower())

        # --- detail view (test 18) ---
        result.check(
            "the per-payee detail shows the correct gross/outbound/inbound/payable figures for Cycle A",
            "$60.00" in html_a and "$10.00" in html_a and "$5.00" in html_a and "$55.00" in html_a,
        )
        result.check("the detail view shows the correct Business Date", "2026-09-10" in html_a)

        # --- no sensitive banking data (test 19) ---
        # Checks actual VALUES that would constitute a leak — never a blanket
        # ban on the English words "token"/"secret", which legitimately
        # appear in this page's own boundary-explaining copy ("never a
        # production Mercury endpoint or token").
        for forbidden in (
            "SECRET-RECIPIENT-A-DO-NOT-LEAK", "SECRET-RECIPIENT-B-DO-NOT-LEAK",
            "routing_number", "account_number", "routingNumber", "accountNumber",
        ):
            result.check(f"'{forbidden}' never appears in the rendered Payment Control HTML", forbidden not in html_a and forbidden not in html_b)
    finally:
        engine.dispose()
        cleanup_disposable_test_database_url(url)

    if result.success:
        print(f"Tips Payment Control UI tests: SUCCESS ({len(result.checks_passed)}/{len(result.checks_passed)} checks passed)")
        return 0
    print(f"Tips Payment Control UI tests: FAILURE ({len(result.checks_passed)} passed, {len(result.checks_failed)} failed)")
    for description in result.checks_failed:
        print(f"  FAILED: {description}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
