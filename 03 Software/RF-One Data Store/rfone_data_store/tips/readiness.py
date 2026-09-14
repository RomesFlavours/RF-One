"""Tip Calculation readiness — Process Activation / Trigger Intelligence
(TASK_TIPS_CORE2_PILOT §4; TASK_TIPS_COMPLETE_001 §5; Core 2.0 `00 Core/
ConceptualArchitecture/13_Process_Activation_and_Trigger_Intelligence.md`).

Exposes ONE channel-independent question — "is there a Business Date ready
to be CALCULATED, and what state is it in?" — callable identically from the
existing Flask UI, a script, `tips/scheduler.py`'s automatic calculation
loop, or a future Cognito Trigger Intelligence capability (`00 Core/
ImplementationGuidelines.md`, "Channel Independence"). No scheduler, cron
expression, or "run at 02:00" rule is defined here — the Business Date being
fully settled (no newer Order data expected to still arrive for it) is a
deterministic fact derivable from already-persisted Clover data today; per
Core 2.0 §5 ("Time is just an event"), this module treats readiness as a
data condition, never a wall-clock rule.

PAYMENT readiness is a SEPARATE concept, deliberately not answered here
(TASK_TIPS_COMPLETE_001 §2/§4: Calculation Schedule != Payment Schedule) —
see `tips/payment_cycle_service.describe_payment_cycle_readiness` for "is
there an unpaid balance ready to be aggregated into a Payment Cycle."

Clover readiness gate (§5): automatic calculation must never start just
because the scheduled time arrived — `ready_to_calculate` additionally
requires that this Restaurant's Clover-sourced Location(s) have a Live Sync/
Backfill cursor (`IngestionRun.source_window_end`) that has already reached
PAST this Business Date's own end. This is intentionally the Live Cursor
only (this baseline predates the separate, approved Correction/
Reconciliation Poller architecture decision — CLOVER_CONTINUOUS_
SYNCHRONIZATION_ARCHITECTURE.md — which is not implemented on this branch);
see this task's own final report "Known gaps" for what a fuller
reconciliation-based gate would add. Cognito's own live operational
freshness (seconds-scale) and this consolidation gate (Business-Date-scale)
remain distinct concepts, never conflated (§21; see also `01 Domains/
Business Domain/Restaurant/Tips/Tips Payment Execution.md`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from . import distribution_engine as engine_svc

UTC = timezone.utc


def _aware_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


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


def _restaurant_location_ids(session: Session, restaurant_id: int) -> list[int]:
    return list(
        session.scalars(
            select(m.RestaurantLocation.location_id).where(m.RestaurantLocation.restaurant_id == restaurant_id)
        )
    )


def _clover_live_sync_readiness(
    session: Session, *, location_ids: list[int], period_end: datetime,
) -> tuple[bool, str]:
    """True (with a reason) when this Business Date's Clover-sourced data
    has had the opportunity to be fully acquired: every Clover-sourced
    Location among `location_ids` has a COMPLETE/PARTIAL Live Sync/Backfill
    run (`technical.connectors.clover.acquisition`/`live_sync`) whose own
    `source_window_end` has already reached `period_end`. A Location with no
    Clover source at all (never onboarded, or a non-Clover Restaurant) is
    skipped — nothing to gate on for it, matching this codebase's existing
    graceful-bypass convention for non-Clover Locations elsewhere (e.g.
    `freshness.ensure_clover_data_fresh`)."""
    if not location_ids:
        return False, "no Location resolved for this Restaurant"

    any_clover_location = False
    for location_id in location_ids:
        location = session.get(m.Location, location_id)
        if location is None or location.source_location_id is None:
            continue
        source_system = session.get(m.SourceSystem, location.source_system_id)
        if source_system is None or source_system.code != "CLOVER":
            continue
        any_clover_location = True

        run = session.scalars(
            select(m.IngestionRun)
            .where(
                m.IngestionRun.location_id == location_id,
                m.IngestionRun.source_system_id == source_system.id,
                m.IngestionRun.status.in_(("COMPLETE", "PARTIAL")),
                m.IngestionRun.source_window_end.is_not(None),
            )
            .order_by(m.IngestionRun.id.desc())
            .limit(1)
        ).first()
        if run is None:
            return False, f"location_id={location_id}: no successful Clover Live Sync/Backfill run yet"
        cursor_end = _aware_utc(run.source_window_end)
        if cursor_end < period_end:
            return False, (
                f"location_id={location_id}: Clover Live Sync cursor at {cursor_end.isoformat()} has not "
                f"yet reached this Business Date's end ({period_end.isoformat()})"
            )

    if not any_clover_location:
        return True, "no Clover-sourced Location for this Restaurant — nothing to gate on"
    return True, "Clover Live Sync/Backfill has passed this Business Date for every Clover-sourced Location"


@dataclass
class BusinessDateReadiness:
    business_date: date | None
    has_orders: bool
    calculation_run: "m.TipDistributionCalculationRun | None"
    already_calculated: bool
    clover_ready: bool
    clover_reason: str
    ready_to_calculate: bool


def describe_readiness(session: Session, restaurant_id: int) -> BusinessDateReadiness:
    """The one entry point a Process Activation caller needs for
    CALCULATION: what is the candidate Business Date, has it already been
    calculated, and is Clover data for it ready. Never mutates anything —
    pure read. See the module docstring for why PAYMENT readiness is a
    separate function in a separate module."""
    business_date = get_latest_business_date_with_orders(session, restaurant_id)
    if business_date is None:
        return BusinessDateReadiness(
            business_date=None, has_orders=False, calculation_run=None, already_calculated=False,
            clover_ready=False, clover_reason="no Business Date candidate yet", ready_to_calculate=False,
        )

    period_start, period_end = business_date_period(business_date)
    run = engine_svc.get_latest_unsuperseded_run(
        session, restaurant_id=restaurant_id, period_start=period_start, period_end=period_end,
    )
    already_calculated = run is not None

    clover_ready, clover_reason = _clover_live_sync_readiness(
        session, location_ids=_restaurant_location_ids(session, restaurant_id), period_end=period_end,
    )

    return BusinessDateReadiness(
        business_date=business_date, has_orders=True, calculation_run=run, already_calculated=already_calculated,
        clover_ready=clover_ready, clover_reason=clover_reason,
        ready_to_calculate=not already_calculated and clover_ready,
    )
