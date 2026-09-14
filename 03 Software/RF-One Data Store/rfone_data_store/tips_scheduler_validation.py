"""Automated synthetic tests for `tips.schedule_service` and `tips.scheduler`
(TASK_TIPS_COMPLETE_001 §3/§16) — Calculation Schedule, Payment Schedule,
and the two separate automatic scheduler loops. Also covers the residual
items not already exercised by `tips_payment_execution_validation.py`:
already-paid Tip Entitlements excluded from a later Payment Cycle (§10/§19
item 11), and a Mercury `blocked` transaction status routed to Attention
(§19 item 17).

Mirrors the existing Tips validation modules' pattern: synthetic fixture,
disposable database, a small fake Mercury client, always rolled back."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import authority_service
from . import models as m
from .technical.connectors.mercury.client import MercuryAccount, MercuryTransaction
from .tips import distribution_rule_service as rule_svc
from .tips import payment_cycle_service as cycle_svc
from .tips import payout_process as payout_svc
from .tips import readiness as readiness_svc
from .tips import schedule_service as sched_svc
from .tips import scheduler

UTC = timezone.utc
T0 = datetime(2026, 5, 1, tzinfo=UTC)


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
            _test_schedule_effective_dating(session, result)
            _test_is_due_logic(session, result)
            _test_calculation_scheduler_end_to_end(session, result)
            _test_payment_scheduler_end_to_end(session, result)
            _test_already_paid_entitlements_excluded(session, result)
            _test_blocked_mercury_status_raises_attention(session, result)
        finally:
            session.rollback()
    return result


class _FakeMercuryClient:
    """Minimal fake — only what this file's scenarios need: a funded
    account and configurable per-recipient behavior, including a
    `blocked` terminal transaction status (task §19 item 17, not otherwise
    exercised by `tips_payment_execution_validation.py`)."""

    def __init__(self, *, available_balance: Decimal = Decimal("100000.00")):
        self._available_balance = available_balance
        self._transactions_by_idempotency_key: dict[str, MercuryTransaction] = {}
        self._transactions_by_id: dict[str, MercuryTransaction] = {}
        self._next_tx_id = 1
        self.next_status = "sent"

    def get_accounts(self) -> list[MercuryAccount]:
        return [
            MercuryAccount(
                id="acct-1", status="active", type="mercury", kind="checking",
                available_balance=self._available_balance, current_balance=self._available_balance,
                name="Fake Checking",
            )
        ]

    def create_transaction(
        self, *, account_id, recipient_id, amount, payment_method, idempotency_key, purpose=None,
    ) -> MercuryTransaction:
        existing = self._transactions_by_idempotency_key.get(idempotency_key)
        if existing is not None:
            return existing
        tx_id = f"fake-tx-{self._next_tx_id}"
        self._next_tx_id += 1
        tx = MercuryTransaction(
            id=tx_id, status=self.next_status, amount=amount, counterparty_name=recipient_id, posted_at=None,
            estimated_delivery_date=None, failed_at=None, reason_for_failure=None, account_id=account_id, raw={},
        )
        self._transactions_by_idempotency_key[idempotency_key] = tx
        self._transactions_by_id[tx_id] = tx
        return tx

    def get_transaction(self, transaction_id: str) -> MercuryTransaction:
        return self._transactions_by_id[transaction_id]


def _at(day: float, hour: int = 12) -> datetime:
    return T0 + timedelta(days=day, hours=hour)


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite round-trips `DateTime(timezone=True)` as offset-naive — same
    caveat documented throughout this codebase (e.g. `acquisition.
    _aware_utc`) — normalize before comparing a DB-read value against a
    freshly-constructed aware one."""
    if dt is None or dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=UTC)


