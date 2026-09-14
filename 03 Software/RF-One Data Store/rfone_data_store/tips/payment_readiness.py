"""Tip PAYMENT Readiness — the reconciliation-aware gate before Approve & Pay
(CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md §3/§7;
TASK_TIPS_RECONCILIATION_AND_PAYMENT_CONTROL_001).

Distinct from `tips/readiness.py`'s CALCULATION readiness ("is there a
Business Date ready to be calculated") — that module's own docstring already
names this exact gap: "PAYMENT readiness is a SEPARATE concept... this
baseline predates the separate, approved Correction/Reconciliation Poller
architecture decision... which is not implemented on this branch." This
module closes it.

The question this module answers: given a Restaurant (and, implicitly, the
Payment Cycle about to be Approved & Paid for it), is it safe to actually
send money —

    Clover live healthy (Live Sync/Backfill is running and succeeding, not
    silently dead) AND reconciliation recent and successful (the Correction/
    Reconciliation Poller has, within a bounded staleness window, checked
    this Restaurant's Clover-sourced Location(s) for corrections and found
    none it could not apply) AND no blocking (CRITICAL) Attention pertinent
    to this Restaurant's Tips payout.

Channel-independent (`00 Core/ImplementationGuidelines.md`, "Channel
Independence"): the Web Payment Control, a future Cognito capability, and
`tips/scheduler.py`'s automatic AUTO WITHOUT APPROVAL path all call this
SAME function before Approve & Pay — never a route/template-local
readiness check (task §9's explicit boundary).

`NOT READY` here is a normal, expected, non-alarming outcome — reconciliation
being stale or still catching up is an ordinary waiting condition, never
itself treated as a financial error (task §3's explicit instruction). Only
a PERSISTENTLY failing reconciliation (`is_persistently_failing` below)
warrants human Attention — raised by `tips.payment_cycle_service.
maybe_raise_attention_for_payment_readiness`, reusing the existing Attention
Management capability, never a Tips-specific escalation mechanism."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m

UTC = timezone.utc

# "Recent enough" for a Correction/Reconciliation Poller run (default cadence
# ~60s, CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md §3) or a Live Sync
# run (default cadence ~15s) to still count as healthy/fresh. Generous
# relative to either cadence so a single missed tick, or the brief gap while
# another acquisition holds the shared Location lock, never flips payment
# readiness — only a genuinely stalled poller does. Configurable per call,
# never hardcoded into a route/template (task §9).
DEFAULT_STALENESS_THRESHOLD = timedelta(minutes=5)

# How long reconciliation may remain non-fresh/failed before it is escalated
# to a human via Attention Management, rather than treated as an ordinary,
# silent "still catching up" wait (task §3, §11 — "NON trattarlo
# automaticamente come errore finanziario" / "se reconciliation fallisce
# persistentemente... usa Attention Management esistente").
DEFAULT_PERSISTENT_FAILURE_THRESHOLD = timedelta(minutes=30)

RECONCILIATION_STATUS_FRESH = "FRESH"
RECONCILIATION_STATUS_STALE = "STALE"
RECONCILIATION_STATUS_FAILED = "FAILED"
RECONCILIATION_STATUS_INCOMPLETE = "INCOMPLETE"
RECONCILIATION_STATUS_NOT_APPLICABLE = "NOT_APPLICABLE"


def _aware_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _restaurant_location_ids(session: Session, restaurant_id: int) -> list[int]:
    return list(
        session.scalars(
            select(m.RestaurantLocation.location_id).where(m.RestaurantLocation.restaurant_id == restaurant_id)
        )
    )


def _clover_location_ids(session: Session, location_ids: list[int]) -> list[int]:
    """Among `location_ids`, only those actually Clover-sourced (onboarded
    with an external identifier) — a non-Clover Location has nothing to
    gate on, matching this codebase's existing graceful-bypass convention
    (`readiness._clover_live_sync_readiness`, `freshness.
    ensure_clover_data_fresh`)."""
    result: list[int] = []
    for location_id in location_ids:
        location = session.get(m.Location, location_id)
        if location is None or location.source_location_id is None:
            continue
        source_system = session.get(m.SourceSystem, location.source_system_id)
        if source_system is None or source_system.code != "CLOVER":
            continue
        result.append(location_id)
    return result


@dataclass
class LiveHealthResult:
    healthy: bool
    reason: str


def _clover_live_health(
    session: Session, *, clover_location_ids: list[int], now: datetime, staleness_threshold: timedelta,
) -> LiveHealthResult:
    """Is Live Sync/Backfill actually running and succeeding for every
    Clover-sourced Location of this Restaurant — not "has it ever reached
    this Business Date" (that is `readiness.describe_readiness`'s own,
    separate, calculation-time question), but "is the connector alive right
    now." A Location whose most recent run is FAILED, or whose most recent
    run finished longer ago than `staleness_threshold`, is not healthy."""
    if not clover_location_ids:
        return LiveHealthResult(healthy=True, reason="no Clover-sourced Location for this Restaurant — nothing to gate on")

    for location_id in clover_location_ids:
        run = session.scalars(
            select(m.IngestionRun)
            .where(m.IngestionRun.location_id == location_id, m.IngestionRun.mode.in_(("LIVE_SYNC", "BACKFILL")))
            .order_by(m.IngestionRun.id.desc())
            .limit(1)
        ).first()
        if run is None:
            return LiveHealthResult(
                healthy=False, reason=f"location_id={location_id}: no Clover Live Sync/Backfill run recorded yet",
            )
        if run.status == "FAILED":
            return LiveHealthResult(
                healthy=False, reason=f"location_id={location_id}: most recent Clover Live Sync/Backfill run FAILED",
            )
        checked_at = run.finished_at or run.started_at
        if checked_at is None or _aware_utc(checked_at) < now - staleness_threshold:
            return LiveHealthResult(
                healthy=False,
                reason=f"location_id={location_id}: Clover Live Sync has not reported in over "
                f"{int(staleness_threshold.total_seconds())}s — connector may be stalled",
            )
    return LiveHealthResult(healthy=True, reason="Clover Live Sync/Backfill is running and healthy for every Clover-sourced Location")


@dataclass
class ReconciliationHealthResult:
    status: str
    reason: str
    last_checked_at: datetime | None
    is_persistently_failing: bool


def _reconciliation_health(
    session: Session, *, clover_location_ids: list[int], now: datetime,
    staleness_threshold: timedelta, persistent_failure_threshold: timedelta,
) -> ReconciliationHealthResult:
    """The Correction/Reconciliation Poller's own health, per Location — the
    concrete instance of CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md
    §7's "reconciliation recente e riuscita" requirement. Returns on the
    first blocking Location found, exactly like `readiness.
    _clover_live_sync_readiness` already does for its own (different)
    question."""
    if not clover_location_ids:
        return ReconciliationHealthResult(
            status=RECONCILIATION_STATUS_NOT_APPLICABLE,
            reason="no Clover-sourced Location for this Restaurant — nothing to reconcile",
            last_checked_at=None, is_persistently_failing=False,
        )

    for location_id in clover_location_ids:
        run = session.scalars(
            select(m.IngestionRun)
            .where(m.IngestionRun.location_id == location_id, m.IngestionRun.mode == "RECONCILIATION")
            .order_by(m.IngestionRun.id.desc())
            .limit(1)
        ).first()
        if run is None:
            return ReconciliationHealthResult(
                status=RECONCILIATION_STATUS_INCOMPLETE,
                reason=f"location_id={location_id}: reconciliation has not run yet for this Location",
                last_checked_at=None, is_persistently_failing=False,
            )
        checked_at = _aware_utc(run.finished_at) if run.finished_at is not None else None
        if run.status == "FAILED":
            persistent = checked_at is not None and checked_at < now - persistent_failure_threshold
            return ReconciliationHealthResult(
                status=RECONCILIATION_STATUS_FAILED,
                reason=f"location_id={location_id}: most recent reconciliation run FAILED",
                last_checked_at=checked_at, is_persistently_failing=persistent,
            )
        if checked_at is None or checked_at < now - staleness_threshold:
            persistent = checked_at is not None and checked_at < now - persistent_failure_threshold
            age = "unknown" if checked_at is None else f"{int((now - checked_at).total_seconds())}s ago"
            return ReconciliationHealthResult(
                status=RECONCILIATION_STATUS_STALE,
                reason=f"location_id={location_id}: last successful reconciliation was {age} — "
                f"waiting for the next cycle (normal, not an error)",
                last_checked_at=checked_at, is_persistently_failing=persistent,
            )
    return ReconciliationHealthResult(
        status=RECONCILIATION_STATUS_FRESH,
        reason="reconciliation is recent and successful for every Clover-sourced Location",
        last_checked_at=now, is_persistently_failing=False,
    )


def _has_blocking_attention(session: Session, *, restaurant_id: int) -> bool:
    """A CRITICAL, still-OPEN/ACKNOWLEDGED Attention Item scoped to this
    Restaurant's Tips is the only thing this gate treats as a blocking
    anomaly (Core `12_Attention_Management.md` §6: "CRITICAL must never be
    aggregated or silenced") — reuses the existing Attention Management
    schema exactly as `payment_cycle_service._raise_attention_for_instruction`
    already writes it; this function only reads it."""
    return session.scalars(
        select(m.AttentionItem.id).where(
            m.AttentionItem.source_domain == "TIPS",
            m.AttentionItem.scope_type == m.POSITION_SCOPE_RESTAURANT,
            m.AttentionItem.scope_id == restaurant_id,
            m.AttentionItem.priority == m.ATTENTION_PRIORITY_CRITICAL,
            m.AttentionItem.status.in_((m.ATTENTION_STATUS_OPEN, m.ATTENTION_STATUS_ACKNOWLEDGED)),
        )
    ).first() is not None


@dataclass
class PaymentReadiness:
    restaurant_id: int
    clover_live_healthy: bool
    clover_live_reason: str
    reconciliation_status: str
    reconciliation_reason: str
    reconciliation_last_checked_at: datetime | None
    is_persistently_failing: bool
    has_blocking_attention: bool
    ready: bool
    reason: str


def describe_payment_readiness(
    session: Session, restaurant_id: int, *, now: datetime | None = None,
    staleness_threshold: timedelta = DEFAULT_STALENESS_THRESHOLD,
    persistent_failure_threshold: timedelta = DEFAULT_PERSISTENT_FAILURE_THRESHOLD,
) -> PaymentReadiness:
    """The one entry point Approve & Pay (any of the three modes — MANUAL,
    AUTO WITH APPROVAL, AUTO WITHOUT APPROVAL), the Web Payment Control, and
    a future Cognito capability all call to answer "READY FOR PAYMENT?".
    Never mutates anything — pure read, exactly like `readiness.
    describe_readiness`'s own convention."""
    now = now or datetime.now(UTC)
    location_ids = _restaurant_location_ids(session, restaurant_id)
    clover_location_ids = _clover_location_ids(session, location_ids)

    live = _clover_live_health(session, clover_location_ids=clover_location_ids, now=now, staleness_threshold=staleness_threshold)
    reconciliation = _reconciliation_health(
        session, clover_location_ids=clover_location_ids, now=now,
        staleness_threshold=staleness_threshold, persistent_failure_threshold=persistent_failure_threshold,
    )
    blocking_attention = _has_blocking_attention(session, restaurant_id=restaurant_id)

    reconciliation_ok = reconciliation.status in (RECONCILIATION_STATUS_FRESH, RECONCILIATION_STATUS_NOT_APPLICABLE)
    ready = live.healthy and reconciliation_ok and not blocking_attention

    if not live.healthy:
        overall_reason = f"Clover live sync is not healthy: {live.reason}"
    elif not reconciliation_ok:
        overall_reason = f"reconciliation not ready: {reconciliation.reason}"
    elif blocking_attention:
        overall_reason = "a CRITICAL Attention item for this Restaurant's Tips must be resolved first"
    else:
        overall_reason = "Clover live healthy, reconciliation recent and successful, no blocking Attention"

    return PaymentReadiness(
        restaurant_id=restaurant_id,
        clover_live_healthy=live.healthy, clover_live_reason=live.reason,
        reconciliation_status=reconciliation.status, reconciliation_reason=reconciliation.reason,
        reconciliation_last_checked_at=reconciliation.last_checked_at,
        is_persistently_failing=reconciliation.is_persistently_failing,
        has_blocking_attention=blocking_attention,
        ready=ready, reason=overall_reason,
    )
