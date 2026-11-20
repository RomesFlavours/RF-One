"""Automated synthetic tests for `tips.payment_readiness`
(TASK_TIPS_RECONCILIATION_AND_PAYMENT_CONTROL_001; STEP 12B integration).

STEP 12B integration note: this is a NEW test file, not a port of the
source branch's own `tips_payment_readiness_validation.py` — that file
exercised an `ingestion_runs.mode`/`technical.connectors.clover.
reconciliation_poller.py`-based draft of `payment_readiness.py` which was
never integrated into main and is intentionally not ported (STEP 12B §7/
§16/§28). This file instead exercises the ACTUAL integrated module, which
reuses main's own canonical `technical.connectors.clover.correction_sync.
describe_reconciliation_status` (STEP 12A) — proving no duplicate,
independently-derived Clover gate exists anywhere in Tips."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .tips import payment_readiness as readiness_svc

UTC = timezone.utc
T0 = datetime(2026, 6, 1, tzinfo=UTC)


@dataclass
class ValidationResult:
    success: bool
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)

    def check(self, description: str, condition: bool) -> None:
        if condition:
            self.checks_passed.append(description)
        else:
            self.checks_failed.append(description)
            self.success = False


def run_validation(session_factory: sessionmaker[Session]) -> ValidationResult:
    result = ValidationResult(success=True)
    with session_factory() as session:
        try:
            _test_no_clover_location_is_not_ready(session, result)
            _test_ready_once_cursors_have_passed_now(session, result)
            _test_persistently_failing_after_threshold(session, result)
            _test_blocking_attention_overrides_reconciliation(session, result)
        finally:
            session.rollback()
    return result


def _make_restaurant_with_clover_location(session: Session, *, suffix: str):
    source_system = session.scalars(select(m.SourceSystem).filter_by(code="CLOVER")).first()
    if source_system is None:
        source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
        session.add(source_system)
        session.flush()
    merchant = m.Merchant(source_system_id=source_system.id, source_merchant_id=f"PR-MERCH-{suffix}", name="PR Merchant")
    session.add(merchant)
    session.flush()
    location = m.Location(
        merchant_id=merchant.id, source_system_id=source_system.id, source_location_id=f"PR-LOC-{suffix}",
        name="PR Location", currency="USD",
    )
    session.add(location)
    session.flush()
    restaurant = m.Restaurant(name=f"Payment Readiness Restaurant {suffix}", default_currency="USD")
    session.add(restaurant)
    session.flush()
    session.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
    session.commit()
    return restaurant, location, source_system


def _seed_cursor(session: Session, *, location, source_system, resource_type: str | None, window_end: datetime) -> None:
    session.add(
        m.IngestionRun(
            source_system_id=source_system.id, location_id=location.id, resource_type=resource_type,
            started_at=window_end, finished_at=window_end, status="COMPLETE",
            source_window_start=window_end - timedelta(hours=1), source_window_end=window_end,
            notes="synthetic payment-readiness cursor seed",
        )
    )


def _seed_all_cursors_past(session: Session, *, location, source_system, instant: datetime) -> None:
    for resource_type in (None, "orders", "payments", "refunds"):
        _seed_cursor(session, location=location, source_system=source_system, resource_type=resource_type, window_end=instant)
    session.commit()


def _test_no_clover_location_is_not_ready(session: Session, result: ValidationResult) -> None:
    """A Restaurant with NO Location at all is NOT READY (main's canonical
    `describe_reconciliation_status`'s own "no Location resolved" rule) —
    deliberately stricter than the superseded draft's own "nothing to gate
    on" leniency for an empty location list (see this module's own
    docstring)."""
    restaurant = m.Restaurant(name="No-Location Restaurant", default_currency="USD")
    session.add(restaurant)
    session.commit()

    readiness = readiness_svc.describe_payment_readiness(session, restaurant.id, now=T0)
    result.check(
        "no Location at all: payment readiness is NOT READY, not silently bypassed",
        not readiness.ready and not readiness.reconciliation_ready,
    )


def _test_ready_once_cursors_have_passed_now(session: Session, result: ValidationResult) -> None:
    """Once Live Sync AND every Correction resource cursor have passed the
    current instant, payment readiness is READY — the SAME canonical
    function `readiness.describe_readiness`'s CALCULATION gate already
    uses, evaluated at `now` instead of a single Business Date's end."""
    restaurant, location, source_system = _make_restaurant_with_clover_location(session, suffix="ready")
    now = T0 + timedelta(days=1)

    before_seed = readiness_svc.describe_payment_readiness(session, restaurant.id, now=now)
    result.check(
        "before any cursor exists: payment readiness is NOT READY (no successful run yet)",
        not before_seed.ready,
    )

    _seed_all_cursors_past(session, location=location, source_system=source_system, instant=now + timedelta(hours=1))
    after_seed = readiness_svc.describe_payment_readiness(session, restaurant.id, now=now)
    result.check(
        "once Live Sync and every Correction resource cursor have passed `now`: payment readiness is READY",
        after_seed.ready and after_seed.reconciliation_ready and not after_seed.is_persistently_failing,
    )