def _build_fixture(session: Session, *, suffix: str):
    source_system = m.SourceSystem(code=f"CLOVER-SCHED-{suffix}", name="Clover", active=True)
    session.add(source_system)
    session.flush()
    merchant = m.Merchant(source_system_id=source_system.id, source_merchant_id=f"SCHED-MERCH-{suffix}", name="Sched Merchant")
    session.add(merchant)
    session.flush()
    location = m.Location(
        merchant_id=merchant.id, source_system_id=source_system.id, source_location_id=f"SCHED-LOC-{suffix}",
        name="Sched Location", currency="USD",
    )
    session.add(location)
    session.flush()
    restaurant = m.Restaurant(name=f"Scheduler Test Restaurant {suffix}", default_currency="USD")
    session.add(restaurant)
    session.flush()
    session.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
    area = m.OperationalArea(restaurant_id=restaurant.id, name="FOH")
    session.add(area)
    session.flush()
    role_server = m.RestaurantRole(restaurant_id=restaurant.id, name="Server")
    session.add(role_server)
    session.flush()
    employee = m.Employee(
        location_id=location.id, source_system_id=source_system.id, source_employee_id=f"EMP-{suffix}",
        display_name=f"Server {suffix}", system_role="EMPLOYEE",
    )
    session.add(employee)
    session.flush()
    session.add(
        m.EmployeeAssignment(
            employee_id=employee.id, restaurant_id=restaurant.id, operational_area_id=area.id,
            restaurant_role_id=role_server.id, valid_from=_at(-300), valid_to=None, assignment_source="MANUAL",
        )
    )
    rule_svc.create_rule(
        session, restaurant_id=restaurant.id, source_role_id=role_server.id, recipient_role_id=role_server.id,
        calculation_base=m.CALC_BASE_VOLUNTARY_TIP, rate=Decimal("0.0000"), effective_from=_at(-300),
        created_by="tester",
    )
    session.commit()
    return restaurant, location, source_system, employee


def _make_order_with_tip(session, *, location, source_system, employee, business_date, order_suffix, tip_minor=1500):
    order_time = datetime(business_date.year, business_date.month, business_date.day, 11, tzinfo=UTC)
    order = m.Order(
        location_id=location.id, source_system_id=source_system.id, source_order_id=f"ORDER-{order_suffix}",
        employee_id=employee.id, source_employee_id=employee.source_employee_id,
        created_at=order_time, business_date=business_date, state="locked", payment_state="PAID",
        currency="USD", total=10000,
    )
    session.add(order)
    session.flush()
    payment = m.Payment(
        order_id=order.id, source_system_id=source_system.id, source_payment_id=f"PAY-{order_suffix}",
        employee_id=employee.id, source_employee_id=employee.source_employee_id,
        created_at=order_time + timedelta(minutes=30), amount=10000, result="SUCCESS", currency="USD",
    )
    session.add(payment)
    session.flush()
    session.add(m.PaymentTip(payment_id=payment.id, amount=tip_minor, source_present=True))
    session.commit()
    return order


def _authorized_approver(session: Session, *, suffix: str) -> m.ActingIdentity:
    approver = m.ActingIdentity(kind="HUMAN_USER", display_name=f"Sched Approver {suffix}", is_active=True)
    session.add(approver)
    session.flush()
    authority_service.grant_authority(
        session, actor=approver, domain=cycle_svc.AUTHORITY_DOMAIN_TIPS,
        action=cycle_svc.AUTHORITY_ACTION_APPROVE_AND_PAY, scope_type=m.SCOPE_GLOBAL, scope_id=None,
    )
    session.commit()
    return approver


def _test_schedule_effective_dating(session: Session, result: ValidationResult) -> None:
    restaurant, _location, _source_system, _employee = _build_fixture(session, suffix="EFFDATE")

    t1 = datetime(2026, 1, 1, tzinfo=UTC)
    cfg1 = sched_svc.set_calculation_schedule(
        session, restaurant_id=restaurant.id, mode="AUTOMATIC", interval_days=1,
        execution_time=time(2, 0), effective_from=t1, created_by="tester",
    )
    t2 = datetime(2026, 2, 1, tzinfo=UTC)
    cfg2 = sched_svc.set_calculation_schedule(
        session, restaurant_id=restaurant.id, mode="AUTOMATIC", interval_days=7,
        execution_time=time(3, 0), effective_from=t2, created_by="tester",
    )
    session.commit()
    session.expire_all()
    cfg1 = session.get(m.TipsCalculationScheduleConfig, cfg1.id)

    result.check(
        "effective dating: the prior config's valid_to was closed at the new config's effective_from, "
        "never rewritten otherwise",
        cfg1.valid_to is not None and _aware(cfg1.valid_to) == t2 and cfg1.interval_days == 1,
    )
    resolved_before = sched_svc.get_calculation_schedule_effective_at(
        session, restaurant_id=restaurant.id, at=datetime(2026, 1, 15, tzinfo=UTC),
    )
    resolved_after = sched_svc.get_calculation_schedule_effective_at(
        session, restaurant_id=restaurant.id, at=datetime(2026, 2, 15, tzinfo=UTC),
    )
    result.check(
        "effective dating: resolving a moment in the OLD window returns the OLD config (interval_days=1)",
        resolved_before is not None and resolved_before.interval_days == 1,
    )
    result.check(
        "effective dating: resolving a moment in the NEW window returns the NEW config (interval_days=7)",
        resolved_after is not None and resolved_after.id == cfg2.id and resolved_after.interval_days == 7,
    )

    invalid_rejected = False
    try:
        sched_svc.set_calculation_schedule(session, restaurant_id=restaurant.id, mode="AUTOMATIC", interval_days=None)
    except sched_svc.ScheduleConfigError:
        invalid_rejected = True
    result.check(
        "validation: AUTOMATIC mode with no interval_days is rejected — never silently defaulted to daily/weekly",
        invalid_rejected,
    )

    # Payment Schedule mirrors the same effective-dating shape, independently.
    pay_cfg = sched_svc.set_payment_schedule(
        session, restaurant_id=restaurant.id, mode="AUTOMATIC", interval_days=7, execution_time=time(4, 0),
        mercury_source_account_id="acct-configured", effective_from=t1, created_by="tester",
    )
    session.commit()
    result.check(
        "Payment Schedule is independent of Calculation Schedule and carries its own Mercury source account",
        pay_cfg.mercury_source_account_id == "acct-configured" and pay_cfg.interval_days == 7,
    )


