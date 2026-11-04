"""Reconstruct a LineItems_RFOne.csv row set comparable to Clover's dashboard
"Line Items" export.

This is the most involved reconstruction in TASK_CLOVER_002. Two facts
drove the design (see CLOVER_EXPORT_MAPPING.md for full evidence):

1. The bulk `orders?expand=lineItems` collection (from TASK_CLOVER_001) does
   NOT include modifier data at all — `modifications` is entirely absent
   from every line item in that export, even for items the reference CSV
   shows a modifier on. Full modifier reconstruction requires a dedicated
   `GET /orders/{orderId}/line_items?expand=modifications` call per order.
2. Every per-column formula below (Item Total, Order Discount Proportion,
   Tax Amount, Service Charge flag, etc.) was reverse-engineered against
   real reference rows for 3 orders (2 discounted, 1 with a modifier, 2
   with a Service Charge "Gratuity" line) and is documented with its
   confidence level in CLOVER_EXPORT_MAPPING.md — this module does not
   invent Clover's discount-allocation algorithm beyond what was verified.
"""

from __future__ import annotations

from typing import Any

from .api_cache import ApiCache
from .client import CloverClient
from .export_models import RawData, ref_id
from .export_orders import PAYMENT_STATE_LABELS, _order_line_items
from .pagination import paginate
from .time_money import (
    cents_to_amount_str,
    format_dashboard_datetime,
    format_percentage,
    round_half_up_cents,
)

LINE_ITEMS_COLUMNS = [
    "Line Item Date",
    "Order Employee ID",
    "Order Employee Name",
    "Order Employee Custom ID",
    "Item ID",
    "Item Product Code",
    "Item SKU",
    "Order ID",
    "Item Name",
    "Currency",
    "Per Unit Quantity",
    "Item Unit",
    "Item Revenue",
    "Modifiers",
    "Modifiers Revenue",
    "Total Revenue",
    "Discounts",
    "Total Discount",
    "Order Discounts",
    "Order Discount Proportion",
    "Item Total",
    "Item Tax Rate",
    "Item Fee",
    "Tax Amount",
    "Item Total with Tax/Fee Amount",
    "Refunded",
    "Exchanged",
    "Order Payment State",
    "Service Charge",
]


def fetch_line_items_with_modifications(
    client: CloverClient, cache: ApiCache, order_id: str
) -> list[dict[str, Any]]:
    def _fetch():
        result = paginate(
            client,
            f"/v3/merchants/{client.merchant_id}/orders/{order_id}/line_items",
            extra_params={"expand": "modifications"},
        )
        return result.elements if result.ok else []

    return cache.get_or_fetch(f"lineitems_{order_id}", _fetch)


def fetch_item_tax_rate(
    client: CloverClient, cache: ApiCache, item_id: str
) -> float | None:
    """Only called for items with defaultTaxRates=False, i.e. items whose
    tax rate is NOT the merchant default and must be resolved individually.
    Returns the rate as a decimal fraction (e.g. 0.0697), or None if
    unresolved."""

    def _fetch():
        r = client.get(
            f"/v3/merchants/{client.merchant_id}/items/{item_id}",
            params={"expand": "taxRates"},
        )
        if not r.ok:
            return None
        rates = (r.data.get("taxRates") or {}).get("elements", [])
        # An item with defaultTaxRates=False and an empty taxRates list has
        # no tax rate assigned at all -- confirmed empirically (wine/liquor
        # items in the reference export show Item Tax Rate "0.0"), not a
        # fetch failure that should fall back to the merchant default.
        return rates[0]["rate"] / 10_000_000 if rates else 0.0

    return cache.get_or_fetch(f"itemtaxrate_{item_id}", _fetch)


def _item_tax_rate_text(rate: float) -> str:
    return str(rate)


def _resolve_tax_rate(
    raw: RawData, client: CloverClient, cache: ApiCache, item_id: str | None
) -> float:
    if item_id:
        item = raw.items_by_id.get(item_id)
        if item and not item.get("defaultTaxRates", True):
            rate = fetch_item_tax_rate(client, cache, item_id)
            if rate is not None:
                return rate
    if raw.default_tax_rate:
        return raw.default_tax_rate.get("rate", 0) / 10_000_000
    return 0.0


