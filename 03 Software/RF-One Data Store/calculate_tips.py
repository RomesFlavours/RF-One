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

Service attribution (TASK_TIPS_004): this CLI now defaults to
`OrderEmployeeServiceAttributionResolver` — the first real, Restaurant-
configurable resolver, built entirely from canonical Sales evidence
(`Order.employee_id`, cross-checked against `Payment.employee_id`; see
`rfone_data_store/tips/resolvers.py`). Pass `--resolver null` to fall back to
the always-UNRESOLVED `NullServiceAttributionResolver` (e.g. to preview a
run's ROLE_PRESENT_AT_PAYMENT-only behavior without any SERVICE_OWNER
allocation).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from rfone_data_store.database import create_configured_engine, create_session_factory
from rfone_data_store.tips.engine import MODE_DRY_RUN, MODE_PERSIST, run_tip_calculation
from rfone_data_store.tips.resolvers import NullServiceAttributionResolver, OrderEmployeeServiceAttributionResolver

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
    parser.add_argument(
        "--supersedes-run-id",
        type=int,
        default=None,
        help=(
            "Explicitly supersede a prior COMPLETE PERSIST run for this Restaurant/period "
            "(a deliberate correction/redo). Without this, --persist over a period an existing, "
            "unsuperseded PERSIST run already covers is refused (idempotency safeguard) — see "
            "run_tip_calculation() in rfone_data_store/tips/engine.py."
        ),
    )
    parser.add_argument(
        "--resolver", choices=["order_employee", "null"], default="order_employee",
        help="Service-attribution resolver to use (TASK_TIPS_004). 'order_employee' (default) is the "
        "real resolver; 'null' always reports UNRESOLVED (no SERVICE_OWNER allocation).",
    )
    args = parser.parse_args()

    engine = create_configured_engine()
    session_factory = create_session_factory(engine)

    resolver = NullServiceAttributionResolver() if args.resolver == "null" else OrderEmployeeServiceAttributionResolver()

    with session_factory() as session:
        run, summary = run_tip_calculation(
            session,
            restaurant_id=args.restaurant_id,
            period_start=args.period_start,
            period_end=args.period_end,
            resolver=resolver,
            mode=MODE_PERSIST if args.persist else MODE_DRY_RUN,
            calculation_version=args.calculation_version,
            supersedes_run_id=args.supersedes_run_id,
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
            if run.status == "FAILED":
                session.rollback()
                print(
                    "Refused: this PERSIST run failed (see blocking issues above) and nothing was "
                    "persisted. If this is a deliberate correction/redo of an existing run, re-run "
                    "with --supersedes-run-id=<that run's id>."
                )
                return 1
            session.commit()
            print("Persisted.")
        else:
            session.rollback()
            print("Dry run — nothing was persisted (pass --persist to commit).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
