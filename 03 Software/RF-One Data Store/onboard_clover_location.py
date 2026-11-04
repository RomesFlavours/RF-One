#!/usr/bin/env python
"""Minimal Clover onboarding for a fresh target database (e.g. RDS DEV).

Creates only the canonical records `import_clover_period()` requires to run
at all: SourceSystem, Merchant, Location, Restaurant, RestaurantLocation.

This is NOT the Historical Backfill and NOT the full bulk ingestion pipeline
(`ingest_clover.py`) — Orders, Payments, Items, Employees and Shifts are
never touched here. It fetches only the Clover Merchant resource, live, via
the existing read-only Clover client/credentials
(`clover_explorer.config.load_config`), and reuses the exact canonical
upsert logic the rest of the connector already uses
(`ingest.ingest_merchant_and_location`).

Idempotent: re-running never creates a second SourceSystem, Merchant,
Location, Restaurant, or RestaurantLocation row for the same Clover account
— Merchant/Location are upserted by their existing source-identity unique
constraints, and Restaurant/RestaurantLocation are skipped once a
RestaurantLocation already links to the onboarded Location.

Usage:
    python onboard_clover_location.py                  # onboard against RDS DEV
    python onboard_clover_location.py --database-url sqlite:///path/to.db

Never prints the Clover API token, the RDS DEV password, or any other
secret value — only the redacted target URL and the resulting record ids.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from rfone_data_store import models as m
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    run_migrations_to_head,
)
from rfone_data_store.ingestion.common import utc_now
from rfone_data_store.technical.aws_secrets import get_rds_postgres_url
from rfone_data_store.technical.connectors.clover import enrichment, ingest
from rfone_data_store.technical.connectors.clover.onboarding import (
    onboard_merchant_and_location_live,
)

RDS_DEV_AWS_PROFILE = "rfone-dev-login"
RDS_DEV_AWS_REGION = "us-east-1"
RDS_DEV_SECRET_ID = "rfone-dev/rds/postgres"


def _resolve_target_url(explicit_url: str | None) -> str:
    if explicit_url:
        return explicit_url
    return get_rds_postgres_url(
        secret_id=RDS_DEV_SECRET_ID,
        profile_name=RDS_DEV_AWS_PROFILE,
        region_name=RDS_DEV_AWS_REGION,
    )


def _onboard_restaurant(session, location: m.Location, retrieved_at) -> tuple[int, bool]:
    """Returns `(restaurant_id, created)`. Idempotency anchor is the
    Location itself (unique per Clover account already): if any
    RestaurantLocation already links to it, reuse that Restaurant rather
    than creating a duplicate — RestaurantLocation carries no unique
    constraint of its own to rely on instead (task-approved: re-association
    after a gap is allowed by design, so only an existing-link check, not a
    DB constraint, can make this idempotent)."""
    existing_link = session.scalars(
        select(m.RestaurantLocation).filter_by(location_id=location.id)
    ).first()
    if existing_link is not None:
        return existing_link.restaurant_id, False

    restaurant = m.Restaurant(
        name=location.name or f"Clover Location {location.source_location_id}",
        default_currency=location.currency,  # never fabricated — None until real Order evidence exists
    )
    session.add(restaurant)
    session.flush()

    session.add(
        m.RestaurantLocation(
            restaurant_id=restaurant.id,
            location_id=location.id,
            valid_from=retrieved_at,
            is_primary=True,
        )
    )
    return restaurant.id, True


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override target DB URL (default: RDS DEV, resolved via AWS Secrets Manager)",
    )
    args = parser.parse_args()

    target_url = _resolve_target_url(args.database_url)
    print(f"Target database: {redact_database_url(target_url)}")

    print("Running migrations to head...")
    run_migrations_to_head(target_url)

    engine = create_configured_engine(target_url)
    session_factory = create_session_factory(engine)

    client = enrichment.get_client()
    retrieved_at = utc_now()

    merchant_id = location_id = restaurant_id = None
    restaurant_created = False

    with session_factory() as session:
        source_system = ingest.upsert(
            session, m.SourceSystem, {"code": "CLOVER"}, {"name": "Clover", "active": True}
        )
        session.flush()

        ingestion_run = m.IngestionRun(
            source_system_id=source_system.id,
            started_at=retrieved_at,
            status="RUNNING",
            notes="Minimal Clover onboarding (SourceSystem/Merchant/Location/"
            "Restaurant/RestaurantLocation only) — no Orders/Payments/Items.",
        )
        session.add(ingestion_run)
        session.flush()

        try:
            merchant_id, location_id = onboard_merchant_and_location_live(
                session, client, source_system.id, ingestion_run.id, retrieved_at
            )
            session.flush()

            location = session.get(m.Location, location_id)
            restaurant_id, restaurant_created = _onboard_restaurant(session, location, retrieved_at)

            ingestion_run.location_id = location_id
            ingestion_run.status = "COMPLETE"
            ingestion_run.finished_at = utc_now()
            session.commit()
        except Exception:  # noqa: BLE001 — a failed run must not be marked successful
            session.rollback()
            ingestion_run.status = "FAILED"
            ingestion_run.finished_at = utc_now()
            session.add(ingestion_run)
            session.commit()
            raise

    engine.dispose()

    print(
        f"SourceSystem id={source_system.id} | Merchant id={merchant_id} | "
        f"Location id={location_id} | Restaurant id={restaurant_id} "
        f"({'created' if restaurant_created else 'already onboarded'})"
    )
    print("Historical Backfill prerequisite satisfied: Location is Clover-sourced and resolvable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
