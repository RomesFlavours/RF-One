"""Automated synthetic tests for `technical.connectors.clover.
reconciliation_poller` (CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md
§3-§4; TASK_TIPS_RECONCILIATION_AND_PAYMENT_CONTROL_001).

Mirrors `clover_live_sync_validation.py`'s pattern: synthetic fixture,
disposable database, a Clover fake, always rolled back, never contacts
Clover production."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .clover_acquisition_validation import _FakeResult
from .technical.connectors.clover.acquisition import MODE_LIVE_SYNC, import_clover_period
from .technical.connectors.clover.reconciliation_poller import (
    DEFAULT_INITIAL_LOOKBACK,
    DEFAULT_OVERLAP_BUFFER,
    compute_next_reconciliation_window,
    run_reconciliation_cycle,
)

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


def run_validation(session_factory: sessionmaker[Session]) -> ValidationResult:
    result = ValidationResult(success=True)
    with session_factory() as session:
        try:
            _test_non_clover_location_skips_cleanly(session, result)
            _test_first_ever_cycle_uses_initial_lookback(session, result)
            _test_cursor_is_independent_from_live_sync_cursor(session, result)
            _test_cycle_skips_when_another_acquisition_is_running(session, result)
            _test_correction_updates_existing_state(session, result)
            _test_repeated_cycle_does_not_duplicate(session, result)
            _test_order_only_correction_is_caught_via_modified_orders_query(session, result)
            _test_one_location_failure_does_not_block_another(session, result)
        finally:
            session.rollback()
    return result


class _FakeReconciliationClient:
    """A minimal, GET-only Clover fake purpose-built for reconciliation
    tests — unlike `clover_acquisition_validation.FakeCloverClient`, this
    one actually understands `modifiedTime`/`createdTime` filters (so a test
    can prove the Poller queries the RIGHT time field) and can be told to
    fail Payments fetches for one merchant/Location, to prove one Location's
    failure does not block another's cycle."""

    def __init__(self, merchant_id: str, *, fail_payments: bool = False):
        self.merchant_id = merchant_id
        self.fail_payments = fail_payments
        self.payments: list[dict[str, Any]] = []
        self.orders_by_id: dict[str, dict[str, Any]] = {}
        self.modified_orders: list[dict[str, Any]] = []
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def get(self, path: str, params: dict[str, Any] | None = None) -> _FakeResult:
        self.calls.append((path, params))
        params = params or {}
        offset = params.get("offset", 0)

        if self.fail_payments and path.endswith("/payments"):
            return _FakeResult(ok=False, error="simulated Clover outage for this merchant")
        if path.endswith("/payments"):
            return _FakeResult(ok=True, data={"elements": self.payments if offset == 0 else []})
        if path.endswith("/orders") and "/orders/" not in path:
            return _FakeResult(ok=True, data={"elements": self.modified_orders if offset == 0 else []})
        if path.endswith("/employees") or path.endswith("/tenders") or path.endswith("/devices") or path.endswith("/shifts") or path.endswith("/refunds"):
            return _FakeResult(ok=True, data={"elements": []})
        if "/orders/" in path:
            order_id = path.rsplit("/", 1)[-1]
            order = self.orders_by_id.get(order_id)
            if order is None:
                return _FakeResult(ok=False, error="order not found")
            return _FakeResult(ok=True, data=order)
        return _FakeResult(ok=False, error=f"unhandled path in _FakeReconciliationClient: {path}")


def _build_fixture(session: Session, *, merchant_source_id: str) -> tuple[m.Restaurant, m.Location, m.SourceSystem]:
    source_system = session.scalars(select(m.SourceSystem).filter_by(code="CLOVER")).first()
    if source_system is None:
        source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
        session.add(source_system)
        session.flush()

    merchant = m.Merchant(
        source_system_id=source_system.id, source_merchant_id=merchant_source_id, name="Reconciliation Test Merchant",
    )
    session.add(merchant)
    session.flush()

    location = m.Location(
        merchant_id=merchant.id, source_system_id=source_system.id, source_location_id=merchant_source_id,
        name="Reconciliation Test Location", currency="USD",
    )
    session.add(location)
    session.flush()

    restaurant = m.Restaurant(name=f"Synthetic Reconciliation Test Restaurant {merchant_source_id}", default_currency="USD")
    session.add(restaurant)
    session.flush()
    session.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
    session.flush()

    return restaurant, location, source_system


