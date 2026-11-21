"""CLOVER_MULTISITE_001 — the one rule for "does this Shift count at that
Location?", shared by Tips and Compensation.

A Shift counts at a Location when:
  * it carries that Location (`Shift.location_id`, written by every Clover
    acquisition since the Location-aware connector); or
  * it carries no Location (older Shifts) AND its Employee's home Location
    (`Employee.location_id`) is that Location — the presence-proxy fallback
    documented on `Shift.location_id`.

A Shift without a Location therefore counts at exactly one site, never at
every site: a Winter Park person's old Shift can no longer make them present
in a Mount Dora calculation (or the reverse). No Shift is modified and no
Location is inferred and stored.
"""
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m


def shift_at_locations(location_ids):
    """SQL condition on `m.Shift` for the rule above. `location_ids` is a
    sequence of ids or a single-column select."""
    home_employees = select(m.Employee.id).where(m.Employee.location_id.in_(location_ids))
    return m.Shift.location_id.in_(location_ids) | (
        m.Shift.location_id.is_(None) & m.Shift.employee_id.in_(home_employees)
    )


def employee_home_locations(session: Session, employee_ids: Iterable[int]) -> dict[int, int | None]:
    ids = {employee_id for employee_id in employee_ids if employee_id is not None}
    if not ids:
        return {}
    return dict(session.execute(select(m.Employee.id, m.Employee.location_id).where(m.Employee.id.in_(ids))).all())


def shift_counts_at(shift, location_id: int, home_locations: dict[int, int | None]) -> bool:
    """The same rule for a Shift already loaded in memory; `home_locations`
    comes from `employee_home_locations`."""
    if shift.location_id is not None:
        return shift.location_id == location_id
    return home_locations.get(shift.employee_id) == location_id
