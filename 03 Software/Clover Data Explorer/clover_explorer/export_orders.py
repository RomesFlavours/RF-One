"""Reconstruct an Orders_RFOne.csv row set comparable to Clover's dashboard
"Orders" export, from raw API data.

Key empirical findings this module encodes (see CLOVER_EXPORT_MAPPING.md
and CLOVER_EXPORT_RECONCILIATION.md §5 for the full evidence):

- Order.Tax/Tip/Payments Total are NOT fields on the order object itself;
  they are derived by summing the order's nested `payments` elements.
- Order.Tip defaults a missing `tipAmount` to 0.00 — this is a *dashboard*
  behavior confirmed against the reference export, distinct from Payments
  (where a missing tipAmount stays blank). Do not generalize this default
  to the Payments export.
- Order.Service Charge is NOT a field anywhere on the order or payment
  objects. It is the sum of the order's `lineItems` that carry
  `isOrderFee: true` (observed name "Gratuity", note "Service Charge").
- Order.Discount is reconstructed only for percentage-type order-level
  discounts (order.discounts[].percentage), applied to revenue line items
  (isRevenue=true, isOrderFee=false). Non-percentage discount types are not
  present in the validated sample and are left unresolved rather than
  guessed (see CLOVER_EXPORT_MAPPING.md).
"""

from __future__ import annotations

from typing import Any

from .api_cache import ApiCache
from .client import CloverClient
from .export_models import RawData, ref_id
from .export_payments import fetch_card_transaction
from .time_money import cents_to_amount_str, format_dashboard_datetime

ORDERS_COLUMNS = [
    "Order Date",
    "Order ID",
    "Invoice Number",
    "Order Number",
    "Order Type",
    "Order Employee ID",
    "Order Employee Name",
    "Order Employee Custom ID",
    "Note",
    "Currency",
    "Tax Amount",
    "Tip",
    "Service Charge",
    "Discount",
    "Order Total",
    "Payments Total",
    "Payment Note",
    "Refunds Total",
    "Manual Refunds Total",
    "Tender",
    "Credit Card Auth Code",
    "Credit Card Transaction ID",
    "Order Payment State",
]

PAYMENT_STATE_LABELS = {
    "PAID": "Paid",
    "OPEN": "Open",
}


def _order_line_items(order: dict[str, Any]) -> list[dict[str, Any]]:
    return (order.get("lineItems") or {}).get("elements", [])


def _order_payments(order: dict[str, Any]) -> list[dict[str, Any]]:
    return (order.get("payments") or {}).get("elements", [])


def compute_service_charge_cents(order: dict[str, Any]) -> int:
    return sum(li.get("price", 0) for li in _order_line_items(order) if li.get("isOrderFee"))


def compute_discount_cents(order: dict[str, Any]) -> tuple[int, bool]:
    """Returns (discount_cents, has_unresolved_component). discount_cents is
    the positive magnitude; the dashboard displays it negated."""
    revenue_items = [
        li for li in _order_line_items(order) if li.get("isRevenue") and not li.get("isOrderFee")
    ]
    total = 0
    unresolved = False
    for d in (order.get("discounts") or {}).get("elements", []):
        pct = d.get("percentage")
        if pct is None:
            unresolved = True
            continue
        total += round(sum(li.get("price", 0) for li in revenue_items) * pct / 100)
    return total, unresolved


def build_order_row(
    order: dict[str, Any],
    raw: RawData,
    payments_by_id: dict[str, dict[str, Any]],
    client: CloverClient,
    cache: ApiCache,
    unresolved_discount_orders: list[str],
) -> dict[str, str]:
    ord_emp_id, ord_emp_name, ord_emp_custom = raw.employee_fields(ref_id(order.get("employee")))

    order_type = raw.order_types_by_id.get(ref_id(order.get("orderType")), {})

    order_payments = _order_payments(order)
    tax_cents = sum(p.get("taxAmount", 0) or 0 for p in order_payments)
    tip_cents = sum(p.get("tipAmount", 0) or 0 for p in order_payments)  # missing -> 0, confirmed
    payments_total_cents = sum(p.get("amount", 0) or 0 for p in order_payments)
    service_charge_cents = compute_service_charge_cents(order)
    discount_cents, discount_unresolved = compute_discount_cents(order)
    if discount_unresolved:
        unresolved_discount_orders.append(order.get("id", ""))

    # Tender + card details: resolved via the top-level payments collection
    # (has tender.label expanded) and the same cardTransaction cache used by
    # the Payments exporter, keyed by payment id, to avoid duplicate calls.
    # Confirmed empirically: the dashboard lists one Tender label PER
    # PAYMENT (not deduplicated), comma-separated, in payment order.
    tender_labels: list[str] = []
    auth_code = ""
    transaction_id = ""
    for p in order_payments:
        full_payment = payments_by_id.get(p.get("id"), {})
        label = (full_payment.get("tender") or {}).get("label")
        if label:
            tender_labels.append(label)
        if not auth_code or not transaction_id:
            card_tx = fetch_card_transaction(client, cache, p.get("id")) or {}
            auth_code = auth_code or card_tx.get("authCode", "")
            transaction_id = transaction_id or card_tx.get("referenceId", "")

    raw_state = order.get("paymentState", "")

    return {
        "Order Date": format_dashboard_datetime(order.get("createdTime")),
        "Order ID": order.get("id", ""),
        "Invoice Number": "",  # Unresolved — no source field observed
        "Order Number": "",  # Unresolved — no source field observed
        "Order Type": order_type.get("label", ""),
        "Order Employee ID": ord_emp_id,
        "Order Employee Name": ord_emp_name,
        "Order Employee Custom ID": ord_emp_custom,
        "Note": order.get("note", ""),
        "Currency": (order.get("currency") or "").upper(),
        "Tax Amount": cents_to_amount_str(tax_cents),
        "Tip": cents_to_amount_str(tip_cents),
        # Service Charge is left BLANK (not "0.00") when no order-fee line
        # item exists — confirmed empirically against the reference export,
        # the opposite default behavior from Tip. Do not unify the two.
        "Service Charge": cents_to_amount_str(service_charge_cents) if service_charge_cents else "",
        "Discount": cents_to_amount_str(-discount_cents) if discount_cents else cents_to_amount_str(0),
        "Order Total": cents_to_amount_str(order.get("total")),
        "Payments Total": cents_to_amount_str(payments_total_cents),
        "Payment Note": "",  # Unresolved — no source field observed
        "Refunds Total": "",  # Unresolved — no refunded order in this run to confirm source
        "Manual Refunds Total": "",  # Unresolved — same as above
        "Tender": ", ".join(tender_labels),
        "Credit Card Auth Code": auth_code,
        "Credit Card Transaction ID": transaction_id,
        "Order Payment State": PAYMENT_STATE_LABELS.get(raw_state, raw_state),
    }


def build_order_rows(
    client: CloverClient,
    raw: RawData,
    orders_in_window: list[dict[str, Any]],
    cache: ApiCache,
) -> tuple[list[dict[str, str]], list[str]]:
    unresolved_discount_orders: list[str] = []
    rows = [
        build_order_row(order, raw, raw.payments_by_id, client, cache, unresolved_discount_orders)
        for order in orders_in_window
    ]
    return rows, unresolved_discount_orders