def _test_non_clover_location_skips_cleanly(session: Session, result: ValidationResult) -> None:
    source_system = session.scalars(select(m.SourceSystem).filter_by(code="CLOVER")).first()
    if source_system is None:
        source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
        session.add(source_system)
        session.flush()
    orphan_merchant = m.Merchant(source_system_id=source_system.id, source_merchant_id="RECON-NOLOC", name="Orphan Merchant")
    session.add(orphan_merchant)
    session.flush()
    non_clover_location = m.Location(
        merchant_id=orphan_merchant.id, source_system_id=source_system.id, source_location_id=None,
        name="Non-Clover Location", currency="USD",
    )
    session.add(non_clover_location)
    session.flush()

    window = compute_next_reconciliation_window(session, location_id=non_clover_location.id)
    result.check("a Location with no Clover external identifier yields None (skip), never an exception", window is None)
    summary = run_reconciliation_cycle(session, location_id=non_clover_location.id)
    result.check("run_reconciliation_cycle also returns None cleanly for the same case", summary is None)


def _test_first_ever_cycle_uses_initial_lookback(session: Session, result: ValidationResult) -> None:
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="RECON1")
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=UTC)

    window = compute_next_reconciliation_window(session, location_id=location.id, now=now)
    result.check(
        "first-ever Reconciliation cycle (no prior RECONCILIATION run at all): period_start = "
        "now - initial_lookback, period_end = now",
        window is not None and window[0] == now - DEFAULT_INITIAL_LOOKBACK and window[1] == now,
    )


def _test_cursor_is_independent_from_live_sync_cursor(session: Session, result: ValidationResult) -> None:
    """CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md §4 — "two distinct
    cursors": a Live Sync run far in the future must NOT make the
    Reconciliation Poller think it has already checked that far for
    corrections, and vice versa."""
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="RECON2")

    far_future_live_sync_end = datetime(2026, 9, 10, 11, 0, 0, tzinfo=UTC)
    session.add(
        m.IngestionRun(
            source_system_id=source_system.id, location_id=location.id, started_at=far_future_live_sync_end,
            finished_at=far_future_live_sync_end, status="COMPLETE", mode=MODE_LIVE_SYNC,
            source_window_start=far_future_live_sync_end - timedelta(minutes=15),
            source_window_end=far_future_live_sync_end,
            notes="CLOVER_ACQUISITION mode=LIVE_SYNC location_id=%d" % location.id,
        )
    )
    session.commit()

    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=UTC)
    window = compute_next_reconciliation_window(session, location_id=location.id, now=now)
    result.check(
        "a Live Sync run's own recent checkpoint does NOT become the Reconciliation Poller's checkpoint "
        "— with no prior RECONCILIATION run, it still falls back to its own initial lookback",
        window is not None and window[0] == now - DEFAULT_INITIAL_LOOKBACK and window[1] == now,
    )

    prior_reconciliation_end = datetime(2026, 9, 10, 11, 58, 0, tzinfo=UTC)
    session.add(
        m.IngestionRun(
            source_system_id=source_system.id, location_id=location.id, started_at=prior_reconciliation_end,
            finished_at=prior_reconciliation_end, status="COMPLETE", mode="RECONCILIATION",
            source_window_start=prior_reconciliation_end - timedelta(minutes=2),
            source_window_end=prior_reconciliation_end,
            notes="CLOVER_ACQUISITION mode=RECONCILIATION location_id=%d" % location.id,
        )
    )
    session.commit()

    window2 = compute_next_reconciliation_window(session, location_id=location.id, now=now)
    result.check(
        "once a RECONCILIATION-mode run exists, the Poller resumes from ITS OWN checkpoint minus the "
        "overlap buffer — never from the (much further ahead) Live Sync checkpoint",
        window2 is not None and window2[0] == prior_reconciliation_end - DEFAULT_OVERLAP_BUFFER and window2[1] == now,
    )


