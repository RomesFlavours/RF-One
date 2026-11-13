"""Record-level identity holds (EMPLOYEE_DIRECTORY_RECORD_HOLD_001, approved by
the Product Owner on 2026-11-02).

An unconfirmed Clover employee identity no longer stops a Location's whole
acquisition. Work records keep arriving with their original Clover IDs and raw
payloads; only the attribution to an RF-One person waits:

- Orders, Payments, Refunds are stored with `employee_id` NULL. The Clover ID
  stays on `source_employee_id` (Orders/Payments) or in the Provider Mirror
  raw (Refunds, which have no such column).
- Shifts require a person (`shifts.employee_id` is NOT NULL), so a held Shift
  is not created; its raw stays in the Provider Mirror (`source_records`).

Nothing here creates a person or guesses an identity. `reattribute_link` runs
when a human confirms a link: it fills only still-NULL attributions from the
Clover ID, so repeating it changes nothing, and it records what it moved.
`unattributed_work` lets Tips refuse to finalize only the affected days.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import String, cast, func, or_, select, update
from sqlalchemy.orm import Session

from .... import models as m
from . import mapping
from .ingest import upsert

UTC = timezone.utc

HOLD_REASON = "Clover employee identity not yet confirmed in Employee Directory"


def pending_external_ids(session: Session, merchant_ids: Iterable[str]) -> set[str]:
    """Clover employee IDs at these merchants that no RF-One person is linked to yet."""
    merchant_ids = [merchant_id for merchant_id in merchant_ids if merchant_id]
    if not merchant_ids:
        return set()
    return set(session.scalars(select(m.EmployeeCloverLink.external_employee_id).where(
        m.EmployeeCloverLink.merchant_id.in_(merchant_ids), m.EmployeeCloverLink.employee_id.is_(None))))


def describe(pending: set[str], counts: dict[str, int]) -> list[str]:
    """The one log/history line for a cycle with pending identities."""
    if not pending:
        return []
    return [f"{len(pending)} Clover employee identities pending in Employee Directory "
            f"({', '.join(sorted(pending))}); held without a person: "
            + ", ".join(f"{name}={count}" for name, count in counts.items())
            + ". Other records were acquired normally; held records are attributed on confirmation."]


def _latest_mirrored(session: Session, *, entity_type: str, external_ids: set[str],
                     location_ids: Iterable[int] | None = None) -> dict[str, tuple[dict[str, Any], int]]:
    """Latest Provider Mirror raw per source record mentioning any of these Clover
    employee IDs, with the Location of the run that fetched it."""
    if not external_ids:
        return {}
    query = (
        select(m.SourceRecord.source_id, m.SourceRecord.raw_json, m.IngestionRun.location_id)
        .join(m.IngestionRun, m.IngestionRun.id == m.SourceRecord.ingestion_run_id)
        .where(m.SourceRecord.entity_type == entity_type,
               or_(*[cast(m.SourceRecord.raw_json, String).like(f'%"{external_id}"%') for external_id in external_ids]))
        .order_by(m.SourceRecord.id)
    )
    if location_ids is not None:
        query = query.where(m.IngestionRun.location_id.in_(list(location_ids)))
    latest: dict[str, tuple[dict[str, Any], int]] = {}
    for source_id, raw, location_id in session.execute(query):
        if isinstance(raw, dict):
            latest[source_id] = (raw, location_id)
    return latest


def _shift_employee_refs(raw: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    values = mapping.map_shift(raw)
    return (values.get("employee_source_id"), values.get("override_in_employee_source_id"),
            values.get("override_out_employee_source_id"))


def held_shifts(session: Session, *, location_ids: Iterable[int], external_ids: set[str]) -> dict[str, dict[str, Any]]:
    """Mirrored Shifts not yet canonical because their employee is still pending."""
    location_ids = list(location_ids)
    held = {}
    for source_id, (raw, _location_id) in _latest_mirrored(
            session, entity_type="shift", external_ids=external_ids, location_ids=location_ids).items():
        if _shift_employee_refs(raw)[0] not in external_ids:
            continue
        exists = session.scalar(select(m.Shift.id).where(m.Shift.source_shift_id == source_id).limit(1))
        if exists is None:
            held[source_id] = raw
    return held


def held_shift_counts(session: Session, *, location_id: int, external_ids: set[str]) -> dict[str, int]:
    """Held Shifts (clock-ins/outs) per pending Clover ID at one Location."""
    counts: dict[str, int] = {}
    for raw in held_shifts(session, location_ids=[location_id], external_ids=external_ids).values():
        external_id = _shift_employee_refs(raw)[0]
        if external_id in external_ids and (raw.get("inTime") is not None or raw.get("outTime") is not None):
            counts[external_id] = counts.get(external_id, 0) + 1
    return counts


def held_order_counts(session: Session, *, location_id: int, external_ids: set[str]) -> dict[str, int]:
    """Orders acquired without a person per pending Clover ID at one Location."""
    if not external_ids:
        return {}
    return dict(session.execute(select(m.Order.source_employee_id, func.count()).where(
        m.Order.location_id == location_id, m.Order.employee_id.is_(None),
        m.Order.source_employee_id.in_(list(external_ids))).group_by(m.Order.source_employee_id)).all())


def _resolved_ids(session: Session, merchant_id: str) -> dict[str, int]:
    return {link.external_employee_id: link.employee_id for link in session.scalars(
        select(m.EmployeeCloverLink).where(m.EmployeeCloverLink.merchant_id == merchant_id,
                                         m.EmployeeCloverLink.employee_id.is_not(None)))}


def reattribute_link(session: Session, link: "m.EmployeeCloverLink") -> dict[str, int]:
    """Attribute the work held for one just-confirmed Clover identity.

    Fills only NULL attributions at the link's own Location, so it is
    idempotent and never overwrites a confirmed attribution. The caller
    records the returned counts in the directory history."""
    if link.employee_id is None:
        raise ValueError("The Clover identity is not confirmed yet; nothing can be attributed.")
    external_id, employee_id, location_id = link.external_employee_id, link.employee_id, link.location_id
    location_orders = select(m.Order.id).where(m.Order.location_id == location_id)
    counts = {
        "orders": session.execute(update(m.Order).where(
            m.Order.location_id == location_id, m.Order.source_employee_id == external_id,
            m.Order.employee_id.is_(None)).values(employee_id=employee_id)).rowcount,
        "payments": session.execute(update(m.Payment).where(
            m.Payment.order_id.in_(location_orders), m.Payment.source_employee_id == external_id,
            m.Payment.employee_id.is_(None)).values(employee_id=employee_id)).rowcount,
        "refunds": 0,
        "shifts": 0,
        "shift_overrides": 0,
    }
    for source_id, (raw, _loc) in _latest_mirrored(
            session, entity_type="refund", external_ids={external_id}, location_ids=[location_id]).items():
        if mapping.map_refund(raw).get("employee_source_id") != external_id:
            continue
        counts["refunds"] += session.execute(update(m.Refund).where(
            m.Refund.source_refund_id == source_id, m.Refund.employee_id.is_(None)
        ).values(employee_id=employee_id)).rowcount

    resolved = _resolved_ids(session, link.merchant_id)
    for source_id, (raw, _loc) in _latest_mirrored(
            session, entity_type="shift", external_ids={external_id}, location_ids=[location_id]).items():
        main, override_in, override_out = _shift_employee_refs(raw)
        shift = session.scalar(select(m.Shift).where(m.Shift.source_shift_id == source_id).limit(1))
        if shift is None:
            if main != external_id or resolved.get(main) is None:
                continue  # held for a different, still-pending person
            values = mapping.map_shift(raw)
            source_system_id = session.scalar(select(m.Location.source_system_id).where(m.Location.id == location_id))
            values.pop("source_shift_id")
            for key in ("employee_source_id", "override_in_employee_source_id", "override_out_employee_source_id"):
                values.pop(key)
            upsert(session, m.Shift, {"source_system_id": source_system_id, "source_shift_id": source_id}, {
                **values, "employee_id": resolved[main], "location_id": location_id,
                "override_in_employee_id": resolved.get(override_in) if override_in else None,
                "override_out_employee_id": resolved.get(override_out) if override_out else None,
            })
            counts["shifts"] += 1
            continue
        for ref, column in ((override_in, "override_in_employee_id"), (override_out, "override_out_employee_id")):
            if ref == external_id and getattr(shift, column) is None:
                setattr(shift, column, employee_id)
                counts["shift_overrides"] += 1
    session.flush()
    return counts


def reattribute_untraced_confirmations(session: Session, merchant_id: str) -> list[dict[str, Any]]:
    """Confirmations made by a runtime without record holds (a web release
    older than this poller): a LINK event with no REATTRIBUTE after it. Legacy
    links seeded by migration have no LINK event and are never touched."""
    from ....employee_directory import _event

    done = []
    for link in session.scalars(select(m.EmployeeCloverLink).where(
            m.EmployeeCloverLink.merchant_id == merchant_id, m.EmployeeCloverLink.employee_id.is_not(None))):
        def last(action):
            return session.scalar(select(func.max(m.EmployeeDirectoryEvent.id)).where(
                m.EmployeeDirectoryEvent.link_id == link.id, m.EmployeeDirectoryEvent.action == action))
        linked = last("LINK")
        if linked is None or (last("REATTRIBUTE") or 0) > linked:
            continue
        counts = reattribute_link(session, link)
        _event(session, "REATTRIBUTE", employee_id=link.employee_id, link=link,
               details={"external_employee_id": link.external_employee_id, "counts": counts,
                        "by": "correction_sync"})
        done.append({"link_id": link.id, **counts})
    session.flush()
    return done


def unattributed_work(session: Session, *, location_ids: Iterable[int], first_business_date, last_business_date,
                      window_start: datetime | None = None, window_end: datetime | None = None) -> dict[str, Any]:
    """Work in these Business Dates still waiting for a pending Clover identity.

    Orders/Payments/Refunds are matched by Business Date; held Shifts by
    clock-in inside `[window_start, window_end)` when that window is given."""
    location_ids = list(location_ids)
    merchant_ids = list(session.scalars(select(m.Location.source_location_id).where(m.Location.id.in_(location_ids))))
    external_ids = pending_external_ids(session, merchant_ids)
    result: dict[str, Any] = {"orders": 0, "payments": 0, "refunds": 0, "shifts": 0, "business_dates": []}
    if not external_ids:
        return result
    held_orders = list(session.execute(select(m.Order.id, m.Order.business_date).where(
        m.Order.location_id.in_(location_ids), m.Order.business_date >= first_business_date,
        m.Order.business_date <= last_business_date, m.Order.employee_id.is_(None),
        m.Order.source_employee_id.in_(external_ids))))
    period_orders = select(m.Order.id).where(
        m.Order.location_id.in_(location_ids), m.Order.business_date >= first_business_date,
        m.Order.business_date <= last_business_date)
    result["orders"] = len(held_orders)
    result["payments"] = len(list(session.scalars(select(m.Payment.id).where(
        m.Payment.order_id.in_(period_orders), m.Payment.employee_id.is_(None),
        m.Payment.source_employee_id.in_(external_ids)))))
    period_order_ids = set(session.scalars(period_orders))
    for source_id, (raw, _loc) in _latest_mirrored(
            session, entity_type="refund", external_ids=external_ids, location_ids=location_ids).items():
        refund = session.scalar(select(m.Refund).where(m.Refund.source_refund_id == source_id).limit(1))
        if (refund is not None and refund.employee_id is None and refund.order_id in period_order_ids
                and mapping.map_refund(raw).get("employee_source_id") in external_ids):
            result["refunds"] += 1
    if window_start is not None and window_end is not None:
        start_ms, end_ms = (int(t.astimezone(UTC).timestamp() * 1000) for t in (window_start, window_end))
        result["shifts"] = sum(
            1 for raw in held_shifts(session, location_ids=location_ids, external_ids=external_ids).values()
            if isinstance(raw.get("inTime"), int) and start_ms <= raw["inTime"] < end_ms)
    result["business_dates"] = sorted({str(day) for _id, day in held_orders if day is not None})
    return result
