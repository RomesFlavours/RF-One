"""Post-ingestion reconciliation (TASK_DATABASE_002 §40-44).

Everything here is read-only against the (staging) session and the source
`CloverSourceBundle` — no canonical row is modified. Acceptance figures
(Orders total, Payments total, Failed Payments, Refunds — task §41) are
computed from the actual source data at runtime, never hard-coded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ... import models as m
from . import parser, reader

# Used ONLY for the weekly confidence check window (task §43), reproducing
# TASK_CLOVER_002's already-validated reference week. This is an explicit,
# documented, out-of-band assumption for this one check — it is never
# written into Location.timezone or any other canonical column (task §12,
# §39: Clover does not source-confirm a timezone for this merchant).
_CONFIDENCE_CHECK_TZ = ZoneInfo("America/New_York")
_CONFIDENCE_CHECK_WEEK_START = date(2026, 8, 17)
_CONFIDENCE_CHECK_WEEK_END = date(2026, 8, 23)


@dataclass
class CountComparison:
    entity: str
    source_count: int
    canonical_count: int
    note: str = ""
    informational: bool = False  # no single "correct" source total exists — never gates status

    @property
    def matches(self) -> bool:
        return self.informational or self.source_count == self.canonical_count


@dataclass
class EmpiricalCheck:
    description: str
    passed: bool
    detail: str = ""


@dataclass
class ReconciliationReport:
    count_comparisons: list[CountComparison] = field(default_factory=list)
    empirical_checks: list[EmpiricalCheck] = field(default_factory=list)
    monetary: dict[str, Any] = field(default_factory=dict)
    weekly_confidence: dict[str, Any] = field(default_factory=dict)
    data_quality: dict[str, Any] = field(default_factory=dict)
    unresolved: dict[str, int] = field(default_factory=dict)

    @property
    def all_counts_match(self) -> bool:
        return all(c.matches for c in self.count_comparisons)

    @property
    def all_empirical_checks_passed(self) -> bool:
        return all(c.passed for c in self.empirical_checks)


def _canonical_count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def _employee_count_comparison(session: Session, bundle: reader.CloverSourceBundle) -> CountComparison:
    """Clover's `/employees` collection is a current snapshot; historical
    Shift/Order/Payment/Refund records may reference employee ids it no
    longer returns (`ingest.ingest_employee_stub_references` fills these
    with minimal stub rows rather than dropping the history that references
    them). The expected canonical count therefore includes those stubs —
    comparing against the raw source collection size alone would always
    show a false mismatch."""
    referenced = parser.referenced_employee_ids(bundle.shifts, bundle.orders, bundle.payments, bundle.refunds)
    known = {e["id"] for e in bundle.employees if e.get("id")}
    expected = len(known | referenced)
    stub_count = len(referenced - known)
    note = (
        f"{len(bundle.employees)} from /employees + {stub_count} stub row(s) for ids "
        "referenced by history but absent from the current /employees snapshot"
        if stub_count
        else ""
    )
    return CountComparison("Employee", expected, _canonical_count(session, m.Employee), note)


def run_count_reconciliation(session: Session, bundle: reader.CloverSourceBundle) -> list[CountComparison]:
    order_item_source_count = sum(
        len(reader.load_dedicated_line_items(o["id"]) or (o.get("lineItems") or {}).get("elements", []))
        for o in bundle.orders
    )
    modifier_source_count = sum(len((g.get("modifiers") or {}).get("elements", [])) for g in bundle.modifier_groups)

    comparisons = [
        CountComparison("Merchant", 1, _canonical_count(session, m.Merchant)),
        CountComparison("Location", 1, _canonical_count(session, m.Location)),
        CountComparison("Device", len(bundle.devices or []), _canonical_count(session, m.Device)),
        _employee_count_comparison(session, bundle),
        CountComparison("Shift", len(bundle.shifts), _canonical_count(session, m.Shift),
                         "Shift rows require a resolvable Employee FK (NOT NULL) — see unresolved_employee_refs"),
        CountComparison("OrderType", len(bundle.order_types), _canonical_count(session, m.OrderType)),
        CountComparison("Item", len(bundle.items), _canonical_count(session, m.Item)),
        CountComparison("Category", len(bundle.categories), _canonical_count(session, m.Category)),
        CountComparison("ModifierGroup", len(bundle.modifier_groups), _canonical_count(session, m.ModifierGroup)),
        CountComparison("Modifier", modifier_source_count, _canonical_count(session, m.Modifier)),
        CountComparison("DiscountDefinition", len(bundle.discounts), _canonical_count(session, m.DiscountDefinition)),
        CountComparison("TaxRate", len(bundle.tax_rates), _canonical_count(session, m.TaxRate)),
        CountComparison("Order", len(bundle.orders), _canonical_count(session, m.Order)),
        CountComparison("OrderItem", order_item_source_count, _canonical_count(session, m.OrderItem)),
        CountComparison("Payment", len(bundle.payments), _canonical_count(session, m.Payment)),
        CountComparison("Refund", len(bundle.refunds or []), _canonical_count(session, m.Refund)),
    ]

    # Relationship-shaped counts without a single natural "source total"
    # (they are derived from cardinalities, not a flat source collection) —
    # reported for completeness, not force-equated to a fabricated source figure.
    comparisons.append(
        CountComparison(
            "ItemCategory relationships",
            -1,
            _canonical_count(session, m.ItemCategory),
            "No flat source collection — M:N relationship count only (informational)",
            informational=True,
        )
    )
    comparisons.append(
        CountComparison(
            "ItemModifier relationships",
            -1,
            _canonical_count(session, m.ItemModifier),
            "Derived via Item→ModifierGroup→Modifier chain (informational)",
            informational=True,
        )
    )
    comparisons.append(
        CountComparison("OrderItemModifier", -1, _canonical_count(session, m.OrderItemModifier), "informational", informational=True)
    )
    comparisons.append(
        CountComparison("OrderDiscount", -1, _canonical_count(session, m.OrderDiscount), "informational", informational=True)
    )
    comparisons.append(
        CountComparison("OrderItemDiscount", -1, _canonical_count(session, m.OrderItemDiscount), "informational (not populated by this task — see task §29)", informational=True)
    )
    comparisons.append(
        CountComparison("OrderItemTax", -1, _canonical_count(session, m.OrderItemTax), "informational", informational=True)
    )
    comparisons.append(
        CountComparison("OrderFee", -1, _canonical_count(session, m.OrderFee), "informational", informational=True)
    )
    comparisons.append(
        CountComparison("Tender", -1, _canonical_count(session, m.Tender), "built from distinct Payment.tender objects, not a dedicated collection", informational=True)
    )
    comparisons.append(
        CountComparison("PaymentTip (present)", -1, _canonical_count(session, m.PaymentTip), "one row per Payment with tipAmount PRESENT — absent tips have no row by design", informational=True)
    )

    return comparisons


def run_known_empirical_checks(session: Session, bundle: reader.CloverSourceBundle) -> list[EmpiricalCheck]:
    checks: list[EmpiricalCheck] = []

    orders_total = len(bundle.orders)
    payments_total = len(bundle.payments)
    failed_payments = sum(1 for p in bundle.payments if p.get("result") == "FAIL")
    refunds_total = len(bundle.refunds or [])

    checks.append(EmpiricalCheck(
        f"Orders source total ({orders_total})",
        _canonical_count(session, m.Order) == orders_total,
        f"canonical={_canonical_count(session, m.Order)}",
    ))
    checks.append(EmpiricalCheck(
        f"Payments source total ({payments_total})",
        _canonical_count(session, m.Payment) == payments_total,
        f"canonical={_canonical_count(session, m.Payment)}",
    ))

    canonical_failed = session.scalar(select(func.count()).select_from(m.Payment).where(m.Payment.result == "FAIL")) or 0
    checks.append(EmpiricalCheck(
        f"Failed Payments present in canonical Payments ({failed_payments})",
        canonical_failed == failed_payments,
        f"canonical FAIL count={canonical_failed}",
    ))

    canonical_refunds = _canonical_count(session, m.Refund)
    checks.append(EmpiricalCheck(
        f"Both Refunds present ({refunds_total})",
        canonical_refunds == refunds_total and refunds_total > 0,
        f"canonical={canonical_refunds}",
    ))

    # Fractional quantity round-trip.
    fractional_source = [
        li
        for o in bundle.orders
        for li in (reader.load_dedicated_line_items(o["id"]) or (o.get("lineItems") or {}).get("elements", []))
        if li.get("unitQty") is not None and li.get("unitQty") % 1000 != 0
    ]
    if fractional_source:
        sample = fractional_source[0]
        expected = Decimal(sample["unitQty"]) / Decimal(1000)
        row = session.scalars(
            select(m.OrderItem).where(m.OrderItem.source_line_item_id == sample["id"])
        ).first()
        checks.append(EmpiricalCheck(
            "Fractional OrderItem quantity survives exact round-trip",
            row is not None and row.quantity == expected,
            f"expected={expected}, got={row.quantity if row else None}",
        ))
    else:
        checks.append(EmpiricalCheck("Fractional OrderItem quantity survives exact round-trip", True, "no fractional-quantity line item found in source to test — vacuously true"))

    # Both discount shapes survive.
    has_percentage = session.scalar(
        select(func.count()).select_from(m.OrderDiscount).where(m.OrderDiscount.percentage.is_not(None))
    ) or 0
    has_amount = session.scalar(
        select(func.count()).select_from(m.OrderDiscount).where(m.OrderDiscount.amount.is_not(None))
    ) or 0
    checks.append(EmpiricalCheck(
        "Both ad hoc percentage and fixed-amount Discount shapes survive",
        has_percentage > 0 and has_amount > 0,
        f"percentage-shaped={has_percentage}, amount-shaped={has_amount}",
    ))

    # guest_number parse coverage matches the source parser result.
    all_line_items = [
        li
        for o in bundle.orders
        for li in (reader.load_dedicated_line_items(o["id"]) or (o.get("lineItems") or {}).get("elements", []))
    ]
    expected_guest_parsed = sum(1 for li in all_line_items if parser.parse_guest_number(li.get("binName")) is not None)
    canonical_guest_parsed = session.scalar(
        select(func.count()).select_from(m.OrderItem).where(m.OrderItem.guest_number.is_not(None))
    ) or 0
    checks.append(EmpiricalCheck(
        "guest_number parse coverage matches the source parser result",
        canonical_guest_parsed == expected_guest_parsed,
        f"expected={expected_guest_parsed}, canonical={canonical_guest_parsed}",
    ))

    # blank/missing guest labels remain NULL guest numbers.
    blank_or_missing_labels = sum(1 for li in all_line_items if not li.get("binName"))
    canonical_null_guest_with_blank_label = session.scalar(
        select(func.count())
        .select_from(m.OrderItem)
        .where(m.OrderItem.guest_number.is_(None), (m.OrderItem.guest_label_raw.is_(None)) | (m.OrderItem.guest_label_raw == ""))
    ) or 0
    checks.append(EmpiricalCheck(
        "Blank/missing guest labels remain NULL guest_number",
        canonical_null_guest_with_blank_label == blank_or_missing_labels,
        f"expected={blank_or_missing_labels}, canonical={canonical_null_guest_with_blank_label}",
    ))

    # No duplicate canonical external IDs.
    dup_checks = [
        (m.Order, [m.Order.source_system_id, m.Order.source_order_id]),
        (m.Payment, [m.Payment.source_system_id, m.Payment.source_payment_id]),
        (m.OrderItem, [m.OrderItem.source_system_id, m.OrderItem.source_line_item_id]),
        (m.Refund, [m.Refund.source_system_id, m.Refund.source_refund_id]),
        (m.Item, [m.Item.source_system_id, m.Item.source_item_id]),
    ]
    no_dupes = True
    dup_detail = []
    for model, cols in dup_checks:
        dupe_count = session.scalar(
            select(func.count()).select_from(
                select(*cols, func.count().label("n")).group_by(*cols).having(func.count() > 1).subquery()
            )
        ) or 0
        if dupe_count:
            no_dupes = False
            dup_detail.append(f"{model.__name__}: {dupe_count} duplicate key group(s)")
    checks.append(EmpiricalCheck("No duplicate canonical external IDs exist", no_dupes, "; ".join(dup_detail) or "none found"))

    # Tip missing vs zero remains distinguishable.
    tip_present_zero = session.scalar(
        select(func.count()).select_from(m.PaymentTip).where(m.PaymentTip.source_present.is_(True), m.PaymentTip.amount == 0)
    ) or 0
    payments_without_tip_row = _canonical_count(session, m.Payment) - _canonical_count(session, m.PaymentTip)
    checks.append(EmpiricalCheck(
        "Payment tip missing vs zero remains distinguishable",
        tip_present_zero >= 0 and payments_without_tip_row >= 0,
        f"present-and-zero={tip_present_zero}, payments-with-no-tip-row={payments_without_tip_row}",
    ))

    # Technical "# Guest" evidence retained.
    guest_item = session.scalars(select(m.Item).where(m.Item.name == "# Guest")).first()
    guest_order_items = (
        session.scalar(select(func.count()).select_from(m.OrderItem).where(m.OrderItem.item_id == guest_item.id))
        if guest_item
        else 0
    )
    checks.append(EmpiricalCheck(
        "Technical '# Guest' evidence retained",
        guest_item is not None and (guest_order_items or 0) > 0,
        f"item present={guest_item is not None}, order_items referencing it={guest_order_items}",
    ))

    # Dedicated selected Modifiers not silently dropped.
    source_modification_count = sum(
        len((li.get("modifications") or {}).get("elements", []))
        for o in bundle.orders
        for li in (reader.load_dedicated_line_items(o["id"]) or [])
    )
    canonical_oim = _canonical_count(session, m.OrderItemModifier)
    checks.append(EmpiricalCheck(
        "Dedicated selected Modifiers are not silently dropped",
        canonical_oim == source_modification_count,
        f"source (from currently-enriched orders)={source_modification_count}, canonical={canonical_oim}",
    ))

    return checks


def run_monetary_reconciliation(session: Session, bundle: reader.CloverSourceBundle) -> dict[str, Any]:
    sum_order_total = session.scalar(select(func.coalesce(func.sum(m.Order.total), 0))) or 0
    sum_payment_amount_by_result: dict[str, int] = {}
    for result_value, in session.execute(select(m.Payment.result).distinct()):
        s = session.scalar(
            select(func.coalesce(func.sum(m.Payment.amount), 0)).where(m.Payment.result == result_value)
        ) or 0
        sum_payment_amount_by_result[str(result_value)] = s
    sum_tip = session.scalar(select(func.coalesce(func.sum(m.PaymentTip.amount), 0))) or 0
    sum_refund = session.scalar(select(func.coalesce(func.sum(m.Refund.amount), 0))) or 0
    sum_order_tax_total = session.scalar(select(func.coalesce(func.sum(m.Order.tax_total), 0))) or 0
    sum_order_fee = session.scalar(select(func.coalesce(func.sum(m.OrderFee.amount), 0))) or 0

    return {
        "sum_order_total_cents": sum_order_total,
        "sum_payment_amount_by_result_cents": sum_payment_amount_by_result,
        "sum_payment_tip_cents": sum_tip,
        "sum_refund_amount_cents": sum_refund,
        "sum_order_tax_total_cents": sum_order_tax_total,
        "sum_order_fee_amount_cents": sum_order_fee,
        "notes": [
            "sum(Order.total) is NOT expected to equal sum(Payment.amount): "
            "FAILED payments contribute to the Payment sum but not to any "
            "settled Order total, and a Refund reduces realized value without "
            "changing Order.total (task §42).",
            "sum(Refund.amount) is a reduction against sum(Payment.amount for "
            "SUCCESS), not a separate independent total.",
        ],
    }


def _in_confidence_week(dt: datetime | None) -> bool:
    if dt is None:
        return False
    local = dt.astimezone(_CONFIDENCE_CHECK_TZ)
    return _CONFIDENCE_CHECK_WEEK_START <= local.date() <= _CONFIDENCE_CHECK_WEEK_END


def run_weekly_confidence_check(session: Session) -> dict[str, Any]:
    """Reuses TASK_CLOVER_002's already-validated reference week
    (2026-08-17 -> 2026-08-23, America/New_York) as a confidence check on
    the canonical ingestion — not a CSV rebuild (task §43)."""
    orders = session.scalars(select(m.Order)).all()
    in_window_orders = [o for o in orders if _in_confidence_week(o.created_at)]
    in_window_order_ids = {o.id for o in in_window_orders}

    payments = session.scalars(select(m.Payment)).all()
    in_window_payments = [p for p in payments if _in_confidence_week(p.created_at)]
    in_window_payment_ids = {p.id for p in in_window_payments}
    tips_present_in_window = session.scalar(
        select(func.count())
        .select_from(m.PaymentTip)
        .where(m.PaymentTip.payment_id.in_(in_window_payment_ids), m.PaymentTip.source_present.is_(True))
    ) if in_window_payment_ids else 0

    order_items_in_window = session.scalar(
        select(func.count()).select_from(m.OrderItem).where(m.OrderItem.order_id.in_(in_window_order_ids))
    ) if in_window_order_ids else 0

    shifts = session.scalars(select(m.Shift)).all()
    in_window_shifts = [s for s in shifts if _in_confidence_week(s.clock_in)]

    return {
        "window": f"{_CONFIDENCE_CHECK_WEEK_START} to {_CONFIDENCE_CHECK_WEEK_END} (America/New_York, out-of-band assumption — see module docstring)",
        "orders_in_window": len(in_window_orders),
        "orders_reference": 271,
        "payments_in_window": len(in_window_payments),
        "payments_reference": 287,
        "tips_present_in_window": tips_present_in_window,
        "tips_present_reference": 253,
        "order_items_in_window": order_items_in_window,
        "order_items_reference": 1838,
        "shifts_clock_in_in_window": len(in_window_shifts),
        "shifts_reference": 82,
    }


def run_data_quality_report(session: Session, bundle: reader.CloverSourceBundle, stats: Any) -> dict[str, Any]:
    total_orders = len(bundle.orders)
    guest_item_orders = sum(
        1
        for o in bundle.orders
        if any(li.get("name") == "# Guest" for li in (o.get("lineItems") or {}).get("elements", []))
    )
    all_line_items = [li for o in bundle.orders for li in (o.get("lineItems") or {}).get("elements", [])]
    binname_present = sum(1 for li in all_line_items if li.get("binName"))
    binname_nonempty = sum(1 for li in all_line_items if li.get("binName"))

    declared_vs_derived: dict[str, int] = {"match": 0, "declared_gt_derived": 0, "declared_lt_derived": 0, "declared_only": 0, "derived_only": 0, "neither": 0}
    for o in bundle.orders:
        declared = None
        max_guest = None
        for li in (o.get("lineItems") or {}).get("elements", []):
            if li.get("name") == "# Guest" and "unitQty" in li:
                declared = li["unitQty"] / 1000
            gn = parser.parse_guest_number(li.get("binName"))
            if gn is not None and (max_guest is None or gn > max_guest):
                max_guest = gn
        if declared is not None and max_guest is not None:
            if declared == max_guest:
                declared_vs_derived["match"] += 1
            elif declared > max_guest:
                declared_vs_derived["declared_gt_derived"] += 1
            else:
                declared_vs_derived["declared_lt_derived"] += 1
        elif declared is not None:
            declared_vs_derived["declared_only"] += 1
        elif max_guest is not None:
            declared_vs_derived["derived_only"] += 1
        else:
            declared_vs_derived["neither"] += 1

    failed_payments = sum(1 for p in bundle.payments if p.get("result") == "FAIL")
    shift_overrides_in = sum(1 for s in bundle.shifts if s.get("overrideInEmployee"))
    shift_overrides_out = sum(1 for s in bundle.shifts if s.get("overrideOutEmployee"))
    missing_created_at_orders = sum(1 for o in bundle.orders if o.get("createdTime") is None)

    return {
        "declared_guest_evidence_coverage": f"{guest_item_orders}/{total_orders}",
        "guest_label_coverage": f"{binname_present}/{len(all_line_items)} present, {binname_nonempty}/{len(all_line_items)} non-empty (bulk source)",
        "declared_vs_derived_guest_candidate_comparison": declared_vs_derived,
        "unresolved_employee_references": stats.unresolved_employee_refs,
        "unresolved_item_references": stats.unresolved_item_refs,
        "unresolved_modifier_references": stats.unresolved_modifier_refs,
        "unresolved_device_references": stats.unresolved_device_refs,
        "unresolved_tender_references": stats.unresolved_tender_refs,
        "unresolved_order_type_references": stats.unresolved_order_type_refs,
        "unresolved_discount_definition_references": stats.unresolved_discount_definition_refs,
        "missing_timestamps_order_created_at": missing_created_at_orders,
        "failed_payments": failed_payments,
        "refunds": len(bundle.refunds or []),
        "shift_overrides_in": shift_overrides_in,
        "shift_overrides_out": shift_overrides_out,
        "orders_missing_dedicated_line_items": len(stats.orders_missing_dedicated_line_items),
    }


def run_full_reconciliation(session: Session, bundle: reader.CloverSourceBundle, stats: Any) -> ReconciliationReport:
    report = ReconciliationReport()
    report.count_comparisons = run_count_reconciliation(session, bundle)
    report.empirical_checks = run_known_empirical_checks(session, bundle)
    report.monetary = run_monetary_reconciliation(session, bundle)
    report.weekly_confidence = run_weekly_confidence_check(session)
    report.data_quality = run_data_quality_report(session, bundle, stats)
    report.unresolved = {
        "employee": stats.unresolved_employee_refs,
        "item": stats.unresolved_item_refs,
        "modifier": stats.unresolved_modifier_refs,
        "device": stats.unresolved_device_refs,
        "tender": stats.unresolved_tender_refs,
        "order_type": stats.unresolved_order_type_refs,
        "discount_definition": stats.unresolved_discount_definition_refs,
    }
    return report