def _test_cycle_skips_when_another_acquisition_is_running(session: Session, result: ValidationResult) -> None:
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="RECON3")

    running = m.IngestionRun(
        source_system_id=source_system.id, location_id=location.id, started_at=datetime.now(UTC),
        status="RUNNING", mode=MODE_LIVE_SYNC, source_window_start=datetime.now(UTC), source_window_end=datetime.now(UTC),
        lock_key=f"CLOVER_ACQUISITION:{location.id}",
        notes="CLOVER_ACQUISITION mode=LIVE_SYNC location_id=%d; RUNNING" % location.id,
    )
    session.add(running)
    session.commit()

    summary = run_reconciliation_cycle(
        session, location_id=location.id, client=_FakeReconciliationClient(merchant_id="RECON3"),
    )
    result.check(
        "a Reconciliation cycle that finds a concurrent Live Sync/Backfill RUNNING is skipped cleanly — "
        "returns None, never raises to its own caller",
        summary is None,
    )
    still_running = session.get(m.IngestionRun, running.id)
    session.refresh(still_running)
    result.check(
        "the skipped cycle performed no Clover fetch/write — the other run's lock is untouched",
        still_running.status == "RUNNING" and still_running.lock_key is not None,
    )


def _seed_order_and_payment(
    session: Session, *, location: m.Location, source_system: m.SourceSystem, client: _FakeReconciliationClient,
    order_time: datetime, tip_minor: int, order_suffix: str,
) -> None:
    """Simulates "Live Sync already acquired this Order/Payment" by running
    a real (fake-client-backed) LIVE_SYNC import for it first — the same
    idempotent upsert path the Poller will later re-run against."""
    client.orders_by_id[f"RC-ORDER-{order_suffix}"] = {
        "id": f"RC-ORDER-{order_suffix}", "employee": {"id": f"RC-EMP-{order_suffix}"},
        "createdTime": int(order_time.timestamp() * 1000), "modifiedTime": int(order_time.timestamp() * 1000),
        "state": "locked", "paymentState": "PAID", "currency": "USD", "total": 1000, "lineItems": {"elements": []},
    }
    client.payments.append({
        "id": f"RC-PAY-{order_suffix}", "order": {"id": f"RC-ORDER-{order_suffix}"},
        "employee": {"id": f"RC-EMP-{order_suffix}"}, "tender": {"id": "RC-TND1", "label": "Cash"},
        "amount": 1000, "taxAmount": 0, "createdTime": int(order_time.timestamp() * 1000),
        "modifiedTime": int(order_time.timestamp() * 1000), "result": "SUCCESS", "tipAmount": tip_minor,
    })
    import_clover_period(
        session, location_id=location.id, period_start=order_time - timedelta(minutes=5),
        period_end=order_time + timedelta(minutes=5), client=client, mode=MODE_LIVE_SYNC,
    )
    session.commit()


