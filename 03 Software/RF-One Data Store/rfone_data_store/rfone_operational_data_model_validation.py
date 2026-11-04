"""Automated synthetic tests for RFONE_OPERATIONAL_DATA_MODEL_001 — the
canonical/provider-mirror separation and the "does not structurally prevent
RF-One from becoming the native POS" property (task §5/§10 item 9).

Mirrors `clover_acquisition_validation.py`'s pattern: synthetic fixture,
disposable database, always rolled back. Never contacts Clover — this suite
is specifically about proving the canonical schema works WITHOUT any
Clover/external-system involvement at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from . import models as m

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
            _test_native_operational_facts_need_no_source_system(session, result)
            _test_two_native_orders_coexist_without_colliding(session, result)
            _test_externally_sourced_uniqueness_still_enforced(session, result)
        finally:
            session.rollback()
    return result


def _test_native_operational_facts_need_no_source_system(session: Session, result: ValidationResult) -> None:
    """The core property task §5/§10 item 9 asks for: a canonical Merchant,
    Location, Order, OrderItem, OrderFee, Payment, and Refund can each be
    created with NO `source_system_id`/`source_*_id` at all — exactly what a
    future RF-One POS (originating data itself, never through any external
    connector) would need to do. Each row's real identity is its own
    autoincrement `id`, never a source id of any kind."""
    native_merchant = m.Merchant(name="Native RF-One Test Merchant")
    session.add(native_merchant)
    session.flush()
    result.check(
        "a Merchant needs no source_system_id/source_merchant_id at all (already nullable pre-task)",
        native_merchant.id is not None and native_merchant.source_system_id is None,
    )

    native_location = m.Location(merchant_id=native_merchant.id, name="Native RF-One Test Location", currency="USD")
    session.add(native_location)
    session.flush()
    result.check(
        "a Location needs no source_system_id/source_location_id at all (already nullable pre-task)",
        native_location.id is not None and native_location.source_system_id is None,
    )

    native_order = m.Order(
        location_id=native_location.id, created_at=datetime.now(UTC), state="locked",
        payment_state="PAID", currency="USD", total=1000,
    )
    session.add(native_order)
    session.flush()
    result.check(
        "an Order can be created with NO source_system_id/source_order_id — its own `id` is its "
        "real, independent identity, never dependent on any external id",
        native_order.id is not None and native_order.source_system_id is None and native_order.source_order_id is None,
    )

    native_item = m.OrderItem(order_id=native_order.id, quantity=1)
    native_payment = m.Payment(order_id=native_order.id, amount=1000, created_at=datetime.now(UTC), result="SUCCESS")
    session.add_all([native_item, native_payment])
    session.flush()
    result.check(
        "an OrderItem and a Payment can each be created with NO source_system_id/source_*_id either",
        native_item.id is not None and native_item.source_system_id is None
        and native_payment.id is not None and native_payment.source_system_id is None,
    )

    native_fee = m.OrderFee(order_id=native_order.id, amount=100)
    native_refund = m.Refund(
        order_id=native_order.id, payment_id=native_payment.id, created_at=datetime.now(UTC), amount=1000,
    )
    session.add_all([native_fee, native_refund])
    session.flush()
    result.check(
        "an OrderFee and a Refund can each be created with NO source_system_id/source_*_id either — "
        "nothing in the canonical operational model structurally requires an external source",
        native_fee.id is not None and native_fee.source_system_id is None
        and native_refund.id is not None and native_refund.source_system_id is None,
    )


def _test_two_native_orders_coexist_without_colliding(session: Session, result: ValidationResult) -> None:
    """Two natively-created Orders (both `source_system_id`/`source_order_id`
    NULL) must NOT collide against `UniqueConstraint(source_system_id,
    source_order_id)` — SQL/SQLite already treats NULL as distinct from any
    other value, including another NULL, in a UNIQUE constraint (the same
    behavior this schema already relies on elsewhere, e.g.
    `IngestionRun.lock_key`)."""
    merchant = m.Merchant(name="Native Coexistence Test Merchant")
    session.add(merchant)
    session.flush()
    location = m.Location(merchant_id=merchant.id, name="Native Coexistence Test Location", currency="USD")
    session.add(location)
    session.flush()

    order_a = m.Order(location_id=location.id, created_at=datetime.now(UTC), currency="USD")
    order_b = m.Order(location_id=location.id, created_at=datetime.now(UTC), currency="USD")
    session.add_all([order_a, order_b])
    try:
        session.flush()
        collided = False
    except IntegrityError:
        session.rollback()
        collided = True
    result.check(
        "two natively-created Orders (both source_system_id/source_order_id NULL) coexist without "
        "violating the UniqueConstraint — NULL is never treated as a colliding duplicate",
        not collided,
    )


def _test_externally_sourced_uniqueness_still_enforced(session: Session, result: ValidationResult) -> None:
    """Regression check: relaxing the NOT NULL constraint must not weaken
    the EXISTING idempotency protection for externally-sourced (e.g.
    Clover) rows — a real duplicate (source_system_id, source_order_id)
    pair is still rejected exactly as before."""
    source_system = m.SourceSystem(code="RFONE_OPDATA_TEST_SRC", name="Test Source", active=True)
    session.add(source_system)
    session.flush()
    merchant = m.Merchant(source_system_id=source_system.id, source_merchant_id="M1", name="Sourced Test Merchant")
    session.add(merchant)
    session.flush()
    location = m.Location(
        merchant_id=merchant.id, source_system_id=source_system.id, source_location_id="M1",
        name="Sourced Test Location", currency="USD",
    )
    session.add(location)
    session.flush()

    order1 = m.Order(
        location_id=location.id, source_system_id=source_system.id, source_order_id="DUPLICATE-TEST",
        created_at=datetime.now(UTC), currency="USD",
    )
    session.add(order1)
    session.flush()

    order2 = m.Order(
        location_id=location.id, source_system_id=source_system.id, source_order_id="DUPLICATE-TEST",
        created_at=datetime.now(UTC), currency="USD",
    )
    session.add(order2)
    try:
        session.flush()
        rejected = False
    except IntegrityError:
        session.rollback()
        rejected = True
    result.check(
        "a genuine duplicate (source_system_id, source_order_id) pair is still rejected — idempotent "
        "upsert-by-source-identity protection for externally-sourced rows is unchanged",
        rejected,
    )