def _test_persistently_failing_after_threshold(session: Session, result: ValidationResult) -> None:
    """NOT READY is an ordinary, expected wait — `is_persistently_failing`
    only becomes True once the SAME condition has held for longer than
    `persistent_failure_threshold`, checked by re-calling the identical
    canonical function at an EARLIER instant, never a second, independently
    -implemented staleness heuristic."""
    restaurant, location, source_system = _make_restaurant_with_clover_location(session, suffix="persist")
    now = T0 + timedelta(days=5)

    # Cursors exist but have NOT reached `now` — reconciliation is behind,
    # but only just, well within the persistent-failure threshold.
    _seed_all_cursors_past(session, location=location, source_system=source_system, instant=now - timedelta(minutes=5))
    recent_lag = readiness_svc.describe_payment_readiness(
        session, restaurant.id, now=now, persistent_failure_threshold=timedelta(minutes=30),
    )
    result.check(
        "reconciliation lagging by only 5 minutes (under the 30-minute threshold): NOT READY but NOT "
        "persistently failing — a normal, non-alarming wait",
        not recent_lag.ready and not recent_lag.is_persistently_failing,
    )

    long_lag = readiness_svc.describe_payment_readiness(
        session, restaurant.id, now=now + timedelta(hours=1), persistent_failure_threshold=timedelta(minutes=30),
    )
    result.check(
        "reconciliation still lagging an hour later (well past the 30-minute threshold): escalated to "
        "persistently failing",
        not long_lag.ready and long_lag.is_persistently_failing,
    )


def _test_blocking_attention_overrides_reconciliation(session: Session, result: ValidationResult) -> None:
    """Even with fresh reconciliation, a CRITICAL, still-open Attention Item
    scoped to this Restaurant's Tips blocks payment readiness — Core
    `12_Attention_Management.md` §6's "CRITICAL must never be aggregated or
    silenced," applied at the payment gate."""
    restaurant, location, source_system = _make_restaurant_with_clover_location(session, suffix="attn")
    now = T0 + timedelta(days=10)
    _seed_all_cursors_past(session, location=location, source_system=source_system, instant=now + timedelta(hours=1))

    fresh = readiness_svc.describe_payment_readiness(session, restaurant.id, now=now)
    result.check("fresh reconciliation, no Attention yet: READY", fresh.ready and not fresh.has_blocking_attention)

    session.add(
        m.AttentionItem(
            source_domain="TIPS", source_module="PAYMENT_EXECUTION", source_process_name="TIP_PAYOUT",
            source_reference=f"Restaurant:{restaurant.id}:test", reason="synthetic CRITICAL block",
            priority=m.ATTENTION_PRIORITY_CRITICAL, status=m.ATTENTION_STATUS_OPEN,
            scope_type=m.POSITION_SCOPE_RESTAURANT, scope_id=restaurant.id,
        )
    )
    session.commit()

    blocked = readiness_svc.describe_payment_readiness(session, restaurant.id, now=now)
    result.check(
        "a CRITICAL, OPEN Attention Item for this Restaurant's Tips blocks payment readiness even though "
        "reconciliation itself is fresh",
        not blocked.ready and blocked.reconciliation_ready and blocked.has_blocking_attention,
    )
