"""Automated synthetic tests for `technical.connectors.clover.correction_sync`
(CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md §3-§4) — the Correction/
Reconciliation Poller.

Mirrors `clover_live_sync_validation.py`'s pattern exactly: synthetic
fixture, disposable database, a small fake Clover client, always rolled
back, never contacts Clover production.

`_CorrectionFakeCloverClient` is deliberately its OWN small fake (not a
modification of `clover_acquisition_validation.FakeCloverClient`, which many
other suites already depend on unchanged): the Correction Poller calls a
BARE `/orders` list endpoint Live Sync/Backfill never call (they only GET an
Order by id), so a distinct, narrowly-scoped fake avoids widening a shared
fixture for one new, narrow need.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .technical.connectors.clover import correction_sync as cs
from .technical.connectors.clover.acquisition import _acquisition_lock_key

UTC = timezone.utc


@dataclass
class ValidationResult:
    success: bool
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)

    def check(self, description: str, condition: bool) -> None:
        if condition:
            self.checks_passed.append(description)
        else:
            self.checks_failed.append(description)
            self.success = False


@dataclass
class _FakeResult:
    ok: bool = True
    data: Any = None
    error: str | None = None
    status_code: int = 200


class _CorrectionFakeCloverClient:
    """A GET-only, in-memory stand-in satisfying `acquisition.
    CloverReadClient`'s shape — never a network call. `fail_orders`/
    `fail_payments`/`fail_refunds` simulate that one resource's list fetch
    itself failing (HTTP-level), independent of the others, for the
    per-resource-cursor-isolation tests."""

    def __init__(self, merchant_id: str):
        self.merchant_id = merchant_id
        self.orders: list[dict[str, Any]] = []
        self.payments: list[dict[str, Any]] = []
        self.refunds: list[dict[str, Any]] = []
        self.fail_orders = False
        self.fail_payments = False
        self.fail_refunds = False
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def get(self, path: str, params: dict[str, Any] | None = None) -> _FakeResult:
        self.calls.append((path, params))
        if path.endswith("/orders"):
            if self.fail_orders:
                return _FakeResult(ok=False, error="simulated Orders list failure", status_code=500)
            return _FakeResult(ok=True, data={"elements": list(self.orders)})
        if path.endswith("/payments"):
            if self.fail_payments:
                return _FakeResult(ok=False, error="simulated Payments list failure", status_code=500)
            return _FakeResult(ok=True, data={"elements": list(self.payments)})
        if path.endswith("/refunds"):
            if self.fail_refunds:
                return _FakeResult(ok=False, error="simulated Refunds list failure", status_code=500)
            return _FakeResult(ok=True, data={"elements": list(self.refunds)})
        # Everything else (notably `.../orders/{id}/line_items`) is
        # deliberately unhandled: `historical_backfill_detail.
        # ingest_order_item_and_modifier_detail` gracefully falls back to the
        # Order's own nested `lineItems` when this dedicated fetch fails —
        # exactly the fallback this fake is designed to exercise.
        return _FakeResult(ok=False, error=f"unhandled path in fake: {path}", status_code=404)


def run_validation(session_factory: sessionmaker[Session]) -> ValidationResult:
    result = ValidationResult(success=True)
    with session_factory() as session:
        try:
            _test_non_clover_location_skips_cleanly(session, result)
            _test_cycle_skips_when_another_acquisition_is_running(session, result)
            _test_first_ever_window_uses_initial_lookback_per_resource(session, result)
            _test_correction_updates_record_outside_a_stale_createdtime_window(session, result)
            _test_per_resource_cursor_advances_only_on_its_own_success(session, result)
            _test_location_failure_does_not_affect_another_location(session, result)
            _test_repeated_cycle_is_idempotent_no_duplicates(session, result)
            _test_reconciliation_status_gates_on_all_cursors(session, result)
            _test_one_bad_record_fails_the_whole_resource_and_self_heals(session, result)
        finally:
            session.rollback()
    return result


def _build_fixture(session: Session, *, merchant_source_id: str) -> tuple[m.Restaurant, m.Location, m.SourceSystem]:
    source_system = session.scalars(select(m.SourceSystem).filter_by(code="CLOVER")).first()
    if source_system is None:
        source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
        session.add(source_system)
        session.flush()

    merchant = m.Merchant(
        source_system_id=source_system.id, source_merchant_id=merchant_source_id, name="Correction Test Merchant",
    )
    session.add(merchant)
    session.flush()

    location = m.Location(
        merchant_id=merchant.id, source_system_id=source_system.id, source_location_id=merchant_source_id,
        name="Correction Test Location", currency="USD",
    )
    session.add(location)
    session.flush()

    restaurant = m.Restaurant(name=f"Synthetic Correction Test Restaurant {merchant_source_id}", default_currency="USD")
    session.add(restaurant)
    session.flush()
    session.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
    session.flush()

    return restaurant, location, source_system


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite round-trips `DateTime(timezone=True)` as offset-naive (same
    caveat `acquisition._aware_utc` already documents) — normalize before
    comparing a DB-read value against a freshly-constructed aware one."""
    if dt is None or dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=UTC)


