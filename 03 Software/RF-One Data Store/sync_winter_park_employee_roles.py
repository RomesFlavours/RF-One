#!/usr/bin/env python
"""Sync Winter Park EmployeeAssignments from real, already-ingested Clover
employee role data (EMPLOYEE_ASSIGNMENT_CLOVER_ALIGNMENT_001).

Clover is the operational source for employee role data: this script reads
ONLY `EmployeeSourceRole` -> `SourceRole` (Clover's own reported Role per
Employee account, already ingested by `ingest_clover.py`/Live Sync) — never
guesses a Role from Orders, Tips, Shifts, employee behavior, or names.

Maps ONLY the five approved Winter Park FOH RestaurantRoles, by an explicit,
hardcoded Clover-role-name -> RestaurantRole-id table (never auto-creating a
Role, unlike `rfone_data_store/profile/bootstrap.py`'s more general
SourceRoleMapping bootstrap, which is NOT used here precisely because it
would auto-create a RestaurantRole for any unmapped Clover role name —
this task's explicit "map only where unambiguous, never invent a Role"
requirement is narrower than that general mechanism). A Clover role with no
entry in the table below (e.g. Admin, BOH, Employee) is skipped and
reported for human review — never guessed, never silently promoted into a
new Role.

Enforces Clover's real operating model — one Employee account = exactly one
active Role at a time, within this one Restaurant — via the existing
`EmployeeAssignment` table's temporal effective-dating (`valid_from`/
`valid_to`), now backed by a DB-level partial unique index
(`ux_employee_assignments_one_active_role_per_restaurant`, migration
`e7c1a9f4d6b3`) that rejects two open Assignments for the same
(Employee, Restaurant). A Role change closes the prior open Assignment and
opens a new one; it never overwrites history.

Idempotent and safe: read-only dry-run by default; `--persist` required to
write. Re-running with unchanged Clover role data creates/closes nothing
further.

Usage:
    python sync_winter_park_employee_roles.py --restaurant-id 1
        # dry-run (default): prints the mapping and what would change
    python sync_winter_park_employee_roles.py --restaurant-id 1 --persist
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from sqlalchemy import select

from rfone_data_store import models as m
from rfone_data_store.database import create_configured_engine, create_session_factory

MODE_DRY_RUN = "DRY_RUN"
MODE_PERSIST = "PERSIST"

UTC = timezone.utc

# Explicit, human-approved mapping — Clover's own reported Role name (as
# stored on `SourceRole.name`) to the EXISTING, already-approved Winter Park
# FOH `RestaurantRole.code`. Keyed by CODE, never by a hardcoded row id:
# the same five approved Roles carry different `RestaurantRole.id` values in
# different databases (local SQLite vs the real RDS instance), so an id
# table would silently assign the WRONG Role there. Codes are resolved
# against the target Restaurant's own Roles at run time and the script
# aborts if any approved Role is missing. Never auto-created, never
# guessed. A Clover role
# with no entry here (e.g. "Admin", "BOH", "Employee") is out of scope for
# this FOH-only mapping and is skipped/reported, never invented as a new
# RestaurantRole.
WINTER_PARK_CLOVER_ROLE_TO_RESTAURANT_ROLE_CODE = {
    "Manager": "MANAGER",
    "Team Leader": "TEAM_LEADER",
    "Server": "SERVER",
    "Busser-Runner": "BUSSER_RUNNER",
    "Host": "HOST",
}

ASSIGNMENT_SOURCE_CLOVER_ROLE_SYNC = "CLOVER_ROLE_SYNC"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--restaurant-id", type=int, required=True)
    parser.add_argument("--persist", action="store_true", help="Write to the database. Default is dry-run.")
    args = parser.parse_args()

    engine = create_configured_engine()
    session_factory = create_session_factory(engine)
    mode = MODE_PERSIST if args.persist else MODE_DRY_RUN

    with session_factory() as session:
        restaurant = session.get(m.Restaurant, args.restaurant_id)
        if restaurant is None:
            print(f"No Restaurant with id={args.restaurant_id}.")
            return 1

        location_ids = list(
            session.scalars(
                select(m.RestaurantLocation.location_id).where(m.RestaurantLocation.restaurant_id == restaurant.id)
            )
        )
        if not location_ids:
            print(f"Restaurant {restaurant.id} has no associated Location. Nothing to sync.")
            return 1

        # Root Operational Area — reused if the Restaurant Profile bootstrap
        # already created one (TASK_RESTAURANT_003's "ROOT" code); created
        # here only if genuinely absent, matching that same minimal-
        # granularity convention rather than inventing a parallel Area.
        root_area = session.scalars(
            select(m.OperationalArea).where(m.OperationalArea.restaurant_id == restaurant.id, m.OperationalArea.code == "ROOT")
        ).first()

        # Earliest real operational evidence at this Restaurant's Location(s)
        # — Clover exposes only CURRENT Role membership, no historical role-
        # assignment log, so a new Assignment's `valid_from` is anchored to
        # the earliest real evidence already on file, never an arbitrary/
        # invented date and never "today" (Shift is the authoritative
        # presence evidence this Restaurant already has).
        earliest_shift = session.scalars(
            select(m.Shift.clock_in).join(m.Employee, m.Shift.employee_id == m.Employee.id)
            .where(m.Employee.location_id.in_(location_ids)).order_by(m.Shift.clock_in).limit(1)
        ).first()
        first_ever_valid_from = (earliest_shift or datetime.now(UTC)).replace(hour=0, minute=0, second=0, microsecond=0)
        if first_ever_valid_from.tzinfo is None:
            first_ever_valid_from = first_ever_valid_from.replace(tzinfo=UTC)
        # A Role CHANGE (an employee who already had a different open
        # Assignment) is detected NOW — closed/opened at sync time, never
        # backdated to the historical anchor above, which is reserved for an
        # employee's very FIRST Assignment ever (bootstrap.py's own T0-vs-
        # "now" convention for a later-detected change).
        sync_time = datetime.now(UTC).replace(microsecond=0, tzinfo=None)

        # Resolve the five approved FOH Roles by CODE against THIS
        # Restaurant's own Role list (never a hardcoded row id — see the
        # mapping table's comment above). Abort rather than sync a partial
        # mapping: a missing Role would silently "skip" every employee who
        # holds it, which is indistinguishable in the report from Clover
        # genuinely not reporting that role.
        roles_by_code = {
            r.code: r
            for r in session.scalars(
                select(m.RestaurantRole).where(m.RestaurantRole.restaurant_id == restaurant.id)
            )
            if r.code
        }
        missing_codes = [c for c in WINTER_PARK_CLOVER_ROLE_TO_RESTAURANT_ROLE_CODE.values() if c not in roles_by_code]
        if missing_codes:
            print(f"Restaurant {restaurant.id} is missing approved FOH Role code(s): {missing_codes}.")
            print("Run seed_winter_park_foh_roles.py --persist first. Nothing synced.")
            return 1
        clover_role_to_role = {
            clover_name: roles_by_code[code]
            for clover_name, code in WINTER_PARK_CLOVER_ROLE_TO_RESTAURANT_ROLE_CODE.items()
        }

        print(f"Restaurant: {restaurant.id} ({restaurant.name!r})")
        print(f"Mode: {mode}")
        print(f"First-ever Assignment valid_from anchor (earliest real Shift evidence): {first_ever_valid_from.isoformat()}")
        print(f"Role-change sync time: {sync_time.isoformat()}")
        print(f"Root Operational Area: {'id=' + str(root_area.id) if root_area else '(will be created)'}")
        print()

        employees = list(session.scalars(select(m.Employee).where(m.Employee.location_id.in_(location_ids)).order_by(m.Employee.id)))

        mapping_rows: list[dict] = []
        skipped: list[dict] = []
        to_create: list[tuple[m.Employee, int, str, datetime]] = []  # (employee, target_role_id, clover_role_name, effective_from)
        to_close: list[m.EmployeeAssignment] = []
        reused: list[tuple[m.Employee, m.EmployeeAssignment]] = []

        for employee in employees:
            esrs = list(session.scalars(select(m.EmployeeSourceRole).where(m.EmployeeSourceRole.employee_id == employee.id)))
            clover_role_names = sorted({
                sr.name for sr in (session.get(m.SourceRole, esr.source_role_id) for esr in esrs) if sr is not None
            })

            existing_open = session.scalars(
                select(m.EmployeeAssignment).where(
                    m.EmployeeAssignment.employee_id == employee.id,
                    m.EmployeeAssignment.restaurant_id == restaurant.id,
                    m.EmployeeAssignment.valid_to.is_(None),
                )
            ).first()

            if not clover_role_names:
                action = "SKIP (no Clover source role on file — ambiguous, human review required)"
                mapping_rows.append({"employee": employee.display_name, "clover_role": "(none)", "rf_one_role": "-", "action": action})
                skipped.append({"employee": employee.display_name, "reason": "no EmployeeSourceRole on file"})
                continue

            if len(clover_role_names) > 1:
                action = f"SKIP (employee has {len(clover_role_names)} distinct Clover roles at once — ambiguous, human review required)"
                mapping_rows.append({"employee": employee.display_name, "clover_role": ", ".join(clover_role_names), "rf_one_role": "-", "action": action})
                skipped.append({"employee": employee.display_name, "reason": f"multiple concurrent Clover roles: {clover_role_names}"})
                continue

            clover_role_name = clover_role_names[0]
            target_role = clover_role_to_role.get(clover_role_name)
            if target_role is None:
                action = "SKIP (Clover role has no approved FOH RestaurantRole mapping — out of scope, human review required)"
                mapping_rows.append({"employee": employee.display_name, "clover_role": clover_role_name, "rf_one_role": "-", "action": action})
                skipped.append({"employee": employee.display_name, "reason": f"unmapped Clover role: {clover_role_name!r}"})
                continue

            target_role_id = target_role.id
            rf_one_role_label = target_role.name

            if existing_open is not None and existing_open.restaurant_role_id == target_role_id:
                action = f"REUSE (already assigned to {rf_one_role_label}, id={existing_open.id})"
                reused.append((employee, existing_open))
            elif existing_open is not None:
                old_role = session.get(m.RestaurantRole, existing_open.restaurant_role_id)
                action = (
                    f"ROLE CHANGE: close assignment id={existing_open.id} "
                    f"({old_role.name if old_role else existing_open.restaurant_role_id}) -> open new {rf_one_role_label}"
                )
                to_close.append(existing_open)
                to_create.append((employee, target_role_id, clover_role_name, sync_time))
            else:
                action = f"CREATE (new open assignment -> {rf_one_role_label})"
                to_create.append((employee, target_role_id, clover_role_name, first_ever_valid_from.replace(tzinfo=None)))

            mapping_rows.append({"employee": employee.display_name, "clover_role": clover_role_name, "rf_one_role": rf_one_role_label, "action": action})

        print("CLOVER EMPLOYEE | CLOVER ROLE | RF-ONE EMPLOYEE | RESTAURANT ROLE | ACTION")
        for row in mapping_rows:
            print(f"  {row['employee']:22s} | {row['clover_role']:14s} | {row['employee']:22s} | {row['rf_one_role']:14s} | {row['action']}")

        print()
        print(f"Summary: {len(to_create)} to create, {len(to_close)} to close, {len(reused)} already correct (reused), {len(skipped)} skipped.")
        if skipped:
            print("\nSkipped (human review required):")
            for s in skipped:
                print(f"  - {s['employee']}: {s['reason']}")

        if mode == MODE_DRY_RUN:
            print("\nDry run — nothing written. Re-run with --persist to write.")
            return 0

        if root_area is None:
            root_area = m.OperationalArea(
                restaurant_id=restaurant.id, name="Restaurant Operations", code="ROOT",
                description="Minimal Restaurant Profile granularity — see profile/bootstrap.py's own ROOT_AREA_DESCRIPTION.",
                active=True,
            )
            session.add(root_area)
            session.flush()

        for assignment in to_close:
            assignment.valid_to = sync_time

        created_count = 0
        for employee, target_role_id, clover_role_name, effective_from in to_create:
            session.add(
                m.EmployeeAssignment(
                    employee_id=employee.id, restaurant_id=restaurant.id, operational_area_id=root_area.id,
                    restaurant_role_id=target_role_id, location_id=employee.location_id,
                    valid_from=effective_from, valid_to=None,
                    assignment_source=ASSIGNMENT_SOURCE_CLOVER_ROLE_SYNC,
                    source_note=(
                        f"Synced from Clover EmployeeSourceRole {clover_role_name!r} "
                        f"(EMPLOYEE_ASSIGNMENT_CLOVER_ALIGNMENT_001) at {sync_time.isoformat()}."
                    ),
                )
            )
            created_count += 1
        session.commit()
        print(f"\nPersisted: {created_count} created, {len(to_close)} closed, {len(reused)} reused unchanged.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
