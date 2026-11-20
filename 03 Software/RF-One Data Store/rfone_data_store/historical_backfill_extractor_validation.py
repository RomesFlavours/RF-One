"""Automated synthetic-fixture validation for CLOVER_HISTORICAL_BACKFILL_
EXTRACTOR_V1 (`technical.connectors.clover.historical_backfill_detail`, and
the `mode == MODE_BACKFILL` branch it adds to `acquisition.
import_clover_period`).

Mirrors `clover_acquisition_validation.py`'s pattern exactly: a synthetic
(never-real) fixture built against a disposable database, always rolled
back. `_FullCoverageFakeCloverClient` subclasses the existing, already-
reviewed `FakeCloverClient` to additionally answer the new catalog/detail
endpoints this extractor adds, without duplicating its existing employee/
tender/device/payment/refund/shift/order dispatch logic.

Scope: proves the SMALL-RANGE validation this task explicitly asks for —
expected entity types populate, the Provider Mirror populates, canonical
rows populate, and a second run over the same range creates no canonical
duplicates. This is deliberately NOT a large historical import (per the
task's own instruction) — one Order, one Payment, a minimal catalog.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .clover_acquisition_validation import FakeCloverClient, _FakeResult
from .technical.connectors.clover.acquisition import import_clover_period

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


class _FullCoverageFakeCloverClient(FakeCloverClient):
    """Extends the existing, already-reviewed `FakeCloverClient` with the
    new catalog/detail endpoints CLOVER_HISTORICAL_BACKFILL_EXTRACTOR_V1
    adds — never duplicates its employee/tender/device/payment/refund/
    shift/order-by-id dispatch, which is reused via `super().get()`."""

    def __init__(self, merchant_id: str):
        super().__init__(merchant_id)
        self.categories: list[dict[str, Any]] = []
        self.modifier_groups: list[dict[str, Any]] = []
        self.discounts: list[dict[str, Any]] = []
        self.tax_rates: list[dict[str, Any]] = []
        self.order_types: list[dict[str, Any]] = []
        self.items: list[dict[str, Any]] = []
        self.roles: list[dict[str, Any]] = []
        self.employees_expand_role: list[dict[str, Any]] = []
        self.line_items_by_order_id: dict[str, list[dict[str, Any]]] = {}
        self.item_tax_rate_overrides: dict[str, list[dict[str, Any]]] = {}

    def get(self, path: str, params: dict[str, Any] | None = None) -> _FakeResult:
        params = params or {}
        offset = params.get("offset", 0)

        def _collection(elements: list[dict[str, Any]]) -> _FakeResult:
            self.calls.append((path, params))
            return _FakeResult(ok=True, data={"elements": elements if offset == 0 else []})

        if path.endswith("/categories"):
            return _collection(self.categories)
        if path.endswith("/modifier_groups"):
            return _collection(self.modifier_groups)
        if path.endswith("/discounts"):
            return _collection(self.discounts)
        if path.endswith("/tax_rates"):
            return _collection(self.tax_rates)
        if path.endswith("/order_types"):
            return _collection(self.order_types)
        if path.endswith("/employees") and params.get("expand") == "role":
            return _collection(self.employees_expand_role)
        if path.endswith("/items") and "/orders/" not in path:
            return _collection(self.items)
        if path.endswith("/roles"):
            return _collection(self.roles)
        if "/line_items" in path:
            self.calls.append((path, params))
            order_id = path.split("/orders/", 1)[1].split("/line_items", 1)[0]
            return _collection(self.line_items_by_order_id.get(order_id, []))
        if "/items/" in path and params.get("expand") == "taxRates":
            self.calls.append((path, params))
            item_id = path.rsplit("/", 1)[-1]
            return _FakeResult(
                ok=True, data={"taxRates": {"elements": self.item_tax_rate_overrides.get(item_id, [])}},
            )
        return super().get(path, params)


def run_validation(session_factory: sessionmaker[Session]) -> ValidationResult:
    result = ValidationResult(success=True)
    with session_factory() as session:
        try:
            _build_fixture_and_assert(session, result)
        finally:
            session.rollback()
    return result


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _ref(source_id: str | None) -> dict[str, str] | None:
    return {"id": source_id} if source_id else None


def _build_fixture_and_assert(session: Session, result: ValidationResult) -> None:
    source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
    session.add(source_system)
    session.flush()

    merchant = m.Merchant(source_system_id=source_system.id, source_merchant_id="BFILLMERCH1", name="Backfill Test Merchant")
    session.add(merchant)
    session.flush()

    location = m.Location(
        merchant_id=merchant.id, source_system_id=source_system.id, source_location_id="BFILLMERCH1",
        name="Backfill Test Location", currency="USD",
    )
    session.add(location)
    session.flush()

    client = _FullCoverageFakeCloverClient(merchant_id="BFILLMERCH1")
    client.employees = [{"id": "EMP1", "name": "Alice", "customId": "A1", "role": "EMPLOYEE"}]
    client.roles = [{"id": "ROLE-SERVER", "name": "Server", "systemRole": "EMPLOYEE"}]
    client.employees_expand_role = [
        {"id": "EMP1", "roles": {"elements": [{"id": "ROLE-SERVER"}]}},
    ]
    client.categories = [{"id": "CAT-FOOD", "name": "Food"}]
    client.modifier_groups = [
        {
            "id": "MG-1", "name": "Extras",
            "modifiers": {"elements": [{"id": "MOD-1", "name": "Extra Cheese", "price": 150}]},
        },
    ]
    client.discounts = [{"id": "DISC-DEF-1", "name": "Happy Hour 10%", "percentage": 10}]
    client.tax_rates = [
        {"id": "TAX-DEFAULT", "name": "Sales Tax", "rate": 650000, "isDefault": True},
        {"id": "TAX-OVERRIDE", "name": "Reduced Rate", "rate": 200000, "isDefault": False},
    ]
    client.order_types = [{"id": "OT-1", "label": "Dine In"}]
    client.items = [
        {
            "id": "ITEM-PIZZA", "name": "Pizza", "price": 5400, "defaultTaxRates": True,
            "categories": {"elements": [{"id": "CAT-FOOD"}]},
            "modifierGroups": {"elements": [{"id": "MG-1", "modifierIds": "MOD-1"}]},
        },
        {
            "id": "ITEM-SODA", "name": "Soda", "price": 300, "defaultTaxRates": False,
            "categories": {"elements": [{"id": "CAT-FOOD"}]},
        },
    ]
    client.item_tax_rate_overrides = {"ITEM-SODA": [{"rate": 200000}]}

    period_start = datetime(2026, 6, 1, tzinfo=UTC)
    period_end = datetime(2026, 6, 2, tzinfo=UTC)
    t0 = period_start + timedelta(hours=2)

    client.orders_by_id["ORDER-A"] = {
        "id": "ORDER-A", "employee": _ref("EMP1"), "createdTime": _ms(t0), "modifiedTime": _ms(t0),
        "state": "locked", "paymentState": "PAID", "currency": "USD", "total": 6210,
        "lineItems": {"elements": []},  # dedicated line_items endpoint is authoritative here
        "discounts": {"elements": [
            {"id": "APPLIED-DISC-1", "discount": {"id": "DISC-DEF-1"}, "name": "Happy Hour 10%"},
        ]},
    }
    client.line_items_by_order_id["ORDER-A"] = [
        {
            "id": "LI-PIZZA", "item": _ref("ITEM-PIZZA"), "name": "Pizza", "price": 5400, "unitQty": 1000,
            "isRevenue": True, "isOrderFee": False,
            "modifications": {"elements": [{"id": "MOD-SEL-1", "modifier": _ref("MOD-1"), "name": "Extra Cheese", "amount": 150}]},
        },
        {
            "id": "LI-SODA", "item": _ref("ITEM-SODA"), "name": "Soda", "price": 300, "unitQty": 1000,
            "isRevenue": True, "isOrderFee": False,
        },
    ]
    client.payments.append({
        "id": "PAY-A", "order": _ref("ORDER-A"), "employee": _ref("EMP1"),
        "tender": {"id": "TND-CARD", "label": "Credit Card"}, "amount": 6210, "taxAmount": 0,
        "createdTime": _ms(t0), "modifiedTime": _ms(t0), "result": "SUCCESS", "tipAmount": 500,
    })

    # =========================================================================
    # First run.
    # =========================================================================
    summary1 = import_clover_period(
        session, location_id=location.id, period_start=period_start, period_end=period_end, client=client,
    )
    session.commit()
    session.expire_all()

    result.check("no errors on the first Historical Backfill run", summary1.errors == [])

    def count(model: type) -> int:
        return len(session.scalars(select(model)).all())

    result.check("Category populates canonically", count(m.Category) == 1)
    result.check("ModifierGroup populates canonically", count(m.ModifierGroup) == 1)
    result.check("Modifier populates canonically", count(m.Modifier) == 1)
    result.check("DiscountDefinition populates canonically", count(m.DiscountDefinition) == 1)
    result.check("TaxRate populates canonically (both rows)", count(m.TaxRate) == 2)
    result.check("OrderType populates canonically", count(m.OrderType) == 1)
    result.check("Item populates canonically (both rows)", count(m.Item) == 2)
    result.check("SourceRole populates canonically", count(m.SourceRole) == 1)
    result.check("EmployeeSourceRole membership populates canonically", count(m.EmployeeSourceRole) == 1)

    order_a = session.scalars(select(m.Order).filter_by(source_system_id=source_system.id, source_order_id="ORDER-A")).one()
    order_items = session.scalars(select(m.OrderItem).where(m.OrderItem.order_id == order_a.id)).all()
    result.check("both Order Items populate canonically (Pizza, Soda) — not fee-lines only", len(order_items) == 2)

    pizza_item = session.scalars(select(m.OrderItem).filter_by(order_id=order_a.id, source_line_item_id="LI-PIZZA")).one()
    result.check(
        "Order Item resolves its catalog Item FK", pizza_item.item_id is not None,
    )
    result.check(
        "Item -> Category (M:N) is populated from the catalog fetch",
        session.scalars(select(m.ItemCategory).filter_by(item_id=pizza_item.item_id)).first() is not None,
    )

    modifiers = session.scalars(select(m.OrderItemModifier).where(m.OrderItemModifier.order_item_id == pizza_item.id)).all()
    result.check(
        "Order Item Modifier populates via the dedicated line_items?expand=modifications endpoint",
        len(modifiers) == 1 and modifiers[0].modifier_id is not None and modifiers[0].amount == 150,
    )

    tax_pizza = session.scalars(select(m.OrderItemTax).filter_by(order_item_id=pizza_item.id)).first()
    result.check(
        "Order Item Tax uses the DEFAULT tax rate for an item with defaultTaxRates=True",
        tax_pizza is not None and tax_pizza.tax_rate_id is not None and round(float(tax_pizza.rate_applied), 4) == 0.0650,
    )

    soda_item = session.scalars(select(m.OrderItem).filter_by(order_id=order_a.id, source_line_item_id="LI-SODA")).one()
    tax_soda = session.scalars(select(m.OrderItemTax).filter_by(order_item_id=soda_item.id)).first()
    result.check(
        "Order Item Tax uses the per-item OVERRIDE rate (live-fetched, not the default) for "
        "defaultTaxRates=False, matching the live client.get('...items/{id}?expand=taxRates') call",
        tax_soda is not None and tax_soda.tax_rate_id is None and round(float(tax_soda.rate_applied), 4) == 0.0200,
    )

    order_discounts = session.scalars(select(m.OrderDiscount).where(m.OrderDiscount.order_id == order_a.id)).all()
    result.check(
        "Order Discount populates, resolved to its catalog DiscountDefinition",
        len(order_discounts) == 1 and order_discounts[0].discount_definition_id is not None,
    )

    payment_a = session.scalars(select(m.Payment).filter_by(source_system_id=source_system.id, source_payment_id="PAY-A")).one()
    result.check("Payment/Tip still populate exactly as before (unchanged path)", payment_a.amount == 6210)
    tip_a = session.get(m.PaymentTip, payment_a.id)
    result.check("Payment Tip still populates exactly as before (unchanged path)", tip_a is not None and tip_a.amount == 500)

    mirror_entity_types = {
        r[0] for r in session.execute(select(m.SourceRecord.entity_type).distinct()).all()
    }
    expected_new_entity_types = {
        "category", "modifier_group", "modifier", "discount_definition", "tax_rate",
        "order_type", "item", "source_role", "order_line_item",
    }
    result.check(
        "Provider Mirror (SourceRecord) populates for every new entity type this extractor adds",
        expected_new_entity_types.issubset(mirror_entity_types),
    )
    order_line_item_mirror = session.scalars(
        select(m.SourceRecord).filter_by(source_system_id=source_system.id, entity_type="order_line_item", source_id="LI-PIZZA")
    ).all()
    result.check(
        "Provider Mirror row for an Order Item is raw/provider-shaped (unmapped Clover dict)",
        len(order_line_item_mirror) == 1 and order_line_item_mirror[0].raw_json.get("id") == "LI-PIZZA",
    )

    # =========================================================================
    # Second run over the SAME range: idempotency.
    # =========================================================================
    summary2 = import_clover_period(
        session, location_id=location.id, period_start=period_start, period_end=period_end, client=client,
    )
    session.commit()
    session.expire_all()

    result.check("no errors on the second (re-run) Historical Backfill", summary2.errors == [])
    result.check("Category count unchanged after re-run — no duplicate", count(m.Category) == 1)
    result.check("Item count unchanged after re-run — no duplicate", count(m.Item) == 2)
    result.check("TaxRate count unchanged after re-run — no duplicate", count(m.TaxRate) == 2)
    order_items_after = session.scalars(select(m.OrderItem).where(m.OrderItem.order_id == order_a.id)).all()
    result.check("OrderItem count unchanged after re-run — no duplicate (still 2, not 4)", len(order_items_after) == 2)
    modifiers_after = session.scalars(select(m.OrderItemModifier).where(m.OrderItemModifier.order_item_id == pizza_item.id)).all()
    result.check("OrderItemModifier count unchanged after re-run — no duplicate", len(modifiers_after) == 1)
    order_discounts_after = session.scalars(select(m.OrderDiscount).where(m.OrderDiscount.order_id == order_a.id)).all()
    result.check("OrderDiscount count unchanged after re-run — no duplicate", len(order_discounts_after) == 1)

    order_line_item_mirror_after = session.scalars(
        select(m.SourceRecord).filter_by(source_system_id=source_system.id, entity_type="order_line_item", source_id="LI-PIZZA")
    ).all()
    result.check(
        "Provider Mirror stays append-only across the two backfill runs (2 rows now, canonical still 1)",
        len(order_line_item_mirror_after) == 2,
    )
