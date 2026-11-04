"""Organizational applicability of a person (EMPLOYEE_APPLICABILITY_001).

Set ONLY in the Employee Directory; every module reads it here and keeps no
copy of its own. Three explicit scopes: one Restaurant, several Restaurants,
or the whole group. A person without a stored scope is NOT_CONFIGURED, which
is a state of its own: never the whole group, never "no restriction".

Applicability is not a permission: it never grants Domain access, it does not
by itself decide which other people a user may select, and it never makes a
dismissed person selectable. Role and area facts stay in
EmployeeAssignment (Workforce); site evidence from Clover stays in
employee_directory and is used for work history, not for applicability.
"""
from dataclasses import dataclass

from sqlalchemy import delete, select

from . import models as m
from . import employee_directory as directory

NOT_CONFIGURED = "NOT_CONFIGURED"
RESTAURANT = m.APPLICABILITY_RESTAURANT
RESTAURANTS = m.APPLICABILITY_RESTAURANTS
GROUP = m.APPLICABILITY_GROUP


@dataclass(frozen=True)
class Applicability:
    kind: str
    restaurant_ids: frozenset = frozenset()

    @property
    def configured(self):
        return self.kind != NOT_CONFIGURED

    def covers_restaurant(self, restaurant_id):
        return self.kind == GROUP or restaurant_id in self.restaurant_ids


UNCONFIGURED = Applicability(NOT_CONFIGURED)


def _from_rows(kind, restaurant_ids):
    return Applicability(kind, frozenset(restaurant_ids)) if kind else UNCONFIGURED


def applicability_map(db, employee_ids):
    """Applicability of many canonical people with two queries."""
    ids = set(employee_ids)
    kinds = dict(db.execute(select(m.EmployeeApplicability.employee_id, m.EmployeeApplicability.scope_kind)
                            .where(m.EmployeeApplicability.employee_id.in_(ids))).all())
    restaurants = {}
    for employee_id, restaurant_id in db.execute(select(
            m.EmployeeApplicabilityRestaurant.employee_id, m.EmployeeApplicabilityRestaurant.restaurant_id)
            .where(m.EmployeeApplicabilityRestaurant.employee_id.in_(ids))):
        restaurants.setdefault(employee_id, set()).add(restaurant_id)
    return {identity: _from_rows(kinds.get(identity), restaurants.get(identity, ())) for identity in ids}


def get_applicability(db, employee_id):
    canonical = directory.resolve_employee_id(db, employee_id)
    return applicability_map(db, [canonical])[canonical]


def account_applicability(db, account_id):
    """Applicability of the person behind an RF-One account. An account with
    no person record, or an ambiguous one, is NOT_CONFIGURED."""
    try:
        person_id = directory.context_person_id(db, "RFONE_ACCOUNT", account_id)
    except ValueError:
        return UNCONFIGURED
    return get_applicability(db, person_id) if person_id is not None else UNCONFIGURED


def restaurant_choices(db):
    return list(db.scalars(select(m.Restaurant).order_by(m.Restaurant.name, m.Restaurant.id)))


def restaurant_names(db, applicabilities):
    """{restaurant_id: name} for displaying the given scopes."""
    ids = set().union(*(a.restaurant_ids for a in applicabilities)) if applicabilities else set()
    return dict(db.execute(select(m.Restaurant.id, m.Restaurant.name).where(m.Restaurant.id.in_(ids))).all())


def set_applicability(db, employee_id, *, kind, restaurant_ids=(), account_id=None):
    """The one write path. Validates the scope explicitly and records the
    previous and new value in the person's append-only directory history."""
    if kind not in (RESTAURANT, RESTAURANTS, GROUP, NOT_CONFIGURED):
        raise ValueError("Unknown applicability.")
    canonical = directory.resolve_employee_id(db, employee_id)
    if db.get(m.Employee, canonical) is None:
        raise ValueError("Employee not found.")
    try:
        chosen = {int(value) for value in restaurant_ids}
    except (TypeError, ValueError):
        raise ValueError("Invalid restaurant selection.") from None
    if kind == RESTAURANT and len(chosen) != 1:
        raise ValueError("Select exactly one restaurant.")
    if kind == RESTAURANTS and len(chosen) < 2:
        raise ValueError("Select at least two restaurants, or choose a single restaurant.")
    if kind in (GROUP, NOT_CONFIGURED) and chosen:
        raise ValueError("The whole group and 'not configured' do not take a restaurant list.")
    known = set(db.scalars(select(m.Restaurant.id).where(m.Restaurant.id.in_(chosen))))
    if known != chosen:
        raise ValueError("Unknown restaurant.")
    before = get_applicability(db, canonical)
    after = _from_rows(None if kind == NOT_CONFIGURED else kind, chosen)
    if after == before:
        return before
    db.execute(delete(m.EmployeeApplicabilityRestaurant).where(
        m.EmployeeApplicabilityRestaurant.employee_id == canonical))
    row = db.get(m.EmployeeApplicability, canonical)
    if kind == NOT_CONFIGURED:
        if row is not None:
            db.delete(row)
    else:
        if row is None:
            row = m.EmployeeApplicability(employee_id=canonical, scope_kind=kind)
            db.add(row)
        row.scope_kind, row.updated_by_account_id = kind, account_id
        db.flush()
        db.add_all(m.EmployeeApplicabilityRestaurant(employee_id=canonical, restaurant_id=restaurant_id)
                   for restaurant_id in sorted(chosen))
    db.add(m.EmployeeDirectoryEvent(employee_id=canonical, account_id=account_id, action="APPLICABILITY_SET",
        details={"before": _describe(before), "after": _describe(after)}))
    db.flush()
    return after


def _describe(applicability):
    return {"kind": applicability.kind, "restaurant_ids": sorted(applicability.restaurant_ids)}