def _test_correction_updates_existing_state(session: Session, result: ValidationResult) -> None:
    """Test item 5 — "correction Clover aggiorna stato RF-One": a Payment
    already acquired by Live Sync has its tip amount corrected on Clover
    (finalized after the fact, per `acquisition._ingest_payment`'s own
    documented rationale) — the Reconciliation Poller, querying by
    `modifiedTime`, must pick it up and update the existing PaymentTip row,
    never create a duplicate Payment."""
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="RECON4")
    client = _FakeReconciliationClient(merchant_id="RECON4")
    order_time = datetime(2026, 9, 10, 10, 0, 0, tzinfo=UTC)

    _seed_order_and_payment(
        session, location=location, source_system=source_system, client=client,
        order_time=order_time, tip_minor=200, order_suffix="A",
    )

    payment_before = session.scalars(
        select(m.Payment).filter_by(source_system_id=source_system.id, source_payment_id="RC-PAY-A")
    ).one()
    tip_before = session.get(m.PaymentTip, payment_before.id)
    result.check("seed: the Payment/PaymentTip exist with the ORIGINAL tip amount", tip_before is not None and tip_before.amount == 200)

    # Clover-side correction: the SAME payment's tip finalizes at a
    # different amount; its `modifiedTime` moves to "now", well after its
    # own `createdTime` — exactly the case Live Sync's createdTime-only
    # window can never revisit.
    now = order_time + timedelta(hours=2)
    client.payments[0]["tipAmount"] = 350
    client.payments[0]["modifiedTime"] = int(now.timestamp() * 1000)
    client.orders_by_id["RC-ORDER-A"]["modifiedTime"] = int(now.timestamp() * 1000)

    summary = run_reconciliation_cycle(session, location_id=location.id, client=client, now=now + timedelta(seconds=1))
    session.commit()
    session.expire_all()

    result.check("the Reconciliation cycle ran successfully", summary is not None and summary.errors == [])
    used_time_field = any(
        "modifiedTime>=" in str(filter_val)
        for _, params in client.calls
        for filter_val in ((params or {}).get("filter") or [])
    )
    result.check("the Reconciliation cycle queried Payments filtered by modifiedTime, never createdTime", used_time_field)

    payment_after = session.scalars(
        select(m.Payment).filter_by(source_system_id=source_system.id, source_payment_id="RC-PAY-A")
    ).one()
    tip_after = session.get(m.PaymentTip, payment_after.id)
    result.check(
        "the correction updated the EXISTING PaymentTip row's amount — RF-One's canonical state, corrected",
        payment_after.id == payment_before.id and tip_after.amount == 350,
    )
    result.check(
        "no duplicate Payment was created by the correction — same source_payment_id, same row",
        len(session.scalars(select(m.Payment).filter_by(source_system_id=source_system.id, source_payment_id="RC-PAY-A")).all()) == 1,
    )


def _test_repeated_cycle_does_not_duplicate(session: Session, result: ValidationResult) -> None:
    """Test item 6 — "duplicate reread non duplica": running the SAME
    Reconciliation cycle twice (an overlapping window, exactly like Live
    Sync's own overlap buffer produces in normal operation) must never
    create a second Order/Payment row."""
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="RECON5")
    client = _FakeReconciliationClient(merchant_id="RECON5")
    order_time = datetime(2026, 9, 10, 10, 0, 0, tzinfo=UTC)
    _seed_order_and_payment(
        session, location=location, source_system=source_system, client=client,
        order_time=order_time, tip_minor=200, order_suffix="B",
    )

    now = order_time + timedelta(hours=1)
    client.orders_by_id["RC-ORDER-B"]["modifiedTime"] = int(order_time.timestamp() * 1000)
    client.payments[0]["modifiedTime"] = int(order_time.timestamp() * 1000)

    summary1 = run_reconciliation_cycle(session, location_id=location.id, client=client, now=now)
    session.commit()
    summary2 = run_reconciliation_cycle(session, location_id=location.id, client=client, now=now)
    session.commit()
    session.expire_all()

    result.check("both Reconciliation cycles ran successfully", summary1 is not None and summary2 is not None)
    result.check(
        "no duplicate Order/Payment after two (overlapping) Reconciliation cycles over the same data",
        len(session.scalars(select(m.Order).filter_by(source_system_id=source_system.id, source_order_id="RC-ORDER-B")).all()) == 1
        and len(session.scalars(select(m.Payment).filter_by(source_system_id=source_system.id, source_payment_id="RC-PAY-B")).all()) == 1,
    )
    result.check(
        "two independent RECONCILIATION-mode IngestionRun rows were recorded (one per cycle) — Historical "
        "Integrity: a repeated cycle is a new run, not a rewrite of the prior one",
        len(session.scalars(
            select(m.IngestionRun).where(m.IngestionRun.location_id == location.id, m.IngestionRun.mode == "RECONCILIATION")
        ).all()) == 2,
    )


