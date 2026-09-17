"""Correction / Reconciliation Poller
(CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md §3-§4).

The second, distinct, continuous Clover synchronization process: where
`live_sync.py` (~15s) keeps NEW records close to real time, this module
(~60s) detects and corrects CHANGES to records already previously acquired,
regardless of how long ago they were created — closing the verified gap
`live_sync.py`'s own module docstring and CLOVER_CONTINUOUS_SYNCHRONIZATION_
ARCHITECTURE.md §3 both name: `import_clover_period()` filters Payments/
Refunds by `createdTime` only, so a correction to a record whose createdTime
has already scrolled out of Live Sync's short window is structurally
invisible to Live Sync no matter how long it keeps running.

Writes to the SAME RF-One Data Store Live Sync writes to — no second
database, no event ledger, no Clover history replica. Reuses the exact same
per-entity mapping/upsert primitives `acquisition.py` and
`historical_backfill_detail.py` already define and Live Sync/Historical
Backfill already trust (`_ingest_order`, `_ingest_payment`, `_ingest_refund`,
`_ingest_fee_line_items`, `ingest_order_item_and_modifier_detail`,
`_mirror_source_record`) — this module owns no mapping logic of its own, it
only decides WHICH records to re-fetch and WHEN.

Not `freshness.py`: `freshness.ensure_clover_data_fresh()` remains what it
already is — an on-demand, synchronous "has this date range been imported at
all yet" check, never a continuous process. This module is the opposite
shape: continuous, unconditional (an on-demand freshness gate never runs
it), and about CHANGE detection, not initial coverage. Neither redefines the
other.

Modification Cursor (§4) — Location × Resource, because each resource has
its own endpoint, fails independently, and exposes change-detection
differently:

- **orders** / **payments** — Clover's raw payload already carries
  `modifiedTime` for both (`mapping.map_order`/`map_payment` already extract
  it into `modified_at`), so this module queries each resource's list
  endpoint with a `modifiedTime`-bounded `filter`, mirroring the exact same
  `filter=[attr>=..., attr<=...]` query shape `acquisition.py` already uses
  (there, on `createdTime`) for Payments/Refunds. This mirrors, rather than
  invents, a pattern already proven correct in this codebase for a sibling
  timestamp attribute on the very same list endpoints; if Clover ever
  rejects it in a given deployment, the resource's fetch simply comes back
  `not ok` — the same graceful, self-healing degradation this codebase
  already relies on elsewhere: the cursor for that resource does not
  advance, and the next cycle retries.
- **refunds** — no `modifiedTime` field has ever been confirmed anywhere in
  this codebase for Clover's Refund object (`mapping.map_refund` maps no
  such field, unlike Order/Payment). Per CLOVER_CONTINUOUS_SYNCHRONIZATION_
  ARCHITECTURE.md §6's own instruction ("document the minimal fallback"),
  Refunds use the documented fallback instead: a rolling recent `createdTime`
  window (`DEFAULT_REFUND_RECENCY_WINDOW`, default 48h), re-scanned and
  re-upserted every cycle via the SAME proven `createdTime` filter Live
  Sync/Backfill already use for this resource. This is deliberately NOT a
  forward-resuming cursor like Orders/Payments (a genuinely modified-then-
  reverted-to-unmodified Refund has no signal to resume from) — only
  `source_window_end` still only advances on success, which is all the Tips
  readiness gate (§7, `tips/readiness.py`) actually needs.
- **employees** — deliberately NOT a separate resource here. Clover's
  `/employees` collection is already fetched IN FULL, unconditionally, every
  Live Sync cycle (`acquisition._fetch_reference_catalogs`, both modes) —
  an Employee record change is already visible within one Live Sync interval
  (~15s), faster than this Poller could ever check it. The gap this
  document's illustrative "employee reassignment corrected after the shift"
  example actually describes is an ORDER's own `employee` reference being
  corrected later — already covered by the Orders resource above (`_ingest_
  order` already overwrites `Order.employee_id`/`source_employee_id` from
  Clover's current value on every re-upsert).
- Order Item / Order Item Modifier / Order Fee / Payment Tip — no separate
  resource either: all four are nested under, and only ever re-verified
  together with, their parent Order/Payment (exactly how Live Sync already
  treats them). Order-level Discounts and Order Item Tax remain a Historical
  Backfill-only concern, unchanged by this module (they depend on catalog
  data — DiscountDefinition/TaxRate/Item — this Poller does not refresh,
  matching Live Sync's own existing scope boundary,
  CLOVER_LIVE_SYNC_SCOPE_REDUCTION_001) — a known, documented, non-goal.

Concurrency: reuses the EXACT SAME Location-scoped `IngestionRun.lock_key`
guard (`acquisition._acquire_import_lock`/`_finalize_import_run`) Live Sync
and Historical Backfill already share — a correction cycle for a Location
can never write concurrently with a Live Sync cycle or a Backfill for that
SAME Location; whichever loses the race simply skips this tick and retries
next interval (`ImportAlreadyRunningError`, caught exactly like Live Sync
already catches it). No new locking primitive is introduced. Each of the
three resources is then processed sequentially inside that one lock, each
writing its OWN Modification Cursor row (created RUNNING, finalized
COMPLETE/FAILED and committed independently — baseline-closure fix: a
per-record failure inside an otherwise-successful scan now finalizes
FAILED, not PARTIAL, so the checkpoint never advances past unretried work;
see `_correct_orders`'s own comment) so one resource's failure never
blocks or reverts another's success, and a Location's failure never
affects any other Location (each Location is its own process invocation,
exactly like Live Sync).

Idempotency: every resource reuses the exact same upsert-by-source-identity
primitives Backfill/Live Sync already use, and a deliberate overlap
buffer/rolling window on every fetch — a repeated or overlapping poll can
only refresh existing rows from Clover's current values, never duplicate
them.

Current state, not POS history: correcting a record means overwriting
RF-One's canonical row with Clover's CURRENT value for it, exactly as
`_ingest_order`/`_ingest_payment`/`_ingest_refund` already do on any
re-import — this module adds no event log, no history table, no
intermediate-state replay. The existing `SourceRecord` Provider Mirror
(append-only, unmapped) is still written for audit/reconciliation,
unchanged in role.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .... import models as m
from ....ingestion.common import utc_now
from . import historical_backfill_detail, mapping
from .acquisition import (
    CloverReadClient,
    ImportAlreadyRunningError,
    _acquire_import_lock,
    _aware_utc,
    _existing_ids_by_source,
    _finalize_import_run,
    _ingest_fee_line_items,
    _ingest_order,
    _ingest_payment,
    _ingest_refund,
    _mirror_source_record,
    _resolve_clover_merchant,
    _safe_error_summary,
    get_default_client,
    paginate,
)

UTC = timezone.utc
LOG = logging.getLogger("clover_correction_sync")

MODE_CORRECTION = "CORRECTION"

RESOURCE_ORDERS = "orders"
RESOURCE_PAYMENTS = "payments"
RESOURCE_REFUNDS = "refunds"
ALL_RESOURCES = (RESOURCE_ORDERS, RESOURCE_PAYMENTS, RESOURCE_REFUNDS)

DEFAULT_POLL_INTERVAL_SECONDS = 60.0

# First-ever correction cycle for a (Location, resource): starts this far
# back rather than the dawn of time — a bounded, documented choice. A
# correction older than this at first-ever run is Historical Backfill's job
# (an operator-triggered, explicit re-import), not this Poller's — matching
# CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md §1/§8's "RF-One is not
# intended to become a full historical replica of Clover's POS data."
DEFAULT_INITIAL_LOOKBACK = timedelta(hours=24)

# Every cycle's window starts this far BEFORE the prior cycle's own
# source_window_end — tolerating Clover write-then-read latency/clock skew,
# same rationale as live_sync.DEFAULT_OVERLAP_BUFFER, just proportionally
# larger given this Poller's slower ~60s cadence.
DEFAULT_OVERLAP_BUFFER = timedelta(minutes=5)

# Refunds fallback (see module docstring "refunds" bullet): a rolling recent
# createdTime window re-scanned every cycle, not a forward-resuming cursor.
DEFAULT_REFUND_RECENCY_WINDOW = timedelta(hours=48)


@dataclass
class _CorrectionSink:
    """Duck-typed `summary=` sink for the reused `_ingest_fee_line_items`/
    `_ingest_payment` helpers, whose real `ImportSummary` counters
    (voluntary tips, split-payment counts, etc.) are pure observability this
    Poller has no report to feed them into. Only `errors` is ever actually
    read back afterward by this module — the rest exist purely because the
    reused functions unconditionally increment them."""

    errors: list[str] = field(default_factory=list)
    automatic_gratuity_count: int = 0
    automatic_gratuity_total_minor: int = 0
    payments_imported: int = 0
    payments_updated: int = 0
    voluntary_tips_count: int = 0
    voluntary_tips_total_minor: int = 0
    zero_tip_payments_count: int = 0
    missing_tip_amount_payments_count: int = 0


@dataclass
class ResourceCorrectionResult:
    resource_type: str
    location_id: int
    window_start: datetime
    window_end: datetime
    status: str  # COMPLETE | FAILED (baseline-closure fix: PARTIAL is never produced by this module anymore)
    records_seen: int = 0
    records_touched: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class CorrectionCycleSummary:
    location_id: int
    results: list[ResourceCorrectionResult] = field(default_factory=list)


@dataclass(frozen=True)
class ReconciliationStatus:
    """Read-only status ("is this Business Date's Clover data reconciled
    enough for Tips") — `tips/readiness.py`'s own consumption of this
    module, per CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md §7."""

    ready: bool
    reason: str


def _latest_cursor_end(
    session: Session, *, location_id: int, source_system_id: int, resource_type: str | None,
) -> tuple[datetime | None, str | None]:
    """The latest COMPLETE/PARTIAL run's own `source_window_end` for this
    (location, resource_type) — `resource_type=None` selects the plain Live
    Cursor (Backfill/Live Sync), the exact same query shape `live_sync.
    compute_next_sync_window` itself uses. Returns `(None, None)` if no
    successful run exists yet for this resource at this Location."""
    run = session.scalars(
        select(m.IngestionRun)
        .where(
            m.IngestionRun.location_id == location_id,
            m.IngestionRun.source_system_id == source_system_id,
            m.IngestionRun.resource_type == resource_type,
            m.IngestionRun.status.in_(("COMPLETE", "PARTIAL")),
            m.IngestionRun.source_window_end.is_not(None),
        )
        .order_by(m.IngestionRun.id.desc())
        .limit(1)
    ).first()
    if run is None:
        return None, None
    return _aware_utc(run.source_window_end), run.status


def _compute_resuming_window(
    session: Session, *, location_id: int, source_system_id: int, resource_type: str, now: datetime,
    initial_lookback: timedelta, overlap_buffer: timedelta,
) -> tuple[datetime, datetime]:
    """Orders/Payments window: resumes from this resource's OWN last
    successful checkpoint (never the Live Cursor's, never another
    resource's), minus an overlap buffer; falls back to `initial_lookback`
    on this resource's first-ever correction cycle for this Location."""
    checkpoint, _status = _latest_cursor_end(
        session, location_id=location_id, source_system_id=source_system_id, resource_type=resource_type,
    )
    if checkpoint is not None:
        return checkpoint - overlap_buffer, now
    return now - initial_lookback, now


def _resolve_order_id(session: Session, *, source_system_id: int, source_order_id: str | None) -> int | None:
    if not source_order_id:
        return None
    order = session.scalars(
        select(m.Order).filter_by(source_system_id=source_system_id, source_order_id=source_order_id)
    ).first()
    return order.id if order is not None else None


def _resolve_payment_id(session: Session, *, source_system_id: int, source_payment_id: str | None) -> int | None:
    if not source_payment_id:
        return None
    payment = session.scalars(
        select(m.Payment).filter_by(source_system_id=source_system_id, source_payment_id=source_payment_id)
    ).first()
    return payment.id if payment is not None else None


def _start_cursor_run(
    session: Session, *, location_id: int, source_system_id: int, resource_type: str,
    window_start: datetime, window_end: datetime,
) -> m.IngestionRun:
    """Creates this resource's Modification Cursor row for THIS cycle,
    flushed (not committed) so its `id` is available for Provider Mirror
    attribution before any Clover fetch happens — mirroring `acquisition.
    _acquire_import_lock`'s own "token exists before the fetch" shape, minus
    the `lock_key` (this row needs no mutex of its own: it is written
    entirely inside the caller's already-acquired Location-level guard)."""
    run = m.IngestionRun(
        source_system_id=source_system_id, location_id=location_id, started_at=utc_now(),
        status="RUNNING", source_window_start=window_start, source_window_end=window_end,
        resource_type=resource_type,
        notes=f"CLOVER_CORRECTION resource={resource_type} location_id={location_id}; RUNNING",
    )
    session.add(run)
    session.flush()
    return run


def _finish_cursor_run(
    session: Session, run: m.IngestionRun, *, status: str, touched: int, seen: int, errors: list[str],
) -> None:
    """The RUNNING -> COMPLETE/PARTIAL/FAILED transition for one resource's
    cursor row, committed independently of every other resource's row —
    per-resource isolation (task §7/§11): another resource's later failure
    can never revert this commit."""
    run.status = status
    run.finished_at = utc_now()
    detail = f"seen={seen}; touched={touched}; errors={len(errors)}"
    if errors:
        detail += "; " + "; ".join(errors[:3])
    run.notes = f"CLOVER_CORRECTION resource={run.resource_type} location_id={run.location_id}; {detail}"
    session.commit()


def _correct_orders(
    session: Session, client: CloverReadClient, *, location_id: int, source_system_id: int,
    merchant_id: str, now: datetime,
) -> ResourceCorrectionResult:
    window_start, window_end = _compute_resuming_window(
        session, location_id=location_id, source_system_id=source_system_id, resource_type=RESOURCE_ORDERS,
        now=now, initial_lookback=DEFAULT_INITIAL_LOOKBACK, overlap_buffer=DEFAULT_OVERLAP_BUFFER,
    )
    cursor_run = _start_cursor_run(
        session, location_id=location_id, source_system_id=source_system_id, resource_type=RESOURCE_ORDERS,
        window_start=window_start, window_end=window_end,
    )
    start_ms = int(window_start.astimezone(UTC).timestamp() * 1000)
    end_ms = int(window_end.astimezone(UTC).timestamp() * 1000)
    retrieved_at = utc_now()
    errors: list[str] = []
    touched = 0
    seen = 0

    result = paginate(
        client, f"/v3/merchants/{merchant_id}/orders",
        extra_params={"filter": [f"modifiedTime>={start_ms}", f"modifiedTime<={end_ms}"], "expand": "employee,lineItems"},
    )
    if not result.ok:
        status = "FAILED"
        errors.append(f"Fetching modified Orders failed: {result.error or 'unknown error'}")
    else:
        seen = len(result.elements)
        employee_by_source_id = _existing_ids_by_source(
            session, m.Employee, source_system_id=source_system_id, source_id_column="source_employee_id",
        )
        for order_raw in result.elements:
            try:
                # A nested SAVEPOINT (this codebase's established pattern for
                # exactly this shape, e.g. purchasing_validation.py) isolates
                # one bad Order's partial writes without discarding the
                # cursor row or any earlier Order already processed in this
                # SAME resource pass — a plain `session.rollback()` here
                # would incorrectly undo the whole pending transaction.
                with session.begin_nested():
                    order, _is_new = _ingest_order(
                        session, order_raw, location_id=location_id, source_system_id=source_system_id,
                        employee_by_source_id=employee_by_source_id,
                        ingestion_run_id=cursor_run.id, retrieved_at=retrieved_at,
                    )
                    _ingest_fee_line_items(
                        session, order_raw, order, source_system_id=source_system_id, summary=_CorrectionSink(),
                    )
                    historical_backfill_detail.ingest_order_item_and_modifier_detail(
                        session, client, order_raw, order, source_system_id=source_system_id,
                        ingestion_run_id=cursor_run.id, retrieved_at=retrieved_at,
                        mirror_source_record=_mirror_source_record,
                    )
                touched += 1
            except Exception as exc:  # noqa: BLE001 — one bad Order must never abort the whole resource pass
                errors.append(f"Order {(order_raw.get('id') or '')[:8]}...: {_safe_error_summary(exc)}")
        # Baseline-closure fix: FAILED, never PARTIAL, when even one Order in
        # this window could not be applied. PARTIAL previously still
        # advanced the checkpoint (`_latest_cursor_end` accepts COMPLETE OR
        # PARTIAL), so a single bad Order was silently, permanently skipped
        # — the checkpoint had already moved past its `modifiedTime` before
        # the next cycle ran. FAILED is excluded from that checkpoint query
        # (STEP 12A's own `window_scan_failed` precedent, extended here from
        # "whole fetch failed" to "any record inside it failed too"), so the
        # ENTIRE window — including the successfully-touched Orders, safe to
        # re-touch via this codebase's existing idempotent upsert — is
        # retried next cycle until the failing Order succeeds or is fixed,
        # with no operator action and no need to know which record failed.
        status = "COMPLETE" if not errors else "FAILED"

    _finish_cursor_run(session, cursor_run, status=status, touched=touched, seen=seen, errors=errors)
    return ResourceCorrectionResult(
        resource_type=RESOURCE_ORDERS, location_id=location_id, window_start=window_start, window_end=window_end,
        status=status, records_seen=seen, records_touched=touched, errors=errors,
    )


def _correct_payments(
    session: Session, client: CloverReadClient, *, location_id: int, source_system_id: int,
    merchant_id: str, now: datetime,
) -> ResourceCorrectionResult:
    window_start, window_end = _compute_resuming_window(
        session, location_id=location_id, source_system_id=source_system_id, resource_type=RESOURCE_PAYMENTS,
        now=now, initial_lookback=DEFAULT_INITIAL_LOOKBACK, overlap_buffer=DEFAULT_OVERLAP_BUFFER,
    )
    cursor_run = _start_cursor_run(
        session, location_id=location_id, source_system_id=source_system_id, resource_type=RESOURCE_PAYMENTS,
        window_start=window_start, window_end=window_end,
    )
    start_ms = int(window_start.astimezone(UTC).timestamp() * 1000)
    end_ms = int(window_end.astimezone(UTC).timestamp() * 1000)
    retrieved_at = utc_now()
    # `errors` — records genuinely NOT applied this pass (skipped, or the
    # upsert itself raised) — is what decides FAILED-vs-COMPLETE below
    # (baseline-closure fix). `informational_notes` — a successfully
    # touched Payment that `_ingest_payment` merely flagged a non-fatal
    # data-quality anomaly on — never blocks the checkpoint; nothing about
    # it needs retrying. Both are recorded in `_finish_cursor_run`'s notes.
    errors: list[str] = []
    informational_notes: list[str] = []
    touched = 0
    seen = 0

    result = paginate(
        client, f"/v3/merchants/{merchant_id}/payments",
        extra_params={
            "expand": "order,tender,employee",
            "filter": [f"modifiedTime>={start_ms}", f"modifiedTime<={end_ms}"],
        },
    )
    if not result.ok:
        status = "FAILED"
        errors.append(f"Fetching modified Payments failed: {result.error or 'unknown error'}")
    else:
        seen = len(result.elements)
        employee_by_source_id = _existing_ids_by_source(
            session, m.Employee, source_system_id=source_system_id, source_id_column="source_employee_id",
        )
        tender_by_source_id = _existing_ids_by_source(
            session, m.Tender, source_system_id=source_system_id, source_id_column="source_tender_id",
        )
        device_by_source_id = _existing_ids_by_source(
            session, m.Device, source_system_id=source_system_id, source_id_column="source_device_id",
        )
        for payment_raw in result.elements:
            order_source_id = mapping.map_payment(payment_raw).get("order_source_id")
            order_id = _resolve_order_id(session, source_system_id=source_system_id, source_order_id=order_source_id)
            if order_id is None:
                errors.append(
                    f"Payment {(payment_raw.get('id') or '')[:8]}... references an Order not yet canonical; skipped."
                )
                continue
            sink = _CorrectionSink()
            try:
                with session.begin_nested():
                    _ingest_payment(
                        session, payment_raw, order_id=order_id, source_system_id=source_system_id,
                        employee_by_source_id=employee_by_source_id, tender_by_source_id=tender_by_source_id,
                        device_by_source_id=device_by_source_id, summary=sink,
                        ingestion_run_id=cursor_run.id, retrieved_at=retrieved_at,
                    )
                touched += 1
                # `_ingest_payment` may flag a non-fatal data-quality anomaly
                # (e.g. a previously-recorded tip now absent on re-fetch) into
                # `summary.errors` without raising — the Payment row itself
                # was still correctly upserted, so this is informational
                # only and never forces a FAILED/non-advancing checkpoint
                # (baseline-closure fix: only a record that was NOT applied
                # — skipped above, or an exception below — does that).
                informational_notes.extend(sink.errors)
            except Exception as exc:  # noqa: BLE001 — one bad Payment must never abort the whole resource pass
                errors.append(f"Payment {(payment_raw.get('id') or '')[:8]}...: {_safe_error_summary(exc)}")
        # FAILED, never PARTIAL, when even one Payment could not be applied
        # (skipped above, or raised here) — see `_correct_orders`'s own
        # comment for the full rationale; the same fix, applied here too.
        status = "COMPLETE" if not errors else "FAILED"

    all_notes = errors + informational_notes
    _finish_cursor_run(session, cursor_run, status=status, touched=touched, seen=seen, errors=all_notes)
    return ResourceCorrectionResult(
        resource_type=RESOURCE_PAYMENTS, location_id=location_id, window_start=window_start, window_end=window_end,
        status=status, records_seen=seen, records_touched=touched, errors=all_notes,
    )


def _correct_refunds(
    session: Session, client: CloverReadClient, *, location_id: int, source_system_id: int,
    merchant_id: str, now: datetime,
) -> ResourceCorrectionResult:
    """Fallback resource (see module docstring): a rolling recent
    `createdTime` window, NOT a forward-resuming cursor — Refund has no
    confirmed `modifiedTime` anywhere in this codebase (`mapping.map_refund`
    maps none). `source_window_end` still only advances on success, which is
    all `describe_reconciliation_status` needs."""
    window_start = now - DEFAULT_REFUND_RECENCY_WINDOW
    window_end = now
    cursor_run = _start_cursor_run(
        session, location_id=location_id, source_system_id=source_system_id, resource_type=RESOURCE_REFUNDS,
        window_start=window_start, window_end=window_end,
    )
    start_ms = int(window_start.astimezone(UTC).timestamp() * 1000)
    end_ms = int(window_end.astimezone(UTC).timestamp() * 1000)
    retrieved_at = utc_now()
    errors: list[str] = []
    touched = 0
    seen = 0

    result = paginate(
        client, f"/v3/merchants/{merchant_id}/refunds",
        extra_params={"filter": [f"createdTime>={start_ms}", f"createdTime<={end_ms}"]},
    )
    if not result.ok:
        status = "FAILED"
        errors.append(f"Fetching recent Refunds failed: {result.error or 'unknown error'}")
    else:
        seen = len(result.elements)
        employee_by_source_id = _existing_ids_by_source(
            session, m.Employee, source_system_id=source_system_id, source_id_column="source_employee_id",
        )
        device_by_source_id = _existing_ids_by_source(
            session, m.Device, source_system_id=source_system_id, source_id_column="source_device_id",
        )
        for refund_raw in result.elements:
            values = mapping.map_refund(refund_raw)
            order_source_id = values.get("order_source_id")
            payment_source_id = values.get("payment_source_id")
            order_id = _resolve_order_id(session, source_system_id=source_system_id, source_order_id=order_source_id)
            payment_id = _resolve_payment_id(
                session, source_system_id=source_system_id, source_payment_id=payment_source_id,
            )
            try:
                with session.begin_nested():
                    _ingest_refund(
                        session, refund_raw, source_system_id=source_system_id,
                        order_by_source_id={order_source_id: order_id} if order_id else {},
                        payment_by_source_id={payment_source_id: payment_id} if payment_id else {},
                        employee_by_source_id=employee_by_source_id, device_by_source_id=device_by_source_id,
                        ingestion_run_id=cursor_run.id, retrieved_at=retrieved_at,
                    )
                touched += 1
            except Exception as exc:  # noqa: BLE001 — one bad Refund must never abort the whole resource pass
                errors.append(f"Refund {(refund_raw.get('id') or '')[:8]}...: {_safe_error_summary(exc)}")
        # FAILED, never PARTIAL, when even one Refund could not be applied
        # — see `_correct_orders`'s own comment for the full rationale.
        status = "COMPLETE" if not errors else "FAILED"

    _finish_cursor_run(session, cursor_run, status=status, touched=touched, seen=seen, errors=errors)
    return ResourceCorrectionResult(
        resource_type=RESOURCE_REFUNDS, location_id=location_id, window_start=window_start, window_end=window_end,
        status=status, records_seen=seen, records_touched=touched, errors=errors,
    )


@dataclass
class _CycleLockSummary:
    """Feeds `_finalize_import_run` for the OUTER per-Location mutex row
    only — always COMPLETE, since per-resource failures are recorded on
    their own cursor rows, never on this bookkeeping row."""

    errors: list[str] = field(default_factory=list)
    window_scan_failed: bool = False
    payments_imported: int = 0
    payments_updated: int = 0
    orders_imported: int = 0
    orders_updated: int = 0
    shifts_imported: int = 0
    refunds_found: int = 0


def run_correction_cycle(
    session: Session, *, location_id: int, client: CloverReadClient | None = None, now: datetime | None = None,
) -> CorrectionCycleSummary | None:
    """One correction cycle for one Location: Orders, then Payments, then
    Refunds — each independently windowed/cursored/committed. Returns `None`
    if this Location is not Clover-sourced, or another Clover acquisition
    (Live Sync, Backfill, or another correction cycle) is already RUNNING
    for it right now — never an error; the next tick tries again."""
    now = now or datetime.now(UTC)
    merchant = _resolve_clover_merchant(session, location_id)
    if merchant is None:
        LOG.info("location_id=%s is not a Clover-sourced Location — skipping this correction cycle.", location_id)
        return None
    source_system_id, merchant_id = merchant

    try:
        # Reuses the SAME Location-scoped lock Live Sync/Backfill already
        # use (see module docstring "Concurrency") — a near-zero window:
        # this row is a pure mutex/audit token, never consulted by
        # `compute_next_sync_window`/`_is_range_covered` for coverage
        # decisions (it carries no `resource_type`, and its window is too
        # narrow to misrepresent any real coverage either way).
        lock_run = _acquire_import_lock(
            session, location_id=location_id, source_system_id=source_system_id,
            period_start=now, period_end=now, mode=MODE_CORRECTION,
        )
    except ImportAlreadyRunningError:
        LOG.info(
            "location_id=%s: another Clover acquisition is already running — skipping this correction cycle, "
            "will retry next interval.", location_id,
        )
        return None

    resolved_client = client or get_default_client()
    summary = CorrectionCycleSummary(location_id=location_id)
    try:
        summary.results.append(
            _correct_orders(
                session, resolved_client, location_id=location_id, source_system_id=source_system_id,
                merchant_id=merchant_id, now=now,
            )
        )
        summary.results.append(
            _correct_payments(
                session, resolved_client, location_id=location_id, source_system_id=source_system_id,
                merchant_id=merchant_id, now=now,
            )
        )
        summary.results.append(
            _correct_refunds(
                session, resolved_client, location_id=location_id, source_system_id=source_system_id,
                merchant_id=merchant_id, now=now,
            )
        )
    except Exception as exc:  # noqa: BLE001 — mirrors acquisition.import_clover_period's own top-level
        # guard: a genuinely unexpected failure (e.g. `_start_cursor_run`'s
        # own flush, or a resource's final commit) must still release the
        # Location-level lock, never leave it RUNNING forever. `rollback()`
        # only discards whatever this failed resource's own uncommitted work
        # was — every EARLIER resource in this same cycle already committed
        # independently (see `_finish_cursor_run`) and is unaffected.
        session.rollback()
        _finalize_import_run(
            lock_run, _CycleLockSummary(errors=[_safe_error_summary(exc)], window_scan_failed=True),
            location_id=location_id, mode=MODE_CORRECTION,
        )
        session.commit()
        raise
    else:
        _finalize_import_run(lock_run, _CycleLockSummary(), location_id=location_id, mode=MODE_CORRECTION)
        session.commit()

    return summary


def _run_forever(
    session_factory: sessionmaker[Session], *, location_id: int, interval_seconds: float,
) -> None:  # pragma: no cover — thin process loop, exercised via run_correction_cycle directly in tests
    LOG.info("Starting Clover Correction/Reconciliation loop for location_id=%s (interval=%.0fs).", location_id, interval_seconds)
    while True:
        try:
            with session_factory() as session:
                summary = run_correction_cycle(session, location_id=location_id)
                if summary is not None:
                    for r in summary.results:
                        LOG.info(
                            "resource=%s status=%s seen=%d touched=%d errors=%d",
                            r.resource_type, r.status, r.records_seen, r.records_touched, len(r.errors),
                        )
        except Exception:  # noqa: BLE001 — one bad cycle must never kill the loop
            LOG.exception("Unhandled error in Correction/Reconciliation cycle — will retry next interval.")
        time.sleep(interval_seconds)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover — thin CLI wrapper
    from ....database import create_configured_engine, create_session_factory, get_database_url, run_migrations_to_head

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--location-id", type=int, required=True)
    parser.add_argument("--interval-seconds", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)
    parser.add_argument(
        "--once", action="store_true",
        help="Run a single cycle and exit, instead of looping forever — for cron/Task Scheduler-driven "
        "invocation rather than a long-running daemon.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    db_url = get_database_url()
    run_migrations_to_head(db_url)
    engine = create_configured_engine(db_url)
    session_factory = create_session_factory(engine)

    if args.once:
        with session_factory() as session:
            summary = run_correction_cycle(session, location_id=args.location_id)
            if summary is not None:
                for r in summary.results:
                    LOG.info(
                        "resource=%s status=%s seen=%d touched=%d errors=%d",
                        r.resource_type, r.status, r.records_seen, r.records_touched, len(r.errors),
                    )
        return 0

    _run_forever(session_factory, location_id=args.location_id, interval_seconds=args.interval_seconds)
    return 0  # unreachable — _run_forever loops until killed


def describe_reconciliation_status(
    session: Session, *, location_ids: list[int], period_end: datetime,
) -> ReconciliationStatus:
    """CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md §7 — "Tips must not
    calculate or pay against a Business Date before that Business Date's
    Clover data has had the opportunity to pass through both the Fast Live
    Extractor and the Correction/Reconciliation Poller." Operationalized
    literally: for every Clover-sourced Location in `location_ids`, BOTH the
    plain Live Cursor AND all three Correction resource cursors must have a
    successful (COMPLETE/PARTIAL) run whose own `source_window_end` has
    already reached `period_end` (the Business Date's own end). A data
    condition, never a wall-clock delay — consistent with `tips/readiness.
    py`'s own stated philosophy (Core 2.0 §5, "Time is just an event")."""
    if not location_ids:
        return ReconciliationStatus(ready=False, reason="no Location resolved for this Restaurant")

    for location_id in location_ids:
        merchant = _resolve_clover_merchant(session, location_id)
        if merchant is None:
            continue  # not a Clover-sourced Location — nothing to reconcile here
        source_system_id, _merchant_id = merchant

        for resource_type in (None, *ALL_RESOURCES):
            label = "Live Sync" if resource_type is None else resource_type
            cursor_end, _status = _latest_cursor_end(
                session, location_id=location_id, source_system_id=source_system_id, resource_type=resource_type,
            )
            if cursor_end is None:
                return ReconciliationStatus(
                    ready=False, reason=f"location_id={location_id}: no successful {label} run yet",
                )
            if cursor_end < period_end:
                return ReconciliationStatus(
                    ready=False,
                    reason=(
                        f"location_id={location_id}: {label} cursor at {cursor_end.isoformat()} has not yet "
                        f"reached this Business Date's end ({period_end.isoformat()})"
                    ),
                )

    return ReconciliationStatus(
        ready=True, reason="Live Sync and all Correction/Reconciliation resources have passed this Business Date",
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
