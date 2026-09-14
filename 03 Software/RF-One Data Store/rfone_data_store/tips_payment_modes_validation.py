"""Automated synthetic tests for the three decided Tips payment modes
(MANUAL, AUTOMATIC+WITH_APPROVAL, AUTOMATIC+WITHOUT_APPROVAL) all
respecting Payment Readiness before any Mercury call
(TASK_TIPS_RECONCILIATION_AND_PAYMENT_CONTROL_001 §4).

Uses bare `TipPaymentCycle` rows with no instructions (readiness is checked
BEFORE instructions/funding are ever touched — see `clover_reconciliation_
poller_validation.py`'s identical rationale) and the same FAKE Mercury
client `tips_payment_execution_validation.py` already defines. Never
contacts Clover or Mercury production."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import acting_identity_service
from . import authority_service
from . import models as m
from .tips import payment_cycle_service as cycle_svc
from .tips import payment_readiness as readiness_svc
from .tips import scheduler as tips_scheduler
from .tips_payment_execution_validation import _FakeMercuryClient

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
            _test_manual_respects_readiness(session, result)
            _test_auto_with_approval_never_auto_pays_but_respects_readiness(session, result)
            _test_auto_without_approval_respects_readiness_and_sends_only_when_ready(session, result)
        finally:
            session.rollback()
    return result


def _build_restaurant_with_clover(session: Session, *, suffix: str) -> tuple[m.Restaurant, m.Location, m.SourceSystem]:
    source_system = session.scalars(select(m.SourceSystem).filter_by(code="CLOVER")).first()
    if source_system is None:
        source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
        session.add(source_system)
        session.flush()

    merchant = m.Merchant(source_system_id=source_system.id, source_merchant_id=f"MODES-{suffix}", name="Payment Modes Test Merchant")
    session.add(merchant)
    session.flush()

    location = m.Location(
        merchant_id=merchant.id, source_system_id=source_system.id, source_location_id=f"MODES-{suffix}",
        name="Payment Modes Test Location", currency="USD",
    )
    session.add(location)
    session.flush()

    restaurant = m.Restaurant(name=f"Synthetic Payment Modes Restaurant {suffix}", default_currency="USD")
    session.add(restaurant)
    session.flush()
    session.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
    session.flush()

    return restaurant, location, source_system


def _seed_reconciliation(session: Session, *, location: m.Location, source_system: m.SourceSystem, fresh: bool) -> None:
    live_sync_finished = NOW - timedelta(seconds=10)
    session.add(
        m.IngestionRun(
            source_system_id=source_system.id, location_id=location.id, started_at=live_sync_finished,
            finished_at=live_sync_finished, status="COMPLETE", mode="LIVE_SYNC",
            source_window_start=live_sync_finished - timedelta(minutes=1), source_window_end=live_sync_finished,
            notes="CLOVER_ACQUISITION mode=LIVE_SYNC",
        )
    )
    reconciliation_finished = NOW - timedelta(seconds=5) if fresh else NOW - readiness_svc.DEFAULT_STALENESS_THRESHOLD - timedelta(minutes=1)
    session.add(
        m.IngestionRun(
            source_system_id=source_system.id, location_id=location.id, started_at=reconciliation_finished,
            finished_at=reconciliation_finished, status="COMPLETE", mode="RECONCILIATION",
            source_window_start=reconciliation_finished - timedelta(minutes=1), source_window_end=reconciliation_finished,
            notes="CLOVER_ACQUISITION mode=RECONCILIATION",
        )
    )
    session.commit()


def _open_cycle(session: Session, *, restaurant_id: int) -> m.TipPaymentCycle:
    cycle = m.TipPaymentCycle(
        restaurant_id=restaurant_id, period_start=NOW - timedelta(days=1), period_end=NOW,
        status=m.TIP_PAYMENT_CYCLE_STATUS_OPEN, triggered_by="MANUAL",
        notes="synthetic payment-modes test cycle (no entitlements).",
    )
    session.add(cycle)
    session.flush()
    return cycle


def _test_manual_respects_readiness(session: Session, result: ValidationResult) -> None:
    """Test item 8 — MANUAL mode: a human directly calling
    `approve_and_pay_cycle` (Tips/app.py's Payment Control, with no
    schedule config at all) is blocked while NOT READY and succeeds once
    READY — the same gate every mode shares, exercised here through the
    plain human/MANUAL path with no scheduler involved at all."""
    restaurant, location, source_system = _build_restaurant_with_clover(session, suffix="MANUAL")
    _seed_reconciliation(session, location=location, source_system=source_system, fresh=False)

    approver = m.ActingIdentity(kind="HUMAN_USER", display_name="Manual Approver", is_active=True)
    session.add(approver)
    session.flush()
    authority_service.grant_authority(
        session, actor=approver, domain=cycle_svc.AUTHORITY_DOMAIN_TIPS,
        action=cycle_svc.AUTHORITY_ACTION_APPROVE_AND_PAY, scope_type=m.SCOPE_RESTAURANT, scope_id=restaurant.id,
    )
    session.commit()

    cycle = _open_cycle(session, restaurant_id=restaurant.id)
    client = _FakeMercuryClient(available_balance=Decimal("1000.00"), recipient_behavior={})

    blocked = False
    try:
        cycle_svc.approve_and_pay_cycle(session, cycle=cycle, acting_identity=approver, client=client, source_account_id="acct-1", now=NOW)
    except cycle_svc.PaymentNotReadyError:
        blocked = True
    result.check("MANUAL: an authorized human is blocked (PaymentNotReadyError) while reconciliation is stale", blocked)
    result.check(
        "MANUAL: the blocked attempt made NO Mercury call and left the cycle OPEN",
        client.create_transaction_calls == 0 and cycle.status == "OPEN",
    )

    _seed_reconciliation(session, location=location, source_system=source_system, fresh=True)
    cycle_svc.approve_and_pay_cycle(session, cycle=cycle, acting_identity=approver, client=client, source_account_id="acct-1", now=NOW)
    session.commit()
    result.check("MANUAL: the SAME human succeeds once reconciliation becomes fresh — cycle now APPROVED", cycle.status == "APPROVED")


def _test_auto_with_approval_never_auto_pays_but_respects_readiness(session: Session, result: ValidationResult) -> None:
    """Test item 9 — AUTOMATIC + WITH_APPROVAL: the scheduler's auto-approval
    tick must NEVER touch this Restaurant's cycle (approval always requires
    the human step) regardless of readiness; the human step, when it
    happens, still respects readiness exactly like MANUAL does."""
    restaurant, location, source_system = _build_restaurant_with_clover(session, suffix="WITHAPPR")
    _seed_reconciliation(session, location=location, source_system=source_system, fresh=True)

    valid_from = NOW - timedelta(days=365)
    session.add(
        m.TipsPaymentScheduleConfig(
            restaurant_id=restaurant.id, mode=m.TIPS_SCHEDULE_MODE_AUTOMATIC, interval_days=7,
            auto_approval_mode=m.TIPS_PAYMENT_AUTO_APPROVAL_MODE_WITH_APPROVAL,
            mercury_source_account_id="acct-1", valid_from=valid_from,
        )
    )
    session.commit()

    cycle = _open_cycle(session, restaurant_id=restaurant.id)
    client = _FakeMercuryClient(available_balance=Decimal("1000.00"), recipient_behavior={})

    outcomes = tips_scheduler.run_due_payment_cycle_auto_approvals(session, now=NOW, client=client)
    result.check(
        "AUTO WITH APPROVAL: the auto-approval tick never touches a WITH_APPROVAL Restaurant's cycle at all",
        all(o.restaurant_id != restaurant.id for o in outcomes) and cycle.status == "OPEN"
        and client.create_transaction_calls == 0,
    )

    approver = m.ActingIdentity(kind="HUMAN_USER", display_name="With-Approval Approver", is_active=True)
    session.add(approver)
    session.flush()
    authority_service.grant_authority(
        session, actor=approver, domain=cycle_svc.AUTHORITY_DOMAIN_TIPS,
        action=cycle_svc.AUTHORITY_ACTION_APPROVE_AND_PAY, scope_type=m.SCOPE_RESTAURANT, scope_id=restaurant.id,
    )
    session.commit()

    _seed_reconciliation(session, location=location, source_system=source_system, fresh=False)
    blocked = False
    try:
        cycle_svc.approve_and_pay_cycle(session, cycle=cycle, acting_identity=approver, client=client, source_account_id="acct-1", now=NOW)
    except cycle_svc.PaymentNotReadyError:
        blocked = True
    result.check("AUTO WITH APPROVAL: the human approval step itself still respects readiness", blocked)


def _test_auto_without_approval_respects_readiness_and_sends_only_when_ready(session: Session, result: ValidationResult) -> None:
    """Test items 10/11 — AUTOMATIC + WITHOUT_APPROVAL: the SYSTEM Acting
    Identity attempts Approve & Pay automatically, but only actually reaches
    Mercury once readiness reports READY — never before."""
    restaurant, location, source_system = _build_restaurant_with_clover(session, suffix="NOAPPR")
    _seed_reconciliation(session, location=location, source_system=source_system, fresh=False)

    valid_from = NOW - timedelta(days=365)
    session.add(
        m.TipsPaymentScheduleConfig(
            restaurant_id=restaurant.id, mode=m.TIPS_SCHEDULE_MODE_AUTOMATIC, interval_days=7,
            auto_approval_mode=m.TIPS_PAYMENT_AUTO_APPROVAL_MODE_WITHOUT_APPROVAL,
            mercury_source_account_id="acct-1", valid_from=valid_from,
        )
    )
    session.commit()

    system_identity = acting_identity_service.get_or_create_system_identity(session)
    authority_service.grant_authority(
        session, actor=system_identity, domain=cycle_svc.AUTHORITY_DOMAIN_TIPS,
        action=cycle_svc.AUTHORITY_ACTION_APPROVE_AND_PAY, scope_type=m.SCOPE_RESTAURANT, scope_id=restaurant.id,
    )
    session.commit()

    cycle = _open_cycle(session, restaurant_id=restaurant.id)
    client = _FakeMercuryClient(available_balance=Decimal("1000.00"), recipient_behavior={})

    outcomes_not_ready = tips_scheduler.run_due_payment_cycle_auto_approvals(session, now=NOW, client=client)
    session.commit()
    this_outcome = next(o for o in outcomes_not_ready if o.restaurant_id == restaurant.id)
    result.check(
        "AUTO WITHOUT APPROVAL (test 10): while reconciliation is stale, the tick reports NOT approved, "
        "with a calm reason — never an exception surfaced to the scheduler loop",
        not this_outcome.approved and this_outcome.reason is not None,
    )
    result.check(
        "AUTO WITHOUT APPROVAL (test 11): NO Mercury call was made and the cycle stayed OPEN while NOT READY",
        client.create_transaction_calls == 0 and cycle.status == "OPEN",
    )

    _seed_reconciliation(session, location=location, source_system=source_system, fresh=True)
    outcomes_ready = tips_scheduler.run_due_payment_cycle_auto_approvals(session, now=NOW, client=client)
    session.commit()
    this_outcome_ready = next(o for o in outcomes_ready if o.restaurant_id == restaurant.id)
    result.check(
        "AUTO WITHOUT APPROVAL (test 11): once READY, the SAME cycle is approved automatically, by the "
        "SYSTEM Acting Identity, with no human step",
        this_outcome_ready.approved and cycle.status == "APPROVED"
        and cycle.approved_by_identity_id == system_identity.id,
    )