def _test_non_clover_location_skips_cleanly(session: Session, result: ValidationResult) -> None:
    source_system = session.scalars(select(m.SourceSystem).filter_by(code="CLOVER")).first()
    if source_system is None:
        source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
        session.add(source_system)
        session.flush()
    orphan_merchant = m.Merchant(source_system_id=source_system.id, source_merchant_id="NOCLOVERLOC-CS", name="Orphan")
    session.add(orphan_merchant)
    session.flush()
    non_clover_location = m.Location(
        merchant_id=orphan_merchant.id, source_system_id=source_system.id, source_location_id=None,
        name="Non-Clover Location", currency="USD",
    )
    session.add(non_clover_location)
    session.flush()

    summary = cs.run_correction_cycle(session, location_id=non_clover_location.id)
    result.check(
        "a Location with no Clover external identifier yields a clean skip (None), never an exception",
        summary is None,
    )


def _test_cycle_skips_when_another_acquisition_is_running(session: Session, result: ValidationResult) -> None:
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="CORR-BUSY")
    running = m.IngestionRun(
        source_system_id=source_system.id, location_id=location.id, started_at=datetime.now(UTC),
        status="RUNNING", source_window_start=datetime.now(UTC), source_window_end=datetime.now(UTC),
        lock_key=_acquisition_lock_key(location.id),
        notes="CLOVER_ACQUISITION mode=LIVE_SYNC location_id=%d; RUNNING" % location.id,
    )
    session.add(running)
    session.commit()

    summary = cs.run_correction_cycle(
        session, location_id=location.id, client=_CorrectionFakeCloverClient(merchant_id="CORR-BUSY"),
    )
    result.check(
        "a correction cycle that finds Live Sync/Backfill already RUNNING for this Location is skipped "
        "cleanly (reuses the SAME Location-scoped lock) — returns None, never raises",
        summary is None,
    )
    still_running = session.get(m.IngestionRun, running.id)
    session.refresh(still_running)
    result.check(
        "the skipped correction cycle performed no write — the other run's lock is untouched",
        still_running.status == "RUNNING" and still_running.lock_key is not None,
    )


def _test_first_ever_window_uses_initial_lookback_per_resource(session: Session, result: ValidationResult) -> None:
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="CORR-FIRST")
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=UTC)

    orders_window = cs._compute_resuming_window(
        session, location_id=location.id, source_system_id=source_system.id, resource_type=cs.RESOURCE_ORDERS,
        now=now, initial_lookback=cs.DEFAULT_INITIAL_LOOKBACK, overlap_buffer=cs.DEFAULT_OVERLAP_BUFFER,
    )
    result.check(
        "Orders' first-ever correction cycle for this Location: window_start = now - 24h, window_end = now",
        orders_window == (now - cs.DEFAULT_INITIAL_LOOKBACK, now),
    )

    client = _CorrectionFakeCloverClient(merchant_id="CORR-FIRST")
    summary = cs.run_correction_cycle(session, location_id=location.id, client=client, now=now)
    session.commit()
    result.check("first-ever correction cycle (no data) still runs cleanly", summary is not None)
    refunds_result = next(r for r in summary.results if r.resource_type == cs.RESOURCE_REFUNDS)
    result.check(
        "Refunds uses its own rolling recency window (48h), NOT the Orders/Payments resuming-cursor shape",
        refunds_result.window_start == now - cs.DEFAULT_REFUND_RECENCY_WINDOW and refunds_result.window_end == now,
    )
    for r in summary.results:
        result.check(f"resource={r.resource_type} first cycle completes with COMPLETE status", r.status == "COMPLETE")


