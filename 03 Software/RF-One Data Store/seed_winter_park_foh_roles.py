#!/usr/bin/env python
"""Seed Rome's Flavours - Winter Park's approved FOH RestaurantRoles.

Creates ONLY the five approved Front-of-House roles: Manager, Team Leader,
Server, Busser-Runner, Host. Uses the existing `restaurant_role_service.py`
(`RestaurantRole` definitions) exactly as-is — no service/model change.
Never creates a "Service Owner" role: in Tips, Service Owner is simply
whichever Employee Clover attributed to the Order (`Order.employee_id`),
resolved via that Employee's own Server-role assignment — a runtime
attribution concept, not a Role definition of its own.

Idempotent and safe: inspects existing rows first, skips any name that
already exists (never creates a duplicate, never overwrites an existing
row's id/data), and is safe read-only dry-run by default — mirrors
`seed_tip_distribution_rules.py`'s exact convention.

Usage:
    python seed_winter_park_foh_roles.py --restaurant-id 1
        # dry-run (default): prints what would be created, writes nothing
    python seed_winter_park_foh_roles.py --restaurant-id 1 --persist
"""

from __future__ import annotations

import argparse
import sys

from rfone_data_store import restaurant_role_service as role_svc
from rfone_data_store import models as m
from rfone_data_store.database import create_configured_engine, create_session_factory

MODE_DRY_RUN = "DRY_RUN"
MODE_PERSIST = "PERSIST"

# (name, code) — code is this script's own uppercase-snake-case rendering
# of the approved name; no other RestaurantRole convention exists yet
# anywhere in this repository to instead reuse (Winter Park's role list was
# entirely empty before this task).
APPROVED_FOH_ROLES = [
    ("Manager", "MANAGER"),
    ("Team Leader", "TEAM_LEADER"),
    ("Server", "SERVER"),
    ("Busser-Runner", "BUSSER_RUNNER"),
    ("Host", "HOST"),
]


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

        print(f"Restaurant: {restaurant.id} ({restaurant.name!r})")
        print(f"Mode: {mode}")
        print()

        existing = role_svc.list_roles(session, restaurant.id)
        existing_by_name = {r.name: r for r in existing}
        print("Existing Roles for this Restaurant:")
        if existing:
            for r in existing:
                print(f"  id={r.id} name={r.name!r} code={r.code!r} active={r.active}")
        else:
            print("  (none)")
        print()

        to_create = []
        for name, code in APPROVED_FOH_ROLES:
            if name in existing_by_name:
                print(f"SKIP (already exists, id={existing_by_name[name].id}): {name!r}")
            else:
                to_create.append((name, code))

        if not to_create:
            print("\nNothing to create — every approved Role already exists.")
            return 0

        print(f"\nWould create {len(to_create)} Role(s): {[n for n, _ in to_create]}")

        if mode == MODE_DRY_RUN:
            print("\nDry run — nothing written. Re-run with --persist to write.")
            return 0

        created = []
        for name, code in to_create:
            role = role_svc.create_role(session, restaurant_id=restaurant.id, name=name, code=code)
            created.append(role)
        session.commit()

        print("\nCreated:")
        for role in created:
            print(f"  id={role.id} name={role.name!r} code={role.code!r}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
