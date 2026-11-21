"""CLOVER_MULTISITE_001 — the one rule for "where did this Shift happen?",
shared by Tips and Compensation (Product Owner decision, 2026-11-21).

The Location of a Shift is CERTAIN when:
  1. the Shift carries it (`Shift.location_id`, written by every Clover
     acquisition since the Location-aware connector); or
  2. the Shift carries none, but the Clover data it was acquired from proves
     it: every Provider Mirror record of that Shift (`SourceRecord`,
     entity_type "shift") was written by acquisition runs of one and the same
     Location (`IngestionRun.location_id`, i.e. one Clover merchant).

Otherwise (no mirror record, a run without a Location, or runs of different
Locations) the Shift is PENDING: it counts at no Location, is excluded from
every calculation that needs a certain Location, and is reported as an
anomaly. A Shift is never attributed through the Employee's home Location.

Read-only: no Shift is modified and no reconstructed Location is stored.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, aliased

from . import models as m

SHIFT_ENTITY = "shift"


def _mirror_locations():
    """Per mirrored Shift (source system + source id): its Location when all
    of its mirror records come from runs of exactly one Location."""
    record, run = aliased(m.SourceRecord), aliased(m.IngestionRun)
    return (
        select(record.source_system_id.label("source_system_id"), record.source_id.label("source_id"),
               func.max(run.location_id).label("location_id"))
        .join(run, run.id == record.ingestion_run_id)
        .where(record.entity_type == SHIFT_ENTITY)
        .group_by(record.source_system_id, record.source_id)
        .having(func.count(func.distinct(run.location_id)) == 1, func.count() == func.count(run.location_id))
        .subquery()
    )


def shift_at_locations(location_ids):
    """SQL condition on `m.Shift`: its certain Location is one of
    `location_ids` (a sequence of ids or a single-column select)."""
    mirror = _mirror_locations()
    reconstructed = exists().where(
        mirror.c.source_system_id == m.Shift.source_system_id,
        mirror.c.source_id == m.Shift.source_shift_id,
        mirror.c.location_id.in_(location_ids),
    )
    return m.Shift.location_id.in_(location_ids) | (m.Shift.location_id.is_(None) & reconstructed)


def shift_location_pending():
    """SQL condition on `m.Shift`: no certain Location (the anomaly)."""
    mirror = _mirror_locations()
    reconstructed = exists().where(
        mirror.c.source_system_id == m.Shift.source_system_id,
        mirror.c.source_id == m.Shift.source_shift_id,
    )
    return m.Shift.location_id.is_(None) & ~reconstructed


def resolve_shift_locations(session: Session, shifts: Iterable[m.Shift]) -> dict[int, int | None]:
    """Shift id -> certain Location id, or None while pending."""
    shifts = list(shifts)
    resolved = {shift.id: shift.location_id for shift in shifts}
    missing = [shift for shift in shifts if shift.location_id is None and shift.source_shift_id]
    if missing:
        mirror = _mirror_locations()
        keys = {shift.source_shift_id for shift in missing}
        found = {(system, source): location for system, source, location in session.execute(
            select(mirror.c.source_system_id, mirror.c.source_id, mirror.c.location_id)
            .where(mirror.c.source_id.in_(keys)))}
        for shift in missing:
            resolved[shift.id] = found.get((shift.source_system_id, shift.source_shift_id))
    return resolved


def shift_counts_at(shift, location_id: int, resolved: dict[int, int | None]) -> bool:
    """The same rule for a Shift already loaded; `resolved` comes from
    `resolve_shift_locations`."""
    if shift.location_id is not None:
        return shift.location_id == location_id
    return resolved.get(shift.id) == location_id


def pending_shift_count(session: Session, *, start: datetime, end: datetime) -> int:
    """Shifts clocked in within [start, end) whose Location is not certain:
    excluded from every site's calculations and reported as anomalies."""
    return session.scalar(select(func.count(m.Shift.id)).where(
        shift_location_pending(), m.Shift.clock_in >= start, m.Shift.clock_in < end)) or 0


def reconstructed_shift_ids(session: Session, shifts: Iterable[m.Shift]) -> set[int]:
    """Ids of the given Shifts whose Location comes from the Clover mirror
    (no own Location, but a certain one)."""
    shifts = [shift for shift in shifts if shift.location_id is None]
    resolved = resolve_shift_locations(session, shifts)
    return {shift.id for shift in shifts if resolved.get(shift.id) is not None}
