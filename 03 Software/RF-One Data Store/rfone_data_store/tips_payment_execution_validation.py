"""Automated synthetic tests for the Tips Core 2.0 Payment Execution pilot
(TASK_TIPS_CORE2_PILOT §18).

Mirrors `tips_distribution_engine_validation.py`'s pattern exactly: builds a
synthetic fixture inside a disposable database, exercises `tips.readiness`,
`tips.payment_instruction`, and `tips.payout_process`, asserts the required
behaviors, and always rolls back.

Uses a FAKE Mercury client (`_FakeMercuryClient` below) — this file makes NO
network call and requires no `MERCURY_SANDBOX_API_TOKEN`. The one real-
sandbox pilot run is a separate, explicitly-marked script
(`03 Software/Tips/sandbox_pilot_e2e.py`), never part of this automated
suite (task §18, "Il test sandbox reale deve essere separato dai test
automatici normali")."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .technical.connectors.mercury.client import (
    MercuryAccount, MercuryDuplicateProtectionError, MercuryTransaction, MercuryValidationError,
)
from .tips import distribution_engine as engine
from .tips import distribution_rule_service as rule_svc
from .tips import payment_instruction as pi_svc
from .tips import payout_process as payout_svc
from .tips import readiness as readiness_svc

UTC = timezone.utc
T0 = datetime(2026, 3, 1, tzinfo=UTC)


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
            _run_all_scenarios(session, result)
        finally:
            session.rollback()
    return result


class _FakeMercuryClient:
    """Duck-types `MercuryClient`'s public surface — no network, no
    `MERCURY_SANDBOX_API_TOKEN` required. `recipient_behavior` maps a
    recipient id to one of: "ok", "sync_fail" (Failure class A),
    "unconfigured" (same as sync_fail, named for readability at call sites).
    `create_transaction_calls` lets a test assert Mercury was (or was not)
    actually called again on a retry."""

    def __init__(self, *, available_balance: Decimal, recipient_behavior: dict[str, str]):
        self._available_balance = available_balance
        self._recipient_behavior = recipient_behavior
        self._transactions_by_idempotency_key: dict[str, MercuryTransaction] = {}
        self._transactions_by_id: dict[str, MercuryTransaction] = {}
        self.create_transaction_calls = 0
        self._next_tx_id = 1

    def get_accounts(self) -> list[MercuryAccount]:
        return [
            MercuryAccount(
                id="acct-1", status="active", type="mercury", kind="checking",
                available_balance=self._available_balance, current_balance=self._available_balance,
                name="Fake Checking",
            )
        ]

    def create_transaction(
        self, *, account_id: str, recipient_id: str, amount: Decimal, payment_method: str, idempotency_key: str,
        purpose: str | None = None,
    ) -> MercuryTransaction:
        self.create_transaction_calls += 1
        existing = self._transactions_by_idempotency_key.get(idempotency_key)
        if existing is not None:
            # Mirrors the REAL sandbox behavior observed in this task's
            # Idempotency Validation test: a resubmission is rejected as a
            # duplicate, never silently returned as success.
            raise MercuryDuplicateProtectionError(
                f"Sorry, this transaction seems to be a duplicate of transaction {existing.id}.", http_status=400,
            )
        behavior = self._recipient_behavior.get(recipient_id, "ok")
        if behavior in ("sync_fail", "unconfigured"):
            raise MercuryValidationError("The recipient is not configured to receive ACH payments", http_status=400)

        tx_id = f"fake-tx-{self._next_tx_id}"
        self._next_tx_id += 1
        tx = MercuryTransaction(
            id=tx_id, status="sent", amount=amount, counterparty_name=recipient_id, posted_at=None,
            estimated_delivery_date=None, failed_at=None, reason_for_failure=None, account_id=account_id, raw={},
        )
        self._transactions_by_idempotency_key[idempotency_key] = tx
        self._transactions_by_id[tx_id] = tx
        return tx

    def get_transaction(self, transaction_id: str) -> MercuryTransaction:
        return self._transactions_by_id[transaction_id]

    def set_transaction_status(self, transaction_id: str, *, status: str, posted_at: str | None = None) -> None:
        """Test-only mutator simulating a later observed Mercury state
        change (e.g. `sent` -> `reversed`) on the next `refresh_outcome`
        poll."""
        tx = self._transactions_by_id[transaction_id]
        self._transactions_by_id[transaction_id] = MercuryTransaction(
            id=tx.id, status=status, amount=tx.amount, counterparty_name=tx.counterparty_name, posted_at=posted_at,
            estimated_delivery_date=tx.estimated_delivery_date, failed_at=tx.failed_at,
            reason_for_failure=tx.reason_for_failure, account_id=tx.account_id, raw=tx.raw,
        )


def _at(day: float, hour: int = 12) -> datetime:
    return T0 + timedelta(days=day, hours=hour)


def _build_base_fixture(session: Session, *, suffix: str = "1"):
    # `suffix` lets this fixture builder be called more than once in the
    # same test session (e.g. a second, independent Restaurant for the
    # insufficient-funding scenario) without violating `SourceSystem.code`'s
    # uniqueness or colliding source ids — each call is a fully isolated
    # source-system/merchant/location/restaurant, never shared state.
    source_system = m.SourceSystem(code=f"CLOVER-PEV-{suffix}", name="Clover", active=True)
    session.add(source_system)
    session.flush()
    merchant = m.Merchant(
        source_system_id=source_system.id, source_merchant_id=f"PEV-MERCH-{suffix}", name="PEV Merchant",
    )
    session.add(merchant)
    session.flush()
    location = m.Location(
        merchant_id=merchant.id, source_system_id=source_system.id, source_location_id=f"PEV-LOC-{suffix}",
        name="PEV Location", currency="USD",
    )
    session.add(location)
    session.flush()
    restaurant = m.Restaurant(name=f"Payment Execution Validation Restaurant {suffix}", default_currency="USD")
    session.add(restaurant)
    session.flush()
    session.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
    area = m.OperationalArea(restaurant_id=restaurant.id, name="FOH")
    session.add(area)
    session.flush()
    role_server = m.RestaurantRole(restaurant_id=restaurant.id, name="Server")
    session.add(role_server)
    session.flush()

    def make_employee(source_id: str, name: str) -> m.Employee:
        emp = m.Employee(
            location_id=location.id, source_system_id=source_system.id, source_employee_id=source_id,
            display_name=name, system_role="EMPLOYEE",
        )
        session.add(emp)
        session.flush()
        return emp

    server_a = make_employee("SRVA", "ServerA")
    server_b = make_employee("SRVB", "ServerB")
    for emp in (server_a, server_b):
        session.add(
            m.EmployeeAssignment(
                employee_id=emp.id, restaurant_id=restaurant.id, operational_area_id=area.id,
                restaurant_role_id=role_server.id, valid_from=_at(-300), valid_to=None, assignment_source="MANUAL",
            )
        )
    session.flush()

    rule_svc.create_rule(
        session, restaurant_id=restaurant.id, source_role_id=role_server.id, recipient_role_id=role_server.id,
        calculation_base=m.CALC_BASE_VOLUNTARY_TIP, rate=Decimal("0.0000"), effective_from=_at(-300),
        created_by="tester",
    )
    session.commit()
    session.expire_all()

    # Must agree with `_at(5, ...)` below (T0 + 5 days = 2026-03-06) — the
    # engine scopes a run by actual Settlement Time, never by this stored
    # `business_date` field directly, so the two must be kept consistent by
    # the fixture itself (exactly as real Clover-derived data always is).
    business_date = date(2026, 3, 6)

    def make_order_with_tip(*, employee: m.Employee, tip_minor: int, order_suffix: str) -> m.Order:
        order = m.Order(
            location_id=location.id, source_system_id=source_system.id, source_order_id=f"ORDER-{order_suffix}",
            employee_id=employee.id, source_employee_id=employee.source_employee_id,
            created_at=_at(5, 11), business_date=business_date, state="locked", payment_state="PAID",
            currency="USD", total=10000,
        )
        session.add(order)
        session.flush()
        payment = m.Payment(
            order_id=order.id, source_system_id=source_system.id, source_payment_id=f"PAY-{order_suffix}",
            employee_id=employee.id, source_employee_id=employee.source_employee_id, created_at=_at(5, 12),
            amount=10000, result="SUCCESS", currency="USD",
        )
        session.add(payment)
        session.flush()
        session.add(m.PaymentTip(payment_id=payment.id, amount=tip_minor, source_present=True))
        session.commit()
        return order

    return restaurant, server_a, server_b, make_order_with_tip


def _link_recipient(session: Session, employee: m.Employee, recipient_id: str) -> None:
    session.add(
        m.EmployeeExternalPaymentAccount(
            employee_id=employee.id, provider="MERCURY", provider_recipient_id=recipient_id, is_active=True,
        )
    )
    session.commit()


def _run_all_scenarios(session: Session, result: ValidationResult) -> None:
    restaurant, server_a, server_b, make_order_with_tip = _build_base_fixture(session)

    # === 1: Trigger / readiness — before any Order, nothing is candidate ===
    state0 = readiness_svc.describe_readiness(session, restaurant.id)
    result.check("readiness: no Business Date candidate before any Order exists", state0.business_date is None)

    make_order_with_tip(employee=server_a, tip_minor=2000, order_suffix="A1")
    make_order_with_tip(employee=server_b, tip_minor=3000, order_suffix="B1")

    state1 = readiness_svc.describe_readiness(session, restaurant.id)
    result.check("readiness: candidate Business Date found once Orders exist", state1.business_date == date(2026, 3, 6))
    result.check("readiness: ready_to_calculate is True before any calculation run", state1.ready_to_calculate)

    _link_recipient(session, server_a, "recipient-a-ok")
    _link_recipient(session, server_b, "recipient-b-fail")

    client = _FakeMercuryClient(
        available_balance=Decimal("100000.00"),
        recipient_behavior={"recipient-a-ok": "ok", "recipient-b-fail": "sync_fail"},
    )

    # === 2: payout success + synchronous failure + one-payee isolation, in
    # ONE batch run — ServerA succeeds, ServerB fails, ServerA is unaffected.
    run_result = payout_svc.run_business_date_payout(
        session, restaurant_id=restaurant.id, client=client, source_account_id="acct-1",
    )
    session.commit()

    by_employee = {i.employee_id: i for i in run_result.instructions}
    result.check("payout: two Payment Instructions were created (one per Employee)", len(run_result.instructions) == 2)
    result.check(
        "payout success: ServerA's instruction reached SENT/OUTCOME_VERIFIED", by_employee[server_a.id].status in ("SENT", "OUTCOME_VERIFIED"),
    )
    result.check(
        "one-payee isolation: ServerB's synchronous failure did not affect ServerA",
        by_employee[server_a.id].status != "NEEDS_ATTENTION",
    )
    result.check(
        "synchronous failure (class A): ServerB's instruction is NEEDS_ATTENTION with SYNCHRONOUS_VALIDATION",
        by_employee[server_b.id].status == "NEEDS_ATTENTION"
        and by_employee[server_b.id].failure_class == pi_svc.FAILURE_SYNCHRONOUS_VALIDATION,
    )
    result.check(
        "batch isolation: ServerB's failure did not roll back ServerA's already-submitted instruction",
        by_employee[server_a.id].provider_transaction_id is not None,
    )

    # === 3: RF-One-side duplicate protection — re-running the SAME Business
    # Date must never create a second instruction for ServerA, and must
    # never call Mercury again for an already-SENT instruction. ===
    calls_before = client.create_transaction_calls
    run_result_2 = payout_svc.run_business_date_payout(
        session, restaurant_id=restaurant.id, client=client, source_account_id="acct-1",
    )
    session.commit()
    result.check(
        "duplicate protection: re-running never creates a second instruction per Employee",
        len(run_result_2.instructions) == 2,
    )
    result.check(
        "duplicate protection: Mercury is never called again for ServerA's already-SENT instruction",
        client.create_transaction_calls == calls_before,
    )

    # === 4: Outcome Verification — Mercury eventually reports `sent` with
    # `postedAt` populated -> OUTCOME_VERIFIED. ===
    server_a_instruction = by_employee[server_a.id]
    client.set_transaction_status(
        server_a_instruction.provider_transaction_id, status="sent", posted_at="2026-03-06T00:00:00Z",
    )
    pi_svc.refresh_outcome(session, server_a_instruction, client)
    session.commit()
    result.check(
        "Outcome Verification: sent + postedAt -> OUTCOME_VERIFIED", server_a_instruction.status == "OUTCOME_VERIFIED",
    )

    # === 5: reversed re-opens a previously verified Outcome ===
    client.set_transaction_status(server_a_instruction.provider_transaction_id, status="reversed")
    pi_svc.refresh_outcome(session, server_a_instruction, client)
    session.commit()
    result.check(
        "reversed success: a later `reversed` observation reopens the Outcome to NEEDS_ATTENTION",
        server_a_instruction.status == "NEEDS_ATTENTION" and server_a_instruction.failure_class == pi_svc.FAILURE_OUTCOME_REOPENED,
    )

    # === 6: retry of ONLY the failed instruction — fix ServerB's reference,
    # then retry ONLY ServerB's instruction; ServerA (already reopened
    # above) must be completely untouched by this call. ===
    server_a_status_before_retry = server_a_instruction.status
    server_b_instruction = by_employee[server_b.id]
    existing_ref = session.scalars(
        select(m.EmployeeExternalPaymentAccount).where(
            m.EmployeeExternalPaymentAccount.employee_id == server_b.id,
            m.EmployeeExternalPaymentAccount.is_active.is_(True),
        )
    ).first()
    existing_ref.is_active = False
    session.commit()
    _link_recipient(session, server_b, "recipient-b-ok")
    client._recipient_behavior["recipient-b-ok"] = "ok"

    payout_svc.retry_instruction(session, server_b_instruction, client, source_account_id="acct-1")
    session.commit()
    result.check(
        "retry-only: the retried instruction (ServerB) now succeeded", server_b_instruction.status in ("SENT", "OUTCOME_VERIFIED"),
    )
    result.check(
        "retry-only: the sibling instruction (ServerA) was not touched by ServerB's retry",
        server_a_instruction.status == server_a_status_before_retry,
    )

    # === 7: insufficient funding blocks the WHOLE batch, no partial payout ==
    restaurant2, server_c, server_d, make_order_with_tip_2 = _build_base_fixture(session, suffix="2")
    make_order_with_tip_2(employee=server_c, tip_minor=500000, order_suffix="C1")
    make_order_with_tip_2(employee=server_d, tip_minor=500000, order_suffix="D1")
    _link_recipient(session, server_c, "recipient-c-ok")
    _link_recipient(session, server_d, "recipient-d-ok")
    poor_client = _FakeMercuryClient(
        available_balance=Decimal("1.00"), recipient_behavior={"recipient-c-ok": "ok", "recipient-d-ok": "ok"},
    )
    funding_result = payout_svc.run_business_date_payout(
        session, restaurant_id=restaurant2.id, client=poor_client, source_account_id="acct-1",
    )
    session.commit()
    result.check(
        "insufficient funding: batch is blocked, reason references funding", funding_result.blocked_reason is not None,
    )
    result.check(
        "insufficient funding: NO instruction was submitted to Mercury (no partial payout)",
        poor_client.create_transaction_calls == 0 and all(i.status == "READY" for i in funding_result.instructions),
    )
