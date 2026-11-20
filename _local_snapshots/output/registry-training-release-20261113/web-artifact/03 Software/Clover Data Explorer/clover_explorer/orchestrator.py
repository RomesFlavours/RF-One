"""Export orchestration: drives the Clover client + pagination + raw_store
across every collection this discovery pass investigates.

No business logic (tip calculation, KPI derivation, normalization) lives
here — only retrieval and raw persistence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import raw_store
from .client import CloverClient
from .pagination import DEFAULT_PAGE_SIZE, paginate

CATEGORY_MERCHANT = "Merchant"
CATEGORY_EMPLOYEES = "Employees"
CATEGORY_CUSTOMERS = "Customers"
CATEGORY_INVENTORY = "Inventory"
CATEGORY_ORDERS = "Orders"
CATEGORY_PAYMENTS = "Payments"

# Sample size for the per-order deep fetch used only to check whether the
# `expand=lineItems` array on the /orders collection is complete relative
# to the order's own dedicated line_items endpoint. Deliberately bounded:
# a full per-order crawl across a merchant's entire order history is a
# separate, much larger job left for a later incremental task.
ORDER_LINE_ITEM_SAMPLE_SIZE = 20


@dataclass
class CollectionSpec:
    name: str
    category: str
    path_suffix: str  # appended to /v3/merchants/{mId}
    expand: str | None = None
    notes: str = ""


COLLECTIONS: list[CollectionSpec] = [
    CollectionSpec("employees", CATEGORY_EMPLOYEES, "/employees"),
    CollectionSpec(
        "shifts",
        CATEGORY_EMPLOYEES,
        "/shifts",
        notes="Investigated for hours and cash-tip-related fields.",
    ),
    CollectionSpec("roles", CATEGORY_EMPLOYEES, "/roles"),
    CollectionSpec(
        "customers",
        CATEGORY_CUSTOMERS,
        "/customers",
        notes="No additional sensitive expansions requested beyond the endpoint default.",
    ),
    CollectionSpec("items", CATEGORY_INVENTORY, "/items"),
    CollectionSpec("categories", CATEGORY_INVENTORY, "/categories"),
    CollectionSpec(
        "modifier_groups",
        CATEGORY_INVENTORY,
        "/modifier_groups",
        expand="modifiers",
        notes="Modifiers retrieved nested via expand; nested array may be truncated independently of the parent page.",
    ),
    CollectionSpec("item_stocks", CATEGORY_INVENTORY, "/item_stocks"),
    CollectionSpec("discounts", CATEGORY_INVENTORY, "/discounts"),
    CollectionSpec("tax_rates", CATEGORY_INVENTORY, "/tax_rates"),
    CollectionSpec("tags", CATEGORY_INVENTORY, "/tags"),
    CollectionSpec("order_types", CATEGORY_INVENTORY, "/order_types"),
    CollectionSpec(
        "orders",
        CATEGORY_ORDERS,
        "/orders",
        expand="lineItems,payments,discounts,customer",
        notes="Expanded nested collections (lineItems/payments/discounts) may be truncated; "
        "see orders_line_item_completeness_sample.json for a bounded completeness check.",
    ),
    CollectionSpec(
        "payments",
        CATEGORY_PAYMENTS,
        "/payments",
        expand="tender",
        notes="First-class payments export; primary source investigated for tip-related fields.",
    ),
]


@dataclass
class ManifestEntry:
    name: str
    category: str
    path: str
    http_success: bool
    http_status_last: int | None = None
    record_count: int | None = None
    pages_fetched: int = 0
    output_file: str | None = None
    error: str | None = None
    truncated_by_safety_guard: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "path": self.path,
            "http_success": self.http_success,
            "http_status_last": self.http_status_last,
            "record_count": self.record_count,
            "pages_fetched": self.pages_fetched,
            "output_file": self.output_file,
            "error": self.error,
            "truncated_by_safety_guard": self.truncated_by_safety_guard,
            "notes": self.notes,
        }


def fetch_merchant(client: CloverClient, run_dir: Path) -> ManifestEntry:
    path = f"/v3/merchants/{client.merchant_id}"
    result = client.get(path)
    if not result.ok:
        return ManifestEntry(
            name="merchant",
            category=CATEGORY_MERCHANT,
            path=path,
            http_success=False,
            http_status_last=result.status_code,
            error=result.error,
        )
    raw_store.save_json(run_dir, "merchant.json", result.data)
    return ManifestEntry(
        name="merchant",
        category=CATEGORY_MERCHANT,
        path=path,
        http_success=True,
        http_status_last=result.status_code,
        record_count=1,
        pages_fetched=1,
        output_file="merchant.json",
    )


def export_collection(client: CloverClient, run_dir: Path, spec: CollectionSpec) -> ManifestEntry:
    path = f"/v3/merchants/{client.merchant_id}{spec.path_suffix}"
    extra_params = {"expand": spec.expand} if spec.expand else None

    result = paginate(client, path, extra_params=extra_params, page_size=DEFAULT_PAGE_SIZE)

    if not result.ok and not result.elements:
        return ManifestEntry(
            name=spec.name,
            category=spec.category,
            path=path,
            http_success=False,
            http_status_last=result.error_status_code,
            pages_fetched=result.pages_fetched,
            error=result.error,
            notes=spec.notes,
        )

    output_file = f"{spec.name}.json"
    raw_store.save_json(run_dir, output_file, result.elements)

    return ManifestEntry(
        name=spec.name,
        category=spec.category,
        path=path,
        http_success=result.ok,
        http_status_last=None if result.ok else result.error_status_code,
        record_count=len(result.elements),
        pages_fetched=result.pages_fetched,
        output_file=output_file,
        error=result.error,
        truncated_by_safety_guard=result.truncated_by_safety_guard,
        notes=spec.notes,
    )


def sample_order_line_item_completeness(
    client: CloverClient, orders: list[dict[str, Any]], sample_size: int = ORDER_LINE_ITEM_SAMPLE_SIZE
) -> list[dict[str, Any]]:
    """For a bounded sample of orders, compare the `expand=lineItems` count
    against the order's own dedicated line_items endpoint, to check whether
    the expanded nested array was truncated."""
    sample = []
    for order in orders[:sample_size]:
        order_id = order.get("id")
        if not order_id:
            continue
        expanded_line_items = order.get("lineItems", {})
        expanded_elements = (
            expanded_line_items.get("elements", []) if isinstance(expanded_line_items, dict) else []
        )
        direct_path = f"/v3/merchants/{client.merchant_id}/orders/{order_id}/line_items"
        direct_result = client.get(direct_path)
        if not direct_result.ok:
            sample.append(
                {
                    "orderId": order_id,
                    "expanded_line_item_count": len(expanded_elements),
                    "direct_fetch_error": direct_result.error,
                }
            )
            continue
        direct_elements = (
            direct_result.data.get("elements", []) if isinstance(direct_result.data, dict) else []
        )
        sample.append(
            {
                "orderId": order_id,
                "expanded_line_item_count": len(expanded_elements),
                "direct_line_item_count": len(direct_elements),
                "counts_match": len(expanded_elements) == len(direct_elements),
            }
        )
    return sample


@dataclass
class ExportRun:
    run_dir: Path
    manifest: dict[str, Any]


def run_full_export(client: CloverClient) -> ExportRun:
    run_dir = raw_store.new_run_dir()
    start_time = datetime.now(timezone.utc).isoformat()

    entries: list[ManifestEntry] = []

    merchant_entry = fetch_merchant(client, run_dir)
    entries.append(merchant_entry)

    if not merchant_entry.http_success:
        # Authentication/authorization failure on the base identity call:
        # do not attempt further collections.
        completion_time = datetime.now(timezone.utc).isoformat()
        manifest = _build_manifest(client, start_time, completion_time, entries, orders_sample=None)
        raw_store.save_manifest(run_dir, manifest)
        return ExportRun(run_dir=run_dir, manifest=manifest)

    orders_elements: list[dict[str, Any]] | None = None
    for spec in COLLECTIONS:
        entry = export_collection(client, run_dir, spec)
        entries.append(entry)
        if spec.name == "orders" and entry.http_success:
            orders_path = run_dir / "orders.json"
            if orders_path.exists():
                orders_elements = json.loads(orders_path.read_text(encoding="utf-8"))

    orders_sample = None
    if orders_elements:
        orders_sample = sample_order_line_item_completeness(client, orders_elements)
        if orders_sample:
            raw_store.save_json(run_dir, "orders_line_item_completeness_sample.json", orders_sample)

    completion_time = datetime.now(timezone.utc).isoformat()
    manifest = _build_manifest(client, start_time, completion_time, entries, orders_sample)
    raw_store.save_manifest(run_dir, manifest)
    return ExportRun(run_dir=run_dir, manifest=manifest)


def _build_manifest(
    client: CloverClient,
    start_time: str,
    completion_time: str,
    entries: list[ManifestEntry],
    orders_sample: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    return {
        "export_start_time": start_time,
        "export_completion_time": completion_time,
        "environment": "production",
        "base_url": client.base_url,
        "merchant_id": client.merchant_id,
        "collections": [e.to_dict() for e in entries],
        "orders_line_item_completeness_sample_size": len(orders_sample) if orders_sample else 0,
        "notes": [
            "Read-only export. Only GET requests were issued.",
            "No tip calculation was performed.",
            "Nested expanded collections may be independently truncated from their parent page; "
            "see each collection's 'notes' field.",
        ],
    }
