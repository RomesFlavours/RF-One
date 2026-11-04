"""Reconstruct a Payments_RFOne.csv row set comparable to Clover's dashboard
"Payments" export, from raw API data plus a small number of supplementary
read-only GET calls (see CLOVER_EXPORT_MAPPING.md for per-column sourcing
and confidence).

Only GET requests are issued. Nothing here writes to Clover.
"""

from __future__ import annotations

from typing import Any

from .api_cache import ApiCache
from .client import CloverClient
from .export_models import RawData, ref_id
from .pagination import paginate
from .time_money import cents_to_amount_str, format_dashboard_datetime

PAYMENTS_COLUMNS = [
    "Payment Date",
    "Payment ID",
    "External Payment ID",
    "Invoice Number",
    "Card Auth Code",
    "Transaction #",
    "Note",
    "Tender",
    "Card Brand",
    "Card Number",
    "Card Entry Type",
    "Currency",
    "Amount",
    "Tax Amount",
    "Tip Amount",
    "Service Charge Amount",
    "Customer Name",
    "Payment Employee ID",
    "Payment Employee Name",
    "Payment Employee Custom ID",
    "Order ID",
    "Order Date",
    "Order Employee ID",
    "Order Employee Name",
    "Order Employee Custom ID",
    "Result",
    "Device",
    "# Refunds",
    "Refund Amount",
    "Custom Fields",
]


def fetch_devices_by_id(client: CloverClient, cache: ApiCache) -> dict[str, dict[str, Any]]:
    def _fetch():
        result = paginate(client, f"/v3/merchants/{client.merchant_id}/devices")
        return result.elements if result.ok else []

    devices = cache.get_or_fetch("devices", _fetch)
    return {d["id"]: d for d in devices if "id" in d}


def fetch_card_transaction(client: CloverClient, cache: ApiCache, payment_id: str) -> dict[str, Any] | None:
    def _fetch():
        r = client.get(
            f"/v3/merchants/{client.merchant_id}/payments/{payment_id}",
            params={"expand": "cardTransaction"},
        )
        if not r.ok:
            return None
        return r.data.get("cardTransaction")

    return cache.get_or_fetch(f"cardtx_{payment_id}", _fetch)


def build_payment_row(
    payment: dict[str, Any],
    raw: RawData,
    devices_by_id: dict[str, dict[str, Any]],
    card_tx: dict[str, Any] | None,
) -> dict[str, str]:
    order_id = ref_id(payment.get("order"))
    order = raw.orders_by_id.get(order_id, {}) if order_id else {}

    pay_emp_id, pay_emp_name, pay_emp_custom = raw.employee_fields(ref_id(payment.get("employee")))
    ord_emp_id, ord_emp_name, ord_emp_custom = raw.employee_fields(ref_id(order.get("employee")))

    device = devices_by_id.get(ref_id(payment.get("device")), {})
    tender = payment.get("tender") or {}

    card_tx = card_tx or {}

    return {
        "Payment Date": format_dashboard_datetime(payment.get("createdTime")),
        "Payment ID": payment.get("id", ""),
        "External Payment ID": "",  # Unresolved — no source field observed
        "Invoice Number": "",  # Unresolved — no source field observed
        "Card Auth Code": card_tx.get("authCode", ""),
        "Transaction #": card_tx.get("transactionNo", ""),
        "Note": "",  # Unresolved — no source field observed
        "Tender": tender.get("label", ""),
        "Card Brand": card_tx.get("cardType", ""),
        "Card Number": card_tx.get("last4", ""),
        "Card Entry Type": card_tx.get("entryType", ""),
        "Currency": (order.get("currency") or "").upper(),
        "Amount": cents_to_amount_str(payment.get("amount")),
        "Tax Amount": cents_to_amount_str(payment.get("taxAmount")),
        # Tip Amount: missing key is preserved as "" (blank), NOT defaulted to
        # 0.00 — empirically confirmed against the reference Payments export
        # (see CLOVER_EXPORT_MAPPING.md / CLOVER_EXPORT_RECONCILIATION.md §1).
        "Tip Amount": cents_to_amount_str(payment.get("tipAmount")),
        # Service Charge Amount: the Clover Payments API/dashboard never
        # carries this value (confirmed empirically — 0/287 reference rows
        # populated). Left blank deliberately, not fabricated.
        "Service Charge Amount": "",
        "Customer Name": card_tx.get("cardholderName", ""),
        "Payment Employee ID": pay_emp_id,
        "Payment Employee Name": pay_emp_name,
        "Payment Employee Custom ID": pay_emp_custom,
        "Order ID": order_id or "",
        "Order Date": format_dashboard_datetime(order.get("createdTime")),
        "Order Employee ID": ord_emp_id,
        "Order Employee Name": ord_emp_name,
        "Order Employee Custom ID": ord_emp_custom,
        "Result": payment.get("result", ""),
        "Device": device.get("serial", ""),
        "# Refunds": "",  # Unresolved — no refunded payment in this run to confirm source
        "Refund Amount": "",  # Unresolved — same as above
        "Custom Fields": "",  # Unresolved — no source field observed
    }


def build_payment_rows(
    client: CloverClient,
    raw: RawData,
    payments_in_window: list[dict[str, Any]],
    cache: ApiCache,
) -> list[dict[str, str]]:
    devices_by_id = fetch_devices_by_id(client, cache)
    rows = []
    for payment in payments_in_window:
        card_tx = fetch_card_transaction(client, cache, payment["id"])
        rows.append(build_payment_row(payment, raw, devices_by_id, card_tx))
    return rows
