"""Mandatory Tips payment-connector acceptance tests (STEP 12B integration
§27) — payment-mode configuration selects the connector to invoke, a fake
connector can replace Mercury purely through configuration,
`TipPaymentInstruction` never changes shape when connector configuration
changes, missing/unknown connector configuration fails closed (never a
silent Mercury fallback), Mercury itself still works through the SAME
resolver when actually selected, and the scheduler's automatic execution
path resolves its connector the same way production code does. No real
external provider call is ever made — the "Mercury" case below is driven by
a fake, `MercuryClient`-shaped stub, exactly like `tips_payment_execution_
validation.py`'s own `_FakeMercuryClient`."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from . import acting_identity_service
from . import authority_service
from . import models as m
from .tips import payment_connector as connector_svc
from .tips import payment_cycle_service as cycle_svc
from .tips import payment_instruction as pi_svc
from .tips import scheduler as scheduler_svc
from .tips import schedule_service as sched_svc

UTC = timezone.utc
T0 = datetime(2026, 5, 1, tzinfo=UTC)

CONNECTOR_CODE_FAKE = "FAKE_TEST_CONNECTOR"


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
            _test_configuration_selects_and_invokes_connector(session, result)
            _test_instruction_unchanged_across_connector_switch(session, result)
            _test_fail_closed_behavior(session, result)
            _test_mercury_through_resolver(session, result)
            _test_scheduler_uses_configured_connector(session, result)
            _test_provider_reflects_actual_connector_not_a_default(session, result)
        finally:
            session.rollback()
    return result


# ---------------------------------------------------------------------------
# A fake connector that is NOT a Mercury adapter at all — proves the seam
# does not secretly assume Mercury shape (test C/G/H/I).
# ---------------------------------------------------------------------------


class _FakeConnector:
    connector_code = CONNECTOR_CODE_FAKE

    def __init__(self, *, available_balance: Decimal = Decimal("100000.00"), fail_recipients: frozenset[str] = frozenset()):
        self.create_transaction_calls = 0
        self._available_balance = available_balance
        self._fail_recipients = fail_recipients
        self._tx_by_id: dict[str, connector_svc.ConnectorTransaction] = {}
        self._next_id = 1

    def create_transaction(self, *, account_id, recipient_id, amount, payment_method, idempotency_key):
        self.create_transaction_calls += 1
        if recipient_id in self._fail_recipients:
            raise connector_svc.ConnectorValidationError(f"fake recipient {recipient_id!r} rejected")
        tx_id = f"fake-{self._next_id}"
        self._next_id += 1
        tx = connector_svc.ConnectorTransaction(id=tx_id, status="sent", posted_at="2026-05-01T00:00:00Z")
        self._tx_by_id[tx_id] = tx
        return tx

    def get_transaction(self, transaction_id):
        return self._tx_by_id[transaction_id]

    def get_accounts(self):
        return [
            connector_svc.ConnectorAccount(
                id="fake-acct-1", type="fake", status="active", kind="checking",
                available_balance=self._available_balance,
            )
        ]

    def find_recipient_by_name(self, name):
        return connector_svc.ConnectorRecipient(id=f"fake-recipient-{name}", name=name)

    def resolve_fallback_source_account_id(self):
        return self.get_accounts()[0].id


class _FakeMercuryClient:
    """Duck-types `MercuryClient`'s public surface exactly like
    `tips_payment_execution_validation._FakeMercuryClient` — separate copy
    here so this file has no import-time dependency on that one."""

    def __init__(self):
        self.create_transaction_calls = 0
        self._tx_by_id: dict = {}
        self._next_id = 1

    def get_accounts(self):
        from .technical.connectors.mercury.client import MercuryAccount
        return [
            MercuryAccount(
                id="mercury-acct-1", status="active", type="mercury", kind="checking",
                available_balance=Decimal("50000.00"), current_balance=Decimal("50000.00"), name="Fake Mercury Checking",
            )
        ]

    def create_transaction(self, *, account_id, recipient_id, amount, payment_method, idempotency_key, purpose=None):
        from .technical.connectors.mercury.client import MercuryTransaction
        self.create_transaction_calls += 1
        tx_id = f"fake-mercury-tx-{self._next_id}"
        self._next_id += 1
        tx = MercuryTransaction(
            id=tx_id, status="sent", amount=amount, counterparty_name=recipient_id, posted_at=None,
            estimated_delivery_date=None, failed_at=None, reason_for_failure=None, account_id=account_id, raw={},
        )
        self._tx_by_id[tx_id] = tx
        return tx

    def get_transaction(self, transaction_id):
        return self._tx_by_id[transaction_id]

    def find_recipient_by_name(self, name):
        from .technical.connectors.mercury.client import MercuryRecipient
        return MercuryRecipient(id=f"mercury-recipient-{name}", name=name, status="active")


class _fake_connector_registered:
    """Test-only context manager: registers `_FakeConnector` under
    `CONNECTOR_CODE_FAKE` in the SAME registry `resolve_connector` reads in
    production, and always restores the registry afterward — proves the
    registry-based seam is genuinely swappable (test C) without leaving a
    test-only connector permanently registered for production code."""

    def __enter__(self):
        connector_svc._CONNECTOR_FACTORIES[CONNECTOR_CODE_FAKE] = _FakeConnector
        return self

    def __exit__(self, *exc_info):
        connector_svc._CONNECTOR_FACTORIES.pop(CONNECTOR_CODE_FAKE, None)


class _recipient_reference_override:
    """Test-only: `_active_recipient_reference` looks up
    `EmployeeExternalPaymentAccount` by exact `provider` match, and that
    table's CHECK constraint deliberately does not (yet) accept
    `CONNECTOR_CODE_FAKE` (see `_make_fixture`'s own comment). This
    monkeypatches `payment_instruction._active_recipient_reference` for the
    duration of one scenario to return a synthetic reference for the fake
    connector — isolating "does connector routing work" from the separate,
    narrower, legitimately-scoped question of which connectors have a real
    onboarded recipient-reference row today."""

    def __init__(self, *, employee_id: int, recipient_id: str):
        self._employee_id = employee_id
        self._recipient_id = recipient_id
        self._original = pi_svc._active_recipient_reference

    def __enter__(self):
        employee_id, recipient_id = self._employee_id, self._recipient_id

        @dataclass
        class _FakeReference:
            id: int
            provider_recipient_id: str

        def _fake_lookup(session, emp_id, *, connector_code):
            if emp_id != employee_id:
                return None
            return _FakeReference(id=1, provider_recipient_id=recipient_id)

        pi_svc._active_recipient_reference = _fake_lookup
        return self

    def __exit__(self, *exc_info):
        pi_svc._active_recipient_reference = self._original


def _make_fixture(session: Session, *, suffix: str, connector_code: str | None):
    """A minimal Restaurant + one Employee + one OPEN TipPaymentCycle with
    one READY TipPaymentInstruction + an active recipient reference for
    whichever connector is configured, plus a TipsPaymentScheduleConfig
    naming `connector_code` (STEP 12B: the setting that identifies the
    connector to invoke). Deliberately bypasses Calculation/Entitlement
    (that pipeline is `tips_payment_execution_validation.py`'s concern) —
    this file is about connector ROUTING, not calculation correctness."""
    source_system = m.SourceSystem(code=f"NONCLOVER-CONN-{suffix}", name="Non-Clover", active=True)
    session.add(source_system)
    session.flush()
    merchant = m.Merchant(
        source_system_id=source_system.id, source_merchant_id=f"CONN-MERCH-{suffix}", name="Connector Test Merchant",
    )
    session.add(merchant)
    session.flush()
    location = m.Location(
        merchant_id=merchant.id, source_system_id=source_system.id, source_location_id=f"CONN-LOC-{suffix}",
        name="Connector Test Location", currency="USD",
    )
    session.add(location)
    session.flush()
    restaurant = m.Restaurant(name=f"Connector Test Restaurant {suffix}", default_currency="USD")
    session.add(restaurant)
    session.flush()
    session.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
    employee = m.Employee(
        location_id=location.id, source_system_id=source_system.id, source_employee_id=f"CONN-EMP-{suffix}",
        display_name=f"Connector Employee {suffix}", system_role="EMPLOYEE",
    )
    session.add(employee)
    session.flush()

    # `employee_external_payment_accounts.provider` is CHECK-constrained to
    # currently-real, onboarded connectors (today just 'MERCURY' — widened
    # by ITS OWN future migration when a second real connector is
    # onboarded, mirroring `f5d11c7966be`'s own precedent). The synthetic
    # `CONNECTOR_CODE_FAKE` used below to prove connector-routing is
    # swappable is deliberately NOT a real onboarded connector, so it is
    # never written to this table — tests exercising it use
    # `_recipient_reference_override` instead (see below), keeping this
    # schema honestly limited to real connectors while still proving the
    # CODE path is connector-agnostic.
    if connector_code == connector_svc.CONNECTOR_CODE_MERCURY:
        session.add(
            m.EmployeeExternalPaymentAccount(
                employee_id=employee.id, provider=connector_code,
                provider_recipient_id=f"recipient-{suffix}", is_active=True,
            )
        )

    cycle = m.TipPaymentCycle(
        restaurant_id=restaurant.id, period_start=T0, period_end=T0 + timedelta(days=1),
        status=m.TIP_PAYMENT_CYCLE_STATUS_OPEN, triggered_by="MANUAL",
        notes="synthetic connector-routing test cycle.",
    )
    session.add(cycle)
    session.flush()
    instruction = m.TipPaymentInstruction(
        payment_cycle_id=cycle.id, employee_id=employee.id, amount_minor=1234, idempotency_key=None, status="READY",
    )
    session.add(instruction)
    session.flush()

    sched_svc.set_payment_schedule(
        session, restaurant_id=restaurant.id, mode="MANUAL", connector_code=connector_code, created_by="tester",
    )
    session.commit()
    return restaurant, employee, cycle, instruction


def _make_authorized_approver(session: Session, *, restaurant_id: int, suffix: str) -> m.ActingIdentity:
    approver = m.ActingIdentity(kind="HUMAN_USER", display_name=f"Connector Approver {suffix}", is_active=True)
    session.add(approver)
    session.flush()
    authority_service.grant_authority(
        session, actor=approver, domain=cycle_svc.AUTHORITY_DOMAIN_TIPS,
        action=cycle_svc.AUTHORITY_ACTION_APPROVE_AND_PAY, scope_type=m.SCOPE_RESTAURANT, scope_id=restaurant_id,
    )
    session.commit()
    return approver


def _test_configuration_selects_and_invokes_connector(session: Session, result: ValidationResult) -> None:
    """A. Payment mode configuration selects connector. B. Configured
    connector is actually invoked. D. TipPaymentInstruction does not change
    when connector configuration changes."""
    with _fake_connector_registered():
        restaurant, employee, cycle, instruction = _make_fixture(session, suffix="ab", connector_code=CONNECTOR_CODE_FAKE)

        config = sched_svc.get_payment_schedule_effective_at(session, restaurant_id=restaurant.id)
        result.check(
            "A. payment mode configuration identifies the connector to invoke",
            config is not None and config.connector_code == CONNECTOR_CODE_FAKE,
        )

        instruction_snapshot_before = (
            instruction.id, instruction.payment_cycle_id, instruction.employee_id, instruction.amount_minor,
        )

        connector = connector_svc.resolve_connector(config.connector_code)
        result.check(
            "A/B setup: resolve_connector returns the registered fake, never a hardcoded Mercury instance",
            isinstance(connector, _FakeConnector) and connector.connector_code == CONNECTOR_CODE_FAKE,
        )

        approver = _make_authorized_approver(session, restaurant_id=restaurant.id, suffix="ab")
        with _recipient_reference_override(employee_id=employee.id, recipient_id=f"fake-recipient-ab"):
            cycle_svc.approve_and_pay_cycle(
                session, cycle=cycle, acting_identity=approver, connector=connector, source_account_id="fake-acct-1",
            )
        session.commit()
        result.check(
            "B. the connector configuration resolved to was actually invoked (create_transaction called once)",
            connector.create_transaction_calls == 1,
        )
        result.check(
            "B. the instruction reflects successful execution through the configured connector",
            instruction.status in ("SENT", "OUTCOME_VERIFIED", "SUBMITTED") and instruction.provider == CONNECTOR_CODE_FAKE,
        )

        instruction_snapshot_after = (
            instruction.id, instruction.payment_cycle_id, instruction.employee_id, instruction.amount_minor,
        )
        result.check(
            "D. TipPaymentInstruction's own identity/amount fields are unchanged by which connector executed it",
            instruction_snapshot_before == instruction_snapshot_after,
        )


def _test_instruction_unchanged_across_connector_switch(session: Session, result: ValidationResult) -> None:
    """C. Fake connector can replace Mercury through configuration — the
    SAME Restaurant's payment schedule is reconfigured from MERCURY to the
    fake connector, and resolution follows the NEW configuration, not a
    cached/hardcoded choice. D (again, across an actual switch, not just
    one configuration): the instruction created before the switch is
    unaffected in shape by the switch itself."""
    with _fake_connector_registered():
        restaurant, employee, cycle, instruction = _make_fixture(session, suffix="c", connector_code="MERCURY")
        before_switch = sched_svc.get_payment_schedule_effective_at(session, restaurant_id=restaurant.id)
        result.check("C setup: Restaurant starts configured for MERCURY", before_switch.connector_code == "MERCURY")

        pre_switch_shape = (instruction.id, instruction.payment_cycle_id, instruction.employee_id, instruction.amount_minor)

        # Reconfigure — effective-dated, never overwrites history (the
        # existing schedule_service discipline).
        sched_svc.set_payment_schedule(
            session, restaurant_id=restaurant.id, mode="MANUAL", connector_code=CONNECTOR_CODE_FAKE, created_by="tester",
        )
        session.commit()

        after_switch = sched_svc.get_payment_schedule_effective_at(session, restaurant_id=restaurant.id)
        result.check(
            "C. reconfiguring payment mode to the fake connector is what resolution now follows",
            after_switch.connector_code == CONNECTOR_CODE_FAKE,
        )

        connector = connector_svc.resolve_connector(after_switch.connector_code)
        result.check("C. resolution after the switch returns the fake connector, not Mercury", isinstance(connector, _FakeConnector))

        approver = _make_authorized_approver(session, restaurant_id=restaurant.id, suffix="c")
        with _recipient_reference_override(employee_id=employee.id, recipient_id="fake-recipient-c"):
            cycle_svc.approve_and_pay_cycle(
                session, cycle=cycle, acting_identity=approver, connector=connector, source_account_id="fake-acct-1",
            )
        session.commit()
        result.check(
            "C. the fake connector (not Mercury) was actually invoked after the configuration switch",
            connector.create_transaction_calls == 1,
        )
        post_switch_shape = (instruction.id, instruction.payment_cycle_id, instruction.employee_id, instruction.amount_minor)
        result.check(
            "D. switching connector configuration mid-lifecycle changes NOTHING about the instruction's own identity",
            pre_switch_shape == post_switch_shape,
        )


def _test_fail_closed_behavior(session: Session, result: ValidationResult) -> None:
    """E. Missing connector configuration fails closed. F. Unknown
    connector fails closed. G. No automatic Mercury fallback in either
    case."""
    missing_raised = False
    missing_returned_mercury = False
    try:
        connector = connector_svc.resolve_connector(None)
        missing_returned_mercury = connector.connector_code == connector_svc.CONNECTOR_CODE_MERCURY
    except connector_svc.ConnectorNotConfiguredError:
        missing_raised = True
    except connector_svc.PaymentConnectorError:
        pass
    result.check("E. missing connector configuration (None) fails closed with ConnectorNotConfiguredError", missing_raised)
    result.check("G. missing configuration never silently resolves to Mercury", not missing_returned_mercury)

    unknown_raised = False
    unknown_returned_mercury = False
    try:
        connector = connector_svc.resolve_connector("SOME_UNREGISTERED_CONNECTOR")
        unknown_returned_mercury = connector.connector_code == connector_svc.CONNECTOR_CODE_MERCURY
    except connector_svc.UnknownConnectorError:
        unknown_raised = True
    except connector_svc.PaymentConnectorError:
        pass
    result.check("F. an unknown/unregistered connector code fails closed with UnknownConnectorError", unknown_raised)
    result.check("G. an unknown connector code never silently resolves to Mercury", not unknown_returned_mercury)

    # Same fail-closed behavior reached through the ordinary Restaurant
    # configuration path (empty string persisted as NULL, exactly like the
    # Tips Configuration UI's "not yet chosen" state), not just by calling
    # resolve_connector directly.
    restaurant, employee, cycle, instruction = _make_fixture(session, suffix="efg", connector_code=None)
    config = sched_svc.get_payment_schedule_effective_at(session, restaurant_id=restaurant.id)
    approver = _make_authorized_approver(session, restaurant_id=restaurant.id, suffix="efg")
    config_path_raised = False
    try:
        connector_svc.resolve_connector(config.connector_code)
    except connector_svc.ConnectorNotConfiguredError:
        config_path_raised = True
    result.check(
        "E. a Restaurant with no connector_code configured fails closed via the ordinary configuration path",
        config.connector_code is None and config_path_raised,
    )
    result.check(
        "G. the unconfigured Restaurant's instruction was never submitted anywhere (still READY)",
        instruction.status == "READY",
    )


def _test_mercury_through_resolver(session: Session, result: ValidationResult) -> None:
    """H. Mercury connector still works through the same resolver when
    selected — driven by a fake, MercuryClient-shaped stub, never a real
    network call."""
    restaurant, employee, cycle, instruction = _make_fixture(session, suffix="h", connector_code="MERCURY")
    config = sched_svc.get_payment_schedule_effective_at(session, restaurant_id=restaurant.id)
    fake_mercury_client = _FakeMercuryClient()
    connector = connector_svc.resolve_connector(config.connector_code, client=fake_mercury_client)
    result.check(
        "H. resolve_connector('MERCURY') returns the real MercuryPaymentConnector adapter",
        isinstance(connector, connector_svc.MercuryPaymentConnector) and connector.connector_code == "MERCURY",
    )

    approver = _make_authorized_approver(session, restaurant_id=restaurant.id, suffix="h")
    cycle_svc.approve_and_pay_cycle(
        session, cycle=cycle, acting_identity=approver, connector=connector, source_account_id="mercury-acct-1",
    )
    session.commit()
    result.check(
        "H. Mercury (via the fake client) was actually invoked through the SAME resolver seam as any other connector",
        fake_mercury_client.create_transaction_calls == 1 and instruction.provider == "MERCURY",
    )


def _test_scheduler_uses_configured_connector(session: Session, result: ValidationResult) -> None:
    """I. Scheduler/execution path also uses configured connector — the
    Payment loop's AUTO WITHOUT APPROVAL tick resolves each Restaurant's
    OWN configured connector, never one client shared/hardcoded for the
    whole tick; a Restaurant with no connector configured fails closed for
    ITSELF alone, without blocking a sibling Restaurant's tick."""
    with _fake_connector_registered():
        now = T0 + timedelta(days=10)

        # Restaurant 1: AUTOMATIC/WITHOUT_APPROVAL, fake connector configured,
        # OPEN cycle, recipient on file -> scheduler should Approve & Pay it.
        r1, emp1, cycle1, instruction1 = _make_fixture(session, suffix="sched1", connector_code=CONNECTOR_CODE_FAKE)
        sched_svc.set_payment_schedule(
            session, restaurant_id=r1.id, mode="AUTOMATIC", interval_days=1, connector_code=CONNECTOR_CODE_FAKE,
            auto_approval_mode="WITHOUT_APPROVAL", effective_from=now - timedelta(days=1), created_by="tester",
        )
        session.commit()

        # Restaurant 2: same automatic/without-approval mode, but NO
        # connector configured — must fail closed for itself only.
        r2, emp2, cycle2, instruction2 = _make_fixture(session, suffix="sched2", connector_code=None)
        sched_svc.set_payment_schedule(
            session, restaurant_id=r2.id, mode="AUTOMATIC", interval_days=1, connector_code=None,
            auto_approval_mode="WITHOUT_APPROVAL", effective_from=now - timedelta(days=1), created_by="tester",
        )
        session.commit()

        system_identity = acting_identity_service.get_or_create_system_identity(session)
        for restaurant_id in (r1.id, r2.id):
            authority_service.grant_authority(
                session, actor=system_identity, domain=cycle_svc.AUTHORITY_DOMAIN_TIPS,
                action=cycle_svc.AUTHORITY_ACTION_APPROVE_AND_PAY, scope_type=m.SCOPE_RESTAURANT, scope_id=restaurant_id,
            )
        session.commit()

        with _recipient_reference_override(employee_id=emp1.id, recipient_id="fake-recipient-sched1"):
            outcomes = scheduler_svc.run_due_payment_cycle_auto_approvals(session, now=now)
        session.commit()
        by_restaurant = {o.restaurant_id: o for o in outcomes}

        result.check(
            "I. the scheduler resolved Restaurant 1's OWN configured (fake) connector and Approved & Paid it",
            r1.id in by_restaurant and by_restaurant[r1.id].approved is True,
        )
        # The fake registered under CONNECTOR_CODE_FAKE is a fresh instance
        # each `resolve_connector` call (no shared client for the whole
        # tick) — the observable proof is the instruction's own outcome.
        result.check(
            "I. Restaurant 1's instruction was actually submitted through its configured connector",
            instruction1.status in ("SENT", "OUTCOME_VERIFIED", "SUBMITTED") and instruction1.provider == CONNECTOR_CODE_FAKE,
        )
        result.check(
            "I. Restaurant 2 (no connector configured) fails closed for ITSELF, reported in its own outcome",
            r2.id in by_restaurant and by_restaurant[r2.id].approved is False
            and "connector" in (by_restaurant[r2.id].reason or "").lower(),
        )
        result.check(
            "I. Restaurant 2's failure never touched Restaurant 1's instruction, and vice versa",
            instruction2.status == "READY",
        )


def _test_provider_reflects_actual_connector_not_a_default(session: Session, result: ValidationResult) -> None:
    """Baseline-closure fix: `TipPaymentInstruction.provider` must reflect
    the connector actually selected by configuration — Mercury is not the
    conceptual default. Covers, explicitly:

    A. a new, unsubmitted instruction does not falsely claim MERCURY;
    B. configured MERCURY execution records MERCURY appropriately;
    C. another registered (fake) connector records its OWN identity;
    D. routing (and the resulting `provider` value) remains
       configuration-driven, never hardcoded."""
    with _fake_connector_registered():
        # --- A: unsubmitted instruction has no provider claim at all. ---
        restaurant_a, employee_a, cycle_a, instruction_a = _make_fixture(
            session, suffix="provA", connector_code=CONNECTOR_CODE_FAKE,
        )
        result.check(
            "A. a new, unsubmitted (READY) TipPaymentInstruction does not falsely claim MERCURY — provider is "
            "unset (None), not defaulted",
            instruction_a.status == "READY" and instruction_a.provider is None,
        )

        # --- B: MERCURY, configured and actually executed, records MERCURY. ---
        restaurant_b, employee_b, cycle_b, instruction_b = _make_fixture(session, suffix="provB", connector_code="MERCURY")
        result.check(
            "B setup: unsubmitted MERCURY-configured instruction is ALSO unset, not pre-filled",
            instruction_b.provider is None,
        )
        config_b = sched_svc.get_payment_schedule_effective_at(session, restaurant_id=restaurant_b.id)
        fake_mercury_client = _FakeMercuryClient()
        connector_b = connector_svc.resolve_connector(config_b.connector_code, client=fake_mercury_client)
        approver_b = _make_authorized_approver(session, restaurant_id=restaurant_b.id, suffix="provB")
        cycle_svc.approve_and_pay_cycle(
            session, cycle=cycle_b, acting_identity=approver_b, connector=connector_b, source_account_id="mercury-acct-1",
        )
        session.commit()
        result.check(
            "B. after real execution through the configured MERCURY connector, provider records 'MERCURY'",
            instruction_b.provider == "MERCURY" and fake_mercury_client.create_transaction_calls == 1,
        )

        # --- C: a different registered connector records ITS OWN identity. ---
        restaurant_c, employee_c, cycle_c, instruction_c = _make_fixture(session, suffix="provC", connector_code=CONNECTOR_CODE_FAKE)
        config_c = sched_svc.get_payment_schedule_effective_at(session, restaurant_id=restaurant_c.id)
        connector_c = connector_svc.resolve_connector(config_c.connector_code)
        approver_c = _make_authorized_approver(session, restaurant_id=restaurant_c.id, suffix="provC")
        with _recipient_reference_override(employee_id=employee_c.id, recipient_id="fake-recipient-provC"):
            cycle_svc.approve_and_pay_cycle(
                session, cycle=cycle_c, acting_identity=approver_c, connector=connector_c, source_account_id="fake-acct-1",
            )
        session.commit()
        result.check(
            "C. a different registered (fake) connector records ITS OWN connector_code, never 'MERCURY'",
            instruction_c.provider == CONNECTOR_CODE_FAKE and instruction_c.provider != "MERCURY",
        )

        # --- D: routing/provider outcome is configuration-driven, not hardcoded —
        # two Restaurants configured for two DIFFERENT connectors end up with
        # two DIFFERENT recorded providers from the identical code path. ---
        result.check(
            "D. routing remains configuration-driven: Restaurant B (MERCURY-configured) and Restaurant C "
            "(fake-connector-configured) recorded DIFFERENT providers from the SAME approve_and_pay_cycle "
            "code path",
            instruction_b.provider == "MERCURY" and instruction_c.provider == CONNECTOR_CODE_FAKE
            and instruction_b.provider != instruction_c.provider,
        )
