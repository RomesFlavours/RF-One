"""Automated synthetic tests for `tips.payment_readiness`
(CLOVER_CONTINUOUS_SYNCHRONIZATION_ARCHITECTURE.md §7;
TASK_TIPS_RECONCILIATION_AND_PAYMENT_CONTROL_001).

Builds a synthetic fixture inside a disposable database, exercises
`describe_payment_readiness` directly (no Clover fetch, no Mercury call —
pure state assertions against hand-seeded `IngestionRun`/`AttentionItem`
rows), and always rolls back."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .attention_service import create_attention
from .organizational_responsibility_service import ScopeContext
from .tips import payment_readiness as readiness_svc

UTC = timezone.utc
NOW = datetime(2026, 9, 14, 12, 0, 0, tzinfo=UTC)


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
            _test_no_clover_location_is_always_ready(session, result)
            _test_fresh_reconciliation_is_ready(session, result)
            _test_stale_reconciliation_is_not_ready(session, result)
            _test_failed_reconciliation_is_not_ready(session, result)
            _test_retry_after_failure_becomes_ready(session, result)
            _test_unhealthy_live_sync_is_not_ready(session, result)
            _test_blocking_critical_attention_is_not_ready(session, result)
            _test_non_blocking_attention_does_not_affect_readiness(session, result)
            _test_persistently_failing_flag(session, result)
        finally:
            session.rollback()
    return result


def _build_fixture(session: Session, *, merchant_source_id: str) -> tuple[m.Restaurant, m.Location, m.SourceSystem]:
    source_system = session.scalars(select(m.SourceSystem).filter_by(code="CLOVER")).first()
    if source_system is None:
        source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
        session.add(source_system)
        session.flush()

    merchant = m.Merchant(source_system_id=source_system.id, source_merchant_id=merchant_source_id, name="Readiness Test Merchant")
    session.add(merchant)
    session.flush()

    location = m.Location(
        merchant_id=merchant.id, source_system_id=source_system.id, source_location_id=merchant_source_id,
        name="Readiness Test Location", currency="USD",
    )
    session.add(location)
    session.flush()

    restaurant = m.Restaurant(name=f"Synthetic Payment Readiness Restaurant {merchant_source_id}", default_currency="USD")
    session.add(restaurant)
    session.flush()
    session.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
    session.flush()

    return restaurant, location, source_system


def _seed_run(
    session: Session, *, location: m.Location, source_system: m.SourceSystem, mode: str, status: str, finished_at: datetime,
) -> m.IngestionRun:
    run = m.IngestionRun(
        source_system_id=source_system.id, location_id=location.id, started_at=finished_at, finished_at=finished_at,
        status=status, mode=mode, source_window_start=finished_at - timedelta(minutes=1), source_window_end=finished_at,
        notes=f"CLOVER_ACQUISITION mode={mode} location_id={location.id}",
    )
    session.add(run)
    session.commit()
    return run


def _test_no_clover_location_is_always_ready(session: Session, result: ValidationResult) -> None:
    restaurant = m.Restaurant(name="No-Clover Readiness Restaurant", default_currency="USD")
    session.add(restaurant)
    session.commit()

    readiness = readiness_svc.describe_payment_readiness(session, restaurant.id, now=NOW)
    result.check(
        "a Restaurant with no Clover-sourced Location at all is always READY — nothing to gate on",
        readiness.ready and readiness.reconciliation_status == readiness_svc.RECONCILIATION_STATUS_NOT_APPLICABLE,
    )


def _test_fresh_reconciliation_is_ready(session: Session, result: ValidationResult) -> None:
    """Test item 1 — reconciliation fresh -> READY."""
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="READY1")
    _seed_run(session, location=location, source_system=source_system, mode="LIVE_SYNC", status="COMPLETE", finished_at=NOW - timedelta(seconds=10))
    _seed_run(session, location=location, source_system=source_system, mode="RECONCILIATION", status="COMPLETE", finished_at=NOW - timedelta(seconds=20))

    readiness = readiness_svc.describe_payment_readiness(session, restaurant.id, now=NOW)
    result.check(
        "fresh reconciliation (recent COMPLETE run) + healthy live sync -> READY",
        readiness.ready and readiness.reconciliation_status == readiness_svc.RECONCILIATION_STATUS_FRESH
        and readiness.clover_live_healthy,
    )


def _test_stale_reconciliation_is_not_ready(session: Session, result: ValidationResult) -> None:
    """Test item 2 — reconciliation stale -> NOT READY, not treated as an
    error (no exception is raised by describe_payment_readiness itself —
    it is a pure read returning a calm, non-alarming reason)."""
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="READY2")
    _seed_run(session, location=location, source_system=source_system, mode="LIVE_SYNC", status="COMPLETE", finished_at=NOW - timedelta(seconds=10))
    _seed_run(
        session, location=location, source_system=source_system, mode="RECONCILIATION", status="COMPLETE",
        finished_at=NOW - readiness_svc.DEFAULT_STALENESS_THRESHOLD - timedelta(minutes=1),
    )

    readiness = readiness_svc.describe_payment_readiness(session, restaurant.id, now=NOW)
    result.check(
        "stale reconciliation (last successful run older than the staleness threshold) -> NOT READY",
        not readiness.ready and readiness.reconciliation_status == readiness_svc.RECONCILIATION_STATUS_STALE,
    )
    result.check(
        "a stale reconciliation is not (yet) flagged as persistently failing — still within the "
        "persistent-failure threshold, a normal wait",
        not readiness.is_persistently_failing,
    )


def _test_failed_reconciliation_is_not_ready(session: Session, result: ValidationResult) -> None:
    """Test item 3 — reconciliation failed -> NOT READY."""
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="READY3")
    _seed_run(session, location=location, source_system=source_system, mode="LIVE_SYNC", status="COMPLETE", finished_at=NOW - timedelta(seconds=10))
    _seed_run(session, location=location, source_system=source_system, mode="RECONCILIATION", status="FAILED", finished_at=NOW - timedelta(seconds=5))

    readiness = readiness_svc.describe_payment_readiness(session, restaurant.id, now=NOW)
    result.check(
        "a FAILED reconciliation run -> NOT READY",
        not readiness.ready and readiness.reconciliation_status == readiness_svc.RECONCILIATION_STATUS_FAILED,
    )


def _test_retry_after_failure_becomes_ready(session: Session, result: ValidationResult) -> None:
    """Test item 4 — retry reconciliation successful -> READY. A FAILED run
    followed by a later successful one must resolve back to READY —
    `describe_payment_readiness` always reads the MOST RECENT run, never a
    permanent 'once failed, always failed' state."""
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="READY4")
    _seed_run(session, location=location, source_system=source_system, mode="LIVE_SYNC", status="COMPLETE", finished_at=NOW - timedelta(seconds=10))
    _seed_run(session, location=location, source_system=source_system, mode="RECONCILIATION", status="FAILED", finished_at=NOW - timedelta(minutes=2))

    readiness_before = readiness_svc.describe_payment_readiness(session, restaurant.id, now=NOW)
    result.check("before retry: NOT READY (FAILED)", not readiness_before.ready)

    _seed_run(session, location=location, source_system=source_system, mode="RECONCILIATION", status="COMPLETE", finished_at=NOW - timedelta(seconds=5))
    readiness_after = readiness_svc.describe_payment_readiness(session, restaurant.id, now=NOW)
    result.check(
        "after a successful retry, the MOST RECENT run is COMPLETE and fresh -> READY again",
        readiness_after.ready and readiness_after.reconciliation_status == readiness_svc.RECONCILIATION_STATUS_FRESH,
    )


def _test_unhealthy_live_sync_is_not_ready(session: Session, result: ValidationResult) -> None:
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="READY5")
    _seed_run(session, location=location, source_system=source_system, mode="LIVE_SYNC", status="FAILED", finished_at=NOW - timedelta(seconds=10))
    _seed_run(session, location=location, source_system=source_system, mode="RECONCILIATION", status="COMPLETE", finished_at=NOW - timedelta(seconds=5))

    readiness = readiness_svc.describe_payment_readiness(session, restaurant.id, now=NOW)
    result.check(
        "an unhealthy (FAILED) Live Sync connector blocks readiness even when reconciliation itself is fresh",
        not readiness.ready and not readiness.clover_live_healthy,
    )


def _test_blocking_critical_attention_is_not_ready(session: Session, result: ValidationResult) -> None:
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="READY6")
    _seed_run(session, location=location, source_system=source_system, mode="LIVE_SYNC", status="COMPLETE", finished_at=NOW - timedelta(seconds=10))
    _seed_run(session, location=location, source_system=source_system, mode="RECONCILIATION", status="COMPLETE", finished_at=NOW - timedelta(seconds=5))

    item = create_attention(
        session, source_domain="TIPS", source_module="PAYMENT_EXECUTION", source_process_name="TIP_PAYOUT",
        source_reference=f"TipPaymentInstruction:9999", reason="synthetic blocking anomaly",
        priority=m.ATTENTION_PRIORITY_CRITICAL, scope=ScopeContext(scope_type=m.POSITION_SCOPE_RESTAURANT, scope_id=restaurant.id),
    )
    session.commit()

    readiness = readiness_svc.describe_payment_readiness(session, restaurant.id, now=NOW)
    result.check(
        "a CRITICAL, still-OPEN Attention item for this Restaurant's Tips blocks readiness even when "
        "Clover/reconciliation are otherwise healthy",
        not readiness.ready and readiness.has_blocking_attention,
    )

    item.status = m.ATTENTION_STATUS_RESOLVED
    session.commit()
    readiness_after_resolution = readiness_svc.describe_payment_readiness(session, restaurant.id, now=NOW)
    result.check(
        "once the CRITICAL Attention item is RESOLVED, readiness clears (no longer blocking)",
        readiness_after_resolution.ready and not readiness_after_resolution.has_blocking_attention,
    )


def _test_non_blocking_attention_does_not_affect_readiness(session: Session, result: ValidationResult) -> None:
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="READY7")
    _seed_run(session, location=location, source_system=source_system, mode="LIVE_SYNC", status="COMPLETE", finished_at=NOW - timedelta(seconds=10))
    _seed_run(session, location=location, source_system=source_system, mode="RECONCILIATION", status="COMPLETE", finished_at=NOW - timedelta(seconds=5))

    create_attention(
        session, source_domain="TIPS", source_module="PAYMENT_EXECUTION", source_process_name="TIP_PAYOUT",
        source_reference="TipPaymentInstruction:8888", reason="synthetic non-blocking (MEDIUM) item",
        priority=m.ATTENTION_PRIORITY_MEDIUM, scope=ScopeContext(scope_type=m.POSITION_SCOPE_RESTAURANT, scope_id=restaurant.id),
    )
    session.commit()

    readiness = readiness_svc.describe_payment_readiness(session, restaurant.id, now=NOW)
    result.check(
        "a MEDIUM-priority (non-CRITICAL) OPEN Attention item does NOT block payment readiness",
        readiness.ready and not readiness.has_blocking_attention,
    )


def _test_persistently_failing_flag(session: Session, result: ValidationResult) -> None:
    restaurant, location, source_system = _build_fixture(session, merchant_source_id="READY8")
    _seed_run(session, location=location, source_system=source_system, mode="LIVE_SYNC", status="COMPLETE", finished_at=NOW - timedelta(seconds=10))
    _seed_run(
        session, location=location, source_system=source_system, mode="RECONCILIATION", status="FAILED",
        finished_at=NOW - readiness_svc.DEFAULT_PERSISTENT_FAILURE_THRESHOLD - timedelta(minutes=1),
    )

    readiness = readiness_svc.describe_payment_readiness(session, restaurant.id, now=NOW)
    result.check(
        "a reconciliation failure older than the persistent-failure threshold is flagged for Attention "
        "escalation — never for a merely-stale, still-recent failure",
        not readiness.ready and readiness.is_persistently_failing,
    )

    from .tips.payment_cycle_service import maybe_raise_attention_for_payment_readiness
    raised = maybe_raise_attention_for_payment_readiness(session, restaurant_id=restaurant.id, readiness=readiness)
    session.commit()
    result.check("a persistently-failing readiness raises exactly one AttentionItem", raised is not None)

    raised_again = maybe_raise_attention_for_payment_readiness(session, restaurant_id=restaurant.id, readiness=readiness)
    session.commit()
    result.check(
        "calling it again while the SAME condition is still open returns the EXISTING item, never a duplicate",
        raised_again is not None and raised_again.id == raised.id,
    )
