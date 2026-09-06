"""Automated synthetic tests for the central Clover data acquisition service
(`technical.connectors.clover.acquisition`, TECHNICAL_CONNECTORS_STRUCTURE_001 —
originally built as CLOVER_TIPS_INGESTION_001's Tips-owned import service,
relocated out of Tips since acquisition is a Restaurant-level concern
shared by Tips, Server Copilot, Server Performance, Sales, and future
modules — task §1/§3).

Mirrors `tips_validation.py`'s pattern: builds a synthetic (never-real)
fixture inside one transaction, exercises `technical.connectors.clover.
acquisition.import_clover_period`, asserts the required behaviors, and
always rolls back — no synthetic row is ever left in the target database.

NEVER contacts Clover production: every call goes through `FakeCloverClient`
below, a small in-memory stand-in satisfying the same `client.get(path,
params) -> result` / `client.merchant_id` shape the real `clover_explorer.
client.CloverClient` and `clover_explorer.pagination.paginate` expect,
returning canned, synthetic Clover-shaped dicts only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .technical.connectors.clover.acquisition import get_order_settlement_time, import_clover_period

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


class FakeCloverClient:
    """A GET-only, in-memory stand-in for `clover_explorer.client.
    CloverClient` — structurally incapable of writing anything anywhere,
    exactly like the real one, and never makes a network call."""

    def __init__(self, merchant_id: str):
        self.merchant_id = merchant_id
        self.payments: list[dict[str, Any]] = []
        self.orders_by_id: dict[str, dict[str, Any]] = {}
        self.employees: list[dict[str, Any]] = []
        self.tenders: list[dict[str, Any]] = []
        self.devices: list[dict[str, Any]] = []
        self.refunds: list[dict[str, Any]] = []
        self.shifts: list[dict[str, Any]] = []
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def get(self, path: str, params: dict[str, Any] | None = None) -> _FakeResult:
        self.calls.append((path, params))
        params = params or {}
        offset = params.get("offset", 0)

        def _collection(elements: list[dict[str, Any]]) -> _FakeResult:
            return _FakeResult(ok=True, data={"elements": elements if offset == 0 else []})

        if path.endswith("/payments"):
            return _collection(self.payments)
        if path.endswith("/employees"):
            return _collection(self.employees)
        if path.endswith("/tenders"):
            return _collection(self.tenders)
        if path.endswith("/devices"):
            return _collection(self.devices)
        if path.endswith("/refunds"):
            return _collection(self.refunds)
        if path.endswith("/shifts"):
            # Real Clover confirmed (CLOVER_TIPS_INGESTION_001, read-only GET)
            # to reject `filter`/`orderBy` on this endpoint with HTTP 400 —
            # the production code never sends them here, so the fake does
            # not need to simulate that rejection; it only needs to return
            # the full collection, exactly like the real unfiltered GET does.
            return _collection(self.shifts)
        if "/orders/" in path:
            order_id = path.rsplit("/", 1)[-1]
            order = self.orders_by_id.get(order_id)
            if order is None:
                return _FakeResult(ok=False, error="order not found", status_code=404)
            return _FakeResult(ok=True, data=order)
        return _FakeResult(ok=False, error=f"unhandled path in FakeCloverClient: {path}", status_code=404)


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
    # --- Base Restaurant/Location fixture (mirrors tips_validation.py) ----
    source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
    session.add(source_system)
    session.flush()

    merchant = m.Merchant(source_system_id=source_system.id, source_merchant_id="TESTMERCH1", name="Test Merchant")
    session.add(merchant)
    session.flush()

    location = m.Location(
        merchant_id=merchant.id, source_system_id=source_system.id, source_location_id="TESTMERCH1",
        name="Test Location", currency="USD",
    )
    session.add(location)
    session.flush()

    restaurant = m.Restaurant(name="Synthetic Clover Import Test Restaurant", default_currency="USD")
    session.add(restaurant)
    session.flush()
    session.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
    session.flush()

    client = FakeCloverClient(merchant_id="TESTMERCH1")
    client.employees = [
        {"id": "EMP1", "name": "Alice", "customId": "A1", "role": "EMPLOYEE"},
        {"id": "EMP2", "name": "Bob", "customId": "B1", "role": "EMPLOYEE"},
    ]
    client.tenders = [
        {"id": "TND-CARD", "label": "Credit Card", "labelKey": "com.clover.tender.credit_card", "enabled": True},
        {"id": "TND-CASH", "label": "Cash", "labelKey": "com.clover.tender.cash", "enabled": True},
    ]
    client.devices = [{"id": "DEV1", "productName": "Flex 4", "model": "Clover_C501", "deviceTypeName": "FLEX"}]

    period_start = datetime(2026, 6, 1, tzinfo=UTC)
    period_end = datetime(2026, 6, 8, tzinfo=UTC)
    t0 = period_start + timedelta(days=1)

    def make_order(order_id: str, *, employee_id: str, total: int, line_items: list[dict] | None = None) -> None:
        client.orders_by_id[order_id] = {
            "id": order_id,
            "employee": _ref(employee_id),
            "createdTime": _ms(t0),
            "modifiedTime": _ms(t0),
            "state": "locked",
            "paymentState": "PAID",
            "currency": "USD",
            "total": total,
            "lineItems": {"elements": line_items or []},
        }

    _TIP_ABSENT = object()

    def make_payment(
        payment_id: str, *, order_id: str, employee_id: str, amount: int, tender_id: str = "TND-CARD",
        tip_amount: int | object = _TIP_ABSENT, created_time: int | None = None,
    ) -> dict[str, Any]:
        raw: dict[str, Any] = {
            "id": payment_id,
            "order": _ref(order_id),
            "employee": _ref(employee_id),
            "tender": {"id": tender_id, "label": "Credit Card" if tender_id == "TND-CARD" else "Cash"},
            "amount": amount,
            "taxAmount": 0,
            "createdTime": created_time if created_time is not None else _ms(t0),
            "modifiedTime": created_time if created_time is not None else _ms(t0),
            "result": "SUCCESS",
        }
        if tip_amount is not _TIP_ABSENT:
            raw["tipAmount"] = tip_amount
        return raw

    # === A: voluntary tip positive ========================================
    make_order("ORDER-A", employee_id="EMP1", total=6000)
    client.payments.append(make_payment("PAY-A", order_id="ORDER-A", employee_id="EMP1", amount=6000, tip_amount=1000))
    # CLOVER_PROVIDER_MIRROR_WIRING: a synthetic cardTransaction field, so the
    # redaction this task adds (`_payment_mirror_payload`) has something real
    # to prove it strips before the raw Payment reaches `SourceRecord`.
    client.payments[-1]["cardTransaction"] = {"last4": "1234", "cardType": "VISA", "type": "CREDIT"}

    # === B: voluntary tip explicit zero ====================================
    make_order("ORDER-B", employee_id="EMP1", total=6000)
    client.payments.append(make_payment("PAY-B", order_id="ORDER-B", employee_id="EMP1", amount=6000, tip_amount=0))

    # === C: tipAmount key entirely absent (cash) ===========================
    make_order("ORDER-C", employee_id="EMP1", total=4000)
    client.payments.append(
        make_payment("PAY-C", order_id="ORDER-C", employee_id="EMP1", amount=4000, tender_id="TND-CASH")
    )

    # === D: split payment — two Payments on one Order ======================
    make_order("ORDER-D", employee_id="EMP1", total=5000)
    client.payments.append(make_payment("PAY-D1", order_id="ORDER-D", employee_id="EMP1", amount=3000, tip_amount=500))
    client.payments.append(make_payment("PAY-D2", order_id="ORDER-D", employee_id="EMP1", amount=2000, tip_amount=300))

    # === E: Payment.employee != Order.employee (mismatch) ==================
    make_order("ORDER-E", employee_id="EMP1", total=5000)
    client.payments.append(make_payment("PAY-E", order_id="ORDER-E", employee_id="EMP2", amount=5000, tip_amount=200))

    # === F: automatic gratuity/service-charge line item, tip 0 =============
    make_order(
        "ORDER-F", employee_id="EMP1", total=6723,
        line_items=[
            {"id": "LI-FOOD", "name": "Pizza", "price": 5400, "isOrderFee": False, "isRevenue": True},
            {
                "id": "LI-FEE", "name": "Gratuity", "note": "Service Charge", "price": 972, "percentage": 180000,
                "isOrderFee": True, "isRevenue": False,
            },
        ],
    )
    client.payments.append(make_payment("PAY-F", order_id="ORDER-F", employee_id="EMP1", amount=6723, tip_amount=0))

    # === G: split payment + gratuity + a later FAILED payment — proves both
    # "gratuity counted once per Order regardless of Payment count" (spec §3)
    # and "Settlement Time = last SUCCESSFUL Payment" (spec §5), ignoring a
    # later-but-failed attempt. =============================================
    make_order(
        "ORDER-G", employee_id="EMP1", total=5800,
        line_items=[
            {"id": "LI-G-FOOD", "name": "Pasta", "price": 5000, "isOrderFee": False, "isRevenue": True},
            {
                "id": "LI-G-FEE", "name": "Gratuity", "note": "Service Charge", "price": 800, "percentage": 160000,
                "isOrderFee": True, "isRevenue": False,
            },
        ],
    )
    g1_time = _ms(t0)
    g2_time = _ms(t0 + timedelta(hours=2))
    g3_fail_time = _ms(t0 + timedelta(hours=3))  # latest of the three, but FAILED — must not count as settlement
    client.payments.append(make_payment("PAY-G1", order_id="ORDER-G", employee_id="EMP1", amount=3000, tip_amount=400, created_time=g1_time))
    client.payments.append(make_payment("PAY-G2", order_id="ORDER-G", employee_id="EMP1", amount=2000, tip_amount=300, created_time=g2_time))
    pay_g3 = make_payment("PAY-G3", order_id="ORDER-G", employee_id="EMP1", amount=800, tip_amount=0, created_time=g3_fail_time)
    pay_g3["result"] = "FAIL"
    client.payments.append(pay_g3)

    # === Shifts: one clocked-in during the period, one well before it =======
    client.shifts = [
        {
            "id": "SHIFT-IN-WINDOW", "employee": _ref("EMP1"),
            "inTime": _ms(t0 - timedelta(hours=1)), "outTime": _ms(t0 + timedelta(hours=3)),
        },
        {
            "id": "SHIFT-OUT-OF-WINDOW", "employee": _ref("EMP2"),
            "inTime": _ms(period_start - timedelta(days=30)), "outTime": _ms(period_start - timedelta(days=30) + timedelta(hours=4)),
        },
    ]

    # === Refund on PAY-A ====================================================
    client.refunds.append(
        {
            "id": "REF-1", "orderRef": _ref("ORDER-A"), "payment": _ref("PAY-A"), "employee": _ref("EMP1"),
            "createdTime": _ms(t0), "amount": 6000, "taxAmount": 0, "tipAmount": 1000,
            "status": "PROCESSED", "voided": False,
        }
    )

    # =========================================================================
    # First import.
    # =========================================================================
    summary1 = import_clover_period(
        session, location_id=location.id, period_start=period_start, period_end=period_end, client=client,
    )
    session.commit()
    session.expire_all()

    result.check("no errors on the first import", summary1.errors == [])
    result.check(
        "10 Payments imported as NEW on the first run (A, B, C, D1, D2, E, F, G1, G2, G3)",
        summary1.payments_imported == 10,
    )
    result.check("7 Orders imported as NEW on the first run (A-G)", summary1.orders_imported == 7)

    def get_tip(payment_source_id: str) -> m.PaymentTip | None:
        payment = session.scalars(
            select(m.Payment).filter_by(source_system_id=source_system.id, source_payment_id=payment_source_id)
        ).one()
        return session.get(m.PaymentTip, payment.id)

    # A: voluntary tip positive.
    tip_a = get_tip("PAY-A")
    result.check("A: voluntary tip positive is recorded present with the exact amount", tip_a is not None and tip_a.amount == 1000 and tip_a.source_present is True)

    # B: voluntary tip explicit zero — present, not absent.
    tip_b = get_tip("PAY-B")
    result.check("B: an explicit zero tip is recorded PRESENT (amount 0), never treated as absent", tip_b is not None and tip_b.amount == 0 and tip_b.source_present is True)

    # C: absent tipAmount preserved as no PaymentTip row (NULL-equivalent), never coerced to 0.
    tip_c = get_tip("PAY-C")
    result.check("C: an absent tipAmount key produces NO PaymentTip row at all — never coerced to 0", tip_c is None)

    # D: split payment — two independent Payments on one Order, each with its own tip.
    order_d = session.scalars(select(m.Order).filter_by(source_system_id=source_system.id, source_order_id="ORDER-D")).one()
    payments_d = session.scalars(select(m.Payment).where(m.Payment.order_id == order_d.id)).all()
    result.check("D: a split-payment Order has exactly 2 Payment rows, both pointing to the same Order", len(payments_d) == 2)
    tip_d1, tip_d2 = get_tip("PAY-D1"), get_tip("PAY-D2")
    result.check("D: each split payment carries its OWN independent tip amount", tip_d1.amount == 500 and tip_d2.amount == 300)

    # E: Payment.employee / Order.employee mismatch preserved, both values kept.
    order_e = session.scalars(select(m.Order).filter_by(source_system_id=source_system.id, source_order_id="ORDER-E")).one()
    payment_e = session.scalars(select(m.Payment).filter_by(source_system_id=source_system.id, source_payment_id="PAY-E")).one()
    result.check(
        "E: Order.employee and Payment.employee are BOTH preserved even when they differ (never silently replaced)",
        order_e.source_employee_id == "EMP1" and payment_e.source_employee_id == "EMP2",
    )
    result.check(
        "E: the Order/Payment employee mismatch is flagged in the import summary for review",
        summary1.employee_mismatches_count == 1
        and summary1.employee_mismatches[0].order_source_id == "ORDER-E"
        and summary1.employee_mismatches[0].payment_source_id == "PAY-E",
    )

    # F: automatic gratuity is separated from voluntary tip, amount read from price (not derived from percentage).
    order_f = session.scalars(select(m.Order).filter_by(source_system_id=source_system.id, source_order_id="ORDER-F")).one()
    fees_f = session.scalars(select(m.OrderFee).filter_by(order_id=order_f.id)).all()
    tip_f = get_tip("PAY-F")
    result.check(
        "F: the automatic gratuity/service-charge line item is stored as an OrderFee, classified "
        "SERVICE_CHARGE, amount taken verbatim from price (972), never derived from percentage",
        len(fees_f) == 1 and fees_f[0].fee_type == "SERVICE_CHARGE" and fees_f[0].amount == 972
        and fees_f[0].note_raw == "Service Charge",
    )
    result.check(
        "F: the automatic gratuity is NEVER merged into Payment.tipAmount — this payment's own tip stays 0",
        tip_f is not None and tip_f.amount == 0,
    )

    # G: split payment (3 Payments, one FAILED) + gratuity + Settlement Time.
    order_g = session.scalars(select(m.Order).filter_by(source_system_id=source_system.id, source_order_id="ORDER-G")).one()
    fees_g = session.scalars(select(m.OrderFee).filter_by(order_id=order_g.id)).all()
    result.check(
        "G: the gratuity line item on a split-payment (3-Payment) Order is stored exactly ONCE — "
        "counted once per Order regardless of Payment count (spec §3)",
        len(fees_g) == 1 and fees_g[0].amount == 800,
    )
    result.check(
        "summary: automatic gratuity is counted once per qualifying Order, not once per Payment "
        "(2 Orders with gratuity — F and G — despite G having 3 Payments)",
        summary1.automatic_gratuity_count == 2 and summary1.automatic_gratuity_total_minor == (972 + 800),
    )
    payments_g = session.scalars(select(m.Payment).where(m.Payment.order_id == order_g.id)).all()
    result.check("G: all 3 Payments (2 SUCCESS + 1 FAILED) are ingested and linked to the same Order", len(payments_g) == 3)
    result.check("summary: ORDER-G's split-payment structure is counted", summary1.split_payment_orders_count == 2)  # D and G

    settlement_g = get_order_settlement_time(session, order_g.id)
    expected_settlement_g = datetime.fromtimestamp(g2_time / 1000, tz=UTC)
    settlement_g_naive = settlement_g.replace(tzinfo=None) if settlement_g and settlement_g.tzinfo else settlement_g
    expected_settlement_g_naive = expected_settlement_g.replace(tzinfo=None)
    result.check(
        "Settlement Time: equals the LAST SUCCESSFUL Payment's timestamp (PAY-G2), ignoring a LATER but "
        "FAILED Payment (PAY-G3) and never the Order's own createdTime/modifiedTime (spec §5)",
        settlement_g is not None and abs((settlement_g_naive - expected_settlement_g_naive).total_seconds()) < 1,
    )

    # Voluntary tip / zero-tip / missing-tip summary counts
    # (A, D1, D2, E, G1, G2 positive; B, F, G3 explicit zero; C absent).
    result.check(
        "summary: voluntary tip count/total match the positive-tip payments only (A, D1, D2, E, G1, G2)",
        summary1.voluntary_tips_count == 6
        and summary1.voluntary_tips_total_minor == (1000 + 500 + 300 + 200 + 400 + 300),
    )
    result.check(
        "summary: zero-tip payments counted separately from missing-tip payments (B, F, G3)",
        summary1.zero_tip_payments_count == 3,
    )
    result.check("summary: missing-tipAmount payments counted (C)", summary1.missing_tip_amount_payments_count == 1)

    # Employees resolved / Shifts imported (task §9/§13 — clock-in/clock-out source facts).
    result.check("summary: both Employees (EMP1, EMP2) are reported resolved", summary1.employees_resolved == 2)
    shift_rows = session.scalars(select(m.Shift).filter_by(source_system_id=source_system.id)).all()
    result.check(
        "Shifts: only the Shift whose clock-in falls WITHIN the requested period is ingested "
        "(SHIFT-IN-WINDOW), the one 30 days earlier (SHIFT-OUT-OF-WINDOW) is not",
        len(shift_rows) == 1 and shift_rows[0].source_shift_id == "SHIFT-IN-WINDOW",
    )
    result.check("summary: shifts imported count matches", summary1.shifts_imported == 1)
    emp1_row = session.scalars(select(m.Employee).filter_by(source_system_id=source_system.id, source_employee_id="EMP1")).one()
    result.check(
        "Shift: clock-in/clock-out and employee linkage preserved as source facts (not yet used for any "
        "eligibility/distribution decision)",
        shift_rows[0].employee_id == emp1_row.id and shift_rows[0].clock_in is not None and shift_rows[0].clock_out is not None,
    )

    # Refund ingestion.
    refund_row = session.scalars(select(m.Refund).filter_by(source_system_id=source_system.id, source_refund_id="REF-1")).one()
    payment_a = session.scalars(select(m.Payment).filter_by(source_system_id=source_system.id, source_payment_id="PAY-A")).one()
    result.check(
        "refund: ingested from the dedicated Refund resource with amount/tipAmount/status/voided preserved, "
        "linked to its Payment",
        refund_row.amount == 6000 and refund_row.tip_amount == 1000 and refund_row.status == "PROCESSED"
        and refund_row.voided is False and refund_row.payment_id == payment_a.id,
    )
    result.check("summary: refunds found is reported", summary1.refunds_found == 1)
    result.check(
        "refund: Payment.result is untouched by the refund (still SUCCESS) — never assumed refunded == failed",
        payment_a.result == "SUCCESS",
    )
    tip_a_after_refund = get_tip("PAY-A")
    result.check(
        "refund: ingesting a Refund fact does NOT automatically reverse or modify the original tip "
        "(spec §18) — PaymentTip.amount for PAY-A is still 1000, unchanged by REF-1",
        tip_a_after_refund is not None and tip_a_after_refund.amount == 1000,
    )

    # No duplicate external ids after the first run.
    payment_a_rows = session.scalars(select(m.Payment).filter_by(source_system_id=source_system.id, source_payment_id="PAY-A")).all()
    result.check("no duplicate Clover external IDs after the first import", len(payment_a_rows) == 1)

    # =========================================================================
    # CLOVER_PROVIDER_MIRROR_WIRING: Provider Mirror (SourceRecord) checks.
    # =========================================================================
    def mirror_rows(entity_type: str, source_id: str) -> list[m.SourceRecord]:
        return session.scalars(
            select(m.SourceRecord)
            .filter_by(source_system_id=source_system.id, entity_type=entity_type, source_id=source_id)
            .order_by(m.SourceRecord.id)
        ).all()

    order_a_mirror = mirror_rows("order", "ORDER-A")
    payment_a_mirror = mirror_rows("payment", "PAY-A")
    refund_1_mirror = mirror_rows("refund", "REF-1")
    employee_1_mirror = mirror_rows("employee", "EMP1")
    tender_mirror = mirror_rows("tender", "TND-CARD")
    device_mirror = mirror_rows("device", "DEV1")
    shift_mirror = mirror_rows("shift", "SHIFT-IN-WINDOW")

    result.check(
        "Historical Backfill/Live Sync (shared path): the first import writes exactly one SourceRecord "
        "per Clover record fetched, for every entity type this connector acquires (order/payment/refund/"
        "employee/tender/device/shift)",
        len(order_a_mirror) == 1 and len(payment_a_mirror) == 1 and len(refund_1_mirror) == 1
        and len(employee_1_mirror) == 1 and len(tender_mirror) == 1 and len(device_mirror) == 1
        and len(shift_mirror) == 1,
    )
    first_run = session.scalars(
        select(m.IngestionRun)
        .where(m.IngestionRun.source_system_id == source_system.id, m.IngestionRun.location_id == location.id)
        .order_by(m.IngestionRun.id)
    ).first()
    result.check(
        "Provider Mirror rows trace back to source: source_system_id + entity_type + source_id "
        "reproduce exactly what was fetched, and each carries the IngestionRun that fetched it",
        payment_a_mirror[0].source_system_id == source_system.id
        and payment_a_mirror[0].ingestion_run_id == first_run.id,
    )
    result.check(
        "SourceRecord stays raw/provider-shaped: raw_json for the Order mirror is the unmapped Clover "
        "dict itself (its own 'id' field still reads 'ORDER-A'), not a canonical/RF-One-shaped record",
        order_a_mirror[0].raw_json is not None and order_a_mirror[0].raw_json.get("id") == "ORDER-A",
    )
    result.check(
        "payload_hash is populated for every mirrored record (a deterministic hash of the raw payload)",
        all(r.payload_hash for r in (order_a_mirror + payment_a_mirror + refund_1_mirror)),
    )
    result.check(
        "safety: a Payment's cardTransaction field (raw cardholder/card metadata) is stripped before "
        "being mirrored into SourceRecord, even though the canonical upsert never touches it either",
        "cardTransaction" not in (payment_a_mirror[0].raw_json or {}),
    )
    result.check(
        "SourceRecord.raw_path is left NULL for this connector (no on-disk bundle exists here, unlike "
        "ingest.py's bulk pipeline) — raw_json is the sole faithful mirror",
        order_a_mirror[0].raw_path is None,
    )

    # =========================================================================
    # Second import over the SAME period: idempotency + late-tip-finalization.
    # =========================================================================
    # Simulate Clover finalizing PAY-A's tip later (task §9 — modifiedTime
    # advances, tip changes from 1000 to 1500; a re-import must refresh it).
    for p in client.payments:
        if p["id"] == "PAY-A":
            p["tipAmount"] = 1500
            p["modifiedTime"] = _ms(t0 + timedelta(hours=5))

    summary2 = import_clover_period(
        session, location_id=location.id, period_start=period_start, period_end=period_end, client=client,
    )
    session.commit()
    session.expire_all()

    result.check("idempotent re-import: no NEW payments created the second time", summary2.payments_imported == 0)
    result.check("idempotent re-import: all 10 previously-imported payments are reported as UPDATED, not duplicated", summary2.payments_updated == 10)
    result.check("idempotent re-import: no NEW orders created the second time", summary2.orders_imported == 0)

    payment_a_rows_after = session.scalars(select(m.Payment).filter_by(source_system_id=source_system.id, source_payment_id="PAY-A")).all()
    result.check("idempotent re-import: still exactly ONE Payment row for PAY-A — never duplicated", len(payment_a_rows_after) == 1)

    tip_a_after = get_tip("PAY-A")
    result.check(
        "modified tip on re-import: PaymentTip.amount is REFRESHED from Clover's current value (1000 -> 1500), "
        "the first observation was never treated as final",
        tip_a_after.amount == 1500,
    )

    order_rows_total = session.scalars(select(m.Order).filter_by(source_system_id=source_system.id)).all()
    expected_order_ids = {"ORDER-A", "ORDER-B", "ORDER-C", "ORDER-D", "ORDER-E", "ORDER-F", "ORDER-G"}
    result.check(
        "idempotent re-import: total distinct Orders in this fixture is still 7 (A-G) after two import runs",
        len({o.source_order_id for o in order_rows_total} & expected_order_ids) == 7,
    )

    shift_rows_after = session.scalars(select(m.Shift).filter_by(source_system_id=source_system.id)).all()
    result.check(
        "idempotent re-import: Shift is refreshed in place on re-import, not duplicated (still exactly 1 row)",
        len(shift_rows_after) == 1,
    )

    ingestion_runs = session.scalars(
        select(m.IngestionRun).where(m.IngestionRun.source_system_id == source_system.id, m.IngestionRun.location_id == location.id)
    ).all()
    result.check("each import run creates its own IngestionRun provenance row (2 runs -> 2 rows)", len(ingestion_runs) == 2)

    # =========================================================================
    # CLOVER_PROVIDER_MIRROR_WIRING: append-only behavior + payload_hash on
    # re-ingestion — the canonical re-import above is idempotent (UPDATE, not
    # duplicate); the Provider Mirror is intentionally NOT — a re-fetch of the
    # same Clover record adds a new row, preserving what was observed at each
    # retrieval, while the canonical upsert stays exactly as idempotent as
    # before this task (unaffected by mirroring being added alongside it).
    # =========================================================================
    order_b_mirror_after = mirror_rows("order", "ORDER-B")  # unchanged fixture — same raw dict both runs
    payment_a_mirror_after = mirror_rows("payment", "PAY-A")  # tipAmount changed 1000 -> 1500 between runs

    result.check(
        "Provider Mirror is append-only: re-ingesting the SAME Clover record on a second run ADDS a new "
        "SourceRecord row rather than overwriting the first (2 runs -> 2 rows per record), for both an "
        "unchanged record (Order B) and a changed one (Payment A)",
        len(order_b_mirror_after) == 2 and len(payment_a_mirror_after) == 2,
    )
    result.check(
        "payload_hash is stable across re-ingestion of an UNCHANGED raw record (Order B's raw dict was "
        "identical on both runs) — a reader can tell nothing changed without re-diffing the full JSON",
        order_b_mirror_after[0].payload_hash == order_b_mirror_after[1].payload_hash,
    )
    result.check(
        "payload_hash CHANGES across re-ingestion of a record Clover actually edited (Payment A's "
        "tipAmount finalized 1000 -> 1500 between runs) — the mirror faithfully reflects the new payload",
        payment_a_mirror_after[0].payload_hash != payment_a_mirror_after[1].payload_hash
        and payment_a_mirror_after[1].raw_json.get("tipAmount") == 1500,
    )
    result.check(
        "canonical idempotency is unaffected by Provider Mirror wiring: Payment A still has exactly ONE "
        "canonical Payment row despite TWO SourceRecord mirror rows now existing for it",
        len(payment_a_rows_after) == 1 and len(payment_a_mirror_after) == 2,
    )

    # No Clover call ever requested cardTransaction / customer PII expansions.
    requested_expansions = " ".join((params or {}).get("expand", "") for _, params in client.calls if params)
    result.check(
        "safety: no call ever requested the cardTransaction expansion (raw cardholder PII) — Tips has no use for it",
        "cardTransaction" not in requested_expansions,
    )
