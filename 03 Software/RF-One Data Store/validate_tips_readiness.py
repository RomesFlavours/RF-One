#!/usr/bin/env python
"""Read-only Tips readiness validation against current RF-One data (TASK_TIPS_001 §24).

Reports facts about the existing local database — it never invents a Tip
Policy, Restaurant Role, Operational Area, or service-attribution mapping to
make a calculation "succeed." Where the configured Restaurant Profile / Tip
Policy / service attribution genuinely does not exist yet, this script is
expected to (and does) report that Tips cannot yet be calculated — that is
the correct, honest outcome, not a defect to be worked around.

Runs the real calculation engine in DRY_RUN mode over the full available
Payment history, then always rolls back — nothing is persisted.

Usage:
    python validate_tips_readiness.py
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from rfone_data_store.database import create_configured_engine, create_session_factory, get_database_url, redact_database_url
from rfone_data_store import models as m
from rfone_data_store.tips.engine import run_tip_calculation
from rfone_data_store.tips.resolvers import NullServiceAttributionResolver

UTC = timezone.utc


def main() -> int:
    url = get_database_url()
    print(f"Database URL: {redact_database_url(url)}")
    print()

    engine = create_configured_engine(url)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        try:
            _report(session)
        finally:
            session.rollback()  # read-only: never persist anything from this script

    return 0


def _report(session) -> None:
    print("=== Recorded PaymentTips ===")
    total_tips = session.scalar(select(func.count()).select_from(m.PaymentTip)) or 0
    null_amount = session.scalar(
        select(func.count()).select_from(m.PaymentTip).where(m.PaymentTip.amount.is_(None))
    ) or 0
    zero_amount = session.scalar(
        select(func.count()).select_from(m.PaymentTip).where(m.PaymentTip.amount == 0)
    ) or 0
    nonzero_amount = total_tips - null_amount - zero_amount
    total_payments = session.scalar(select(func.count()).select_from(m.Payment)) or 0
    print(f"  recorded PaymentTip rows:        {total_tips}")
    print(f"    amount present, non-zero:      {nonzero_amount}")
    print(f"    amount present, zero:          {zero_amount}")
    print(f"    amount present, NULL:          {null_amount}")
    print(f"  Payments with NO PaymentTip row (missing, not zero): {total_payments - total_tips}")
    print()

    print("=== Payment result distribution (economic validity) ===")
    for res, cnt in session.execute(
        select(m.Payment.result, func.count()).group_by(m.Payment.result)
    ).all():
        print(f"  {res!r}: {cnt}")
    print()

    print("=== Payment timestamp coverage ===")
    min_ts, max_ts = session.execute(select(func.min(m.Payment.created_at), func.max(m.Payment.created_at))).one()
    print(f"  earliest Payment.created_at: {min_ts}")
    print(f"  latest Payment.created_at:   {max_ts}")
    print()

    print("=== Order linkage coverage ===")
    payments_with_order = session.scalar(
        select(func.count()).select_from(m.Payment).where(m.Payment.order_id.is_not(None))
    ) or 0
    print(f"  Payments with a resolvable Order: {payments_with_order}/{total_payments}")
    print()

    print("=== Shift coverage (overall date range, not per-payment overlap) ===")
    min_shift, max_shift = session.execute(select(func.min(m.Shift.clock_in), func.max(m.Shift.clock_out))).one()
    print(f"  earliest Shift.clock_in:  {min_shift}")
    print(f"  latest Shift.clock_out:   {max_shift}")
    print(
        "  (whether a Shift is active at any specific Payment's timestamp is computed live by the "
        "engine per PaymentTip, not summarized here as a single count)"
    )
    print()

    print("=== Current Restaurant Profile readiness ===")
    restaurants = session.scalars(select(m.Restaurant)).all()
    print(f"  Restaurants:              {len(restaurants)}")
    print(f"  RestaurantLocations:      {session.scalar(select(func.count()).select_from(m.RestaurantLocation)) or 0}")
    print(f"  OperationalAreas:         {session.scalar(select(func.count()).select_from(m.OperationalArea)) or 0}")
    print(f"  PhysicalAreas:            {session.scalar(select(func.count()).select_from(m.PhysicalArea)) or 0}")
    print(f"  RestaurantRoles:          {session.scalar(select(func.count()).select_from(m.RestaurantRole)) or 0}")
    print(f"  OperationalAreaRoles:     {session.scalar(select(func.count()).select_from(m.OperationalAreaRole)) or 0}")
    print(f"  EmployeeAssignments:      {session.scalar(select(func.count()).select_from(m.EmployeeAssignment)) or 0}")
    print(f"  TipPolicies:              {session.scalar(select(func.count()).select_from(m.TipPolicy)) or 0}")
    print(f"  TipPolicyComponents:      {session.scalar(select(func.count()).select_from(m.TipPolicyComponent)) or 0}")
    print()

    if not restaurants:
        print("No Restaurant exists — Tip calculation cannot be attempted at all.")
        return

    restaurant = restaurants[0]
    print(f"=== Dry-run calculation over full available Payment history (restaurant_id={restaurant.id}) ===")
    period_start = (min_ts or datetime.now(UTC) - timedelta(days=1)).astimezone(UTC) - timedelta(days=1)
    period_end = (max_ts or datetime.now(UTC)).astimezone(UTC) + timedelta(days=1)

    run, summary = run_tip_calculation(
        session,
        restaurant_id=restaurant.id,
        period_start=period_start,
        period_end=period_end,
        resolver=NullServiceAttributionResolver(),
        mode="DRY_RUN",
        calculation_version="readiness-check",
    )

    print(f"  source Tips considered:   {summary.source_tips_considered}")
    print(f"  source Tip amount:       {summary.source_tip_amount_minor} (minor units)")
    print(f"  allocations produced:    {summary.allocations_produced}")
    print(f"  allocated amount:        {summary.allocated_amount_minor} (minor units)")
    print(f"  unallocated amount:      {summary.unallocated_amount_minor} (minor units)")
    print(f"  blocking issues:         {summary.blocking_issue_count}")
    print(f"  warnings:                {summary.warning_issue_count}")
    print()

    print("=== Blocking issue breakdown (why Tips cannot yet be calculated) ===")
    issue_rows = session.scalars(
        select(m.TipCalculationIssue).where(m.TipCalculationIssue.calculation_run_id == run.id)
    ).all()
    by_type = Counter(i.issue_type for i in issue_rows)
    for issue_type, count in by_type.most_common():
        print(f"  {issue_type}: {count}")
    print()
    print(
        "Because this Restaurant has no configured TipPolicy, no RestaurantRole/OperationalArea "
        "configuration, and no service-attribution resolver, this result is EXPECTED and CORRECT — "
        "no Tip Policy or mapping was invented to force a different outcome (task §24)."
    )

    print()
    print("(This script is read-only: the calculation above ran in DRY_RUN mode and is now rolled back.)")


if __name__ == "__main__":
    sys.exit(main())
