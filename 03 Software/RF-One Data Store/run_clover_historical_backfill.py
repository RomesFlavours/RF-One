#!/usr/bin/env python
"""Invokes the EXISTING Clover Historical Backfill
(`technical.connectors.clover.acquisition.import_clover_period`) for a
single operator-chosen date range against a target database.

This is a thin caller, not a new ingestion implementation — it contains no
fetch/mapping/upsert logic of its own. It mirrors exactly the same
period-parsing semantics `03 Software/Tips/app.py`'s `/historical-backfill`
route already uses (`datetime.strptime(..., "%Y-%m-%d").replace(tzinfo=UTC)`,
`period_end` inclusive through 23:59:59 of the Through day), so a range
requested here means exactly what it would mean through that UI.

Usage:
    python run_clover_historical_backfill.py --from-date 2026-08-28 --through-date 2026-08-29
    python run_clover_historical_backfill.py --from-date 2026-08-28 --through-date 2026-08-29 --database-url sqlite:///...

Never prints the Clover API token, the RDS password, or any other secret
value.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from datetime import datetime, timezone

from sqlalchemy import select

from rfone_data_store import models as m
from rfone_data_store.database import (
    create_configured_engine,
    create_session_factory,
    redact_database_url,
    run_migrations_to_head,
)
from rfone_data_store.technical.aws_secrets import get_rds_postgres_url
from rfone_data_store.technical.connectors.clover.acquisition import (
    MODE_BACKFILL,
    ImportAlreadyRunningError,
    import_clover_period,
)

UTC = timezone.utc

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


def _parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)


def _resolve_clover_location_id(session) -> int | None:
    """Same join `Tips/app.py`'s `_resolve_clover_location_id` uses —
    Restaurant -> RestaurantLocation -> Location, filtered to a
    Clover-sourced SourceSystem. This connector itself has no concept of
    Restaurant; that resolution belongs to the caller, same as it already
    does in Tips."""
    return session.scalars(
        select(m.Location.id)
        .join(m.RestaurantLocation, m.RestaurantLocation.location_id == m.Location.id)
        .join(m.SourceSystem, m.SourceSystem.id == m.Location.source_system_id)
        .where(m.SourceSystem.code == "CLOVER")
    ).first()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--from-date", required=True, help="YYYY-MM-DD (inclusive)")
    parser.add_argument("--through-date", required=True, help="YYYY-MM-DD (inclusive)")
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override target DB URL (default: RDS DEV, resolved via AWS Secrets Manager)",
    )
    args = parser.parse_args()

    start = _parse_date(args.from_date)
    end = _parse_date(args.through_date)
    if end < start:
        print("Through date must not be before From date.", file=sys.stderr)
        return 2
    end = end.replace(hour=23, minute=59, second=59)  # inclusive through end of Through day

    target_url = _resolve_target_url(args.database_url)
    print(f"Target database: {redact_database_url(target_url)}")
    print("Running migrations to head...")
    run_migrations_to_head(target_url)

    engine = create_configured_engine(target_url)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        location_id = _resolve_clover_location_id(session)
        if location_id is None:
            print(
                "No Clover-sourced Location is configured — run onboarding first.",
                file=sys.stderr,
            )
            return 1

        print(f"location_id={location_id} | period_start={start.isoformat()} | period_end={end.isoformat()}")

        try:
            summary = import_clover_period(
                session, location_id=location_id, period_start=start, period_end=end, mode=MODE_BACKFILL,
            )
        except ImportAlreadyRunningError:
            print("Another Clover acquisition is already RUNNING for this Location.", file=sys.stderr)
            return 1
        session.commit()

    engine.dispose()

    data = asdict(summary)
    data["period_start"] = summary.period_start.isoformat()
    data["period_end"] = summary.period_end.isoformat()
    for key, value in data.items():
        print(f"  {key}: {value}")

    if summary.errors:
        print("Status: COMPLETED WITH ERRORS")
        return 1

    print("Status: COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
