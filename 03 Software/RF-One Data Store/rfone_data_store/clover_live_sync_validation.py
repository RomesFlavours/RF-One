"""Automated synthetic tests for `technical.connectors.clover.live_sync`
(TECHNICAL_CONNECTORS_STRUCTURE_001 / CLOVER_DATA_ACQUISITION_ARCHITECTURE_001)
— the near-real-time Clover acquisition path.

Mirrors `clover_acquisition_validation.py`'s pattern: synthetic fixture,
disposable database, `FakeCloverClient`, always rolled back, never contacts
Clover production.

Location-scoped, not Restaurant-scoped: every call here uses `location_id`
directly, matching the Clover connector's own API (it has no concept of
Restaurant) — the fixture still creates a Restaurant/RestaurantLocation row
for realism (mirroring the real onboarding shape) but nothing under test
reads it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .clover_acquisition_validation import FakeCloverClient
from .historical_backfill_extractor_validation import _FullCoverageFakeCloverClient
from .technical.connectors.clover.live_sync import (
    DEFAULT_INITIAL_LOOKBACK,
    DEFAULT_OVERLAP_BUFFER,
    compute_next_sync_window,
    run_live_sync_cycle,
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
            _test_subsequent_cycle_resumes_from_checkpoint_with_overlap(session, result)
            _test_backfill_advances_the_same_checkpoint_live_sync_reads(session, result)
            _test_cycle_skips_when_another_acquisition_is_running(session, result)
            _test_live_sync_cycle_populates_provider_mirror(session, result)
            _test_live_sync_cycle_reduced_scope_and_idempotency(session, result)
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
        source_system_id=source_system.id, source_merchant_id=merchant_source_id, name="Live Sync Test Merchant",
    )
    session.add(merchant)
    session.flush()

    location = m.Location(
        merchant_id=merchant.id, source_system_id=source_system.id, source_location_id=merchant_source_id,
        name="Live Sync Test Location", currency="USD",
    )
    session.add(location)
    session.flush()

    # Realism only — the Clover connector itself never reads Restaurant/
    # RestaurantLocation (TECHNICAL_CONNECTORS_STRUCTURE_001); a Domain
    # caller (e.g. Tips) would resolve restaurant -> location_id before
    # calling in, exactly as this fixture mirrors the real onboarding shape.
    restaurant = m.Restaurant(name=f"Synthetic Live Sync Test Restaurant {merchant_source_id}", default_currency="USD")
    session.add(restaurant)
    session.flush()
    session.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
    session.flush()

    return restaurant, location, source_system


def _test_non_clover_location_skips_cleanly(session: Session, result: ValidationResult) -> None:
    """A Location with no Clover external identifier (e.g. never onboarded)
    must be skipped cleanly, never raise — the connector has no fallback/
    inference for "which Location did you mean," it simply reports "not
    acquirable" for this one."""
    source_system = session.scalars(select(m.SourceSystem).filter_by(code="CLOVER")).first()
    if source_system is None:
        source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
        session.add(source_system)
        session.flush()
    orphan_merchant = m.Merchant(
        source_system_id=source_system.id, source_merchant_id="NOCLOVERLOC", name="Orphan Merchant",
    )
    session.add(orphan_merchant)
    session.flush()
    # `source_location_id=None` — never onboarded with an external
    # identifier, exactly the case `_resolve_clover_merchant` must reject.
    non_clover_location = m.Location(
        merchant_id=orphan_merchant.id, source_system_id=source_system.id, source_location_id=None,
        name="Non-Clover Location", currency="USD",
    )
    session.add(non_clover_location)
    session.flush()

    window = compute_next_sync_window(session, location_id=non_clover_location.id)
    result.check(
        "a Location with no Clover external identifier yields None (skip), never an exception",
        window is None,
    )
    summary = run_live_sync_cycle(session, location_id=non_clover_location.id)
    result.check("run_live_sync_cycle also returns None cleanly for the same case", summary is None)

    nonexistent_location_id = non_clover_location.id + 1_000_000
    result.check(
        "a nonexistent location_id also yields a clean skip, never an exception",
        compute_next_sync_window(session, location_id=nonexistent_location_id) is None
        and run_live_sync_cycle(session, location_id=nonexistent_location_id) is None,
    )