def _order_discount_shares(order: dict[str, Any]) -> dict[str, tuple[int, list[str]]]:
    """For each revenue line item id in `order`, returns
    (discount_share_cents, [description texts]) contributed by the order's
    percentage-type discounts. Line items not eligible for a discount share
    are simply absent from the returned dict."""
    revenue_items = [
        li for li in _order_line_items(order) if li.get("isRevenue") and not li.get("isOrderFee")
    ]
    shares: dict[str, tuple[int, list[str]]] = {li["id"]: (0, []) for li in revenue_items}
    for d in (order.get("discounts") or {}).get("elements", []):
        pct = d.get("percentage")
        if pct is None:
            continue  # non-percentage discount type: not reconstructed (see mapping doc)
        name = d.get("name", "")
        for li in revenue_items:
            share_cents = round_half_up_cents(li.get("price", 0) * pct / 100)
            prev_cents, prev_texts = shares[li["id"]]
            text = f"{name} ({format_percentage(pct)}%) -${share_cents / 100:.2f}"
            shares[li["id"]] = (prev_cents + share_cents, prev_texts + [text])
    return shares


def build_line_item_rows_for_order(
    order: dict[str, Any],
    raw: RawData,
    client: CloverClient,
    cache: ApiCache,
) -> list[dict[str, str]]:
    order_id = order["id"]
    ord_emp_id, ord_emp_name, ord_emp_custom = raw.employee_fields(ref_id(order.get("employee")))
    line_item_date = format_dashboard_datetime(order.get("createdTime"))
    currency = (order.get("currency") or "").upper()
    payment_state = PAYMENT_STATE_LABELS.get(order.get("paymentState", ""), order.get("paymentState", ""))
    discount_shares = _order_discount_shares(order)

    line_items = fetch_line_items_with_modifications(client, cache, order_id)

    rows = []
    for li in line_items:
        item_id = ref_id(li.get("item"))
        item = raw.items_by_id.get(item_id, {}) if item_id else {}
        is_fee = bool(li.get("isOrderFee"))

        item_revenue_cents = li.get("price", 0)
        mods = (li.get("modifications") or {}).get("elements", [])
        mods_revenue_cents = sum(m.get("amount", 0) for m in mods) if mods else None
        modifiers_text = ", ".join(
            f"{m.get('name', '')} ({ref_id(m.get('modifier')) or ''}) ${m.get('amount', 0) / 100:.2f}"
            for m in mods
        )
        total_revenue_cents = item_revenue_cents + (mods_revenue_cents or 0)

        discount_share_cents, discount_texts = discount_shares.get(li["id"], (0, []))
        item_total_cents = total_revenue_cents - discount_share_cents

        if is_fee:
            tax_rate = 0.0
            tax_rate_text = "0.0"
        else:
            tax_rate = _resolve_tax_rate(raw, client, cache, item_id)
            tax_rate_text = _item_tax_rate_text(tax_rate)

        item_fee_cents = 0  # confirmed 0.00 in every validated sample row; see mapping doc
        tax_amount_cents = round_half_up_cents(item_total_cents * tax_rate)
        total_with_tax_cents = item_total_cents + item_fee_cents + tax_amount_cents

        per_unit_qty = li.get("unitQty")

        rows.append(
            {
                "Line Item Date": line_item_date,
                "Order Employee ID": ord_emp_id,
                "Order Employee Name": ord_emp_name,
                "Order Employee Custom ID": ord_emp_custom,
                "Item ID": item_id or "",
                "Item Product Code": item.get("code", ""),
                "Item SKU": item.get("sku", ""),
                "Order ID": order_id,
                "Item Name": li.get("name", ""),
                "Currency": currency,
                "Per Unit Quantity": f"{per_unit_qty / 1000:.3f}" if per_unit_qty is not None else "",
                "Item Unit": li.get("unitName", ""),
                "Item Revenue": cents_to_amount_str(item_revenue_cents),
                "Modifiers": modifiers_text,
                "Modifiers Revenue": cents_to_amount_str(mods_revenue_cents),
                "Total Revenue": cents_to_amount_str(total_revenue_cents),
                "Discounts": "",  # Unresolved — no line-item-level (as opposed to order-level) discount observed
                "Total Discount": "0.00",  # confirmed 0.00 in every validated sample; see mapping doc
                "Order Discounts": "; ".join(discount_texts),
                "Order Discount Proportion": cents_to_amount_str(-discount_share_cents),
                "Item Total": cents_to_amount_str(item_total_cents),
                "Item Tax Rate": tax_rate_text,
                "Item Fee": cents_to_amount_str(item_fee_cents),
                "Tax Amount": cents_to_amount_str(tax_amount_cents),
                "Item Total with Tax/Fee Amount": cents_to_amount_str(total_with_tax_cents),
                "Refunded": "true" if li.get("refunded") else "false",
                "Exchanged": "true" if li.get("exchanged") else "false",
                "Order Payment State": payment_state,
                "Service Charge": "True" if is_fee else "",
            }
        )
    return rows


def build_line_item_rows(
    client: CloverClient,
    raw: RawData,
    orders_in_window: list[dict[str, Any]],
    cache: ApiCache,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for order in orders_in_window:
        rows.extend(build_line_item_rows_for_order(order, raw, client, cache))
    return rows