def _test_is_due_logic(session: Session, result: ValidationResult) -> None:
    anchor = date(2026, 1, 1)
    exec_time = time(2, 0)

    not_yet = sched_svc.is_due(
        mode="AUTOMATIC", interval_days=7, execution_time=exec_time, anchor_date=anchor,
        now=datetime(2025, 12, 25, 12, 0, tzinfo=UTC), last_triggered_at=None,
    )
    result.check("is_due: False while the anchor date itself is still in the future", not_yet is False)

    already_handled_anchor_day = sched_svc.is_due(
        mode="AUTOMATIC", interval_days=7, execution_time=exec_time, anchor_date=anchor,
        now=datetime(2026, 1, 5, 12, 0, tzinfo=UTC),
        last_triggered_at=datetime(2026, 1, 1, 3, 0, tzinfo=UTC),
    )
    result.check(
        "is_due: False once the anchor day's own occurrence was already triggered, even before the next "
        "(day 8) occurrence arrives",
        already_handled_anchor_day is False,
    )

    before_time = sched_svc.is_due(
        mode="AUTOMATIC", interval_days=7, execution_time=exec_time, anchor_date=anchor,
        now=datetime(2026, 1, 8, 1, 0, tzinfo=UTC), last_triggered_at=None,
    )
    result.check("is_due: False on the due DAY but before the configured execution_time", before_time is False)

    due_now = sched_svc.is_due(
        mode="AUTOMATIC", interval_days=7, execution_time=exec_time, anchor_date=anchor,
        now=datetime(2026, 1, 8, 3, 0, tzinfo=UTC), last_triggered_at=None,
    )
    result.check("is_due: True once the due day AND execution_time have both passed", due_now is True)

    already_handled = sched_svc.is_due(
        mode="AUTOMATIC", interval_days=7, execution_time=exec_time, anchor_date=anchor,
        now=datetime(2026, 1, 8, 5, 0, tzinfo=UTC),
        last_triggered_at=datetime(2026, 1, 8, 3, 0, tzinfo=UTC),
    )
    result.check(
        "is_due: False again once this occurrence was already triggered — a scheduler poll tick never "
        "re-triggers the same occurrence",
        already_handled is False,
    )

    manual_never_due = sched_svc.is_due(
        mode="MANUAL", interval_days=None, execution_time=None, anchor_date=None,
        now=datetime(2026, 1, 8, 3, 0, tzinfo=UTC), last_triggered_at=None,
    )
    result.check("is_due: MANUAL mode is never due, regardless of timing", manual_never_due is False)


