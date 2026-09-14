#!/usr/bin/env python
"""Final End-to-End Validation of RF-One Tips — Payment Control (web) phase
(TASK_TIPS_END_TO_END_VALIDATION_001 §5).

Runs the SAME backend fixture as `test_tips_end_to_end.py` (Winter Park +
Mount Dora, multi-day, multi-role distribution, all three payment modes,
success/failure/retry/reversal already resolved), then opens the REAL Tips
Flask app (`03 Software/Tips/app.py`) against that same database via its
own `test_client()` to verify Payment Control: the mobile-first summary,
the responsive structural hooks (viewport meta tag, stat grid, CSS-only
responsive table), the per-payee detail figures, Attention visibility, and
the `/payment-control/cycle/<cycle_id>` deep link resolving the CORRECT
Restaurant/Cycle for each of the two Restaurants independently.

A desktop vs. smartphone VIEWPORT is a client-side CSS/rendering concern a
headless HTTP test cannot literally screenshot; what this script verifies
is the same thing `test_tips_payment_control_ui.py` already established as
sufficient evidence of responsive structure: the page ships the mobile
viewport meta tag and the responsive CSS hooks (`stat-grid`,
`responsive-table`, `status-line`) in the SAME HTML response regardless of
viewport — there is no separate "desktop HTML" vs. "mobile HTML" to diff.

Additionally seeds one extra, minimal "fresh and READY right now" cycle
(real wall-clock time, not the backend fixture's fictional 2026 dates) to
verify Approve & Pay is genuinely shown as accessible when authorized and
READY — the main fixture's two cycles are already APPROVED by the time
this phase runs, which correctly hides that control, but does not exercise
the "still open and payable" rendering path.

Never contacts Clover or Mercury production."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

_DATA_STORE_DIR = os.path.dirname(os.path.abspath(__file__))
if _DATA_STORE_DIR not in sys.path:
    sys.path.insert(0, _DATA_STORE_DIR)

from rfone_data_store.database import (  # noqa: E402
    cleanup_disposable_test_database_url, create_configured_engine, create_session_factory,
    redact_database_url, resolve_test_database_url, run_migrations_to_head,
)

import test_tips_end_to_end as backend  # noqa: E402

UTC = timezone.utc


def _seed_ready_now_cycle(session_factory, restaurant_id: int, location, source_system, person_y_id: int):
    """A minimal OPEN cycle, freshly reconciled as of REAL wall-clock time,
    so the Payment Control page's own (real-time) readiness computation
    shows READY and Approve & Pay accessible."""
    from rfone_data_store import models as m
    with session_factory() as session:
        now = datetime.now(UTC)
        backend._seed_reconciliation(session, location=location, source_system=source_system, now=now, fresh=True)
        cycle = m.TipPaymentCycle(
            restaurant_id=restaurant_id, period_start=now - timedelta(days=1), period_end=now,
            status=m.TIP_PAYMENT_CYCLE_STATUS_OPEN, triggered_by="MANUAL", notes="UI ready-now check cycle",
        )
        session.add(cycle)
        session.commit()
        return cycle.id


def main() -> int:
    checks_passed: list[str] = []
    checks_failed: list[str] = []

    def check(desc: str, cond: bool) -> None:
        (checks_passed if cond else checks_failed).append(desc)

    url = resolve_test_database_url("tips_end_to_end_ui")
    print(f"Database URL: {redact_database_url(url)}")
    run_migrations_to_head(url)
    engine = create_configured_engine(url)
    session_factory = create_session_factory(engine)

    try:
        result, ids = backend.run_validation(session_factory)
        check("backend fixture (both Restaurants, full flow) built successfully before UI phase", result.success)

        with session_factory() as session:
            from sqlalchemy import select
            from rfone_data_store import models as m
            wp = session.get(m.Restaurant, ids["wp_id"])
            wp_location_id = session.scalars(select(m.RestaurantLocation.location_id).where(m.RestaurantLocation.restaurant_id == wp.id)).first()
            wp_location = session.get(m.Location, wp_location_id)
            wp_source_system = session.get(m.SourceSystem, wp_location.source_system_id)

        ready_now_cycle_id = _seed_ready_now_cycle(session_factory, ids["wp_id"], wp_location, wp_source_system, ids["person_y_id"])

        os.environ["RFONE_DATABASE_URL"] = url
        tips_dir = os.path.normpath(os.path.join(_DATA_STORE_DIR, "..", "Tips"))
        if tips_dir not in sys.path:
            sys.path.insert(0, tips_dir)
        import app as tips_app  # noqa: E402

        client = tips_app.app.test_client()

        # --- default Payment Control (Winter Park, the lowest-id Restaurant) ---
        resp = client.get("/payment-control")
        html = resp.get_data(as_text=True)
        check("Payment Control (default/Winter Park) returns 200", resp.status_code == 200)
        check("mobile viewport meta tag present", 'name="viewport"' in html)
        check("mobile-first summary stat grid present", 'class="stat-grid"' in html)
        check("READY/NOT READY status line present", 'class="status-line' in html)
        check("Restaurant name shown", "Winter Park" in html)
        check("no Flask/connector crash despite no Mercury sandbox token in this environment", resp.status_code == 200)

        # --- deep links: each resolves its OWN Restaurant/Cycle ---
        resp_wp_cycle = client.get(f"/payment-control/cycle/{ids['cycle_wp_id']}")
        html_wp_cycle = resp_wp_cycle.get_data(as_text=True)
        check(
            "deep link to Winter Park's cycle resolves Winter Park, marks itself a deep link",
            resp_wp_cycle.status_code == 200 and f"#{ids['cycle_wp_id']}" in html_wp_cycle and "deep link" in html_wp_cycle.lower(),
        )
        # Winter Park's cycle, by this point in the flow, has: Server B
        # retried-successful, Host/Busser sent, Server A reopened by the
        # §9 reversal -> its Attention must be visible.
        check("Attention is visible on the deep-linked Winter Park cycle (Server A's reopened item)", "NEEDS_ATTENTION" in html_wp_cycle)
        check("per-payee detail (Business Date breakdown) is present", "Business Date(s)" in html_wp_cycle)
        check("responsive (table -> card) CSS hook present on a cycle that actually has instructions to render", 'class="responsive-table"' in html_wp_cycle)
        check("no full account/routing number or recipient id ever rendered", "WP-RECIP" not in html_wp_cycle and "routing_number" not in html_wp_cycle and "account_number" not in html_wp_cycle)

        resp_md_cycle = client.get(f"/payment-control/cycle/{ids['cycle_md_id']}")
        html_md_cycle = resp_md_cycle.get_data(as_text=True)
        check(
            "deep link to Mount Dora's cycle resolves Mount Dora, NOT Winter Park's content",
            resp_md_cycle.status_code == 200 and f"#{ids['cycle_md_id']}" in html_md_cycle and "Mount Dora" in html_md_cycle,
        )
        content_md = html_md_cycle.split('id="content-start"', 1)[-1]
        check("Mount Dora's deep-linked content never shows Winter Park's name (Restaurant separation holds in the UI too)", "Winter Park" not in content_md)

        # --- a genuinely READY, OPEN cycle: Approve & Pay must be visibly offered ---
        resp_ready = client.get(f"/payment-control/cycle/{ready_now_cycle_id}")
        html_ready = resp_ready.get_data(as_text=True)
        check("a fresh, READY, OPEN cycle shows the READY status", resp_ready.status_code == 200 and "READY FOR PAYMENT" in html_ready)
        check("Approve & Pay control is present for a READY, authorized-identity-available cycle", "Approve &amp; Pay" in html_ready or "Approve & Pay" in html_ready)
        check("the authorized identity (Person Y, Winter-Park-scoped) is offered in the Acting-as list", "Person Y" in html_ready)

    finally:
        engine.dispose()
        cleanup_disposable_test_database_url(url)

    if not checks_failed:
        print(f"Tips End-to-End (Payment Control UI) tests: SUCCESS ({len(checks_passed)}/{len(checks_passed)} checks passed)")
        return 0
    print(f"Tips End-to-End (Payment Control UI) tests: FAILURE ({len(checks_passed)} passed, {len(checks_failed)} failed)")
    for d in checks_failed:
        print(f"  FAILED: {d}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
