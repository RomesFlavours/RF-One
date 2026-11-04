#!/usr/bin/env python
"""Restaurant Profile bootstrap/sync from Clover source configuration
(TASK_RESTAURANT_003).

Populates the Restaurant Profile (root Operational Area, RestaurantRoles,
explicit SourceRole->RestaurantRole mappings, prospective EmployeeAssignments
from an explicit T0) from the already-ingested canonical `Employee`/
`SourceRole`/`EmployeeSourceRole` facts for a Restaurant. Never talks to
Clover directly (see `03 Software/Clover Data Explorer/
fetch_profile_bootstrap_snapshot.py` for the optional fresh, read-only
live-congruence snapshot this command can additionally use).

Defaults to safe, read-only dry-run behavior: the bootstrap/sync always
runs and its results are computed and printed, but nothing is committed to
the database unless `--persist` is explicitly passed.

Usage:
    python bootstrap_restaurant_profile.py --restaurant-id 1 [--persist]
    python bootstrap_restaurant_profile.py --restaurant-id 1 --use-snapshot [--persist]

Never prints Employee names — only counts (task §15).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from rfone_data_store.database import create_configured_engine, create_session_factory
from rfone_data_store import models as m
from rfone_data_store.profile.bootstrap import (
    MODE_DRY_RUN,
    MODE_PERSIST,
    bootstrap_restaurant_profile,
)
from rfone_data_store.profile.source_snapshot import load_latest_snapshot
from sqlalchemy import select

UTC = timezone.utc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--restaurant-id", type=int, required=True)
    parser.add_argument("--source-system-code", default="CLOVER")
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Commit the bootstrap run/mappings/roles/assignments/issues. Default is dry-run (rolled back).",
    )
    parser.add_argument(
        "--use-snapshot",
        action="store_true",
        help=(
            "Cross-check against the latest fresh Clover snapshot saved by "
            "fetch_profile_bootstrap_snapshot.py, if one exists."
        ),
    )
    args = parser.parse_args()

    engine = create_configured_engine()
    session_factory = create_session_factory(engine)

    fresh_snapshot = load_latest_snapshot() if args.use_snapshot else None
    if args.use_snapshot and fresh_snapshot is None:
        print("--use-snapshot requested but no fresh Clover snapshot was found; continuing without it.")

    sync_time = datetime.now(UTC)

    with session_factory() as session:
        source_system = session.scalars(
            select(m.SourceSystem).where(m.SourceSystem.code == args.source_system_code)
        ).first()
        if source_system is None:
            print(f"No SourceSystem with code={args.source_system_code!r} found.")
            return 1

        run, summary = bootstrap_restaurant_profile(
            session,
            restaurant_id=args.restaurant_id,
            source_system_id=source_system.id,
            mode=MODE_PERSIST if args.persist else MODE_DRY_RUN,
            sync_time=sync_time,
            fresh_snapshot=fresh_snapshot,
        )

        print(f"Bootstrap run id: {run.id} (mode={run.mode}, status={run.status})")
        print(f"  T0 / managed_from:              {summary.managed_from.isoformat() if summary.managed_from else None} (created this run: {summary.t0_created})")
        print(f"  current source Employees:       {summary.current_source_employees}")
        print(f"  historical stubs skipped:       {summary.historical_stubs_skipped}")
        print(f"  current SourceRoles:            {summary.current_source_roles}")
        print(f"  SourceRole->RestaurantRole mappings: created={summary.mappings_created} reused={summary.mappings_reused}")
        print(f"  RestaurantRoles:                 created={summary.restaurant_roles_created} reused={summary.restaurant_roles_reused}")
        print(f"  OperationalAreas:                 created={summary.operational_areas_created} reused={summary.operational_areas_reused}")
        print(f"  EmployeeAssignments:              created={summary.assignments_created} reused={summary.assignments_reused} closed={summary.assignments_closed}")
        print(f"  reconciliation issues:            created={summary.issues_created} reused={summary.issues_reused} (blocking={summary.blocking_issue_count} warning={summary.warning_issue_count})")
        print(f"  fresh snapshot used:              {summary.snapshot_used} (fetched_at={summary.snapshot_fetched_at.isoformat() if summary.snapshot_fetched_at else None})")

        if args.persist:
            session.commit()
            print("Persisted.")
        else:
            session.rollback()
            print("Dry run — nothing was persisted (pass --persist to commit).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