def _test_correction_updates_record_outside_a_stale_createdtime_window(session: Session, result: ValidationResult) -> None:
    """The core gap this Poller closes (CLOVER_CONTINUOUS_SYNCHRONIZATION_
    ARCHITECTURE.md §3): an Order created long ago (far outside any
    createdTime-based window Live Sync could ever revisit) but modified
    recently must still be picked up and corrected, via `modifiedTime`
    filtering — and the correction overwrites RF-One's canonical row with
    Clover's CURRENT value, never appending a parallel history."""
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="CORR-STALE")
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=UTC)
    created_long_ago = now - timedelta(days=10)
    modified_recently = now - timedelta(minutes=30)

    client = _CorrectionFakeCloverClient(merchant_id="CORR-STALE")
    client.orders.append({
        "id": "CS-ORDER-1", "employee": {"id": "CS-EMP1"}, "createdTime": _ms(created_long_ago),
        "modifiedTime": _ms(modified_recently), "state": "locked", "paymentState": "PAID",
        "currency": "USD", "total": 1000, "lineItems": {"elements": []},
    })
    client.payments.append({
        "id": "CS-PAY-1", "order": {"id": "CS-ORDER-1"}, "employee": {"id": "CS-EMP1"},
        "tender": {"id": "CS-TND1", "label": "Cash"}, "amount": 1000, "taxAmount": 0,
        "createdTime": _ms(created_long_ago), "modifiedTime": _ms(modified_recently),
        "result": "SUCCESS", "tipAmount": 200,
    })

    summary1 = cs.run_correction_cycle(session, location_id=location.id, client=client, now=now)
    session.commit()
    session.expire_all()
    result.check(
        "first correction cycle: an Order created 10 days ago but modified 30 minutes ago IS picked up "
        "(modifiedTime filtering, not createdTime) — the exact gap Live Sync cannot close",
        summary1 is not None and all(r.status == "COMPLETE" for r in summary1.results),
    )
    order = session.scalars(select(m.Order).filter_by(source_system_id=source_system.id, source_order_id="CS-ORDER-1")).one()
    payment = session.scalars(select(m.Payment).filter_by(source_system_id=source_system.id, source_payment_id="CS-PAY-1")).one()
    tip = session.get(m.PaymentTip, payment.id)
    result.check("Order ingested with its original total", order.total == 1000)
    result.check("Payment/PaymentTip ingested with the original tip", tip is not None and tip.amount == 200)

    # === Simulate a later Clover-side correction: total and tip both change,
    # modifiedTime advances again, but createdTime never does. ===
    now2 = now + timedelta(minutes=2)
    modified_again = now2 - timedelta(seconds=10)
    client.orders[0]["total"] = 1500
    client.orders[0]["modifiedTime"] = _ms(modified_again)
    client.payments[0]["tipAmount"] = 350
    client.payments[0]["modifiedTime"] = _ms(modified_again)

    summary2 = cs.run_correction_cycle(session, location_id=location.id, client=client, now=now2)
    session.commit()
    session.expire_all()
    result.check("second correction cycle (the actual correction) runs cleanly", summary2 is not None)

    order2 = session.scalars(select(m.Order).filter_by(source_system_id=source_system.id, source_order_id="CS-ORDER-1")).one()
    payment2 = session.scalars(select(m.Payment).filter_by(source_system_id=source_system.id, source_payment_id="CS-PAY-1")).one()
    tip2 = session.get(m.PaymentTip, payment2.id)
    result.check(
        "Order's canonical row reflects Clover's CURRENT total (1500) — corrected in place, not appended",
        order2.total == 1500 and order2.id == order.id,
    )
    result.check(
        "Payment's tip reflects Clover's CURRENT value (350) — the exact scenario acquisition.py's own "
        "comment anticipates ('card tips can finalize after createdTime')",
        tip2 is not None and tip2.amount == 350,
    )
    result.check(
        "freshness: Order.modified_at advances to the new modifiedTime — current-vs-stale is answerable",
        _aware(order2.modified_at) == modified_again,
    )
    result.check(
        "no duplicate Order/Payment row was created by the correction — still exactly one of each",
        session.scalar(select(m.Order).filter_by(source_system_id=source_system.id, source_order_id="CS-ORDER-1").exists().select()) is not None
        and len(session.scalars(select(m.Order).filter_by(source_system_id=source_system.id, source_order_id="CS-ORDER-1")).all()) == 1
        and len(session.scalars(select(m.Payment).filter_by(source_system_id=source_system.id, source_payment_id="CS-PAY-1")).all()) == 1,
    )
    result.check(
        "no separate POS-history/event-log table was populated by this correction beyond the pre-existing, "
        "append-only SourceRecord Provider Mirror",
        len(session.scalars(select(m.SourceRecord).filter_by(source_system_id=source_system.id, entity_type="order", source_id="CS-ORDER-1")).all()) == 2,
    )

    orders_cursor_end, orders_status = cs._latest_cursor_end(
        session, location_id=location.id, source_system_id=source_system.id, resource_type=cs.RESOURCE_ORDERS,
    )
    result.check(
        "Orders' Modification Cursor advanced to this cycle's own window end (now2), independent of Live Cursor",
        orders_cursor_end == now2 and orders_status == "COMPLETE",
    )


