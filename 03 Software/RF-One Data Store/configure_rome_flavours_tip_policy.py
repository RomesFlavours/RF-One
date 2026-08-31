#!/usr/bin/env python
"""Configure the approved Rome's Flavours Tip Policy (TASK_TIPS_004).

Product-Owner-approved policy structure (`01 Domains/Restaurant/Tips/Tip
Policy.md` remains the generic Domain definition; the actual values below
are Rome's Flavours' own configuration — never hard-coded into
`rfone_data_store/tips/engine.py`):

    Component 1 — Server / Service Owner
        recipient_basis = SERVICE_OWNER
        share_percentage = 90.0000

    Component 2 — Host tip-out
        recipient_basis = ROLE_PRESENT_AT_PAYMENT
        RestaurantRole = "Host"
        share_percentage = 10.0000
        split_method = EQUAL_ELIGIBLE_HEADCOUNT
        no_eligible_behavior = RETURN_TO_SERVICE_OWNER  (no Host on shift ->
            the Server keeps the full Tip)

Tip Policies are LOCATION-SPECIFIC (never one Restaurant-wide inherited
policy): this script configures one independent `TipPolicy` row per current
Location of the given Restaurant, each with its own `valid_from` set to the
earliest real Tip evidence *at that specific Location* — never a single
shared date, and never fabricated. A Location with no recorded Tip evidence
yet is skipped and reported, never given a guessed effective date.

If Mount Dora (or any additional Location) is added to the Restaurant later,
re-running this exact script is the activation step: it will automatically
configure that Location's own policy from its own earliest evidence, with no
code change required.

Usage:
    python configure_rome_flavours_tip_policy.py --restaurant-id 1
        # dry-run (default): prints what would be configured, writes nothing

    python configure_rome_flavours_tip_policy.py --restaurant-id 1 --persist
        # writes the TipPolicy/TipPolicyComponent rows; idempotent — safe to
        # re-run
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal

from sqlalchemy import select

from rfone_data_store.database import create_configured_engine, create_session_factory
from rfone_data_store import models as m
from rfone_data_store.tips.policy_bootstrap import (
    MODE_DRY_RUN,
    MODE_PERSIST,
    ComponentSpec,
    configure_location_tip_policy,
    earliest_tip_evidence_at,
)


def _component_specs(host_role_id: int) -> list[ComponentSpec]:
    return [
        ComponentSpec(
            sequence=1,
            recipient_basis="SERVICE_OWNER",
            share_percentage=Decimal("90.0000"),
            split_method="EQUAL_ELIGIBLE_HEADCOUNT",
            no_eligible_behavior="LEAVE_UNALLOCATED",
        ),
        ComponentSpec(
            sequence=2,
            recipient_basis="ROLE_PRESENT_AT_PAYMENT",
            restaurant_role_id=host_role_id,
            share_percentage=Decimal("10.0000"),
            split_method="EQUAL_ELIGIBLE_HEADCOUNT",
            no_eligible_behavior="RETURN_TO_SERVICE_OWNER",
        ),
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

        host_role = session.scalars(
            select(m.RestaurantRole).where(
                m.RestaurantRole.restaurant_id == restaurant.id, m.RestaurantRole.name == "Host"
            )
        ).one_or_none()
        if host_role is None:
            print(
                f"No 'Host' RestaurantRole configured for Restaurant {restaurant.id} — cannot configure "
                "Component 2 without it. Nothing was changed."
            )
            return 1

        locations = session.scalars(
            select(m.RestaurantLocation).where(m.RestaurantLocation.restaurant_id == restaurant.id)
        ).all()
        if not locations:
            print(f"Restaurant {restaurant.id} has no associated Location. Nothing to configure.")
            return 1

        print(f"Restaurant: {restaurant.id} ({restaurant.name!r})")
        print(f"Host RestaurantRole id: {host_role.id}")
        print(f"Mode: {mode}")
        print()

        any_skipped = False
        for rl in locations:
            location = session.get(m.Location, rl.location_id)
            valid_from = earliest_tip_evidence_at(session, location_id=rl.location_id)
            print(f"Location {rl.location_id} ({location.name if location else '?'}):")
            if valid_from is None:
                print("  No PaymentTip evidence exists yet at this Location — SKIPPED. "
                      "No effective date was guessed; re-run this script once real Tip data exists here.")
                any_skipped = True
                print()
                continue

            print(f"  earliest real PaymentTip-bearing Payment: {valid_from.isoformat()}")
            result = configure_location_tip_policy(
                session,
                restaurant_id=restaurant.id,
                location_id=rl.location_id,
                name="Rome's Flavours Tip Policy",
                valid_from=valid_from,
                components=_component_specs(host_role.id),
                mode=mode,
            )
            if mode == MODE_DRY_RUN:
                print("  DRY RUN — nothing written. Pass --persist to commit.")
            elif result.created:
                print(f"  Created TipPolicy id={result.policy_id}, components={result.component_ids}")
            else:
                print(f"  Already configured — reused existing TipPolicy id={result.policy_id} "
                      f"(idempotent, no duplicate created)")
            print()

        if mode == MODE_PERSIST:
            session.commit()
            print("Persisted.")
        else:
            session.rollback()
            print("Dry run — nothing was persisted (pass --persist to commit).")

        if any_skipped:
            print("NOTE: at least one Location was skipped (no Tip evidence yet) — see above.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