def _test_calculation_scheduler_end_to_end(session: Session, result: ValidationResult) -> None:
    restaurant, location, source_system, employee = _build_fixture(session, suffix="CALCSCHED")
    business_date = date(2026, 5, 3)
    _make_order_with_tip(session, location=location, source_system=source_system, employee=employee, business_date=business_date, order_suffix="CS1")

    now = datetime(2026, 5, 3, 23, 0, tzinfo=UTC)
    sched_svc.set_calculation_schedule(
        session, restaurant_id=restaurant.id, mode="AUTOMATIC", interval_days=1, execution_time=time(22, 0),
        anchor_date=date(2026, 5, 3), effective_from=now - timedelta(days=1),
    )
    session.commit()

    outcomes = scheduler.run_due_calculations(session, now=now)
    session.commit()
    mine = [o for o in outcomes if o.restaurant_id == restaurant.id]
    result.check(
        "calculation scheduler: an AUTOMATIC Restaurant whose cycle is due gets calculated",
        len(mine) == 1 and mine[0].result.ran,
    )

    outcomes_again = scheduler.run_due_calculations(session, now=now + timedelta(minutes=5))
    mine_again = [o for o in outcomes_again if o.restaurant_id == restaurant.id]
    result.check(
        "calculation scheduler: polling again within the same due window does not re-trigger",
        len(mine_again) == 0,
    )

    # A second, MANUAL-mode Restaurant must never be touched by the scheduler.
    restaurant_manual, location_m, source_system_m, employee_m = _build_fixture(session, suffix="CALCMANUAL")
    _make_order_with_tip(session, location=location_m, source_system=source_system_m, employee=employee_m, business_date=business_date, order_suffix="CM1")
    outcomes_manual_check = scheduler.run_due_calculations(session, now=now)
    touched_manual = [o for o in outcomes_manual_check if o.restaurant_id == restaurant_manual.id]
    result.check(
        "calculation scheduler: a Restaurant with no AUTOMATIC Calculation Schedule is never triggered",
        len(touched_manual) == 0,
    )
    state = readiness_svc.describe_readiness(session, restaurant_manual.id)
    result.check(
        "calculation scheduler: the untouched Restaurant's Business Date remains uncalculated",
        not state.already_calculated,
    )


def _test_payment_scheduler_end_to_end(session: Session, result: ValidationResult) -> None:
    restaurant, location, source_system, employee = _build_fixture(session, suffix="PAYSCHED")
    business_date = date(2026, 5, 3)
    _make_order_with_tip(session, location=location, source_system=source_system, employee=employee, business_date=business_date, order_suffix="PS1")
    calc = payout_svc.run_calculation_now(session, restaurant_id=restaurant.id)
    session.commit()
    result.check("payment scheduler fixture: calculation ran so there is something unpaid to aggregate", calc.ran)

    now = datetime(2026, 5, 10, 23, 0, tzinfo=UTC)
    sched_svc.set_payment_schedule(
        session, restaurant_id=restaurant.id, mode="AUTOMATIC", interval_days=7, execution_time=time(22, 0),
        anchor_date=date(2026, 5, 3), effective_from=now - timedelta(days=8),
    )
    session.commit()

    outcomes = scheduler.run_due_payment_cycle_starts(session, now=now)
    session.commit()
    mine = [o for o in outcomes if o.restaurant_id == restaurant.id]
    result.check(
        "payment scheduler: an AUTOMATIC Restaurant whose payment cycle is due gets an OPEN cycle started "
        "— but is NEVER auto-approved (Approve & Pay always requires an explicit authorized action)",
        len(mine) == 1 and mine[0].cycle is not None and mine[0].cycle.status == "OPEN",
    )

    outcomes_again = scheduler.run_due_payment_cycle_starts(session, now=now + timedelta(minutes=5))
    mine_again = [o for o in outcomes_again if o.restaurant_id == restaurant.id]
    result.check(
        "payment scheduler: polling again does not open a second concurrent cycle",
        len(mine_again) == 0 or (len(mine_again) == 1 and mine_again[0].cycle.id == mine[0].cycle.id),
    )