def _test_per_resource_cursor_advances_only_on_its_own_success(session: Session, result: ValidationResult) -> None:
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="CORR-PARTIALFAIL")
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=UTC)
    client = _CorrectionFakeCloverClient(merchant_id="CORR-PARTIALFAIL")
    client.fail_orders = True  # Payments/Refunds still succeed in the SAME cycle

    summary = cs.run_correction_cycle(session, location_id=location.id, client=client, now=now)
    session.commit()
    result.check("a cycle with one failing resource still completes (does not raise)", summary is not None)

    orders_result = next(r for r in summary.results if r.resource_type == cs.RESOURCE_ORDERS)
    payments_result = next(r for r in summary.results if r.resource_type == cs.RESOURCE_PAYMENTS)
    refunds_result = next(r for r in summary.results if r.resource_type == cs.RESOURCE_REFUNDS)
    result.check("Orders (the failing resource) is reported FAILED", orders_result.status == "FAILED")
    result.check(
        "Payments and Refunds (unaffected resources in the SAME cycle) still succeed independently",
        payments_result.status == "COMPLETE" and refunds_result.status == "COMPLETE",
    )

    orders_cursor_end, _ = cs._latest_cursor_end(
        session, location_id=location.id, source_system_id=source_system.id, resource_type=cs.RESOURCE_ORDERS,
    )
    payments_cursor_end, _ = cs._latest_cursor_end(
        session, location_id=location.id, source_system_id=source_system.id, resource_type=cs.RESOURCE_PAYMENTS,
    )
    result.check(
        "Orders' Modification Cursor did NOT advance (no successful run exists for it yet)",
        orders_cursor_end is None,
    )
    result.check(
        "Payments' Modification Cursor DID advance, unaffected by Orders' failure in the same cycle",
        payments_cursor_end == now,
    )

    # A second cycle, Orders now recovering: proves the next cycle retries
    # the SAME ground (no gap silently skipped) rather than resuming past it.
    client.fail_orders = False
    now2 = now + timedelta(seconds=60)
    summary2 = cs.run_correction_cycle(session, location_id=location.id, client=client, now=now2)
    session.commit()
    orders_result2 = next(r for r in summary2.results if r.resource_type == cs.RESOURCE_ORDERS)
    result.check(
        "Orders recovers on the next cycle and its window still starts from the ORIGINAL initial lookback "
        "(now - 24h), never from a checkpoint a failed run never actually earned",
        orders_result2.status == "COMPLETE" and orders_result2.window_start == now2 - cs.DEFAULT_INITIAL_LOOKBACK,
    )


