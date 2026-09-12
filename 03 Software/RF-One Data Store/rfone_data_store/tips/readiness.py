"""Tip payout Process Activation / readiness (TASK_TIPS_CORE2_PILOT §4;
Core 2.0 `00 Core/ConceptualArchitecture/13_Process_Activation_and_Trigger_
Intelligence.md`).

Exposes ONE channel-independent question — "is there a Business Date ready
to be calculated/paid out, and what state is it in?" — callable identically
from the existing Flask UI, a script, a future scheduler, or a future
Cognito Trigger Intelligence capability (`00 Core/ImplementationGuidelines.
md`, "Channel Independence"). No scheduler, cron expression, or "run at
02:00" rule is defined here — the Business Date being fully settled (no
newer Order data expected to still arrive for it) is a deterministic fact
derivable from already-persisted Clover data today; per Core 2.0 §5
("Time is just an event"), this module treats readiness as a data
condition, never a wall-clock rule, so it composes without change with a
future Trigger Intelligence that recognizes the SAME condition from an
observed event instead of from a caller asking on demand.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from . import distribution_engine as engine_svc

UTC = timezone.utc


def business_date_period(business_date: date) -> tuple[datetime, datetime]:
    """A single Business Date as a `[period_start, period_end)` pair, in the
    same EXCLUSIVE-at-end convention `distribution_engine` already uses
    (Tips/app.py's `_calculation_period`) — one calendar day."""
    start = datetime(business_date.year, business_date.month, business_date.day, tzinfo=UTC)
    return start, start + timedelta(days=1)


def get_latest_business_date_with_orders(session: Session, restaurant_id: int) -> date | None:
    """The latest operational Business Date (`Order.business_date`) already
    on file for this Restaurant — the same canonical field Tips/app.py's
    `_max_order_business_date` already reads, exposed here as a reusable
    Domain-layer fact rather than an app-local helper, so it is usable
    outside the Flask request/response cycle."""
    location_ids_subq = select(m.RestaurantLocation.location_id).where(
        m.RestaurantLocation.restaurant_id == restaurant_id
    )
    return session.scalars(
        select(func.max(m.Order.business_date)).where(m.Order.location_id.in_(location_ids_subq))
    ).first()


@dataclass
class BusinessDateReadiness:
    business_date: date | None
    has_orders: bool
    calculation_run: "m.TipDistributionCalculationRun | None"
    already_calculated: bool
    payment_instructions_total: int
    payment_instructions_needing_attention: int
    payment_instructions_verified: int
    ready_to_calculate: bool
    ready_to_submit_payouts: bool
    fully_settled: bool


def describe_readiness(session: Session, restaurant_id: int) -> BusinessDateReadiness:
    """The one entry point a Process Activation caller needs: what is the
    candidate Business Date, what condition makes it ready, and has it
    already been processed / does it need to be resumed (task §4's explicit
    checklist). Never mutates anything — pure read."""
    business_date = get_latest_business_date_with_orders(session, restaurant_id)
    if business_date is None:
        return BusinessDateReadiness(
            business_date=None, has_orders=False, calculation_run=None, already_calculated=False,
            payment_instructions_total=0, payment_instructions_needing_attention=0,
            payment_instructions_verified=0, ready_to_calculate=False, ready_to_submit_payouts=False,
            fully_settled=False,
        )

    period_start, period_end = business_date_period(business_date)
    run = engine_svc.get_latest_unsuperseded_run(
        session, restaurant_id=restaurant_id, period_start=period_start, period_end=period_end,
    )
    already_calculated = run is not None

    instructions: list[m.TipPaymentInstruction] = []
    if run is not None:
        instructions = list(
            session.scalars(
                select(m.TipPaymentInstruction).where(m.TipPaymentInstruction.calculation_run_id == run.id)
            )
        )
    needing_attention = sum(1 for i in instructions if i.status == "NEEDS_ATTENTION")
    verified = sum(1 for i in instructions if i.status == "OUTCOME_VERIFIED")

    fully_settled = already_calculated and bool(instructions) and verified == len(instructions)

    return BusinessDateReadiness(
        business_date=business_date, has_orders=True, calculation_run=run, already_calculated=already_calculated,
        payment_instructions_total=len(instructions), payment_instructions_needing_attention=needing_attention,
        payment_instructions_verified=verified,
        ready_to_calculate=not already_calculated,
        ready_to_submit_payouts=already_calculated and not fully_settled,
        fully_settled=fully_settled,
    )
