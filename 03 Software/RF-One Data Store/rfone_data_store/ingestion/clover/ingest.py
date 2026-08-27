"""Orchestrates loading a `CloverSourceBundle` into a canonical database
session, using upsert-by-source-identity semantics throughout (task §9,
idempotency) and creating `SourceRecord`/`IngestionRun` provenance (task
§38-39).

This module never talks to Clover directly (no network) — it only maps and
writes what `reader.py` (disk) and `enrichment.py` (already-cached, refreshed
by a prior run) have made available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from ... import models as m
from ..common import payload_hash, utc_now
from . import mapping, parser, reader

T = TypeVar("T")


def upsert(session: Session, model: type[T], unique_filter: dict[str, Any], values: dict[str, Any]) -> T:
    """Idempotent insert-or-update keyed by `unique_filter` (expected to
    match one of the schema's `UniqueConstraint`s — task §9). Existing rows
    are updated in place rather than duplicated."""
    stmt = select(model).filter_by(**unique_filter)
    existing = session.scalars(stmt).first()
    if existing is not None:
        for key, value in values.items():
            setattr(existing, key, value)
        return existing
    obj = model(**unique_filter, **values)
    session.add(obj)
    return obj


@dataclass
class IngestionStats:
    counts: dict[str, int] = field(default_factory=dict)
    unresolved_employee_refs: int = 0
    unresolved_item_refs: int = 0
    unresolved_modifier_refs: int = 0
    unresolved_device_refs: int = 0
    unresolved_tender_refs: int = 0
    unresolved_order_type_refs: int = 0
    unresolved_discount_definition_refs: int = 0
    unresolved_tax_rate_refs: int = 0
    orders_missing_dedicated_line_items: list[str] = field(default_factory=list)

    def bump(self, key: str, n: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + n


def _add_source_record(
    session: Session,
    *,
    ingestion_run_id: int,
    source_system_id: int,
    entity_type: str,
    source_id: str,
    retrieved_at: datetime,
    raw_path: str | None,
    payload: Any | None = None,
) -> None:
    session.add(
        m.SourceRecord(
            ingestion_run_id=ingestion_run_id,
            source_system_id=source_system_id,
            entity_type=entity_type,
            source_id=source_id,
            retrieved_at=retrieved_at,
            payload_hash=payload_hash(payload) if payload is not None else None,
            raw_path=raw_path,
            raw_json=None,  # avoid duplicating large raw payloads (task §38); raw_path is enough
        )
    )


@dataclass
class CatalogMaps:
    order_type_by_source_id: dict[str, int] = field(default_factory=dict)
    category_by_source_id: dict[str, int] = field(default_factory=dict)
    modifier_group_by_source_id: dict[str, int] = field(default_factory=dict)
    modifier_by_source_id: dict[str, int] = field(default_factory=dict)
    item_by_source_id: dict[str, int] = field(default_factory=dict)
    discount_definition_by_source_id: dict[str, int] = field(default_factory=dict)
    tax_rate_by_source_id: dict[str, int] = field(default_factory=dict)
    tender_by_source_id: dict[str, int] = field(default_factory=dict)
    device_by_source_id: dict[str, int] = field(default_factory=dict)
    employee_by_source_id: dict[str, int] = field(default_factory=dict)
    source_role_by_source_id: dict[str, int] = field(default_factory=dict)

    # Populated by `resolve_tax_defaults()` once tax_rates and items are
    # ingested — used only by `_ingest_order_item_tax`.
    default_tax_rate_id: int | None = None
    default_tax_rate_value: float | None = None
    item_uses_override_tax_rate: set[str] = field(default_factory=set)


def resolve_tax_defaults(bundle: reader.CloverSourceBundle, catalog: CatalogMaps) -> None:
    from . import parser

    for raw in bundle.tax_rates:
        if raw.get("isDefault"):
            catalog.default_tax_rate_value = parser.canonical_tax_rate(raw.get("rate"))
            catalog.default_tax_rate_id = catalog.tax_rate_by_source_id.get(raw.get("id"))
            break

    catalog.item_uses_override_tax_rate = {
        i["id"] for i in bundle.items_raw if i.get("defaultTaxRates") is False and i.get("id")
    }


def ingest_merchant_and_location(
    session: Session,
    bundle: reader.CloverSourceBundle,
    source_system_id: int,
    ingestion_run_id: int,
    retrieved_at: datetime,
) -> tuple[int, int]:
    merchant_values = mapping.map_merchant(bundle.merchant)
    merchant_source_id = merchant_values.pop("source_merchant_id")
    merchant = upsert(
        session,
        m.Merchant,
        {"source_system_id": source_system_id, "source_merchant_id": merchant_source_id},
        merchant_values,
    )
    session.flush()

    observed_currency = _dominant_order_currency(bundle.orders)
    location_values = mapping.map_location(bundle.merchant, observed_currency)
    location_source_id = location_values.pop("source_location_id")
    location = upsert(
        session,
        m.Location,
        {"source_system_id": source_system_id, "source_location_id": location_source_id},
        {**location_values, "merchant_id": merchant.id},
    )
    session.flush()

    _add_source_record(
        session,
        ingestion_run_id=ingestion_run_id,
        source_system_id=source_system_id,
        entity_type="merchant",
        source_id=merchant_source_id,
        retrieved_at=retrieved_at,
        raw_path=str(bundle.run_dir / "merchant.json"),
    )

    return merchant.id, location.id


def _dominant_order_currency(orders: list[dict[str, Any]]) -> str | None:
    if not orders:
        return None
    counts: dict[str, int] = {}
    for o in orders:
        c = o.get("currency")
        if c:
            counts[c] = counts.get(c, 0) + 1
    if not counts:
        return None
    return max(counts, key=lambda k: counts[k])


def ingest_devices(
    session: Session,
    bundle: reader.CloverSourceBundle,
    location_id: int,
    source_system_id: int,
    ingestion_run_id: int,
    retrieved_at: datetime,
) -> dict[str, int]:
    device_map: dict[str, int] = {}
    for device_raw in bundle.devices or []:
        values = mapping.map_device(device_raw)
        source_id = values.pop("source_device_id")
        device = upsert(
            session,
            m.Device,
            {"source_system_id": source_system_id, "source_device_id": source_id},
            {**values, "location_id": location_id},
        )
        session.flush()
        device_map[source_id] = device.id
        _add_source_record(
            session,
            ingestion_run_id=ingestion_run_id,
            source_system_id=source_system_id,
            entity_type="device",
            source_id=source_id,
            retrieved_at=retrieved_at,
            raw_path="generated_exports/_api_cache/supplementary/devices.json",
        )
    return device_map


def ingest_order_types(
    session: Session,
    bundle: reader.CloverSourceBundle,
    location_id: int,
    source_system_id: int,
    ingestion_run_id: int,
    retrieved_at: datetime,
) -> dict[str, int]:
    result: dict[str, int] = {}
    for raw in bundle.order_types:
        values = mapping.map_order_type(raw)
        source_id = values.pop("source_order_type_id")
        obj = upsert(
            session,
            m.OrderType,
            {"source_system_id": source_system_id, "source_order_type_id": source_id},
            {**values, "location_id": location_id},
        )
        session.flush()
        result[source_id] = obj.id
        _add_source_record(
            session,
            ingestion_run_id=ingestion_run_id,
            source_system_id=source_system_id,
            entity_type="order_type",
            source_id=source_id,
            retrieved_at=retrieved_at,
            raw_path=str(bundle.run_dir / "order_types.json"),
        )
    return result


def ingest_categories(
    session: Session,
    bundle: reader.CloverSourceBundle,
    location_id: int,
    source_system_id: int,
    ingestion_run_id: int,
    retrieved_at: datetime,
) -> dict[str, int]:
    result: dict[str, int] = {}
    for raw in bundle.categories:
        values = mapping.map_category(raw)
        source_id = values.pop("source_category_id")
        obj = upsert(
            session,
            m.Category,
            {"source_system_id": source_system_id, "source_category_id": source_id},
            {**values, "location_id": location_id},
        )
        session.flush()
        result[source_id] = obj.id
        _add_source_record(
            session,
            ingestion_run_id=ingestion_run_id,
            source_system_id=source_system_id,
            entity_type="category",
            source_id=source_id,
            retrieved_at=retrieved_at,
            raw_path=str(bundle.run_dir / "categories.json"),
        )
    return result


def ingest_modifier_groups_and_modifiers(
    session: Session,
    bundle: reader.CloverSourceBundle,
    location_id: int,
    source_system_id: int,
    ingestion_run_id: int,
    retrieved_at: datetime,
) -> tuple[dict[str, int], dict[str, int]]:
    group_map: dict[str, int] = {}
    modifier_map: dict[str, int] = {}

    for group_raw in bundle.modifier_groups:
        group_values = mapping.map_modifier_group(group_raw)
        group_source_id = group_values.pop("source_modifier_group_id")
        group = upsert(
            session,
            m.ModifierGroup,
            {"source_system_id": source_system_id, "source_modifier_group_id": group_source_id},
            {**group_values, "location_id": location_id},
        )
        session.flush()
        group_map[group_source_id] = group.id
        _add_source_record(
            session,
            ingestion_run_id=ingestion_run_id,
            source_system_id=source_system_id,
            entity_type="modifier_group",
            source_id=group_source_id,
            retrieved_at=retrieved_at,
            raw_path=str(bundle.run_dir / "modifier_groups.json"),
        )

        nested_modifiers = (group_raw.get("modifiers") or {}).get("elements", [])
        for modifier_raw in nested_modifiers:
            mod_values = mapping.map_modifier(modifier_raw)
            mod_source_id = mod_values.pop("source_modifier_id")
            modifier = upsert(
                session,
                m.Modifier,
                {"source_system_id": source_system_id, "source_modifier_id": mod_source_id},
                {**mod_values, "location_id": location_id, "modifier_group_id": group.id},
            )
            session.flush()
            modifier_map[mod_source_id] = modifier.id
            _add_source_record(
                session,
                ingestion_run_id=ingestion_run_id,
                source_system_id=source_system_id,
                entity_type="modifier",
                source_id=mod_source_id,
                retrieved_at=retrieved_at,
                raw_path=str(bundle.run_dir / "modifier_groups.json"),
            )

    return group_map, modifier_map


def ingest_discount_definitions(
    session: Session,
    bundle: reader.CloverSourceBundle,
    location_id: int,
    source_system_id: int,
    ingestion_run_id: int,
    retrieved_at: datetime,
) -> dict[str, int]:
    result: dict[str, int] = {}
    for raw in bundle.discounts:
        values = mapping.map_discount_definition(raw)
        source_id = values.pop("source_discount_id")
        obj = upsert(
            session,
            m.DiscountDefinition,
            {"source_system_id": source_system_id, "source_discount_id": source_id},
            {**values, "location_id": location_id},
        )
        session.flush()
        result[source_id] = obj.id
        _add_source_record(
            session,
            ingestion_run_id=ingestion_run_id,
            source_system_id=source_system_id,
            entity_type="discount_definition",
            source_id=source_id,
            retrieved_at=retrieved_at,
            raw_path=str(bundle.run_dir / "discounts.json"),
        )
    return result


def ingest_tax_rates(
    session: Session,
    bundle: reader.CloverSourceBundle,
    location_id: int,
    source_system_id: int,
    ingestion_run_id: int,
    retrieved_at: datetime,
) -> dict[str, int]:
    result: dict[str, int] = {}
    for raw in bundle.tax_rates:
        values = mapping.map_tax_rate(raw)
        source_id = values.pop("source_tax_rate_id")
        obj = upsert(
            session,
            m.TaxRate,
            {"source_system_id": source_system_id, "source_tax_rate_id": source_id},
            {**values, "location_id": location_id},
        )
        session.flush()
        result[source_id] = obj.id
        _add_source_record(
            session,
            ingestion_run_id=ingestion_run_id,
            source_system_id=source_system_id,
            entity_type="tax_rate",
            source_id=source_id,
            retrieved_at=retrieved_at,
            raw_path=str(bundle.run_dir / "tax_rates.json"),
        )
    return result


def ingest_tenders(
    session: Session,
    bundle: reader.CloverSourceBundle,
    location_id: int,
    source_system_id: int,
    ingestion_run_id: int,
    retrieved_at: datetime,
) -> dict[str, int]:
    """Tenders have no dedicated top-level Clover collection in this
    integration — they are built from the distinct `tender` objects nested
    on Payments (task §22)."""
    result: dict[str, int] = {}
    seen: dict[str, dict[str, Any]] = {}
    for payment_raw in bundle.payments:
        tender_obj = payment_raw.get("tender")
        if isinstance(tender_obj, dict) and tender_obj.get("id"):
            seen[tender_obj["id"]] = tender_obj

    for tender_source_id, tender_obj in seen.items():
        values = mapping.map_tender(tender_obj)
        values.pop("source_tender_id")
        obj = upsert(
            session,
            m.Tender,
            {"source_system_id": source_system_id, "source_tender_id": tender_source_id},
            {**values, "location_id": location_id},
        )
        session.flush()
        result[tender_source_id] = obj.id
        _add_source_record(
            session,
            ingestion_run_id=ingestion_run_id,
            source_system_id=source_system_id,
            entity_type="tender",
            source_id=tender_source_id,
            retrieved_at=retrieved_at,
            raw_path=str(bundle.run_dir / "payments.json"),
        )
    return result


def ingest_items_and_categories(
    session: Session,
    bundle: reader.CloverSourceBundle,
    location_id: int,
    source_system_id: int,
    category_map: dict[str, int],
    modifier_map: dict[str, int],
    ingestion_run_id: int,
    retrieved_at: datetime,
) -> dict[str, int]:
    item_map: dict[str, int] = {}
    for item_raw in bundle.items:
        values = mapping.map_item(item_raw)
        source_id = values.pop("source_item_id")
        item = upsert(
            session,
            m.Item,
            {"source_system_id": source_system_id, "source_item_id": source_id},
            {**values, "location_id": location_id},
        )
        session.flush()
        item_map[source_id] = item.id
        _add_source_record(
            session,
            ingestion_run_id=ingestion_run_id,
            source_system_id=source_system_id,
            entity_type="item",
            source_id=source_id,
            retrieved_at=retrieved_at,
            raw_path=str(bundle.run_dir / "items.json"),
        )

        # Item -> Category (M:N), only available on the enriched source.
        for cat_ref in (item_raw.get("categories") or {}).get("elements", []):
            cat_source_id = cat_ref.get("id")
            category_id = category_map.get(cat_source_id)
            if category_id is None:
                continue
            existing = session.scalars(
                select(m.ItemCategory).filter_by(item_id=item.id, category_id=category_id)
            ).first()
            if existing is None:
                session.add(m.ItemCategory(item_id=item.id, category_id=category_id))

        # Item -> Modifier availability, derived via the Item -> ModifierGroup
        # -> Modifier chain (the enriched source gives Item -> ModifierGroup;
        # ModifierGroup -> Modifier comes from modifier_groups.json's own
        # nested expand). This is a DERIVED (not direct) relationship — see
        # CLOVER_INGESTION.md.
        for mg_ref in (item_raw.get("modifierGroups") or {}).get("elements", []):
            for modifier_source_id in _modifier_ids_in_group(mg_ref):
                modifier_id = modifier_map.get(modifier_source_id)
                if modifier_id is None:
                    continue
                existing = session.scalars(
                    select(m.ItemModifier).filter_by(item_id=item.id, modifier_id=modifier_id)
                ).first()
                if existing is None:
                    session.add(m.ItemModifier(item_id=item.id, modifier_id=modifier_id))

    return item_map


def _modifier_ids_in_group(modifier_group_ref: dict[str, Any]) -> list[str]:
    ids_csv = modifier_group_ref.get("modifierIds")
    if ids_csv:
        return [x for x in ids_csv.split(",") if x]
    nested = (modifier_group_ref.get("modifiers") or {}).get("elements", [])
    return [el["id"] for el in nested if el.get("id")]


def ingest_employees(
    session: Session,
    bundle: reader.CloverSourceBundle,
    location_id: int,
    source_system_id: int,
    ingestion_run_id: int,
    retrieved_at: datetime,
) -> dict[str, int]:
    result: dict[str, int] = {}
    for raw in bundle.employees:
        values = mapping.map_employee(raw)
        source_id = values.pop("source_employee_id")
        obj = upsert(
            session,
            m.Employee,
            {"source_system_id": source_system_id, "source_employee_id": source_id},
            {**values, "location_id": location_id},
        )
        session.flush()
        result[source_id] = obj.id
        _add_source_record(
            session,
            ingestion_run_id=ingestion_run_id,
            source_system_id=source_system_id,
            entity_type="employee",
            source_id=source_id,
            retrieved_at=retrieved_at,
            raw_path=str(bundle.run_dir / "employees.json"),
        )
    return result


def ingest_source_roles(
    session: Session,
    bundle: reader.CloverSourceBundle,
    location_id: int,
    source_system_id: int,
    ingestion_run_id: int,
    retrieved_at: datetime,
) -> dict[str, int]:
    """Clover's named-Role catalog (TASK_CLOVER_004) — e.g. `Server`,
    `Host`, `BOH`, `Employee`, `Team Leader`, `Manager`, `Admin`. Distinct
    from `Employee.system_role` (the systemRole TIER only, unchanged)."""
    result: dict[str, int] = {}
    for raw in bundle.roles:
        values = mapping.map_source_role(raw)
        source_id = values.pop("source_role_id")
        obj = upsert(
            session,
            m.SourceRole,
            {"source_system_id": source_system_id, "source_role_id": source_id},
            {**values, "location_id": location_id},
        )
        session.flush()
        result[source_id] = obj.id
        _add_source_record(
            session,
            ingestion_run_id=ingestion_run_id,
            source_system_id=source_system_id,
            entity_type="source_role",
            source_id=source_id,
            retrieved_at=retrieved_at,
            raw_path=str(bundle.run_dir / "roles.json"),
        )
    return result


def ingest_employee_source_roles(
    session: Session,
    bundle: reader.CloverSourceBundle,
    source_system_id: int,
    employee_map: dict[str, int],
    source_role_map: dict[str, int],
    retrieved_at: datetime,
    stats: IngestionStats,
) -> None:
    """Employee <-> named Role membership (TASK_CLOVER_004), discovered via
    `employees?expand=role` — confirmed to return the SPECIFIC named Role
    (id/name/systemRole), not merely the systemRole tier `bundle.employees`
    already carries. Source is `bundle.employees_expand_role`, which is
    `None` if that supplementary cache was never fetched — in that case this
    is a no-op, never a fabricated membership. Clover's Employee resource
    (and therefore this relationship) is a CURRENT SNAPSHOT ONLY — an
    employee id absent from `bundle.employees_expand_role` (e.g. a
    historical stub, TASK_DATABASE_002 § 7) simply gets no membership row,
    never an invented one."""
    for emp_raw in bundle.employees_expand_role or []:
        employee_source_id = emp_raw.get("id")
        employee_id = employee_map.get(employee_source_id)
        if employee_id is None:
            continue
        for role_ref in (emp_raw.get("roles") or {}).get("elements", []):
            role_source_id = role_ref.get("id")
            source_role_id = source_role_map.get(role_source_id)
            if source_role_id is None:
                stats.bump("employee_source_roles_unresolved_role")
                continue
            existing = session.scalars(
                select(m.EmployeeSourceRole).filter_by(
                    employee_id=employee_id, source_role_id=source_role_id
                )
            ).first()
            if existing is not None:
                existing.observed_at = retrieved_at
            else:
                session.add(
                    m.EmployeeSourceRole(
                        employee_id=employee_id,
                        source_role_id=source_role_id,
                        source_system_id=source_system_id,
                        observed_at=retrieved_at,
                    )
                )
            stats.bump("employee_source_roles")
    session.flush()


def ingest_employee_stub_references(
    session: Session,
    bundle: reader.CloverSourceBundle,
    location_id: int,
    source_system_id: int,
    employee_map: dict[str, int],
    ingestion_run_id: int,
    retrieved_at: datetime,
    stats: IngestionStats,
) -> None:
    """Clover's `/employees` collection is a CURRENT snapshot — it does not
    include employees who have since been removed from the account, even
    though Shifts/Orders/Payments/Refunds referencing them remain in history
    (confirmed empirically this run: 13 employee ids referenced by 667/4,368
    Shifts do not appear in `employees.json`).

    Rather than silently dropping those historical facts (forbidden — task
    §54) or weakening `Shift.employee_id`'s NOT NULL constraint (no evidence
    this task's other findings require it), a minimal stub Employee row is
    created for each such id: only `source_employee_id` is set, every other
    field stays NULL — nothing about the person is fabricated, only their
    bare identity is acknowledged as "referenced by history, profile
    unavailable from the current source"."""
    referenced = parser.referenced_employee_ids(bundle.shifts, bundle.orders, bundle.payments, bundle.refunds)
    missing = sorted(referenced - set(employee_map.keys()))
    for source_id in missing:
        obj = upsert(
            session,
            m.Employee,
            {"source_system_id": source_system_id, "source_employee_id": source_id},
            {
                "display_name": None,
                "custom_id": None,
                "system_role": None,
                "active": None,
                "source_created_at": None,
                "source_modified_at": None,
                "location_id": location_id,
            },
        )
        session.flush()
        employee_map[source_id] = obj.id
        stats.bump("employee_stub_references_created")
        _add_source_record(
            session,
            ingestion_run_id=ingestion_run_id,
            source_system_id=source_system_id,
            entity_type="employee_stub_reference",
            source_id=source_id,
            retrieved_at=retrieved_at,
            raw_path=None,
        )


def ingest_shifts(
    session: Session,
    bundle: reader.CloverSourceBundle,
    source_system_id: int,
    employee_map: dict[str, int],
    ingestion_run_id: int,
    retrieved_at: datetime,
    stats: IngestionStats,
) -> None:
    for raw in bundle.shifts:
        values = mapping.map_shift(raw)
        source_id = values.pop("source_shift_id")
        employee_source_id = values.pop("employee_source_id")
        override_in_source_id = values.pop("override_in_employee_source_id")
        override_out_source_id = values.pop("override_out_employee_source_id")

        employee_id = employee_map.get(employee_source_id)
        if employee_id is None:
            stats.unresolved_employee_refs += 1
            continue  # Shift.employee_id is NOT NULL — cannot ingest an orphaned shift

        upsert(
            session,
            m.Shift,
            {"source_system_id": source_system_id, "source_shift_id": source_id},
            {
                **values,
                "employee_id": employee_id,
                "override_in_employee_id": employee_map.get(override_in_source_id),
                "override_out_employee_id": employee_map.get(override_out_source_id),
            },
        )
        _add_source_record(
            session,
            ingestion_run_id=ingestion_run_id,
            source_system_id=source_system_id,
            entity_type="shift",
            source_id=source_id,
            retrieved_at=retrieved_at,
            raw_path=str(bundle.run_dir / "shifts.json"),
        )
    session.flush()


@dataclass
class OrderIngestResult:
    order_map: dict[str, int] = field(default_factory=dict)


def ingest_orders_and_children(
    session: Session,
    bundle: reader.CloverSourceBundle,
    location_id: int,
    source_system_id: int,
    catalog: CatalogMaps,
    ingestion_run_id: int,
    retrieved_at: datetime,
    stats: IngestionStats,
) -> OrderIngestResult:
    result = OrderIngestResult()

    for order_raw in bundle.orders:
        order_values = mapping.map_order(order_raw)
        order_source_id = order_values.pop("source_order_id")
        employee_source_id = order_values.pop("source_employee_id")
        employee_source_id_for_fk = order_values.pop("employee_source_id")
        order_type_source_id = order_values.pop("order_type_source_id")
        device_source_id = order_values.pop("device_source_id")

        employee_id = catalog.employee_by_source_id.get(employee_source_id_for_fk)
        if employee_source_id_for_fk and employee_id is None:
            stats.unresolved_employee_refs += 1
        order_type_id = catalog.order_type_by_source_id.get(order_type_source_id)
        if order_type_source_id and order_type_id is None:
            stats.unresolved_order_type_refs += 1
        device_id = catalog.device_by_source_id.get(device_source_id)
        if device_source_id and device_id is None:
            stats.unresolved_device_refs += 1

        order = upsert(
            session,
            m.Order,
            {"source_system_id": source_system_id, "source_order_id": order_source_id},
            {
                **order_values,
                "location_id": location_id,
                "table_service_id": None,  # never reconstructed here (task §23, §36)
                "source_employee_id": employee_source_id,
                "employee_id": employee_id,
                "order_type_id": order_type_id,
                "device_id": device_id,
                "device_source_id": device_source_id,
            },
        )
        session.flush()
        result.order_map[order_source_id] = order.id
        stats.bump("orders")

        _add_source_record(
            session,
            ingestion_run_id=ingestion_run_id,
            source_system_id=source_system_id,
            entity_type="order",
            source_id=order_source_id,
            retrieved_at=retrieved_at,
            raw_path=str(bundle.run_dir / "orders.json"),
        )

        _ingest_order_items_for_order(
            session, order_raw, order, source_system_id, catalog, ingestion_run_id, retrieved_at, stats
        )
        _ingest_order_discounts_for_order(session, order_raw, order, source_system_id, catalog, stats)

    session.flush()
    return result


def _ingest_order_items_for_order(
    session: Session,
    order_raw: dict[str, Any],
    order: m.Order,
    source_system_id: int,
    catalog: CatalogMaps,
    ingestion_run_id: int,
    retrieved_at: datetime,
    stats: IngestionStats,
) -> None:
    order_id_str = order_raw["id"]
    dedicated = reader.load_dedicated_line_items(order_id_str)
    if dedicated is not None:
        line_items = dedicated
        source_path = str(reader.dedicated_line_items_cache_path(order_id_str))
        _add_source_record(
            session,
            ingestion_run_id=ingestion_run_id,
            source_system_id=source_system_id,
            entity_type="order_line_items",
            source_id=order_id_str,
            retrieved_at=retrieved_at,
            raw_path=source_path,
        )
    else:
        # Bulk-nested fallback: carries no `modifications` (TASK_CLOVER_003) —
        # OrderItems are still ingested (never silently dropped), but their
        # selected Modifiers cannot be. Recorded explicitly, not hidden.
        line_items = (order_raw.get("lineItems") or {}).get("elements", [])
        stats.orders_missing_dedicated_line_items.append(order_id_str)

    for li_raw in line_items:
        oi_values = mapping.map_order_item(li_raw)
        source_line_item_id = oi_values.pop("source_line_item_id")
        item_source_id = oi_values.pop("item_source_id")
        item_id = catalog.item_by_source_id.get(item_source_id)
        if item_source_id and item_id is None:
            stats.unresolved_item_refs += 1

        order_item = upsert(
            session,
            m.OrderItem,
            {"source_system_id": source_system_id, "source_line_item_id": source_line_item_id},
            {**oi_values, "order_id": order.id, "item_id": item_id},
        )
        session.flush()
        stats.bump("order_items")

        for mod_raw in (li_raw.get("modifications") or {}).get("elements", []):
            oim_values = mapping.map_order_item_modifier(mod_raw)
            modifier_source_id = oim_values.pop("modifier_source_id")
            modifier_id = catalog.modifier_by_source_id.get(modifier_source_id)
            if modifier_source_id and modifier_id is None:
                stats.unresolved_modifier_refs += 1
            source_modification_id = oim_values.get("source_modification_id")
            unique_filter = (
                {"order_item_id": order_item.id, "source_modification_id": source_modification_id}
                if source_modification_id
                else None
            )
            if unique_filter is not None:
                existing = session.scalars(
                    select(m.OrderItemModifier).filter_by(**unique_filter)
                ).first()
            else:
                existing = None
            if existing is not None:
                for k, v in oim_values.items():
                    setattr(existing, k, v)
                existing.modifier_id = modifier_id
            else:
                session.add(
                    m.OrderItemModifier(
                        order_item_id=order_item.id,
                        modifier_id=modifier_id,
                        source_system_id=source_system_id,
                        **oim_values,
                    )
                )
            stats.bump("order_item_modifiers")

        if li_raw.get("isOrderFee"):
            fee_values = mapping.map_order_fee(li_raw)
            source_line_item_id_for_fee = fee_values.get("source_line_item_id")
            existing_fee = session.scalars(
                select(m.OrderFee).filter_by(
                    order_id=order.id, source_line_item_id=source_line_item_id_for_fee
                )
            ).first()
            if existing_fee is not None:
                for k, v in fee_values.items():
                    if k != "source_line_item_id":
                        setattr(existing_fee, k, v)
            else:
                session.add(
                    m.OrderFee(order_id=order.id, source_system_id=source_system_id, **fee_values)
                )
            stats.bump("order_fees")

        _ingest_order_item_tax(session, order_item, item_source_id, catalog, source_system_id, stats)


def _ingest_order_item_tax(
    session: Session,
    order_item: m.OrderItem,
    item_source_id: str | None,
    catalog: CatalogMaps,
    source_system_id: int,
    stats: IngestionStats,
) -> None:
    """Derives the applicable tax rate for a revenue line item, using the
    confirmed rule (TASK_CLOVER_002/003): an item with `defaultTaxRates=False`
    and an EMPTY per-item override list means 0%, not "fall back to default"
    — never fabricated where the source only supports an Order total (task
    §30). Skipped entirely for fee lines (fees are not taxed line items)."""
    if order_item.is_order_fee or not order_item.is_revenue:
        return
    if item_source_id is None:
        return

    item_id = catalog.item_by_source_id.get(item_source_id)
    if item_id is None:
        return

    rate_decimal: float | None
    used_override = False
    if item_source_id in catalog.item_uses_override_tax_rate:
        override = reader.load_item_tax_rate(item_source_id)
        if override is None:
            return  # not yet enriched — do not fabricate a rate
        rate_decimal = override
        used_override = True
    else:
        rate_decimal = catalog.default_tax_rate_value

    if rate_decimal is None:
        return

    from decimal import Decimal

    tax_rate_id = None if used_override else catalog.default_tax_rate_id
    amount = None
    if order_item.historical_unit_price is not None:
        amount = round(order_item.historical_unit_price * rate_decimal)

    existing = session.scalars(
        select(m.OrderItemTax).filter_by(order_item_id=order_item.id)
    ).first()
    values = {
        "tax_rate_id": tax_rate_id,
        "amount": amount,
        "rate_applied": Decimal(str(rate_decimal)),
        "source_system_id": source_system_id,
        "source_tax_reference": item_source_id,
    }
    if existing is not None:
        for k, v in values.items():
            setattr(existing, k, v)
    else:
        session.add(m.OrderItemTax(order_item_id=order_item.id, **values))


def _ingest_order_discounts_for_order(
    session: Session,
    order_raw: dict[str, Any],
    order: m.Order,
    source_system_id: int,
    catalog: CatalogMaps,
    stats: IngestionStats,
) -> None:
    from decimal import Decimal

    for discount_el in (order_raw.get("discounts") or {}).get("elements", []):
        classified = parser.classify_applied_discount(discount_el)
        source_discount_id = classified["source_discount_id"]
        discount_definition_id = catalog.discount_definition_by_source_id.get(
            classified["discount_definition_source_id"]
        )
        if classified["discount_definition_source_id"] and discount_definition_id is None:
            stats.unresolved_discount_definition_refs += 1

        values = {
            "discount_definition_id": discount_definition_id,
            "name_raw": classified["name_raw"],
            "percentage": Decimal(str(classified["percentage"])) if classified["percentage"] is not None else None,
            "amount": classified["amount"],
            "raw_shape_json": discount_el,
        }
        if source_discount_id:
            existing = session.scalars(
                select(m.OrderDiscount).filter_by(order_id=order.id, source_discount_id=source_discount_id)
            ).first()
        else:
            existing = None
        if existing is not None:
            for k, v in values.items():
                setattr(existing, k, v)
        else:
            session.add(
                m.OrderDiscount(
                    order_id=order.id,
                    source_system_id=source_system_id,
                    source_discount_id=source_discount_id,
                    **values,
                )
            )
        stats.bump("order_discounts")
        stats.bump(f"order_discount_shape_{classified['shape']}")


def ingest_payments_and_tips(
    session: Session,
    bundle: reader.CloverSourceBundle,
    source_system_id: int,
    catalog: CatalogMaps,
    order_map: dict[str, int],
    ingestion_run_id: int,
    retrieved_at: datetime,
    stats: IngestionStats,
) -> dict[str, int]:
    """Ingests ALL top-level Payments (task §32) — not only the nested
    `Order.payments`, which TASK_CLOVER_003 proved excludes FAILED attempts."""
    payment_map: dict[str, int] = {}

    for payment_raw in bundle.payments:
        values = mapping.map_payment(payment_raw)
        source_payment_id = values.pop("source_payment_id")
        order_source_id = values.pop("order_source_id")
        employee_source_id_fk = values.pop("employee_source_id")
        tender_source_id = values.pop("tender_source_id")
        device_source_id = values.pop("device_source_id")

        order_id = order_map.get(order_source_id)
        if order_id is None:
            # Order.id FK on Payment is NOT NULL by schema — a payment
            # without a resolvable Order cannot be ingested. Not expected in
            # this source (every payment observed references an ingested
            # order), but never silently skipped without being counted.
            stats.bump("payments_skipped_unresolved_order")
            continue

        employee_id = catalog.employee_by_source_id.get(employee_source_id_fk)
        if employee_source_id_fk and employee_id is None:
            stats.unresolved_employee_refs += 1
        tender_id = catalog.tender_by_source_id.get(tender_source_id)
        if tender_source_id and tender_id is None:
            stats.unresolved_tender_refs += 1
        device_id = catalog.device_by_source_id.get(device_source_id)
        if device_source_id and device_id is None:
            stats.unresolved_device_refs += 1

        payment = upsert(
            session,
            m.Payment,
            {"source_system_id": source_system_id, "source_payment_id": source_payment_id},
            {
                **values,
                "order_id": order_id,
                "employee_id": employee_id,
                "tender_id": tender_id,
                "device_id": device_id,
                "device_source_id": device_source_id,
            },
        )
        session.flush()
        payment_map[source_payment_id] = payment.id
        stats.bump("payments")
        stats.bump(f"payments_result_{payment_raw.get('result', 'UNKNOWN')}")

        _add_source_record(
            session,
            ingestion_run_id=ingestion_run_id,
            source_system_id=source_system_id,
            entity_type="payment",
            source_id=source_payment_id,
            retrieved_at=retrieved_at,
            raw_path=str(bundle.run_dir / "payments.json"),
        )

        tip_values = mapping.map_payment_tip(payment_raw)
        if tip_values["source_present"]:
            existing_tip = session.get(m.PaymentTip, payment.id)
            if existing_tip is not None:
                existing_tip.amount = tip_values["amount"]
                existing_tip.source_present = True
            else:
                session.add(
                    m.PaymentTip(
                        payment_id=payment.id, amount=tip_values["amount"], source_present=True
                    )
                )
            stats.bump("payment_tips_present")
        else:
            # No PaymentTip row at all — the literal representation of
            # "tip field absent from source" (task §33; DATABASE_SCHEMA.md).
            stats.bump("payment_tips_absent")

    return payment_map


def ingest_refunds(
    session: Session,
    bundle: reader.CloverSourceBundle,
    source_system_id: int,
    catalog: CatalogMaps,
    order_map: dict[str, int],
    payment_map: dict[str, int],
    ingestion_run_id: int,
    retrieved_at: datetime,
    stats: IngestionStats,
) -> None:
    """Mandatory (task §34). Ingested from the dedicated Refund resource
    only — never derived from Order.payment_state / Payment.result /
    OrderItem.refunded_flag, all three of which TASK_CLOVER_003 confirmed
    stay unchanged even for a genuinely refunded Order/Payment."""
    for refund_raw in bundle.refunds or []:
        values = mapping.map_refund(refund_raw)
        source_refund_id = values.pop("source_refund_id")
        order_source_id = values.pop("order_source_id")
        payment_source_id = values.pop("payment_source_id")
        employee_source_id = values.pop("employee_source_id")
        device_source_id = values.pop("device_source_id")

        order_id = order_map.get(order_source_id)
        if order_source_id and order_id is None:
            stats.bump("refunds_unresolved_order")
        payment_id = payment_map.get(payment_source_id)
        if payment_source_id and payment_id is None:
            stats.bump("refunds_unresolved_payment")
        employee_id = catalog.employee_by_source_id.get(employee_source_id)
        if employee_source_id and employee_id is None:
            stats.unresolved_employee_refs += 1
        device_id = catalog.device_by_source_id.get(device_source_id)
        if device_source_id and device_id is None:
            stats.unresolved_device_refs += 1

        upsert(
            session,
            m.Refund,
            {"source_system_id": source_system_id, "source_refund_id": source_refund_id},
            {
                **values,
                "order_id": order_id,
                "payment_id": payment_id,
                "employee_id": employee_id,
                "device_id": device_id,
                "device_source_id": device_source_id,
            },
        )
        stats.bump("refunds")

        _add_source_record(
            session,
            ingestion_run_id=ingestion_run_id,
            source_system_id=source_system_id,
            entity_type="refund",
            source_id=source_refund_id,
            retrieved_at=retrieved_at,
            raw_path=str(reader.TASK3_AUDIT_CACHE_DIR / "refunds_page1.json"),
        )
    session.flush()


def run_full_ingestion(
    session: Session,
    bundle: reader.CloverSourceBundle,
    source_system_id: int,
    ingestion_run_id: int,
    progress: Any = None,
) -> IngestionStats:
    """The single entry point `ingest_clover.py` calls against a (staging)
    session. Order matters: catalog before Employees/Orders/Payments/Refunds,
    since later phases resolve FKs against the maps built here.

    `progress`, if given, is called with a short phase description — the
    CLI's concise progress printing (task §45); this module never prints
    directly, so it stays usable from a dry-run or a test without noise."""

    def _p(msg: str) -> None:
        if progress:
            progress(msg)

    stats = IngestionStats()
    retrieved_at = utc_now()
    catalog = CatalogMaps()

    _p("Ingesting merchant/location...")
    merchant_id, location_id = ingest_merchant_and_location(
        session, bundle, source_system_id, ingestion_run_id, retrieved_at
    )

    _p("Ingesting catalog...")
    catalog.device_by_source_id = ingest_devices(
        session, bundle, location_id, source_system_id, ingestion_run_id, retrieved_at
    )
    catalog.order_type_by_source_id = ingest_order_types(
        session, bundle, location_id, source_system_id, ingestion_run_id, retrieved_at
    )
    catalog.category_by_source_id = ingest_categories(
        session, bundle, location_id, source_system_id, ingestion_run_id, retrieved_at
    )
    catalog.modifier_group_by_source_id, catalog.modifier_by_source_id = (
        ingest_modifier_groups_and_modifiers(
            session, bundle, location_id, source_system_id, ingestion_run_id, retrieved_at
        )
    )
    catalog.discount_definition_by_source_id = ingest_discount_definitions(
        session, bundle, location_id, source_system_id, ingestion_run_id, retrieved_at
    )
    catalog.tax_rate_by_source_id = ingest_tax_rates(
        session, bundle, location_id, source_system_id, ingestion_run_id, retrieved_at
    )
    catalog.tender_by_source_id = ingest_tenders(
        session, bundle, location_id, source_system_id, ingestion_run_id, retrieved_at
    )
    catalog.item_by_source_id = ingest_items_and_categories(
        session,
        bundle,
        location_id,
        source_system_id,
        catalog.category_by_source_id,
        catalog.modifier_by_source_id,
        ingestion_run_id,
        retrieved_at,
    )
    resolve_tax_defaults(bundle, catalog)

    _p("Ingesting employees/shifts...")
    catalog.employee_by_source_id = ingest_employees(
        session, bundle, location_id, source_system_id, ingestion_run_id, retrieved_at
    )
    ingest_employee_stub_references(
        session, bundle, location_id, source_system_id, catalog.employee_by_source_id, ingestion_run_id, retrieved_at, stats
    )
    catalog.source_role_by_source_id = ingest_source_roles(
        session, bundle, location_id, source_system_id, ingestion_run_id, retrieved_at
    )
    ingest_employee_source_roles(
        session, bundle, source_system_id, catalog.employee_by_source_id, catalog.source_role_by_source_id, retrieved_at, stats
    )
    ingest_shifts(session, bundle, source_system_id, catalog.employee_by_source_id, ingestion_run_id, retrieved_at, stats)

    _p("Ingesting orders...")
    order_result = ingest_orders_and_children(
        session, bundle, location_id, source_system_id, catalog, ingestion_run_id, retrieved_at, stats
    )

    _p("Ingesting payments...")
    payment_map = ingest_payments_and_tips(
        session, bundle, source_system_id, catalog, order_result.order_map, ingestion_run_id, retrieved_at, stats
    )

    _p("Ingesting refunds...")
    ingest_refunds(
        session,
        bundle,
        source_system_id,
        catalog,
        order_result.order_map,
        payment_map,
        ingestion_run_id,
        retrieved_at,
        stats,
    )

    return stats