def _test_location_failure_does_not_affect_another_location(session: Session, result: ValidationResult) -> None:
    _r1, location_a, _s1 = _build_fixture(session, merchant_source_id="CORR-LOCA")
    _r2, location_b, _s2 = _build_fixture(session, merchant_source_id="CORR-LOCB")
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=UTC)

    client_a = _CorrectionFakeCloverClient(merchant_id="CORR-LOCA")
    client_b = _CorrectionFakeCloverClient(merchant_id="CORR-LOCB")
    client_b.fail_orders = True
    client_b.fail_payments = True
    client_b.fail_refunds = True

    summary_a = cs.run_correction_cycle(session, location_id=location_a.id, client=client_a, now=now)
    session.commit()
    summary_b = cs.run_correction_cycle(session, location_id=location_b.id, client=client_b, now=now)
    session.commit()

    result.check(
        "Location A's correction cycle succeeds fully, independent of Location B",
        summary_a is not None and all(r.status == "COMPLETE" for r in summary_a.results),
    )
    result.check(
        "Location B's total failure (all 3 resources) is isolated to Location B — never raised, never "
        "affects Location A's already-committed results",
        summary_b is not None and all(r.status == "FAILED" for r in summary_b.results),
    )


def _test_repeated_cycle_is_idempotent_no_duplicates(session: Session, result: ValidationResult) -> None:
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="CORR-IDEMP")
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=UTC)
    order_time = now - timedelta(hours=1)

    client = _CorrectionFakeCloverClient(merchant_id="CORR-IDEMP")
    client.orders.append({
        "id": "CI-ORDER-1", "employee": {"id": "CI-EMP1"}, "createdTime": _ms(order_time),
        "modifiedTime": _ms(order_time), "state": "locked", "paymentState": "PAID",
        "currency": "USD", "total": 500, "lineItems": {"elements": []},
    })
    client.payments.append({
        "id": "CI-PAY-1", "order": {"id": "CI-ORDER-1"}, "employee": {"id": "CI-EMP1"},
        "tender": {"id": "CI-TND1", "label": "Cash"}, "amount": 500, "taxAmount": 0,
        "createdTime": _ms(order_time), "modifiedTime": _ms(order_time), "result": "SUCCESS",
    })
    client.refunds.append({
        "id": "CI-REFUND-1", "orderRef": {"id": "CI-ORDER-1"}, "payment": {"id": "CI-PAY-1"},
        "createdTime": _ms(order_time), "amount": 100, "status": "PROCESSED",
    })

    # Same `now` on both cycles -> a strictly overlapping window on the
    # second run, same shape as `clover_live_sync_validation.py`'s own
    # overlap-idempotency proof.
    cs.run_correction_cycle(session, location_id=location.id, client=client, now=now)
    session.commit()
    session.expire_all()
    cs.run_correction_cycle(session, location_id=location.id, client=client, now=now)
    session.commit()
    session.expire_all()

    result.check(
        "no duplicate Order/Payment/Refund after a repeated, overlapping correction cycle",
        len(session.scalars(select(m.Order).filter_by(source_system_id=source_system.id, source_order_id="CI-ORDER-1")).all()) == 1
        and len(session.scalars(select(m.Payment).filter_by(source_system_id=source_system.id, source_payment_id="CI-PAY-1")).all()) == 1
        and len(session.scalars(select(m.Refund).filter_by(source_system_id=source_system.id, source_refund_id="CI-REFUND-1")).all()) == 1,
    )


def _test_reconciliation_status_gates_on_all_cursors(session: Session, result: ValidationResult) -> None:
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="CORR-READY")
    business_date_end = datetime(2026, 9, 10, 0, 0, 0, tzinfo=UTC)

    status0 = cs.describe_reconciliation_status(
        session, location_ids=[location.id], period_end=business_date_end,
    )
    result.check(
        "reconciliation is NOT ready when no correction/live-sync run has ever happened for this Location",
        status0.ready is False,
    )

    # Seed a Live Cursor (resource_type=None) and all 3 Correction resource
    # cursors, each past `business_date_end`.
    for resource_type in (None, *cs.ALL_RESOURCES):
        session.add(
            m.IngestionRun(
                source_system_id=source_system.id, location_id=location.id, started_at=business_date_end,
                finished_at=business_date_end, status="COMPLETE",
                source_window_start=business_date_end - timedelta(hours=1),
                source_window_end=business_date_end + timedelta(hours=1),
                resource_type=resource_type,
                notes="synthetic seed for reconciliation-status test",
            )
        )
    session.commit()

    status1 = cs.describe_reconciliation_status(
        session, location_ids=[location.id], period_end=business_date_end,
    )
    result.check(
        "reconciliation IS ready once Live Sync's cursor AND all 3 Correction resource cursors have "
        "each passed this Business Date's own end",
        status1.ready is True,
    )

    # Now let ONE resource (refunds) lag behind the Business Date.
    lagging = session.scalars(
        select(m.IngestionRun).where(
            m.IngestionRun.location_id == location.id, m.IngestionRun.resource_type == cs.RESOURCE_REFUNDS,
        )
    ).one()
    lagging.source_window_end = business_date_end - timedelta(minutes=5)
    session.commit()

    status2 = cs.describe_reconciliation_status(
        session, location_ids=[location.id], period_end=business_date_end,
    )
    result.check(
        "reconciliation is NOT ready when even ONE required resource (here: refunds) has not yet reached "
        "this Business Date's end, even though Live Sync and the other 2 resources have",
        status2.ready is False and "refunds" in status2.reason,
    )


