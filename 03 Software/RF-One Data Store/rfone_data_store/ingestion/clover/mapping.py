"""Clover raw dict → canonical column-kwargs dict, per entity.

Every function here is pure (no DB session, no network) and returns a plain
`dict` of keyword arguments matching the corresponding ORM model's *own*
columns — never a resolved foreign key. Resolving `*_id` FKs from the
`*_source_id` values these functions return is `ingest.py`'s job, via
source-id → canonical-id lookup maps built as each entity type is upserted.

Every mapping decision that is not a direct 1:1 field copy is called out in
a comment, and mirrored in `CLOVER_INGESTION.md` § entity mapping.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..common import epoch_ms_to_utc
from . import parser


def map_merchant(merchant_raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_merchant_id": merchant_raw.get("id"),
        "name": merchant_raw.get("name"),
        "active": True,  # no active/inactive field is exposed on Merchant; the
        # single merchant reachable by this token is, by construction, active.
    }


def map_location(merchant_raw: dict[str, Any], observed_currency: str | None) -> dict[str, Any]:
    """Clover exposes no distinct Location resource — the single merchant
    IS the single location for this integration. `source_location_id` reuses
    the merchant's own id, documented explicitly (not a separate Clover field).
    `timezone` is intentionally left NULL: TASK_CLOVER_003 confirmed no
    timezone field exists anywhere on the Clover Merchant object (task §12).
    """
    return {
        "source_location_id": merchant_raw.get("id"),
        "name": merchant_raw.get("name"),
        "timezone": None,
        # Derived from the empirically-observed Order.currency value (100%
        # "USD" across all 3,521 orders) — not a direct Merchant/Location
        # field, since Clover exposes none. Left NULL if no Order evidence
        # exists to derive it from, rather than hard-coding "USD".
        "currency": observed_currency,
        "active": True,
    }


def map_device(device_raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_device_id": device_raw.get("id"),
        # Clover has no plain "name" field on Device; `productName` (e.g.
        # "Flex 4", "Station Solo") is the closest human-readable label —
        # `model` (e.g. "Clover_C501") is preserved separately, unchanged.
        "name": device_raw.get("productName"),
        "model": device_raw.get("model"),
        "device_type": device_raw.get("deviceTypeName"),
    }


def map_employee(employee_raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_employee_id": employee_raw.get("id"),
        "display_name": employee_raw.get("name"),  # PII, local DB only — never in tracked reports
        "custom_id": employee_raw.get("customId"),
        "system_role": employee_raw.get("role"),
        "active": None,  # no active/inactive field is exposed by Clover (TASK_CLOVER_003 §B)
        "source_created_at": None,  # no confirmed creation-time field on Employee
        "source_modified_at": None,
    }


def map_source_role(role_raw: dict[str, Any]) -> dict[str, Any]:
    """Clover's named Role catalog entry (e.g. `Server`, `Host`, `BOH`,
    `Admin` — TASK_CLOVER_004). `systemRole` here is a catalog attribute of
    the Role itself, distinct from `Employee.system_role`."""
    return {
        "source_role_id": role_raw.get("id"),
        "name": role_raw.get("name"),
        "source_system_role": role_raw.get("systemRole"),
    }


def map_shift(shift_raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_shift_id": shift_raw.get("id"),
        "employee_source_id": parser.ref_id(shift_raw.get("employee")),
        "clock_in": epoch_ms_to_utc(shift_raw.get("inTime")),
        "clock_out": epoch_ms_to_utc(shift_raw.get("outTime")),
        "override_in_employee_source_id": parser.ref_id(shift_raw.get("overrideInEmployee")),
        "override_in_time": epoch_ms_to_utc(shift_raw.get("overrideInTime")),
        "override_out_employee_source_id": parser.ref_id(shift_raw.get("overrideOutEmployee")),
        "override_out_time": epoch_ms_to_utc(shift_raw.get("overrideOutTime")),
        "server_banking": shift_raw.get("serverBanking"),
        "source_created_at": None,  # no confirmed field
        "source_modified_at": None,
    }


def map_order_type(order_type_raw: dict[str, Any]) -> dict[str, Any]:
    is_deleted = order_type_raw.get("isDeleted")
    return {
        "source_order_type_id": order_type_raw.get("id"),
        "name": order_type_raw.get("label"),
        "min_order_amount": order_type_raw.get("minOrderAmount"),
        "max_order_amount": order_type_raw.get("maxOrderAmount"),
        "configured_fee": order_type_raw.get("fee"),
        "average_order_time": order_type_raw.get("avgOrderTime"),
        # isDeleted is 100%-present per TASK_CLOVER_003 — a direct, non-speculative
        # basis for active/inactive, unlike isHidden (visibility, not existence).
        "active": (not is_deleted) if is_deleted is not None else None,
    }


def map_category(category_raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_category_id": category_raw.get("id"),
        "name": category_raw.get("name"),
    }


def map_modifier_group(group_raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_modifier_group_id": group_raw.get("id"),
        "name": group_raw.get("name"),
    }


def map_modifier(modifier_raw: dict[str, Any]) -> dict[str, Any]:
    is_deleted = modifier_raw.get("deleted")
    return {
        "source_modifier_id": modifier_raw.get("id"),
        "name": modifier_raw.get("name"),
        "alternate_name": modifier_raw.get("alternateName"),
        "price_delta": modifier_raw.get("price"),
        "active": (not is_deleted) if is_deleted is not None else None,
    }


def map_discount_definition(discount_raw: dict[str, Any]) -> dict[str, Any]:
    percentage = discount_raw.get("percentage")
    return {
        "source_discount_id": discount_raw.get("id"),
        "name": discount_raw.get("name"),
        # Canonical decimal PERCENT value (e.g. 50 -> Decimal("50")), matching
        # Clover's own catalog encoding (already a plain percent integer, NOT
        # scaled like TaxRate.rate) — see DATABASE_SCHEMA.md § 0.
        "percentage": Decimal(str(percentage)) if percentage is not None else None,
        "amount": discount_raw.get("amount"),
        "active": None,  # no active/deleted field confirmed on Clover's discounts.json
    }


def map_tax_rate(tax_rate_raw: dict[str, Any]) -> dict[str, Any]:
    rate = parser.canonical_tax_rate(tax_rate_raw.get("rate"))
    return {
        "source_tax_rate_id": tax_rate_raw.get("id"),
        "name": tax_rate_raw.get("name"),
        "rate": Decimal(str(rate)) if rate is not None else None,
        "active": None,  # no active/deleted field confirmed on Clover's tax_rates.json
    }


def map_tender(tender_obj: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_tender_id": tender_obj.get("id"),
        "label": tender_obj.get("label"),
        # `labelKey` (an i18n key, e.g. "com.clover.tender.cash") is the
        # closest structural type Clover exposes. `opensCashDrawer` is
        # deliberately NOT used — TASK_CLOVER_003 disproved it as a cash/card
        # signal for this merchant (task §22).
        "source_type": tender_obj.get("labelKey"),
        "active": tender_obj.get("enabled"),
    }


def map_item(item_raw: dict[str, Any]) -> dict[str, Any]:
    is_deleted = item_raw.get("deleted")
    return {
        "source_item_id": item_raw.get("id"),
        "name": item_raw.get("name"),
        "sku": item_raw.get("sku"),
        "code": item_raw.get("code"),
        "current_price": item_raw.get("price"),
        "price_without_vat": item_raw.get("priceWithoutVat"),
        "price_type": item_raw.get("priceType"),
        "item_type": item_raw.get("type"),
        "item_nature": None,  # RF-One classification — never auto-derived (task §17)
        # `deleted` is the least speculative of Clover's three status-like
        # Item flags (deleted/hidden/available); `hidden`/`available` are not
        # collapsed into this single column, per the existing schema, and are
        # not otherwise persisted — see CLOVER_INGESTION.md.
        "active": (not is_deleted) if is_deleted is not None else None,
        "source_created_at": None,  # no confirmed creation-time field on Item
        "source_modified_at": epoch_ms_to_utc(item_raw.get("modifiedTime")),
    }


def map_order(order_raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_order_id": order_raw.get("id"),
        "source_employee_id": parser.ref_id(order_raw.get("employee")),
        "employee_source_id": parser.ref_id(order_raw.get("employee")),
        "order_type_source_id": parser.ref_id(order_raw.get("orderType")),
        "device_source_id": parser.ref_id(order_raw.get("device")),
        "client_created_at": epoch_ms_to_utc(order_raw.get("clientCreatedTime")),
        "created_at": epoch_ms_to_utc(order_raw.get("createdTime")),
        "modified_at": epoch_ms_to_utc(order_raw.get("modifiedTime")),
        "state": order_raw.get("state"),
        "payment_state": order_raw.get("paymentState"),
        "pay_type": order_raw.get("payType"),
        "currency": order_raw.get("currency"),
        # subtotal/discount_total are intentionally NOT populated here: Clover
        # exposes neither directly, and computing them accurately requires the
        # same percentage-to-cents allocation the task explicitly calls
        # "derived analytics, not source truth" (§29) when applied at the
        # Order Item level — left for a future analytics pass, not fabricated
        # here. tax_total IS populated: it is a simple, non-allocative sum of
        # the order's own nested Payments (task §30; TASK_CLOVER_002-confirmed
        # formula), owned conceptually by Order per the Restaurant Sales Model.
        "subtotal": None,
        "discount_total": None,
        "tax_total": _sum_nested_payment_field(order_raw, "taxAmount"),
        "total": order_raw.get("total"),
        "title_raw": order_raw.get("title"),
        "note": order_raw.get("note"),
        "test_mode": order_raw.get("testMode"),
        "manual_transaction": order_raw.get("manualTransaction"),
        "tax_removed": order_raw.get("taxRemoved"),
        "is_vat": order_raw.get("isVat"),
    }


def _sum_nested_payment_field(order_raw: dict[str, Any], field_name: str) -> int | None:
    payments = (order_raw.get("payments") or {}).get("elements") or []
    if not payments:
        return None
    return sum(p.get(field_name) or 0 for p in payments)


def map_order_item(line_item_raw: dict[str, Any]) -> dict[str, Any]:
    unit_qty = line_item_raw.get("unitQty")
    return {
        "source_line_item_id": line_item_raw.get("id"),
        "item_source_id": parser.ref_id(line_item_raw.get("item")),
        "created_at": epoch_ms_to_utc(line_item_raw.get("createdTime")),
        "source_name": line_item_raw.get("name"),
        # Never defaulted to 1 when the source key is absent (task §19/§24).
        "quantity": (Decimal(unit_qty) / Decimal(1000)) if unit_qty is not None else None,
        "quantity_decimal_digits": line_item_raw.get("unitQtyDecimalDigits"),
        "unit_name": line_item_raw.get("unitName"),
        "historical_unit_price": line_item_raw.get("price"),
        "guest_number": parser.parse_guest_number(line_item_raw.get("binName")),
        "guest_label_raw": line_item_raw.get("binName"),
        "item_code_raw": line_item_raw.get("itemCode"),
        "is_revenue": line_item_raw.get("isRevenue"),
        "is_order_fee": line_item_raw.get("isOrderFee"),
        "printed": line_item_raw.get("printed"),
        "refunded_flag": line_item_raw.get("refunded"),
        "exchanged_flag": line_item_raw.get("exchanged"),
        "line_item_info_json": line_item_raw.get("lineItemInfo"),
    }


def map_order_item_modifier(modification_raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_modification_id": modification_raw.get("id"),
        "modifier_source_id": parser.ref_id(modification_raw.get("modifier")),
        "name_raw": modification_raw.get("name"),
        "amount": modification_raw.get("amount"),
    }


def map_order_fee(fee_line_item_raw: dict[str, Any]) -> dict[str, Any]:
    """`fee_line_item_raw` is a Clover line item with `isOrderFee: true`
    (the synthetic "Gratuity"/Service Charge line — task §31)."""
    note = fee_line_item_raw.get("note")
    return {
        "source_fee_id": parser.ref_id(fee_line_item_raw.get("orderFee")),
        "source_line_item_id": fee_line_item_raw.get("id"),
        # Only the one confirmed real-world combination (note == "Service
        # Charge") is classified; anything else is left NULL rather than
        # guessed (task §31: "do not classify arbitrary fee-like Item names
        # automatically").
        "fee_type": "SERVICE_CHARGE" if note == "Service Charge" else None,
        "name_raw": fee_line_item_raw.get("name"),
        "amount": fee_line_item_raw.get("price"),
        "percentage": (
            Decimal(str(fee_line_item_raw.get("percentage")))
            if fee_line_item_raw.get("percentage") is not None
            else None
        ),
    }


def map_payment(payment_raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_payment_id": payment_raw.get("id"),
        "order_source_id": parser.ref_id(payment_raw.get("order")),
        "employee_source_id": parser.ref_id(payment_raw.get("employee")),
        "source_employee_id": parser.ref_id(payment_raw.get("employee")),
        "tender_source_id": parser.ref_id(payment_raw.get("tender")),
        "device_source_id": parser.ref_id(payment_raw.get("device")),
        "client_created_at": epoch_ms_to_utc(payment_raw.get("clientCreatedTime")),
        "created_at": epoch_ms_to_utc(payment_raw.get("createdTime")),
        "modified_at": epoch_ms_to_utc(payment_raw.get("modifiedTime")),
        "amount": payment_raw.get("amount"),
        "tax_amount_source": payment_raw.get("taxAmount"),
        "cash_tendered": payment_raw.get("cashTendered"),
        "cashback_amount": payment_raw.get("cashbackAmount"),
        "result": payment_raw.get("result"),
        "offline": payment_raw.get("offline"),
        # No direct `currency` field exists on Payment (CLOVER_EXPORT_MAPPING.md
        # § 1: "Strongly supported [via Order], no direct field on Payment
        # itself") — left NULL rather than copied from the parent Order.
        "currency": None,
    }


def map_payment_tip(payment_raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_present": "tipAmount" in payment_raw,
        "amount": payment_raw.get("tipAmount"),
    }


def map_refund(refund_raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_refund_id": refund_raw.get("id"),
        "order_source_id": parser.ref_id(refund_raw.get("orderRef")),
        "payment_source_id": parser.ref_id(refund_raw.get("payment")),
        "employee_source_id": parser.ref_id(refund_raw.get("employee")),
        "device_source_id": parser.ref_id(refund_raw.get("device")),
        "created_at": epoch_ms_to_utc(refund_raw.get("createdTime")),
        "amount": refund_raw.get("amount"),
        "tax_amount": refund_raw.get("taxAmount"),
        "tip_amount": refund_raw.get("tipAmount"),
        "status": refund_raw.get("status"),
        "voided": refund_raw.get("voided"),
    }
