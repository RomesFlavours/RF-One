"""Tip PAYMENT Readiness — the reconciliation-aware gate before Approve & Pay
(CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md §3/§7;
TASK_TIPS_RECONCILIATION_AND_PAYMENT_CONTROL_001; STEP 12B integration).

Distinct from `tips/readiness.py`'s CALCULATION readiness ("is there a
Business Date ready to be calculated") — see that module's own docstring.
This module answers the PAYMENT question: given a Restaurant (and,
implicitly, the Payment Cycle about to be Approved & Paid for it), is it
safe to actually send money — Clover Live Sync and every Correction/
Reconciliation resource cursor have caught up to the current moment, AND
no blocking (CRITICAL) Attention is pertinent to this Restaurant's Tips
payout.

STEP 12B integration note: an earlier draft of this module
(TASK_TIPS_RECONCILIATION_AND_PAYMENT_CONTROL_001, on
`feature/tips-complete`) derived Clover live-health/reconciliation health
from an `ingestion_runs.mode` column and a standalone
`technical.connectors.clover.reconciliation_poller.py` — an independently-
developed mechanism NEVER integrated into main. Main's own canonical
Correction/Reconciliation Sync (STEP 12A;
`technical.connectors.clover.correction_sync.describe_reconciliation_
status`, `IngestionRun.resource_type`) already answers the identical
underlying question ("has Live Sync and every Correction resource cursor
passed a given instant") for `tips/readiness.py`'s own CALCULATION gate.
This module REUSES that exact same canonical function — called twice, once
for "right now" and once for "`persistent_failure_threshold` ago" — rather
than re-deriving a second, independently-implemented Clover gate. No
`ingestion_runs.mode` column and no `reconciliation_poller.py` import
appear anywhere in this module.

Channel-independent (`00 Core/ImplementationGuidelines.md`, "Channel
Independence"): the Web Payment Control, a future Cognito capability, and
`tips/scheduler.py`'s automatic AUTO WITHOUT APPROVAL path all call this
SAME function before Approve & Pay — never a route/template-local
readiness check.

`NOT READY` here is a normal, expected, non-alarming outcome —
reconciliation being stale or still catching up is an ordinary waiting
condition, never itself treated as a financial error. Only a PERSISTENTLY
failing reconciliation (`is_persistently_failing` below) warrants human
Attention — raised by `tips.payment_cycle_service.
maybe_raise_attention_for_payment_readiness`, reusing the existing
Attention Management capability, never a Tips-specific escalation
mechanism."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..technical.connectors.clover.correction_sync import describe_reconciliation_status

UTC = timezone.utc

# How long reconciliation may remain non-fresh/failed before it is escalated
# to a human via Attention Management, rather than treated as an ordinary,
# silent "still catching up" wait ("NON trattarlo automaticamente come
# errore finanziario" / "se reconciliation fallisce persistentemente...
# usa Attention Management esistente").
DEFAULT_PERSISTENT_FAILURE_THRESHOLD = timedelta(minutes=30)


def _restaurant_location_ids(session: Session, restaurant_id: int) -> list[int]:
    return list(
        session.scalars(
            select(m.RestaurantLocation.location_id).where(m.RestaurantLocation.restaurant_id == restaurant_id)
        )
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
    reconciliation_ready: bool
    reconciliation_reason: str
    is_persistently_failing: bool
    has_blocking_attention: bool
    ready: bool
    reason: str


def describe_payment_readiness(
    session: Session, restaurant_id: int, *, now: datetime | None = None,
    persistent_failure_threshold: timedelta = DEFAULT_PERSISTENT_FAILURE_THRESHOLD,
) -> PaymentReadiness:
    """The one entry point Approve & Pay (any of the three modes — MANUAL,
    AUTO WITH APPROVAL, AUTO WITHOUT APPROVAL), the Web Payment Control, and
    a future Cognito capability all call to answer "READY FOR PAYMENT?".
    Never mutates anything — pure read, exactly like `readiness.
    describe_readiness`'s own convention."""
    now = now or datetime.now(UTC)
    location_ids = _restaurant_location_ids(session, restaurant_id)

    current = describe_reconciliation_status(session, location_ids=location_ids, period_end=now)

    is_persistently_failing = False
    if not current.ready:
        earlier = describe_reconciliation_status(
            session, location_ids=location_ids, period_end=now - persistent_failure_threshold,
        )
        is_persistently_failing = not earlier.ready

    blocking_attention = _has_blocking_attention(session, restaurant_id=restaurant_id)
    ready = current.ready and not blocking_attention

    if not current.ready:
        overall_reason = f"reconciliation not ready: {current.reason}"
    elif blocking_attention:
        overall_reason = "a CRITICAL Attention item for this Restaurant's Tips must be resolved first"
    else:
        overall_reason = "Clover Live Sync and Correction/Reconciliation have passed the current moment; no blocking Attention"

    return PaymentReadiness(
        restaurant_id=restaurant_id, reconciliation_ready=current.ready, reconciliation_reason=current.reason,
        is_persistently_failing=is_persistently_failing, has_blocking_attention=blocking_attention,
        ready=ready, reason=overall_reason,
    )
