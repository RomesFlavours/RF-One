#!/usr/bin/env python
"""Post-hoc Tip calculation entry point (TASK_TIPS_001 §27).

RF-One does not observe or control the POS at payment time. This calculates
Tips later, from already-persisted source facts, for a requested Restaurant
and period.

Usage:
    python calculate_tips.py --restaurant-id 1 \\
        --period-start 2026-06-01 --period-end 2026-07-01 \\
        [--persist]

Defaults to safe, read-only dry-run behavior: the calculation always runs
and its results are computed and printed, but nothing is committed to the
database unless `--persist` is explicitly passed.

Service attribution: this task does not configure a real Restaurant service-
attribution resolver (task §22 restriction). By default this CLI uses
`NullServiceAttributionResolver`, which always reports UNRESOLVED — the
correct, honest behavior until a Restaurant/Product-Owner-specific resolver
is configured and wired in by a future task.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from rfone_data_store.database import create_configured_engine, create_session_factory
from rfone_data_store.tips.engine import MODE_DRY_RUN, MODE_PERSIST, run_tip_calculation
from rfone_data_store.tips.resolvers import NullServiceAttributionResolver

UTC = timezone.utc


def _parse_datetime(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--restaurant-id", type=int, required=True)
    parser.add_argument("--period-start", type=_parse_datetime, required=True, help="ISO 8601, e.g. 2026-06-01")
    parser.add_argument("--period-end", type=_parse_datetime, required=True, help="ISO 8601, exclusive upper bound")
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Commit the calculation run/allocations/issues. Default is dry-run (rolled back).",
    )
    parser.add_argument(
        "--calculation-version",
        default="1",
        help="Free-form label recorded on the run for reproducibility (task §28).",
    )
    args = parser.parse_args()

    engine = create_configured_engine()
    session_factory = create_session_factory(engine)

    resolver = NullServiceAttributionResolver()

    with session_factory() as session:
        run, summary = run_tip_calculation(
            session,
            restaurant_id=args.restaurant_id,
            period_start=args.period_start,
            period_end=args.period_end,
            resolver=resolver,
            mode=MODE_PERSIST if args.persist else MODE_DRY_RUN,
            calculation_version=args.calculation_version,
        )

        print(f"Calculation run id: {run.id} (mode={run.mode}, status={run.status})")
        print(f"  source Tips considered:  {summary.source_tips_considered}")
        print(f"  source Tip amount:       {summary.source_tip_amount_minor} (minor units)")
        print(f"  allocations produced:    {summary.allocations_produced}")
        print(f"  allocated amount:        {summary.allocated_amount_minor} (minor units)")
        print(f"  unallocated amount:      {summary.unallocated_amount_minor} (minor units)")
        print(f"  blocking issues:         {summary.blocking_issue_count}")
        print(f"  warnings:                {summary.warning_issue_count}")

        if args.persist:
            session.commit()
            print("Persisted.")
        else:
            session.rollback()
            print("Dry run — nothing was persisted (pass --persist to commit).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