def _test_one_bad_record_fails_the_whole_resource_and_self_heals(session: Session, result: ValidationResult) -> None:
    """Baseline-closure invariant: RF-One must NOT permanently skip a failed
    Clover correction record merely because other records in the SAME scan
    succeeded. One Order ("poisoned" so its own ingestion raises,
    independent of anything the fake Clover client itself returns) sits
    alongside one good Order in the same window. Proves: (1) the resource
    is reported FAILED, not PARTIAL/COMPLETE; (2) the checkpoint does NOT
    advance past the failed record's window; (3) the identical next cycle
    automatically retries the SAME window with no operator action and no
    need to know which record failed; (4) the good Order, retried again
    too, is upserted idempotently (no duplicate row); (5) once the poison
    is lifted, the cycle finally reports COMPLETE and the checkpoint
    advances; (6) Payments/Refunds and a SECOND, independent Location are
    completely unaffected throughout."""
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="CORR-ONEBADREC")
    other_restaurant, other_location, _other_source_system = _build_fixture(session, merchant_source_id="CORR-ONEBADREC-OTHER")
    now = datetime(2026, 9, 12, 12, 0, 0, tzinfo=UTC)

    good_order = {
        "id": "OBR-GOOD-1", "employee": {"id": "OBR-EMP1"}, "createdTime": _ms(now - timedelta(hours=2)),
        "modifiedTime": _ms(now - timedelta(hours=1)), "state": "locked", "paymentState": "PAID",
        "currency": "USD", "total": 2000, "lineItems": {"elements": []},
    }
    bad_order = {
        "id": "OBR-BAD-1", "employee": {"id": "OBR-EMP1"}, "createdTime": _ms(now - timedelta(hours=2)),
        "modifiedTime": _ms(now - timedelta(hours=1)), "state": "locked", "paymentState": "PAID",
        "currency": "USD", "total": 3000, "lineItems": {"elements": []},
    }
    client = _CorrectionFakeCloverClient(merchant_id="CORR-ONEBADREC")
    client.orders = [good_order, bad_order]

    other_client = _CorrectionFakeCloverClient(merchant_id="CORR-ONEBADREC-OTHER")

    # Poison exactly ONE Order's ingestion — independent of anything the
    # fake Clover client itself returns (a real deployment could hit this
    # from a transient DB hiccup or a genuine data-quality edge case; the
    # fix's correctness does not depend on WHY ingestion raised).
    original_ingest_order = cs._ingest_order
    poisoned = {"active": True}

    def poison_ingest_order(session_, order_raw, **kwargs):
        if poisoned["active"] and order_raw.get("id") == "OBR-BAD-1":
            raise ValueError("synthetic poison: this Order cannot be ingested")
        return original_ingest_order(session_, order_raw, **kwargs)

    cs._ingest_order = poison_ingest_order
    try:
        # === Cycle 1: one bad record among a good one -> whole resource FAILED. ===
        summary1 = cs.run_correction_cycle(session, location_id=location.id, client=client, now=now)
        session.commit()
        session.expire_all()
        orders_result1 = next(r for r in summary1.results if r.resource_type == cs.RESOURCE_ORDERS)
        result.check(
            "(1) a scan with one bad record among good ones is reported FAILED, never COMPLETE/PARTIAL",
            orders_result1.status == "FAILED",
        )
        result.check(
            "the good Order in the SAME failed scan was still upserted (per-record isolation preserved)",
            session.scalars(
                select(m.Order).filter_by(source_system_id=source_system.id, source_order_id="OBR-GOOD-1")
            ).one_or_none() is not None,
        )
        result.check(
            "the bad Order itself was never created",
            session.scalars(
                select(m.Order).filter_by(source_system_id=source_system.id, source_order_id="OBR-BAD-1")
            ).one_or_none() is None,
        )

        orders_cursor_end_1, orders_status_1 = cs._latest_cursor_end(
            session, location_id=location.id, source_system_id=source_system.id, resource_type=cs.RESOURCE_ORDERS,
        )
        result.check(
            "(2) the checkpoint does NOT advance past the failed window — no successful cursor exists yet "
            "for Orders at this Location",
            orders_cursor_end_1 is None and orders_status_1 is None,
        )

        # === Cycle 2 (poison still active): identical window is retried
        # automatically, with no operator action, no knowledge of WHICH
        # record failed, and no duplicate of the already-upserted good
        # Order. ===
        now2 = now + timedelta(minutes=1)
        summary2 = cs.run_correction_cycle(session, location_id=location.id, client=client, now=now2)
        session.commit()
        session.expire_all()
        orders_result2 = next(r for r in summary2.results if r.resource_type == cs.RESOURCE_ORDERS)
        result.check(
            "(3) the very next cycle automatically retries the SAME unresolved window — both the good AND "
            "bad Order are seen again (nothing was skipped ahead), still FAILED, still no operator input, "
            "still no record-identity required from the caller",
            orders_result2.status == "FAILED" and orders_result2.records_seen == 2,
        )
        result.check(
            "(4) the good Order, re-touched on retry, is upserted idempotently — still exactly one row",
            len(session.scalars(
                select(m.Order).filter_by(source_system_id=source_system.id, source_order_id="OBR-GOOD-1")
            ).all()) == 1,
        )

        # === Lift the poison — the SAME window (no operator needing to know
        # which record it was) now succeeds in full. ===
        poisoned["active"] = False
        now3 = now2 + timedelta(minutes=1)
        summary3 = cs.run_correction_cycle(session, location_id=location.id, client=client, now=now3)
        session.commit()
        session.expire_all()
        orders_result3 = next(r for r in summary3.results if r.resource_type == cs.RESOURCE_ORDERS)
        result.check(
            "(5) once the underlying issue is resolved, the SAME still-pending window finally reports "
            "COMPLETE, and the previously-failing Order is now ingested too",
            orders_result3.status == "COMPLETE"
            and session.scalars(
                select(m.Order).filter_by(source_system_id=source_system.id, source_order_id="OBR-BAD-1")
            ).one_or_none() is not None,
        )
        orders_cursor_end_3, orders_status_3 = cs._latest_cursor_end(
            session, location_id=location.id, source_system_id=source_system.id, resource_type=cs.RESOURCE_ORDERS,
        )
        result.check(
            "(5) the checkpoint FINALLY advances once the resource is genuinely fully successful",
            orders_status_3 == "COMPLETE" and orders_cursor_end_3 is not None,
        )

        payments_result3 = next(r for r in summary3.results if r.resource_type == cs.RESOURCE_PAYMENTS)
        refunds_result3 = next(r for r in summary3.results if r.resource_type == cs.RESOURCE_REFUNDS)
        result.check(
            "(6) Payments/Refunds for the SAME Location, and SAME cycle, were never affected by the "
            "Orders-resource failure/retry",
            payments_result3.status == "COMPLETE" and refunds_result3.status == "COMPLETE",
        )
    finally:
        cs._ingest_order = original_ingest_order

    # === (6) A completely independent, second Location is unaffected by
    # any of the above — its OWN correction cycle, never touched by the
    # first Location's poisoned Order at any point. ===
    other_summary = cs.run_correction_cycle(session, location_id=other_location.id, client=other_client, now=now)
    session.commit()
    result.check(
        "(6) a second, independent Location's own correction cycle is completely unaffected by the first "
        "Location's per-record failure/retry history",
        other_summary is not None and all(r.status == "COMPLETE" for r in other_summary.results),
    )
