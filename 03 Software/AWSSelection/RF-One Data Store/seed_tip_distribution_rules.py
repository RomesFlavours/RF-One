#!/usr/bin/env python
"""Seed Rome's Flavours' currently known Tip Distribution Rule
(TIPS_DISTRIBUTION_RULES_001).

Rule (from `01 Domains/Business Domain/Restaurant/Functional Specifications/
TIP_DISTRIBUTION_ENGINE_FUNCTIONAL_SPEC_001.md`'s own "Rome's Flavours —
Initial Configuration" section):

    Source Role:        SERVER
    Recipient Role:     HOST
    Calculation Base:   TIP_PLUS_GRATUITY
    Rate:               10%

This is restaurant-configurable DATA only — the universal
`TipDistributionRule`/`TipDistributionRuleVersion` schema and
`rfone_data_store/tips/distribution_rule_service.py` have no knowledge that
Rome's Flavours uses this specific rule; this script is the one place that
fact is written down.

Mirrors `configure_rome_flavours_tip_policy.py`'s exact convention: safe,
read-only dry-run by default; `--persist` required to actually write.
`effective_from` is derived from the earliest real Tip evidence at this
Restaurant's Location (reusing the existing, already-reviewed
`tips.policy_bootstrap.earliest_tip_evidence_at` helper) — never an
arbitrary "today" date, so historical Orders remain coverable by this rule
version once a calculation engine exists, rather than leaving a gap before
today. Idempotent: re-running with `--persist` when a SERVER -> HOST rule
already exists for this Restaurant changes nothing and reports that.

Usage:
    python seed_tip_distribution_rules.py --restaurant-id 1
        # dry-run (default): prints what would be seeded, writes nothing
    python seed_tip_distribution_rules.py --restaurant-id 1 --persist
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal

from sqlalchemy import select

from rfone_data_store import models as m
from rfone_data_store.database import create_configured_engine, create_session_factory
from rfone_data_store.tips import distribution_rule_service as rule_svc
from rfone_data_store.tips.policy_bootstrap import earliest_tip_evidence_at

MODE_DRY_RUN = "DRY_RUN"
MODE_PERSIST = "PERSIST"


def find_romes_flavours_server_host_rule(
    session, restaurant_id: int, source_role_id: int, recipient_role_id: int,
) -> "m.TipDistributionRule | None":
    """Idempotency check: does a Rule already exist for this Restaurant whose
    CURRENT (latest) version already names this exact Source/Recipient Role
    pair? If so, this script has nothing to do."""
    for rule in rule_svc.list_rules(session, restaurant_id):
        versions = rule_svc.list_versions(session, rule.id)
        if not versions:
            continue
        latest = versions[-1]
        if latest.source_role_id == source_role_id and latest.recipient_role_id == recipient_role_id:
            return rule
    return None


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

        server_role = session.scalars(
            select(m.RestaurantRole).where(
                m.RestaurantRole.restaurant_id == restaurant.id, m.RestaurantRole.name == "Server"
            )
        ).one_or_none()
        host_role = session.scalars(
            select(m.RestaurantRole).where(
                m.RestaurantRole.restaurant_id == restaurant.id, m.RestaurantRole.name == "Host"
            )
        ).one_or_none()
        if server_role is None or host_role is None:
            print(
                f"Restaurant {restaurant.id} is missing a 'Server' and/or 'Host' RestaurantRole — "
                "cannot seed this rule without them. Nothing was changed."
            )
            return 1

        print(f"Restaurant: {restaurant.id} ({restaurant.name!r})")
        print(f"Server RestaurantRole id: {server_role.id}; Host RestaurantRole id: {host_role.id}")
        print(f"Mode: {mode}")
        print()

        existing = find_romes_flavours_server_host_rule(session, restaurant.id, server_role.id, host_role.id)
        if existing is not None:
            print(f"A SERVER -> HOST rule already exists (TipDistributionRule id={existing.id}) — nothing to do.")
            return 0

        locations = session.scalars(
            select(m.RestaurantLocation).where(m.RestaurantLocation.restaurant_id == restaurant.id)
        ).all()
        if not locations:
            print(f"Restaurant {restaurant.id} has no associated Location. Nothing to seed.")
            return 1

        effective_from = None
        for rl in locations:
            candidate = earliest_tip_evidence_at(session, location_id=rl.location_id)
            if candidate is not None and (effective_from is None or candidate < effective_from):
                effective_from = candidate

        if effective_from is None:
            print(
                "No PaymentTip evidence exists yet at any of this Restaurant's Locations — SKIPPED. "
                "No effective date was guessed; re-run this script once real Tip data exists."
            )
            return 1

        print(f"Earliest real Tip evidence across this Restaurant's Location(s): {effective_from.isoformat()}")
        print("Would seed: Source Role=Server, Recipient Role=Host, Calculation Base=TIP_PLUS_GRATUITY, Rate=10%")

        if mode == MODE_DRY_RUN:
            print()
            print("Dry run — nothing written. Re-run with --persist to write.")
            return 0

        rule = rule_svc.create_rule(
            session, restaurant_id=restaurant.id, source_role_id=server_role.id, recipient_role_id=host_role.id,
            calculation_base=m.CALC_BASE_TIP_PLUS_GRATUITY, rate=Decimal("10.0000"), effective_from=effective_from,
            created_by="seed_tip_distribution_rules.py",
        )
        session.commit()
        print(f"Seeded TipDistributionRule id={rule.id} (version 1).")
        return 0


if __name__ == "__main__":
    sys.exit(main())
