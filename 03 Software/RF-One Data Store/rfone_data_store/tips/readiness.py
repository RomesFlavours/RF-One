"""Tip CALCULATION Process Activation / readiness (TASK_TIPS_CORE2_PILOT §4;
Core 2.0 `00 Core/ConceptualArchitecture/13_Process_Activation_and_Trigger_
Intelligence.md`; STEP 12A Clover Correction/Reconciliation Sync; STEP 12B
integration).

Exposes ONE channel-independent question — "is there a Business Date ready
to be CALCULATED, and what state is it in?" — callable identically from the
existing Flask UI, a script, `tips/scheduler.py`'s automatic calculation
loop, or a future Cognito Trigger Intelligence capability (`00 Core/
ImplementationGuidelines.md`, "Channel Independence"). No scheduler, cron
expression, or "run at 02:00" rule is defined here — the Business Date being
fully settled (no newer Order data expected to still arrive for it) is a
deterministic fact derivable from already-persisted Clover data today; per
Core 2.0 §5 ("Time is just an event"), this module treats readiness as a
data condition, never a wall-clock rule, so it composes without change with
a future Trigger Intelligence that recognizes the SAME condition from an
observed event instead of from a caller asking on demand.

PAYMENT readiness is a SEPARATE concept, deliberately not answered here
(TASK_TIPS_COMPLETE_001 §2/§4: Calculation Schedule != Payment Schedule) —
see `tips/payment_readiness.describe_payment_readiness` for "is it safe to
Approve & Pay a Payment Cycle right now," and `tips/payment_cycle_service.
describe_payment_cycle_readiness` for "is there an unpaid balance ready to
be aggregated into one." Both REUSE, never re-derive, THIS module's own
canonical Clover Correction/Reconciliation Sync gate below — STEP 12B
integration audit: no duplicate Clover gate anywhere in this Domain.

STEP 12B integration note: `BusinessDateReadiness` previously (TASK_TIPS_
CORE2_PILOT) also carried `payment_instructions_total`/
`payment_instructions_needing_attention`/`payment_instructions_verified`/
`fully_settled`/`ready_to_submit_payouts`, derived from `TipPaymentInstruction.
calculation_run_id` — a column that no longer exists once Tips adopted the
Payment Cycle model (a Payment Instruction now aggregates MANY calculation
runs via `TipEntitlement`, so "this run's own payment instructions" is no
longer a coherent question at all). Those fields are removed here, not
preserved: the underlying schema they read is gone by construction of the
approved Payment Cycle schema change, and the settlement question they
answered now belongs to the Payment Cycle level (`payment_cycle_service.
describe_payment_cycle_readiness`), never re-derived per-Business-Date.
`ready_to_calculate`/`reconciliation_ready`/`reconciliation_reason` below —
the actual Clover Correction/Reconciliation Sync gate this note exists to
protect — are otherwise UNCHANGED from current main.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from ..technical.connectors.clover.correction_sync import describe_reconciliation_status
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
    ready_to_calculate: bool
    # CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md §7 — Tips privileges
    # consolidation over freshness: `reconciliation_ready` reflects whether
    # this Business Date's Clover data has had the opportunity to pass
    # through both the Fast Live Extractor and the Correction/Reconciliation
    # Poller (`technical.connectors.clover.correction_sync.
    # describe_reconciliation_status`). `reconciliation_reason` is the
    # human-readable "why" — never used to gate anything itself.
    reconciliation_ready: bool
    reconciliation_reason: str


def _restaurant_location_ids(session: Session, restaurant_id: int) -> list[int]:
    return list(
        session.scalars(
            select(m.RestaurantLocation.location_id).where(m.RestaurantLocation.restaurant_id == restaurant_id)
        )
    )


def describe_readiness(session: Session, restaurant_id: int) -> BusinessDateReadiness:
    """The one entry point a Process Activation caller needs: what is the
    candidate Business Date, what condition makes it ready, and has it
    already been processed / does it need to be resumed (task §4's explicit
    checklist). Never mutates anything — pure read."""
    business_date = get_latest_business_date_with_orders(session, restaurant_id)
    if business_date is None:
        return BusinessDateReadiness(
            business_date=None, has_orders=False, calculation_run=None, already_calculated=False,
            ready_to_calculate=False, reconciliation_ready=False,
            reconciliation_reason="no Business Date candidate yet",
        )

    period_start, period_end = business_date_period(business_date)
    run = engine_svc.get_latest_unsuperseded_run(
        session, restaurant_id=restaurant_id, period_start=period_start, period_end=period_end,
    )
    already_calculated = run is not None

    reconciliation = describe_reconciliation_status(
        session, location_ids=_restaurant_location_ids(session, restaurant_id), period_end=period_end,
    )

    return BusinessDateReadiness(
        business_date=business_date, has_orders=True, calculation_run=run, already_calculated=already_calculated,
        ready_to_calculate=not already_calculated and reconciliation.ready,
        reconciliation_ready=reconciliation.ready, reconciliation_reason=reconciliation.reason,
    )