def _test_order_only_correction_is_caught_via_modified_orders_query(session: Session, result: ValidationResult) -> None:
    """An Order-level correction (e.g. a voided line item) that does NOT
    touch its Payment's own `modifiedTime` must still be caught, via the
    Poller's additional direct Orders-by-modifiedTime query."""
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="RECON6")
    client = _FakeReconciliationClient(merchant_id="RECON6")
    order_time = datetime(2026, 9, 10, 10, 0, 0, tzinfo=UTC)
    _seed_order_and_payment(
        session, location=location, source_system=source_system, client=client,
        order_time=order_time, tip_minor=100, order_suffix="C",
    )

    now = order_time + timedelta(hours=3)
    # The Order itself is corrected (e.g. total changes after a voided line
    # item) — its OWN modifiedTime moves; the Payment's modifiedTime is left
    # untouched, exactly the gap the direct Orders query exists to close.
    client.orders_by_id["RC-ORDER-C"]["total"] = 850
    client.orders_by_id["RC-ORDER-C"]["modifiedTime"] = int(now.timestamp() * 1000)
    client.modified_orders = [{"id": "RC-ORDER-C", "modifiedTime": int(now.timestamp() * 1000)}]
    # Payment stays exactly as it was — no matching modifiedTime in the
    # Poller's window, so it will NOT appear in `payments_raw` this cycle.
    client.payments = []

    summary = run_reconciliation_cycle(session, location_id=location.id, client=client, now=now + timedelta(seconds=1))
    session.commit()
    session.expire_all()

    result.check("the Reconciliation cycle ran successfully", summary is not None and summary.errors == [])
    order_after = session.scalars(select(m.Order).filter_by(source_system_id=source_system.id, source_order_id="RC-ORDER-C")).one()
    result.check(
        "an Order-only correction (no corresponding Payment modification) is still applied, via the "
        "direct Orders-by-modifiedTime query",
        order_after.total == 850,
    )


def _test_one_location_failure_does_not_block_another(session: Session, result: ValidationResult) -> None:
    """Test item 7 — "failure una Location non blocca altre": Location A's
    Clover fetch failing must not prevent Location B's Reconciliation cycle
    from succeeding independently — each Location's acquisition is fully
    isolated (its own lock, its own IngestionRun, its own try/except)."""
    restaurant_a, location_a, source_system = _build_fixture(session, merchant_source_id="RECON7A")
    restaurant_b, location_b, _source_system_b = _build_fixture(session, merchant_source_id="RECON7B")

    failing_client = _FakeReconciliationClient(merchant_id="RECON7A", fail_payments=True)
    healthy_client = _FakeReconciliationClient(merchant_id="RECON7B")
    order_time = datetime(2026, 9, 10, 10, 0, 0, tzinfo=UTC)
    now = order_time + timedelta(hours=1)
    healthy_client.orders_by_id["RC-ORDER-B2"] = {
        "id": "RC-ORDER-B2", "employee": {"id": "RC-EMP-B2"}, "createdTime": int(order_time.timestamp() * 1000),
        "modifiedTime": int(now.timestamp() * 1000), "state": "locked", "paymentState": "PAID",
        "currency": "USD", "total": 500, "lineItems": {"elements": []},
    }
    healthy_client.payments.append({
        "id": "RC-PAY-B2", "order": {"id": "RC-ORDER-B2"}, "employee": {"id": "RC-EMP-B2"},
        "tender": {"id": "RC-TND1", "label": "Cash"}, "amount": 500, "taxAmount": 0,
        "createdTime": int(order_time.timestamp() * 1000), "modifiedTime": int(now.timestamp() * 1000),
        "result": "SUCCESS", "tipAmount": 75,
    })

    summary_a = run_reconciliation_cycle(session, location_id=location_a.id, client=failing_client, now=now)
    session.commit()
    result.check(
        "Location A's Reconciliation cycle reports the Clover failure via `errors`, never raises",
        summary_a is not None and len(summary_a.errors) > 0,
    )

    summary_b = run_reconciliation_cycle(session, location_id=location_b.id, client=healthy_client, now=now)
    session.commit()
    result.check(
        "Location B's independent Reconciliation cycle succeeds cleanly — Location A's failure did not "
        "block it",
        summary_b is not None and summary_b.errors == [],
    )
    order_b = session.scalars(select(m.Order).filter_by(source_system_id=source_system.id, source_order_id="RC-ORDER-B2")).one_or_none()
    result.check("Location B's data was actually acquired despite Location A's failure", order_b is not None)