def _test_first_ever_cycle_uses_initial_lookback(session: Session, result: ValidationResult) -> None:
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="LIVESYNC1")
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=UTC)

    window = compute_next_sync_window(session, location_id=location.id, now=now)
    result.check(
        "first-ever cycle (no prior acquisition run at all): period_start = now - initial_lookback, "
        "period_end = now",
        window is not None and window[0] == now - DEFAULT_INITIAL_LOOKBACK and window[1] == now,
    )


def _test_subsequent_cycle_resumes_from_checkpoint_with_overlap(session: Session, result: ValidationResult) -> None:
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="LIVESYNC2")
    prior_window_end = datetime(2026, 9, 10, 11, 55, 0, tzinfo=UTC)

    session.add(
        m.IngestionRun(
            source_system_id=source_system.id, location_id=location.id, started_at=prior_window_end,
            finished_at=prior_window_end, status="COMPLETE",
            source_window_start=prior_window_end - timedelta(minutes=15), source_window_end=prior_window_end,
            notes="CLOVER_ACQUISITION mode=LIVE_SYNC location_id=%d; payments=0 orders=0 shifts=0 refunds=0" % location.id,
        )
    )
    session.commit()

    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=UTC)
    window = compute_next_sync_window(session, location_id=location.id, now=now)
    result.check(
        "a subsequent cycle resumes from the prior run's own source_window_end, minus the overlap "
        "buffer — never from scratch, and never a razor's-edge boundary",
        window is not None and window[0] == prior_window_end - DEFAULT_OVERLAP_BUFFER and window[1] == now,
    )


def _test_backfill_advances_the_same_checkpoint_live_sync_reads(session: Session, result: ValidationResult) -> None:
    """A manual Historical Backfill through a recent date and a Live Sync
    cycle both call the exact same `import_clover_period`, populating
    `source_window_start`/`source_window_end` identically — so a Backfill
    naturally advances Live Sync's own checkpoint too, with no special-case
    code needed."""
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="LIVESYNC3")
    from .technical.connectors.clover.acquisition import MODE_BACKFILL, import_clover_period

    backfill_end = datetime(2026, 9, 9, 23, 59, 59, tzinfo=UTC)
    client = FakeCloverClient(merchant_id="LIVESYNC3")
    import_clover_period(
        session, location_id=location.id, period_start=datetime(2026, 9, 9, tzinfo=UTC),
        period_end=backfill_end, client=client, mode=MODE_BACKFILL,
    )
    session.commit()

    now = datetime(2026, 9, 10, 0, 5, 0, tzinfo=UTC)
    window = compute_next_sync_window(session, location_id=location.id, now=now)
    result.check(
        "a Historical Backfill's own source_window_end becomes Live Sync's next checkpoint — the two "
        "modes share one continuous timeline, never two independent ones",
        window is not None and window[0] == backfill_end - DEFAULT_OVERLAP_BUFFER and window[1] == now,
    )


def _test_cycle_skips_when_another_acquisition_is_running(session: Session, result: ValidationResult) -> None:
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="LIVESYNC4")

    running = m.IngestionRun(
        source_system_id=source_system.id, location_id=location.id, started_at=datetime.now(UTC),
        status="RUNNING", source_window_start=datetime.now(UTC), source_window_end=datetime.now(UTC),
        lock_key=f"CLOVER_ACQUISITION:{location.id}",
        notes="CLOVER_ACQUISITION mode=BACKFILL location_id=%d; RUNNING" % location.id,
    )
    session.add(running)
    session.commit()

    summary = run_live_sync_cycle(session, location_id=location.id, client=FakeCloverClient(merchant_id="LIVESYNC4"))
    result.check(
        "a cycle that finds another acquisition (e.g. a concurrent manual Backfill) already RUNNING "
        "is skipped cleanly — returns None, never raises ImportAlreadyRunningError to its own caller",
        summary is None,
    )
    still_running = session.get(m.IngestionRun, running.id)
    session.refresh(still_running)
    result.check(
        "the skipped cycle performed no Clover fetch/write — the other run's lock is untouched",
        still_running.status == "RUNNING" and still_running.lock_key is not None,
    )


