"""Clover role observations used by the Tips engine.

TIPS_REGISTRY_ROLES_001 (Product Owner, 2026-11-21): the Clover role -> RF-One role correspondence comes
ONLY from Registry (`RegistryRoleMapping`, Anagrafica > Reparti e ruoli), per Restaurant and over time.
Tips' former table `SourceRoleMapping` is no longer read (retired, kept unchanged for history).
A Clover role without an RF-One role in Registry is "to be defined": never guessed.

Product Owner decisions, 2026-11-21 (TIPS_REGISTRY_ROLES_002):
- the first Registry version of a correspondence applies retroactively, unless it contradicts historical
  evidence: a human-confirmed (MANUAL) Registry assignment valid at that instant with another role is an
  explicit exception (uncertain, named in the reason);
- before the first Clover observation of a person, the role is the Registry assignment documented and
  valid at that instant (any source, never one that starts later: the current role is never projected
  into the past); none, or two different ones, is an explicit exception.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select

from .. import models as m
from ..employee_directory import named_roles


@dataclass(frozen=True)
class RoleCorrespondence:
    """One Registry correspondence, as Tips reads it. `valid_from` None = since always: the first version
    Registry holds for a Clover role states what that role has always meant at this Restaurant (the
    table was introduced after the roles existed); every later version applies from its own date."""
    restaurant_role_id: int
    valid_from: datetime | None
    valid_to: datetime | None
    mapping_status: str = "ACTIVE"
    recorded_from: datetime | None = None   # when Registry recorded it (for a version applied since always)


def registry_correspondences(session, restaurant_id):
    """Clover role id -> [RoleCorrespondence] from Registry, plus the ids Registry leaves to be defined."""
    rows = list(session.scalars(select(m.RegistryRoleMapping).where(
        m.RegistryRoleMapping.restaurant_id == restaurant_id, m.RegistryRoleMapping.source == "CLOVER",
    ).order_by(m.RegistryRoleMapping.original_key, m.RegistryRoleMapping.valid_from, m.RegistryRoleMapping.id)))
    by_key = defaultdict(list)
    for row in rows:
        by_key[row.original_key].append(row)
    out, undefined = defaultdict(list), {}
    for key, versions in by_key.items():
        for index, row in enumerate(versions):
            if row.restaurant_role_id is None:
                if row.valid_to is None:
                    undefined[key] = row.original_label
                continue
            out[key].append(RoleCorrespondence(row.restaurant_role_id, None if index == 0 else row.valid_from, row.valid_to,
                                               recorded_from=row.valid_from))
    return out, undefined


def utc(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc)


class CloverRoleHistory:
    def __init__(self, session, restaurant_id, locations):
        self.observations = defaultdict(dict)
        self.mappings = defaultdict(list)
        self.confirmed = defaultdict(list)
        self.documented = defaultdict(list)   # every Registry assignment of these employees at this restaurant
        self.undefined = {}          # Clover role id -> name: no RF-One role in Registry yet
        self.role_names = {}
        links = session.scalars(select(m.EmployeeCloverLink).where(
            m.EmployeeCloverLink.location_id.in_(locations),
            m.EmployeeCloverLink.employee_id.is_not(None),
        )).all()
        if not links:
            return
        keys = {link.id: (link.employee_id, link.location_id) for link in links}
        event = m.EmployeeDirectoryEvent
        for row in session.scalars(select(event).where(
            event.link_id.in_(keys),
            event.action.in_(("IMPORT", "CLOVER_ROLE_CHANGE", "CLOVER_ROLE_OBSERVED")),
        ).order_by(event.id)):
            points = self.observations[keys[row.link_id]]
            if row.action == "IMPORT":
                roles = named_roles(row.details.get("snapshot"))
                if roles:
                    points.setdefault(utc(row.details.get("observed_at") or row.created_at), frozenset(roles))
                continue
            if row.details["previous_observed_at"] and row.details["before"]:
                points[utc(row.details["previous_observed_at"])] = frozenset(row.details["before"])
            points[utc(row.details["observed_at"])] = frozenset(row.details["after"])
        for link in links:
            roles = named_roles(link.snapshot)
            last_seen = (link.snapshot or {}).get("roles_observed_at") or link.last_seen_at
            if roles and last_seen:
                self.observations[keys[link.id]][utc(last_seen)] = frozenset(roles)
        self.observations = {key: sorted(points.items()) for key, points in self.observations.items() if points}
        # From here on, observations never change; the correspondences come from Registry only.
        correspondences, self.undefined = registry_correspondences(session, restaurant_id)
        for source_id, entries in correspondences.items():
            self.mappings[source_id].extend(entries)
        for link in links:
            self.role_names.update(named_roles(link.snapshot))

        assignment = m.EmployeeAssignment
        for row in session.scalars(select(assignment).where(
            assignment.restaurant_id == restaurant_id,
            assignment.employee_id.in_({employee for employee, _ in keys.values()}),
        )):
            self.documented[row.employee_id].append(row)
            if row.assignment_source == "MANUAL":
                self.confirmed[row.employee_id].append(row)

    def map_roles(self, source_roles, instant):
        mapped = set()
        for source_id in source_roles:
            active = {entry.restaurant_role_id for entry in self.mappings[source_id]
                      if entry.mapping_status == "ACTIVE" and (entry.valid_from is None or utc(entry.valid_from) <= instant)
                      and (entry.valid_to is None or instant < utc(entry.valid_to))}
            if len(active) != 1:
                return set()
            mapped.update(active)
        return mapped

    def has_any_role(self, employee, location, roles):
        return any(mapping.restaurant_role_id in roles
                   for _, observed in self.observations.get((employee, location), ())
                   for source_id in observed for mapping in self.mappings[source_id])

    def documented_roles(self, employee, location, instant, *, manual_only=False):
        """RF-One roles of the Registry assignments valid at `instant` (documented history, never later ones)."""
        rows = self.confirmed[employee] if manual_only else self.documented[employee]
        return {row.restaurant_role_id for row in rows if row.location_id in (None, location)
                and utc(row.valid_from) <= instant and (row.valid_to is None or instant < utc(row.valid_to))}

    def _retroactive(self, source_roles, instant):
        """True when the mapping used at `instant` is a first version applied before Registry recorded it."""
        return any(entry.valid_from is None and entry.recorded_from is not None and instant < utc(entry.recorded_from)
                   for source_id in source_roles for entry in self.mappings[source_id])

    def explain(self, employee, location, instant):
        """Why the role at `instant` is uncertain, in words (None when it is not)."""
        points = self.observations.get((employee, location))
        if not points or len(self.roles_at(employee, location, instant) or ()) == 1:
            return None
        previous = next(((at, roles) for at, roles in reversed(points) if at <= instant), None)
        if previous is None:
            found = self.documented_roles(employee, location, instant)
            return (f"no Clover role observed before {points[0][0]:%Y-%m-%d} and no Registry assignment valid on {instant:%Y-%m-%d}"
                    if not found else f"{len(found)} different Registry assignments valid on {instant:%Y-%m-%d}")
        undefined = [self.role_names.get(r) or self.undefined.get(r) or r for r in previous[1] if not self.mappings.get(r)]
        if undefined:
            return "Clover role without an RF-One role in Registry: " + ", ".join(sorted(undefined))
        mapped = self.map_roles(previous[1], instant)
        manual = self.documented_roles(employee, location, instant, manual_only=True)
        if len(mapped) == 1 and manual and manual != mapped:
            return "a confirmed Registry assignment contradicts the Clover role for that date"
        return "Clover role changed between two observations; the effective time is not documented"

    def roles_at(self, employee, location, instant):
        """None means legacy assignment; empty means the tracked role is uncertain."""
        points = self.observations.get((employee, location))
        if not points:
            return None
        previous = next(((at, roles) for at, roles in reversed(points) if at <= instant), None)
        if previous is None:
            # Before the first Clover observation: the documented Registry assignment valid at that date.
            found = self.documented_roles(employee, location, instant)
            return found if len(found) == 1 else set()
        following = next(((at, roles) for at, roles in points if at > instant), previous)
        if previous[0] != instant and previous[1] != following[1]:
            before = self.map_roles(previous[1], previous[0])
            after = self.map_roles(following[1], following[0])
            # A dated manual handoff can provide the effective time independently
            # of the poll timestamps. Require both sides of the transition.
            if len(before) == len(after) == 1 and before != after:
                assignments = [row for row in self.confirmed[employee]
                               if row.location_id in (None, location)]
                handoffs = {utc(new.valid_from) for new in assignments if new.restaurant_role_id in after
                            and previous[0] < utc(new.valid_from) <= following[0]
                            and any(old.restaurant_role_id in before and old.valid_to
                                    and utc(old.valid_to) == utc(new.valid_from)
                                    for old in assignments)}
                if len(handoffs) == 1:
                    return self.map_roles(previous[1] if instant < handoffs.pop() else following[1], instant)
            return set()
        mapped = self.map_roles(previous[1], instant)
        if len(mapped) == 1 and self._retroactive(previous[1], instant):
            manual = self.documented_roles(employee, location, instant, manual_only=True)
            if manual and manual != mapped:
                return set()          # the retroactive mapping contradicts a confirmed assignment
        return mapped

    def undefined_roles(self, employee, location, start, end):
        """Names of the Clover roles held in [start, end) that Registry does not map to an RF-One role."""
        points = self.observations.get((employee, location), ())
        held = set()
        for index, (at, roles) in enumerate(points):
            following = points[index + 1][0] if index + 1 < len(points) else None
            if at < end and (following is None or following > start):
                held |= set(roles)
        return sorted(self.role_names.get(r) or self.undefined.get(r) or r for r in held if not self.mappings.get(r))

    def uncertain_shift(self, employee, location, start, end):
        points = self.observations.get((employee, location))
        if not points:
            return False
        boundaries = {start, *(at for at, _ in points if start <= at < end)}
        for _, roles in points:
            for role in roles:
                for entry in self.mappings[role]:
                    for at in (entry.valid_from, entry.valid_to):
                        if at and start <= utc(at) < end:
                            boundaries.add(utc(at))
        # Also check open intervals, including the time between two observations.
        ordered = sorted(boundaries | {end})
        return any(len(self.roles_at(employee, location, at) or ()) != 1
                   for left, right in zip(ordered, ordered[1:])
                   for at in (left, left + (right - left) / 2))

    def coverage(self, employee, location, role, start, end):
        points = self.observations[(employee, location)]
        cutoffs = {start, end, *(at for at, _ in points if start < at < end)}
        cutoffs.update(utc(at) for row in self.confirmed[employee]
                       if row.location_id in (None, location) for at in (row.valid_from, row.valid_to)
                       if at is not None and start < utc(at) < end)
        for _, source_roles in points:
            for source_role in source_roles:
                cutoffs.update(utc(at) for mapping in self.mappings[source_role]
                               for at in (mapping.valid_from, mapping.valid_to)
                               if at is not None and start < utc(at) < end)
        bounds = sorted(cutoffs)
        return [(lo, hi) for lo, hi in zip(bounds, bounds[1:])
                if role in self.roles_at(employee, location, lo+(hi-lo)/2)]
