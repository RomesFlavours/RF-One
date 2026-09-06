"""CLOVER_HISTORICAL_BACKFILL_EXTRACTOR_V1 / CLOVER_LIVE_SYNC_SCOPE_
REDUCTION_001 — the full menu/catalog and Order-detail coverage that
`acquisition.import_clover_period()`'s own base logic never fetches on its
own, per its module docstring: "Deliberately NOT ingested here (left to
ingest_clover.py's own full pipeline): OrderItem/menu/catalog detail,
per-item tax, discounts, source roles."

History: originally Historical-Backfill-only. CLOVER_LIVE_SYNC_EXTRACTOR_V1
briefly widened Live Sync to call the SAME full-detail functions too.
CLOVER_LIVE_SYNC_SCOPE_REDUCTION_001 reverted that: Live Sync no longer
refreshes catalog/reference data continuously (Items, Categories, Modifier
Groups/Modifiers, Tax Rates, Discount Definitions, Order Types, Tenders,
Devices, Source Roles) — only Historical Backfill does, via `fetch_full_
catalog()`/`ingest_employee_source_roles()`/`ingest_order_detail()` below,
gated `mode == MODE_BACKFILL` in `acquisition.py`. Live Sync keeps its own,
separate, smaller function — `ingest_order_item_and_modifier_detail()` —
covering only the two entities that remained in its retained-entity list
(OrderItem, OrderItemModifier), resolving `item_id`/`modifier_id` against
whatever is already canonical rather than a live-refreshed catalog map.
Both functions reuse the exact same `mapping.py` pure functions and the
exact same dedicated `line_items?expand=modifications` endpoint — one
mapping architecture, two call shapes for two different refresh needs.

Every mapping decision here reuses the exact same pure `mapping.py`
functions, the exact same `ingest.upsert()` idempotent upsert-by-source-
identity helper, and the exact same `ingest.CatalogMaps` shape the older,
on-disk-bundle-driven `ingest.py` bulk pipeline already uses and has
already proven correct — this module only supplies a LIVE (network-fetched)
source for the same data `ingest.py` reads from a locally cached bundle.
No second mapping/ingestion architecture is introduced.

Endpoints used by the Historical-Backfill-only functions (all read-only
`client.get()`/`paginate()`, matching the exact same paths `ingest_clover.
py`'s pipeline and `enrichment.py`'s own per-order/per-item enrichment
calls already establish as correct):

- `/categories`, `/modifier_groups?expand=modifiers`, `/discounts`,
  `/tax_rates`, `/order_types`, `/items?expand=categories,modifierGroups`,
  `/roles`, `/employees?expand=role` — catalog/reference data, fetched in
  full once per Historical Backfill run (not windowed by date — these are
  configuration, not transactional history). Live Sync never calls these.
- `/orders/{id}/line_items?expand=modifications` — the SAME dedicated
  endpoint `enrichment.py`'s `_fetch_and_cache_line_items` already uses to
  obtain selected Modifiers (confirmed unavailable on the cheaper Order-
  nested `lineItems` shape, TASK_CLOVER_003) — fetched live per Order,
  by BOTH `ingest_order_detail()` (Backfill) and `ingest_order_item_and_
  modifier_detail()` (Live Sync), not cached to disk.
- `/items/{id}?expand=taxRates` — the per-item tax-rate override lookup
  `enrichment.py`'s `_fetch_and_cache_item_tax_rate` already establishes
  (an empty `taxRates` list means 0%, never "fall back to default" —
  TASK_CLOVER_002/003), fetched live and memoized per run via
  `tax_override_cache`. Backfill-only — Live Sync computes no Order Item
  Tax at all (it depends on the Item/TaxRate catalog Live Sync no longer
  refreshes).

`Order.order_type_id` resolution is deliberately NOT added here — the
OrderType catalog itself IS ingested (this task's required entity list),
but wiring it onto `Order.order_type_id` would mean changing `acquisition.
_ingest_order()`; that remains the pre-existing, separately-scoped gap it
already was (`acquisition.py`'s own comment: "not resolved here — out of
scope for this module"), unchanged by this task.

`OrderItemDiscount` (Order-Item-level applied discounts) is deliberately
NOT populated here either: no mapping function for it exists anywhere in
this codebase, and CLOVER_INGESTION.md §12 / CANONICAL_OPERATIONAL_DB_
GAP_REVIEW_001 both confirm no such evidence has ever been observed in this
merchant's real Clover data — fabricating a mapping with nothing to
validate it against would be exactly the kind of speculative field this
task instructs against.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from .... import models as m
from . import mapping, parser
from .ingest import CatalogMaps, _modifier_ids_in_group, upsert


class _PaginatingClient(Protocol):
    merchant_id: str

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any: ...


MirrorFn = Callable[..., None]


def _paginate(client: _PaginatingClient, path: str, *, expand: str | None = None) -> list[dict[str, Any]]:
    """Thin wrapper around the same `clover_explorer.pagination.paginate`
    primitive `acquisition.py` already imports — imported lazily here to
    reuse the exact same sys.path bootstrap `acquisition.py` performs,
    without duplicating it a second time in this file."""
    from .acquisition import paginate  # local import avoids a circular import at module load time

    result = paginate(client, path, extra_params={"expand": expand} if expand else None)
    return result.elements if result.ok else []


def fetch_full_catalog(
    client: _PaginatingClient, session: Session, *, location_id: int, source_system_id: int,
    ingestion_run_id: int, retrieved_at: datetime, mirror_source_record: MirrorFn,
) -> CatalogMaps:
    """Historical Backfill only. Fetches and upserts every catalog/reference
    entity Live Sync never touches: Category, ModifierGroup + Modifier,
    DiscountDefinition, TaxRate, Item (+ its Category/Modifier
    availability), OrderType, SourceRole. Returns the populated
    `CatalogMaps` — the caller (`acquisition.import_clover_period`) fills in
    `employee_by_source_id`/`tender_by_source_id`/`device_by_source_id`
    from the maps it already built via `_fetch_reference_catalogs`, so
    those three are never fetched twice."""
    catalog = CatalogMaps()
    merchant_id = client.merchant_id

    for raw in _paginate(client, f"/v3/merchants/{merchant_id}/categories"):
        values = mapping.map_category(raw)
        source_id = values.pop("source_category_id")
        obj = upsert(
            session, m.Category, {"source_system_id": source_system_id, "source_category_id": source_id},
            {**values, "location_id": location_id},
        )
        session.flush()
        catalog.category_by_source_id[source_id] = obj.id
        mirror_source_record(
            session, ingestion_run_id=ingestion_run_id, source_system_id=source_system_id,
            entity_type="category", source_id=source_id, retrieved_at=retrieved_at, raw=raw,
        )

    for group_raw in _paginate(client, f"/v3/merchants/{merchant_id}/modifier_groups", expand="modifiers"):
        group_values = mapping.map_modifier_group(group_raw)
        group_source_id = group_values.pop("source_modifier_group_id")
        group = upsert(
            session, m.ModifierGroup, {"source_system_id": source_system_id, "source_modifier_group_id": group_source_id},
            {**group_values, "location_id": location_id},
        )
        session.flush()
        catalog.modifier_group_by_source_id[group_source_id] = group.id
        mirror_source_record(
            session, ingestion_run_id=ingestion_run_id, source_system_id=source_system_id,
            entity_type="modifier_group", source_id=group_source_id, retrieved_at=retrieved_at, raw=group_raw,
        )

        for modifier_raw in (group_raw.get("modifiers") or {}).get("elements", []):
            mod_values = mapping.map_modifier(modifier_raw)
            mod_source_id = mod_values.pop("source_modifier_id")
            modifier = upsert(
                session, m.Modifier, {"source_system_id": source_system_id, "source_modifier_id": mod_source_id},
                {**mod_values, "location_id": location_id, "modifier_group_id": group.id},
            )
            session.flush()
            catalog.modifier_by_source_id[mod_source_id] = modifier.id
            mirror_source_record(
                session, ingestion_run_id=ingestion_run_id, source_system_id=source_system_id,
                entity_type="modifier", source_id=mod_source_id, retrieved_at=retrieved_at, raw=modifier_raw,
            )

    for raw in _paginate(client, f"/v3/merchants/{merchant_id}/discounts"):
        values = mapping.map_discount_definition(raw)
        source_id = values.pop("source_discount_id")
        obj = upsert(
            session, m.DiscountDefinition, {"source_system_id": source_system_id, "source_discount_id": source_id},
            {**values, "location_id": location_id},
        )
        session.flush()
        catalog.discount_definition_by_source_id[source_id] = obj.id
        mirror_source_record(
            session, ingestion_run_id=ingestion_run_id, source_system_id=source_system_id,
            entity_type="discount_definition", source_id=source_id, retrieved_at=retrieved_at, raw=raw,
        )

    tax_rates_raw = _paginate(client, f"/v3/merchants/{merchant_id}/tax_rates")
    for raw in tax_rates_raw:
        values = mapping.map_tax_rate(raw)
        source_id = values.pop("source_tax_rate_id")
        obj = upsert(
            session, m.TaxRate, {"source_system_id": source_system_id, "source_tax_rate_id": source_id},
            {**values, "location_id": location_id},
        )
        session.flush()
        catalog.tax_rate_by_source_id[source_id] = obj.id
        mirror_source_record(
            session, ingestion_run_id=ingestion_run_id, source_system_id=source_system_id,
            entity_type="tax_rate", source_id=source_id, retrieved_at=retrieved_at, raw=raw,
        )
    for raw in tax_rates_raw:
        if raw.get("isDefault"):
            catalog.default_tax_rate_value = parser.canonical_tax_rate(raw.get("rate"))
            catalog.default_tax_rate_id = catalog.tax_rate_by_source_id.get(raw.get("id"))
            break

    for raw in _paginate(client, f"/v3/merchants/{merchant_id}/order_types"):
        values = mapping.map_order_type(raw)
        source_id = values.pop("source_order_type_id")
        obj = upsert(
            session, m.OrderType, {"source_system_id": source_system_id, "source_order_type_id": source_id},
            {**values, "location_id": location_id},
        )
        session.flush()
        catalog.order_type_by_source_id[source_id] = obj.id
        mirror_source_record(
            session, ingestion_run_id=ingestion_run_id, source_system_id=source_system_id,
            entity_type="order_type", source_id=source_id, retrieved_at=retrieved_at, raw=raw,
        )

    for raw in _paginate(client, f"/v3/merchants/{merchant_id}/items", expand="categories,modifierGroups"):
        values = mapping.map_item(raw)
        source_id = values.pop("source_item_id")
        obj = upsert(
            session, m.Item, {"source_system_id": source_system_id, "source_item_id": source_id},
            {**values, "location_id": location_id},
        )
        session.flush()
        catalog.item_by_source_id[source_id] = obj.id
        mirror_source_record(
            session, ingestion_run_id=ingestion_run_id, source_system_id=source_system_id,
            entity_type="item", source_id=source_id, retrieved_at=retrieved_at, raw=raw,
        )

        for cat_ref in (raw.get("categories") or {}).get("elements", []):
            category_id = catalog.category_by_source_id.get(cat_ref.get("id"))
            if category_id is None:
                continue
            existing = session.scalars(
                select(m.ItemCategory).filter_by(item_id=obj.id, category_id=category_id)
            ).first()
            if existing is None:
                session.add(m.ItemCategory(item_id=obj.id, category_id=category_id))

        for mg_ref in (raw.get("modifierGroups") or {}).get("elements", []):
            for modifier_source_id in _modifier_ids_in_group(mg_ref):
                modifier_id = catalog.modifier_by_source_id.get(modifier_source_id)
                if modifier_id is None:
                    continue
                existing = session.scalars(
                    select(m.ItemModifier).filter_by(item_id=obj.id, modifier_id=modifier_id)
                ).first()
                if existing is None:
                    session.add(m.ItemModifier(item_id=obj.id, modifier_id=modifier_id))

        if raw.get("defaultTaxRates") is False:
            catalog.item_uses_override_tax_rate.add(source_id)

    for raw in _paginate(client, f"/v3/merchants/{merchant_id}/roles"):
        values = mapping.map_source_role(raw)
        source_id = values.pop("source_role_id")
        obj = upsert(
            session, m.SourceRole, {"source_system_id": source_system_id, "source_role_id": source_id},
            {**values, "location_id": location_id},
        )
        session.flush()
        catalog.source_role_by_source_id[source_id] = obj.id
        mirror_source_record(
            session, ingestion_run_id=ingestion_run_id, source_system_id=source_system_id,
            entity_type="source_role", source_id=source_id, retrieved_at=retrieved_at, raw=raw,
        )

    session.flush()
    return catalog


def ingest_employee_source_roles(
    session: Session, client: _PaginatingClient, *, source_system_id: int,
    employee_by_source_id: dict[str, int], catalog: CatalogMaps, retrieved_at: datetime,
) -> None:
    """Employee <-> named source Role membership, via `/employees?expand=
    role` — a CURRENT-STATE snapshot only (no historical log exists), so
    `observed_at` is simply refreshed to this run's `retrieved_at` on an
    already-existing membership row rather than creating a duplicate."""
    for raw in _paginate(client, f"/v3/merchants/{client.merchant_id}/employees", expand="role"):
        employee_source_id = raw.get("id")
        employee_id = employee_by_source_id.get(employee_source_id)
        if employee_id is None:
            continue
        for role_ref in (raw.get("roles") or {}).get("elements", []):
            role_source_id = role_ref.get("id")
            source_role_id = catalog.source_role_by_source_id.get(role_source_id)
            if source_role_id is None:
                continue
            existing = session.scalars(
                select(m.EmployeeSourceRole).filter_by(employee_id=employee_id, source_role_id=source_role_id)
            ).first()
            if existing is not None:
                existing.observed_at = retrieved_at
            else:
                session.add(
                    m.EmployeeSourceRole(
                        employee_id=employee_id, source_role_id=source_role_id,
                        source_system_id=source_system_id, observed_at=retrieved_at,
                    )
                )
    session.flush()


def _resolve_item_override_tax_rate(
    client: _PaginatingClient, item_source_id: str, tax_override_cache: dict[str, float],
) -> float:
    """The SAME per-item override lookup `enrichment.py`'s
    `_fetch_and_cache_item_tax_rate` already establishes as correct — an
    empty `taxRates` list means 0%, never "fetch failed, fall back to
    default" (TASK_CLOVER_002/003). Memoized in `tax_override_cache` (one
    dict per Historical Backfill run) so the same Item referenced by many
    Order Items across many Orders in the window is only ever fetched once."""
    if item_source_id in tax_override_cache:
        return tax_override_cache[item_source_id]
    result = client.get(
        f"/v3/merchants/{client.merchant_id}/items/{item_source_id}", params={"expand": "taxRates"},
    )
    rate = 0.0
    if getattr(result, "ok", False):
        rates = (result.data.get("taxRates") or {}).get("elements", [])
        rate = rates[0]["rate"] / 10_000_000 if rates else 0.0
    tax_override_cache[item_source_id] = rate
    return rate


def _ingest_order_item_tax(
    session: Session, client: _PaginatingClient, order_item: m.OrderItem, item_source_id: str | None,
    catalog: CatalogMaps, source_system_id: int, tax_override_cache: dict[str, float],
) -> None:
    """Mirrors `ingest.py`'s `_ingest_order_item_tax` decision tree exactly,
    swapping only its disk-cache-dependent override lookup
    (`reader.load_item_tax_rate`) for a live, memoized network fetch —
    everything else (skip rule for fee/non-revenue lines, the "empty means
    0%" rule, the amount formula) is unchanged."""
    if order_item.is_order_fee or not order_item.is_revenue:
        return
    if item_source_id is None:
        return
    item_id = catalog.item_by_source_id.get(item_source_id)
    if item_id is None:
        return

    used_override = item_source_id in catalog.item_uses_override_tax_rate
    if used_override:
        rate_decimal: float | None = _resolve_item_override_tax_rate(client, item_source_id, tax_override_cache)
    else:
        rate_decimal = catalog.default_tax_rate_value
    if rate_decimal is None:
        return

    tax_rate_id = None if used_override else catalog.default_tax_rate_id
    amount = None
    if order_item.historical_unit_price is not None:
        amount = round(order_item.historical_unit_price * rate_decimal)

    existing = session.scalars(select(m.OrderItemTax).filter_by(order_item_id=order_item.id)).first()
    values = {
        "tax_rate_id": tax_rate_id, "amount": amount, "rate_applied": Decimal(str(rate_decimal)),
        "source_system_id": source_system_id, "source_tax_reference": item_source_id,
    }
    if existing is not None:
        for key, value in values.items():
            setattr(existing, key, value)
    else:
        session.add(m.OrderItemTax(order_item_id=order_item.id, **values))


def ingest_order_detail(
    session: Session, client: _PaginatingClient, order_raw: dict[str, Any], order: m.Order, *,
    source_system_id: int, catalog: CatalogMaps, ingestion_run_id: int, retrieved_at: datetime,
    mirror_source_record: MirrorFn, tax_override_cache: dict[str, float],
) -> None:
    """Historical Backfill only, called once per Order after `acquisition.
    _ingest_order()`/`_ingest_fee_line_items()` have already run (both
    unchanged, both still shared with Live Sync). Adds: full OrderItem
    coverage (not fee lines only), OrderItemModifier, OrderItemTax, and
    Order-level OrderDiscount.

    Uses the dedicated `line_items?expand=modifications` endpoint as the
    authoritative Order Item source (falling back to the Order's own
    cheaper nested `lineItems`, without modifications, only if that
    dedicated fetch fails) — this never conflicts with `_ingest_fee_line_
    items`' own, separate, unchanged read of `order_raw`'s nested
    `lineItems`: that call writes `OrderFee` rows; this one writes
    `OrderItem`/`OrderItemModifier`/`OrderItemTax` rows. Both are
    idempotent upserts against the same underlying Clover fact, so no
    ordering dependency exists between them."""
    order_source_id = order_raw["id"]
    li_elements = _paginate(
        client, f"/v3/merchants/{client.merchant_id}/orders/{order_source_id}/line_items", expand="modifications",
    )
    line_items = li_elements if li_elements else (order_raw.get("lineItems") or {}).get("elements", [])

    for li_raw in line_items:
        oi_values = mapping.map_order_item(li_raw)
        source_line_item_id = oi_values.pop("source_line_item_id")
        item_source_id = oi_values.pop("item_source_id")
        item_id = catalog.item_by_source_id.get(item_source_id)

        order_item = upsert(
            session, m.OrderItem, {"source_system_id": source_system_id, "source_line_item_id": source_line_item_id},
            {**oi_values, "order_id": order.id, "item_id": item_id},
        )
        session.flush()
        mirror_source_record(
            session, ingestion_run_id=ingestion_run_id, source_system_id=source_system_id,
            entity_type="order_line_item", source_id=source_line_item_id, retrieved_at=retrieved_at, raw=li_raw,
        )

        for mod_raw in (li_raw.get("modifications") or {}).get("elements", []):
            oim_values = mapping.map_order_item_modifier(mod_raw)
            modifier_source_id = oim_values.pop("modifier_source_id")
            modifier_id = catalog.modifier_by_source_id.get(modifier_source_id)
            source_modification_id = oim_values.get("source_modification_id")

            existing = None
            if source_modification_id:
                existing = session.scalars(
                    select(m.OrderItemModifier).filter_by(
                        order_item_id=order_item.id, source_modification_id=source_modification_id,
                    )
                ).first()
            if existing is not None:
                for key, value in oim_values.items():
                    setattr(existing, key, value)
                existing.modifier_id = modifier_id
            else:
                session.add(
                    m.OrderItemModifier(
                        order_item_id=order_item.id, modifier_id=modifier_id,
                        source_system_id=source_system_id, **oim_values,
                    )
                )

        _ingest_order_item_tax(
            session, client, order_item, item_source_id, catalog, source_system_id, tax_override_cache,
        )

    for discount_el in (order_raw.get("discounts") or {}).get("elements", []):
        classified = parser.classify_applied_discount(discount_el)
        source_discount_id = classified["source_discount_id"]
        discount_definition_id = catalog.discount_definition_by_source_id.get(
            classified["discount_definition_source_id"]
        )
        values = {
            "discount_definition_id": discount_definition_id,
            "name_raw": classified["name_raw"],
            "percentage": Decimal(str(classified["percentage"])) if classified["percentage"] is not None else None,
            "amount": classified["amount"],
            "raw_shape_json": discount_el,
        }
        existing = None
        if source_discount_id:
            existing = session.scalars(
                select(m.OrderDiscount).filter_by(order_id=order.id, source_discount_id=source_discount_id)
            ).first()
        if existing is not None:
            for key, value in values.items():
                setattr(existing, key, value)
        else:
            session.add(
                m.OrderDiscount(
                    order_id=order.id, source_system_id=source_system_id,
                    source_discount_id=source_discount_id, **values,
                )
            )

    session.flush()


def ingest_order_item_and_modifier_detail(
    session: Session, client: _PaginatingClient, order_raw: dict[str, Any], order: m.Order, *,
    source_system_id: int, ingestion_run_id: int, retrieved_at: datetime, mirror_source_record: MirrorFn,
) -> None:
    """CLOVER_LIVE_SYNC_SCOPE_REDUCTION_001 — Live Sync's counterpart to
    `ingest_order_detail()`, covering only the two entities Live Sync's
    retained-entity list keeps: OrderItem and OrderItemModifier. Reuses the
    exact same pure `mapping.map_order_item()`/`map_order_item_modifier()`
    functions and the same dedicated `line_items?expand=modifications`
    endpoint `ingest_order_detail()` uses — no second mapping architecture.

    The one real difference: `item_id`/`modifier_id` are resolved with a
    direct per-row database lookup (`Item`/`Modifier` by `source_system_id`
    + their own source id) instead of an in-memory `CatalogMaps` built from
    a live catalog fetch — Live Sync no longer refreshes the Item/Modifier
    catalog continuously (that catalog fetch is Historical-Backfill-only
    again, see `acquisition.py`), so there is no in-memory map to consult;
    reading the already-canonical row is the minimal way to keep this FK
    resolving correctly for anything Historical Backfill has already
    discovered, without doing a live catalog refresh. A source_id neither
    catalog has ever seen simply resolves to `None`, the same graceful-
    degradation shape already used everywhere else in this schema for an
    unresolved reference.

    No OrderItemTax, no OrderDiscount here — both depend on catalogs
    (TaxRate/Item's `defaultTaxRates`, DiscountDefinition) Live Sync no
    longer refreshes; `ingest_order_detail()` (Historical Backfill only)
    remains the only place either is computed."""
    order_source_id = order_raw["id"]
    li_elements = _paginate(
        client, f"/v3/merchants/{client.merchant_id}/orders/{order_source_id}/line_items", expand="modifications",
    )
    line_items = li_elements if li_elements else (order_raw.get("lineItems") or {}).get("elements", [])

    for li_raw in line_items:
        oi_values = mapping.map_order_item(li_raw)
        source_line_item_id = oi_values.pop("source_line_item_id")
        item_source_id = oi_values.pop("item_source_id")
        item_id = None
        if item_source_id:
            item = session.scalars(
                select(m.Item).filter_by(source_system_id=source_system_id, source_item_id=item_source_id)
            ).first()
            item_id = item.id if item is not None else None

        order_item = upsert(
            session, m.OrderItem, {"source_system_id": source_system_id, "source_line_item_id": source_line_item_id},
            {**oi_values, "order_id": order.id, "item_id": item_id},
        )
        session.flush()
        mirror_source_record(
            session, ingestion_run_id=ingestion_run_id, source_system_id=source_system_id,
            entity_type="order_line_item", source_id=source_line_item_id, retrieved_at=retrieved_at, raw=li_raw,
        )

        for mod_raw in (li_raw.get("modifications") or {}).get("elements", []):
            oim_values = mapping.map_order_item_modifier(mod_raw)
            modifier_source_id = oim_values.pop("modifier_source_id")
            modifier_id = None
            if modifier_source_id:
                modifier = session.scalars(
                    select(m.Modifier).filter_by(source_system_id=source_system_id, source_modifier_id=modifier_source_id)
                ).first()
                modifier_id = modifier.id if modifier is not None else None
            source_modification_id = oim_values.get("source_modification_id")

            existing = None
            if source_modification_id:
                existing = session.scalars(
                    select(m.OrderItemModifier).filter_by(
                        order_item_id=order_item.id, source_modification_id=source_modification_id,
                    )
                ).first()
            if existing is not None:
                for key, value in oim_values.items():
                    setattr(existing, key, value)
                existing.modifier_id = modifier_id
            else:
                session.add(
                    m.OrderItemModifier(
                        order_item_id=order_item.id, modifier_id=modifier_id,
                        source_system_id=source_system_id, **oim_values,
                    )
                )

    session.flush()