def _test_live_sync_cycle_populates_provider_mirror(session: Session, result: ValidationResult) -> None:
    """CLOVER_PROVIDER_MIRROR_WIRING minimum validation item: "SourceRecord
    is populated by Live Sync" specifically (not only by Historical
    Backfill, already proven exhaustively by `clover_acquisition_validation.
    py` for the shared `import_clover_period` path both modes call). Runs an
    actual `run_live_sync_cycle` — the real Live Sync entry point, not
    `import_clover_period` directly — against a fixture with one real
    Payment/Order, and confirms a Provider Mirror row is written for each."""
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="LIVESYNC5")
    client = FakeCloverClient(merchant_id="LIVESYNC5")
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=UTC)
    order_time = now - timedelta(minutes=30)
    client.orders_by_id["LS-ORDER-1"] = {
        "id": "LS-ORDER-1", "employee": {"id": "LS-EMP1"}, "createdTime": int(order_time.timestamp() * 1000),
        "modifiedTime": int(order_time.timestamp() * 1000), "state": "locked", "paymentState": "PAID",
        "currency": "USD", "total": 1000, "lineItems": {"elements": []},
    }
    client.payments.append({
        "id": "LS-PAY-1", "order": {"id": "LS-ORDER-1"}, "employee": {"id": "LS-EMP1"},
        "tender": {"id": "LS-TND1", "label": "Cash"}, "amount": 1000, "taxAmount": 0,
        "createdTime": int(order_time.timestamp() * 1000), "modifiedTime": int(order_time.timestamp() * 1000),
        "result": "SUCCESS",
    })

    summary = run_live_sync_cycle(session, location_id=location.id, client=client, now=now)
    session.commit()

    result.check("the Live Sync cycle itself (not a direct import_clover_period call) ran successfully", summary is not None and summary.errors == [])

    order_mirror = session.scalars(
        select(m.SourceRecord).filter_by(source_system_id=source_system.id, entity_type="order", source_id="LS-ORDER-1")
    ).all()
    payment_mirror = session.scalars(
        select(m.SourceRecord).filter_by(source_system_id=source_system.id, entity_type="payment", source_id="LS-PAY-1")
    ).all()
    result.check(
        "SourceRecord is populated by Live Sync, exactly as it is by Historical Backfill — both modes "
        "share the one `import_clover_period` path, so a Live Sync cycle mirrors its fetched Order and "
        "Payment into the Provider Mirror too",
        len(order_mirror) == 1 and len(payment_mirror) == 1
        and order_mirror[0].raw_json.get("id") == "LS-ORDER-1"
        and payment_mirror[0].raw_json.get("id") == "LS-PAY-1",
    )
    live_sync_run = session.scalars(
        select(m.IngestionRun).where(
            m.IngestionRun.source_system_id == source_system.id, m.IngestionRun.location_id == location.id,
        )
    ).first()
    result.check(
        "the Provider Mirror row created by this cycle is attributed to the LIVE_SYNC-mode IngestionRun",
        live_sync_run is not None and order_mirror[0].ingestion_run_id == live_sync_run.id
        and "mode=LIVE_SYNC" in (live_sync_run.notes or ""),
    )