def _test_already_paid_entitlements_excluded(session: Session, result: ValidationResult) -> None:
    restaurant, location, source_system, employee = _build_fixture(session, suffix="PAIDEXCL")
    day1 = date(2026, 5, 3)
    _make_order_with_tip(session, location=location, source_system=source_system, employee=employee, business_date=day1, order_suffix="PE1", tip_minor=1000)
    calc1 = payout_svc.run_calculation_now(session, restaurant_id=restaurant.id)
    session.commit()
    result.check("already-paid exclusion fixture: day 1 calculated", calc1.ran)

    from .technical.connectors.mercury.client import MercuryClient  # noqa: F401 — type reference only, not used
    client = _FakeMercuryClient()
    _link = lambda emp, ref: session.add(  # noqa: E731
        m.EmployeeExternalPaymentAccount(employee_id=emp.id, provider="MERCURY", provider_recipient_id=ref, is_active=True)
    )
    _link(employee, "recipient-paidexcl")
    session.commit()

    cycle1 = cycle_svc.start_payment_cycle(session, restaurant_id=restaurant.id, triggered_by="MANUAL")
    session.commit()
    approver = _authorized_approver(session, suffix="PAIDEXCL")
    cycle_svc.approve_and_pay_cycle(session, cycle=cycle1, acting_identity=approver, client=client, source_account_id="acct-1")
    session.commit()

    day1_entitlement = session.scalars(
        select(m.TipEntitlement).where(m.TipEntitlement.calculation_run_id == calc1.calculation_run.id)
    ).first()
    result.check(
        "already-paid: day 1's entitlement is now linked to a Payment Instruction (paid)",
        day1_entitlement is not None and day1_entitlement.tip_payment_instruction_id is not None,
    )

    readiness_after_pay = cycle_svc.describe_payment_cycle_readiness(session, restaurant.id)
    result.check(
        "already-paid: with cycle 1 APPROVED and nothing new calculated, there is nothing unpaid left",
        not readiness_after_pay.has_unpaid,
    )

    # A NEW Business Date's entitlement must be the ONLY thing the NEXT
    # cycle aggregates — day 1's already-paid entitlement must never
    # reappear in it.
    day2 = date(2026, 5, 4)
    _make_order_with_tip(session, location=location, source_system=source_system, employee=employee, business_date=day2, order_suffix="PE2", tip_minor=2000)
    calc2 = payout_svc.run_calculation_now(session, restaurant_id=restaurant.id)
    session.commit()
    result.check("already-paid exclusion fixture: day 2 calculated independently", calc2.ran)

    cycle2 = cycle_svc.start_payment_cycle(session, restaurant_id=restaurant.id, triggered_by="MANUAL")
    session.commit()
    cycle2_entitlements = session.scalars(
        select(m.TipEntitlement).where(
            m.TipEntitlement.restaurant_id == restaurant.id, m.TipEntitlement.tip_payment_instruction_id.in_(
                select(m.TipPaymentInstruction.id).where(m.TipPaymentInstruction.payment_cycle_id == cycle2.id)
            ),
        )
    ).all()
    result.check(
        "already-paid: the second Payment Cycle aggregates ONLY day 2's entitlement — day 1's already-paid "
        "entitlement is correctly excluded",
        len(cycle2_entitlements) == 1 and cycle2_entitlements[0].business_date == day2,
    )
    cycle2_instruction = session.scalars(
        select(m.TipPaymentInstruction).where(m.TipPaymentInstruction.payment_cycle_id == cycle2.id)
    ).first()
    result.check(
        "already-paid: the second cycle's instruction amount reflects ONLY day 2's tip, not day 1's again",
        cycle2_instruction is not None and cycle2_instruction.amount_minor == 2000,
    )


def _test_blocked_mercury_status_raises_attention(session: Session, result: ValidationResult) -> None:
    restaurant, location, source_system, employee = _build_fixture(session, suffix="BLOCKED")
    business_date = date(2026, 5, 3)
    _make_order_with_tip(session, location=location, source_system=source_system, employee=employee, business_date=business_date, order_suffix="BL1")
    calc = payout_svc.run_calculation_now(session, restaurant_id=restaurant.id)
    session.commit()
    result.check("blocked-status fixture: calculation ran", calc.ran)

    session.add(
        m.EmployeeExternalPaymentAccount(employee_id=employee.id, provider="MERCURY", provider_recipient_id="recipient-blocked", is_active=True)
    )
    session.commit()

    client = _FakeMercuryClient()
    client.next_status = "blocked"
    cycle = cycle_svc.start_payment_cycle(session, restaurant_id=restaurant.id, triggered_by="MANUAL")
    session.commit()
    approver = _authorized_approver(session, suffix="BLOCKED")
    cycle_svc.approve_and_pay_cycle(session, cycle=cycle, acting_identity=approver, client=client, source_account_id="acct-1")
    session.commit()

    instruction = session.scalars(
        select(m.TipPaymentInstruction).where(m.TipPaymentInstruction.payment_cycle_id == cycle.id)
    ).first()
    result.check(
        "Mercury 'blocked' status is a distinct, real exception path this test now exercises",
        instruction is not None and instruction.provider_status == "blocked",
    )
    # `submit_payment_instruction` only classifies a SYNCHRONOUS exception
    # (an HTTP-level rejection) as NEEDS_ATTENTION at submit time; an
    # asynchronous `blocked` observed later via `refresh_outcome` is also
    # classified as NEEDS_ATTENTION (PROVIDER_STATUS_FAILURE) — verify via
    # an explicit refresh pass, since `create_transaction` here returns
    # `blocked` synchronously (this fake's simplification).
    if instruction.status != "NEEDS_ATTENTION" and instruction.provider_transaction_id is not None:
        cycle_svc.refresh_outcomes_for_cycle(session, cycle, client)
        session.commit()
    result.check(
        "Mercury 'blocked' status routes this instruction to NEEDS_ATTENTION with an AttentionItem raised",
        instruction.status == "NEEDS_ATTENTION" and instruction.attention_item_id is not None,
    )