def _test_live_sync_cycle_reduced_scope_and_idempotency(session: Session, result: ValidationResult) -> None:
    """CLOVER_LIVE_SYNC_SCOPE_REDUCTION_001 — proves Live Sync keeps only
    its retained entities (Order, Order Item, Order Item Modifier, Payment,
    Payment Tip, Refund, Order Fee, Shift, Employee) current, and no longer
    refreshes catalog/reference data (Item, Category, Modifier Group/
    Modifier, Tax Rate, Discount Definition, Order Type, Tender, Device,
    Source Role) or computes Order Item Tax/Order Discount (both depend on
    catalogs it no longer refreshes). Reuses `_FullCoverageFakeCloverClient`
    (the same fake `test_historical_backfill_extractor.py` validates) purely
    as a client capable of answering catalog endpoints IF Live Sync were to
    call them — the test's real assertion is that it never does.

    A Modifier row is pre-seeded directly (simulating "Historical Backfill
    already ran once") to prove `ingest_order_item_and_modifier_detail()`'s
    DB-lookup resolution genuinely works when the catalog IS already known,
    not only the degenerate "nothing resolves" case. `Item` is deliberately
    NOT pre-seeded, to also prove an unresolved reference degrades
    gracefully to `None` rather than erroring.

    Runs TWO Live Sync cycles with the SAME `now`, so the second cycle's
    window is a strict subset of the first (via `compute_next_sync_window`'s
    own overlap-buffer mechanism, unmodified) — a real "repeated overlapping
    window", not an artificially forced one."""
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="LIVESYNC7")

    # Simulates a prior Historical Backfill having already discovered this
    # Modifier — Live Sync itself never fetches `/modifier_groups`.
    seeded_modifier = m.Modifier(
        location_id=location.id, source_system_id=source_system.id, source_modifier_id="LS7-MOD-1",
        name="Extra Sauce", price_delta=100,
    )
    session.add(seeded_modifier)
    session.commit()

    client = _FullCoverageFakeCloverClient(merchant_id="LIVESYNC7")
    now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=UTC)
    order_time = now - timedelta(minutes=30)

    client.employees = [{"id": "LS7-EMP1", "name": "Sam", "customId": "S1", "role": "EMPLOYEE"}]
    # Populated so the fake COULD answer these if asked — the assertion
    # below is that Live Sync never asks.
    client.roles = [{"id": "LS7-ROLE-SERVER", "name": "Server", "systemRole": "EMPLOYEE"}]
    client.categories = [{"id": "LS7-CAT-FOOD", "name": "Food"}]
    client.modifier_groups = [
        {"id": "LS7-MG-1", "name": "Extras", "modifiers": {"elements": [{"id": "LS7-MOD-1", "name": "Extra Sauce", "price": 100}]}},
    ]
    client.discounts = [{"id": "LS7-DISC-DEF-1", "name": "Staff Meal 20%", "percentage": 20}]
    client.tax_rates = [{"id": "LS7-TAX-DEFAULT", "name": "Sales Tax", "rate": 650000, "isDefault": True}]
    client.order_types = [{"id": "LS7-OT-1", "label": "Dine In"}]
    client.items = [{
        "id": "LS7-ITEM-BURGER", "name": "Burger", "price": 1200, "defaultTaxRates": True,
        "categories": {"elements": [{"id": "LS7-CAT-FOOD"}]},
        "modifierGroups": {"elements": [{"id": "LS7-MG-1", "modifierIds": "LS7-MOD-1"}]},
    }]

    client.orders_by_id["LS7-ORDER-1"] = {
        "id": "LS7-ORDER-1", "employee": {"id": "LS7-EMP1"}, "createdTime": int(order_time.timestamp() * 1000),
        "modifiedTime": int(order_time.timestamp() * 1000), "state": "locked", "paymentState": "PAID",
        "currency": "USD", "total": 1272, "lineItems": {"elements": []},
        "discounts": {"elements": [{"id": "LS7-APPLIED-DISC-1", "discount": {"id": "LS7-DISC-DEF-1"}, "name": "Staff Meal 20%"}]},
    }
    client.line_items_by_order_id["LS7-ORDER-1"] = [{
        "id": "LS7-LI-BURGER", "item": {"id": "LS7-ITEM-BURGER"}, "name": "Burger", "price": 1200, "unitQty": 1000,
        "isRevenue": True, "isOrderFee": False,
        "modifications": {"elements": [{"id": "LS7-MOD-SEL-1", "modifier": {"id": "LS7-MOD-1"}, "name": "Extra Sauce", "amount": 100}]},
    }]
    client.payments.append({
        "id": "LS7-PAY-1", "order": {"id": "LS7-ORDER-1"}, "employee": {"id": "LS7-EMP1"},
        "tender": {"id": "LS7-TND1", "label": "Cash"}, "amount": 1272, "taxAmount": 72,
        "createdTime": int(order_time.timestamp() * 1000), "modifiedTime": int(order_time.timestamp() * 1000),
        "result": "SUCCESS", "tipAmount": 200,
    })

    summary1 = run_live_sync_cycle(session, location_id=location.id, client=client, now=now)
    session.commit()
    session.expire_all()
    result.check("first Live Sync cycle ran successfully", summary1 is not None and summary1.errors == [])

    def count(model: type) -> int:
        return len(session.scalars(select(model)).all())

    order = session.scalars(select(m.Order).filter_by(source_system_id=source_system.id, source_order_id="LS7-ORDER-1")).one()
    order_item = session.scalars(select(m.OrderItem).filter_by(order_id=order.id, source_line_item_id="LS7-LI-BURGER")).one()
    payment = session.scalars(select(m.Payment).filter_by(source_system_id=source_system.id, source_payment_id="LS7-PAY-1")).one()

    result.check(
        "Live Sync still populates its retained entities: Order, Order Item, Payment, Payment Tip",
        order.id is not None and order_item.id is not None and payment.amount == 1272
        and session.get(m.PaymentTip, payment.id) is not None,
    )
    order_item_modifier = session.scalars(select(m.OrderItemModifier).filter_by(order_item_id=order_item.id)).first()
    result.check(
        "Live Sync populates Order Item Modifier, resolving modifier_id against the ALREADY-canonical "
        "Modifier (seeded above) — no live catalog fetch needed for a source_id it already knows",
        order_item_modifier is not None and order_item_modifier.modifier_id == seeded_modifier.id,
    )
    result.check(
        "Order Item's item_id gracefully stays unresolved (None) — Live Sync never fetched the Item "
        "catalog, so a source_id it has never seen (LS7-ITEM-BURGER was never Backfilled) is simply unknown",
        order_item.item_id is None,
    )
    result.check(
        "Live Sync does NOT compute Order Item Tax — it depends on the Item/TaxRate catalog Live Sync "
        "no longer refreshes",
        session.scalars(select(m.OrderItemTax).filter_by(order_item_id=order_item.id)).first() is None,
    )
    result.check(
        "Live Sync does NOT populate Order-level Discount detail — it depends on the DiscountDefinition "
        "catalog Live Sync no longer refreshes",
        len(session.scalars(select(m.OrderDiscount).filter_by(order_id=order.id)).all()) == 0,
    )
    result.check(
        "Live Sync does NOT refresh catalog/reference data: Category/ModifierGroup/DiscountDefinition/"
        "TaxRate/OrderType/SourceRole all stay at zero — only the pre-seeded Modifier exists (count 1)",
        count(m.Category) == 0 and count(m.ModifierGroup) == 0 and count(m.Modifier) == 1
        and count(m.DiscountDefinition) == 0 and count(m.TaxRate) == 0 and count(m.OrderType) == 0
        and count(m.SourceRole) == 0 and count(m.Item) == 0,
    )
    called_paths = " ".join(path for path, _ in client.calls)
    result.check(
        "Live Sync never even CALLS the removed catalog endpoints (not just 'ignores the response')",
        "/categories" not in called_paths and "/modifier_groups" not in called_paths
        and "/discounts" not in called_paths and "/tax_rates" not in called_paths
        and "/order_types" not in called_paths and "/roles" not in called_paths
        and "/tenders" not in called_paths and "/devices" not in called_paths
        and "expand=role" not in called_paths,
    )
    mirror_entity_types = {r[0] for r in session.execute(select(m.SourceRecord.entity_type).distinct()).all()}
    result.check(
        "Provider Mirror behavior for entities Live Sync still handles is unchanged: order/payment/"
        "order_line_item all still mirror",
        {"order", "payment", "order_line_item"}.issubset(mirror_entity_types),
    )
    result.check(
        "Provider Mirror gets no rows for the removed catalog entity types from this Live Sync cycle",
        not {"category", "modifier_group", "modifier", "discount_definition", "tax_rate", "order_type",
             "item", "source_role", "tender", "device"}.intersection(mirror_entity_types),
    )

    # =========================================================================
    # Second cycle, SAME `now` -> a strictly overlapping window.
    # =========================================================================
    summary2 = run_live_sync_cycle(session, location_id=location.id, client=client, now=now)
    session.commit()
    session.expire_all()
    result.check("second (overlapping-window) Live Sync cycle ran successfully", summary2 is not None and summary2.errors == [])

    result.check(
        "Order count unchanged after the overlapping cycle — no duplicate",
        len(session.scalars(
            select(m.Order).filter_by(source_system_id=source_system.id, source_order_id="LS7-ORDER-1")
        ).all()) == 1,
    )
    result.check(
        "OrderItem/OrderItemModifier counts unchanged after the overlapping cycle — no duplicates, and "
        "still correctly resolved/unresolved exactly as before",
        len(session.scalars(select(m.OrderItem).filter_by(order_id=order.id)).all()) == 1
        and len(session.scalars(select(m.OrderItemModifier).filter_by(order_item_id=order_item.id)).all()) == 1,
    )
    result.check(
        "no OrderItemTax/OrderDiscount appeared on the second cycle either",
        session.scalars(select(m.OrderItemTax).filter_by(order_item_id=order_item.id)).first() is None
        and len(session.scalars(select(m.OrderDiscount).filter_by(order_id=order.id)).all()) == 0,
    )
    result.check("Modifier catalog still just the one pre-seeded row — no duplicate, still no live refresh", count(m.Modifier) == 1)
    order_line_item_mirror_after = session.scalars(
        select(m.SourceRecord).filter_by(source_system_id=source_system.id, entity_type="order_line_item", source_id="LS7-LI-BURGER")
    ).all()
    result.check(
        "Provider Mirror stays append-only across the two overlapping cycles (2 rows now, canonical still 1)",
        len(order_line_item_mirror_after) == 2,
    )
