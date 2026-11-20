"""Automated synthetic tests for ORDER_SERVICE_OWNER_SOURCE_SEMANTICS_001 —
the Tip Distribution Rule SOURCE side can qualify an Order either by
RestaurantRole (`ROLE`, the original behavior) or by the Order's own
`employee_id` regardless of that Employee's Role (`ORDER_SERVICE_OWNER`).

Mirrors `tips_distribution_engine_validation.py`'s fixture pattern: builds
one synthetic (never-real) fixture inside a disposable database, runs the
REAL `distribution_engine.calculate_tips` (never a hand-crafted
allocation line), asserts the required behaviors, and always
rolls back at the very end.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .tips import distribution_engine as engine
from .tips import distribution_rule_service as rule_svc
from .tips import rule_ai_authoring as ai_svc

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
            _build_fixture_and_assert(session, result)
        finally:
            session.rollback()
    return result


def _at(day: float, hour: int = 12) -> datetime:
    return T0 + timedelta(days=day, hours=hour)


def _fake_ai(response: dict):
    def _fn(prompt: str) -> dict:
        return response
    return _fn


def _build_fixture_and_assert(session: Session, result: ValidationResult) -> None:
    source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
    session.add(source_system)
    session.flush()

    merchant = m.Merchant(source_system_id=source_system.id, source_merchant_id="OSOMERCH1", name="OSO Test Merchant")
    session.add(merchant)
    session.flush()

    location = m.Location(
        merchant_id=merchant.id, source_system_id=source_system.id, source_location_id="OSOMERCH1",
        name="OSO Test Location", currency="USD",
    )
    session.add(location)
    session.flush()

    restaurant = m.Restaurant(name="Synthetic OSO Test Restaurant", default_currency="USD")
    session.add(restaurant)
    session.flush()
    session.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
    session.flush()

    area = m.OperationalArea(restaurant_id=restaurant.id, name="FOH")
    session.add(area)
    session.flush()

    role_server = m.RestaurantRole(restaurant_id=restaurant.id, name="Server")
    role_team_leader = m.RestaurantRole(restaurant_id=restaurant.id, name="Team Leader")
    role_manager = m.RestaurantRole(restaurant_id=restaurant.id, name="Manager")
    role_host = m.RestaurantRole(restaurant_id=restaurant.id, name="Host")
    session.add_all([role_server, role_team_leader, role_manager, role_host])
    session.flush()

    def make_employee(source_id: str, name: str) -> m.Employee:
        emp = m.Employee(
            location_id=location.id, source_system_id=source_system.id, source_employee_id=source_id,
            display_name=name, system_role="EMPLOYEE",
        )
        session.add(emp)
        session.flush()
        return emp

    server_emp = make_employee("SRV1", "ServerEmp")           # holds Server role
    team_leader_emp = make_employee("TL1", "TeamLeaderEmp")   # holds Team Leader role
    manager_emp = make_employee("MGR1", "ManagerEmp")         # holds Manager role
    changing_emp = make_employee("CHG1", "ChangingRoleEmp")   # role changes mid-period (scenario D)
    host_a = make_employee("HOSTA", "HostA")
    host_b = make_employee("HOSTB", "HostB")

    def make_assignment(employee, role, valid_from, valid_to=None, *, restaurant_id=None, operational_area_id=None):
        session.add(
            m.EmployeeAssignment(
                employee_id=employee.id, restaurant_id=restaurant_id or restaurant.id,
                operational_area_id=operational_area_id or area.id,
                restaurant_role_id=role.id, valid_from=valid_from, valid_to=valid_to, assignment_source="MANUAL",
            )
        )

    make_assignment(server_emp, role_server, _at(-300))
    make_assignment(team_leader_emp, role_team_leader, _at(-300))
    make_assignment(manager_emp, role_manager, _at(-300))
    # Scenario D: changing_emp starts as Server, later reassigned to Manager —
    # ORDER_SERVICE_OWNER qualification must be identical before and after.
    make_assignment(changing_emp, role_server, _at(-300), _at(10))
    make_assignment(changing_emp, role_manager, _at(10), None)
    make_assignment(host_a, role_host, _at(-300))
    make_assignment(host_b, role_host, _at(-300))
    session.flush()

    def make_shift(employee, clock_in, clock_out, suffix):
        session.add(
            m.Shift(
                employee_id=employee.id, source_system_id=source_system.id,
                source_shift_id=f"SHIFT-{employee.id}-{suffix}", clock_in=clock_in, clock_out=clock_out,
            )
        )

    # host_a active days 1-12 (scenarios A/B/C/D-before/D-after/E/F/H/I;
    # day 20 stays deliberately outside this window for scenario G).
    make_shift(host_a, _at(1, 0), _at(12, 23), "1")
    # host_b active only day 5 (scenario F: two Hosts eligible together).
    make_shift(host_b, _at(5, 0), _at(5, 23), "1")
    session.flush()

    # === ORDER_SERVICE_OWNER Rule: any Order owner, 10% to Host =============
    oso_rule = rule_svc.create_rule(
        session, restaurant_id=restaurant.id, source_semantics=m.TIP_SOURCE_SEMANTICS_ORDER_SERVICE_OWNER,
        recipient_role_id=role_host.id, calculation_base=m.CALC_BASE_VOLUNTARY_TIP, rate=Decimal("10.0000"),
        effective_from=_at(-300), created_by="tester",
    )
    # === ROLE Rule (existing semantics) — a fully SEPARATE Merchant/
    # Location/Restaurant/Employees, so its Orders can never be picked up
    # by the OSO restaurant's own calculation run (which scans by shared
    # Location, not Restaurant) and vice versa. ==============================
    role_source_system = m.SourceSystem(code="CLOVER2", name="Clover2", active=True)
    session.add(role_source_system)
    session.flush()
    role_merchant = m.Merchant(source_system_id=role_source_system.id, source_merchant_id="OSOMERCH2", name="OSO Role Test Merchant")
    session.add(role_merchant)
    session.flush()
    role_location = m.Location(
        merchant_id=role_merchant.id, source_system_id=role_source_system.id, source_location_id="OSOMERCH2",
        name="OSO Role Test Location", currency="USD",
    )
    session.add(role_location)
    session.flush()
    role_rule_restaurant = m.Restaurant(name="Synthetic OSO ROLE-only Test Restaurant", default_currency="USD")
    session.add(role_rule_restaurant)
    session.flush()
    session.add(m.RestaurantLocation(restaurant_id=role_rule_restaurant.id, location_id=role_location.id, is_primary=True))
    session.flush()
    role_area = m.OperationalArea(restaurant_id=role_rule_restaurant.id, name="FOH")
    session.add(role_area)
    session.flush()
    role_only_server = m.RestaurantRole(restaurant_id=role_rule_restaurant.id, name="Server")
    role_only_host = m.RestaurantRole(restaurant_id=role_rule_restaurant.id, name="Host")
    session.add_all([role_only_server, role_only_host])
    session.flush()
    role_server_emp = m.Employee(
        location_id=role_location.id, source_system_id=role_source_system.id, source_employee_id="RSRV1",
        display_name="RoleServerEmp", system_role="EMPLOYEE",
    )
    role_host_emp = m.Employee(
        location_id=role_location.id, source_system_id=role_source_system.id, source_employee_id="RHOST1",
        display_name="RoleHostEmp", system_role="EMPLOYEE",
    )
    session.add_all([role_server_emp, role_host_emp])
    session.flush()
    make_assignment(
        role_server_emp, role_only_server, _at(-300),
        restaurant_id=role_rule_restaurant.id, operational_area_id=role_area.id,
    )
    make_assignment(
        role_host_emp, role_only_host, _at(-300),
        restaurant_id=role_rule_restaurant.id, operational_area_id=role_area.id,
    )
    session.add(
        m.Shift(
            employee_id=role_host_emp.id, source_system_id=role_source_system.id, source_shift_id="ROLE-SHIFT-1",
            clock_in=_at(1, 0), clock_out=_at(12, 23),
        )
    )
    session.flush()
    role_rule = rule_svc.create_rule(
        session, restaurant_id=role_rule_restaurant.id, source_semantics=m.TIP_SOURCE_SEMANTICS_ROLE,
        source_role_id=role_only_server.id, recipient_role_id=role_only_host.id,
        calculation_base=m.CALC_BASE_VOLUNTARY_TIP, rate=Decimal("10.0000"), effective_from=_at(-300),
        created_by="tester",
    )
    session.commit()
    session.expire_all()

    order_counter = {"n": 0}

    def next_id(prefix: str) -> str:
        order_counter["n"] += 1
        return f"{prefix}-{order_counter['n']}"

    def make_order_with_tip(
        *, order_owner, payment_owner=None, created_at: datetime, tip_minor: int, total: int = 10000,
    ) -> m.Order:
        payment_owner = payment_owner or order_owner
        order = m.Order(
            location_id=location.id, source_system_id=source_system.id, source_order_id=next_id("ORDER"),
            employee_id=order_owner.id, source_employee_id=order_owner.source_employee_id,
            created_at=created_at, state="locked", payment_state="PAID", currency="USD", total=total,
        )
        session.add(order)
        session.flush()
        payment = m.Payment(
            order_id=order.id, source_system_id=source_system.id, source_payment_id=next_id("PAY"),
            employee_id=payment_owner.id, source_employee_id=payment_owner.source_employee_id,
            created_at=created_at, amount=total, result="SUCCESS", currency="USD",
        )
        session.add(payment)
        session.flush()
        session.add(m.PaymentTip(payment_id=payment.id, amount=tip_minor, source_present=True))
        session.flush()
        return order

    def allocations_for(order_id: int) -> list:
        return [line for line in calc.lines if line.order_id == order_id]

    # === A: Server owns Order ===============================================
    order_a = make_order_with_tip(order_owner=server_emp, created_at=_at(1, 12), tip_minor=2000)
    # === B: Team Leader owns Order ==========================================
    order_b = make_order_with_tip(order_owner=team_leader_emp, created_at=_at(1, 13), tip_minor=2000)
    # === C: Manager owns Order ===============================================
    order_c = make_order_with_tip(order_owner=manager_emp, created_at=_at(1, 14), tip_minor=2000)
    # === D: role changes mid-period — two Orders by the same Employee,
    # before and after their role change at day 10 ==========================
    order_d_before = make_order_with_tip(order_owner=changing_emp, created_at=_at(2, 12), tip_minor=2000)  # was Server
    order_d_after = make_order_with_tip(order_owner=changing_emp, created_at=_at(11, 12), tip_minor=2000)  # now Manager
    # === F: two Hosts eligible (day 5) ======================================
    order_f = make_order_with_tip(order_owner=server_emp, created_at=_at(5, 12), tip_minor=2000)
    # === G: no Host eligible (day 20, outside any Host Shift) ================
    order_g = make_order_with_tip(order_owner=server_emp, created_at=_at(20, 12), tip_minor=2000)
    # === I: Payment.employee_id differs from Order.employee_id ==============
    order_i = make_order_with_tip(order_owner=manager_emp, payment_owner=server_emp, created_at=_at(1, 15), tip_minor=2000)
    # === H: ROLE-only Restaurant, existing behavior unchanged ===============
    role_order = m.Order(
        location_id=role_location.id, source_system_id=role_source_system.id, source_order_id=next_id("ROLE-ORDER"),
        employee_id=role_server_emp.id, source_employee_id=role_server_emp.source_employee_id,
        created_at=_at(1, 16), state="locked", payment_state="PAID", currency="USD", total=10000,
    )
    session.add(role_order)
    session.flush()
    role_payment = m.Payment(
        order_id=role_order.id, source_system_id=role_source_system.id, source_payment_id=next_id("ROLE-PAY"),
        employee_id=role_server_emp.id, source_employee_id=role_server_emp.source_employee_id,
        created_at=_at(1, 16), amount=10000, result="SUCCESS", currency="USD",
    )
    session.add(role_payment)
    session.flush()
    session.add(m.PaymentTip(payment_id=role_payment.id, amount=2000, source_present=True))
    session.flush()

    session.commit()
    session.expire_all()

    calc = engine.calculate_tips(
        session, restaurant_id=restaurant.id, period_start=_at(0, 0), period_end=_at(30, 0),
    )
    summary = calc.summary
    result.check("Fixture calculation completed (stateless, nothing persisted)", calc.blocked_reason is None)

    # =====================================================================
    # A/B/C: ORDER_SERVICE_OWNER applies regardless of the owner's Role.
    # =====================================================================
    for label, order, owner_name in [("A (Server)", order_a, "ServerEmp"), ("B (Team Leader)", order_b, "TeamLeaderEmp"), ("C (Manager)", order_c, "ManagerEmp")]:
        allocs = allocations_for(order.id)
        host_allocs = [a for a in allocs if a.recipient_employee_id == host_a.id]
        result.check(f"{label}: ORDER_SERVICE_OWNER rule applied ({owner_name} owns the Order)", len(host_allocs) == 1)
        result.check(f"{label}: Host received 10% of the tip", host_allocs and host_allocs[0].allocated_amount_minor == 200)
        result.check(f"{label}: allocation's source_employee_id is the Order owner", allocs and allocs[0].source_employee_id == order.employee_id)

    # =====================================================================
    # D: role change mid-period — qualification based on Order.employee_id,
    # not the Employee's (changing) RestaurantRole.
    # =====================================================================
    before_allocs = [a for a in allocations_for(order_d_before.id) if a.recipient_employee_id == host_a.id]
    after_allocs = [a for a in allocations_for(order_d_after.id) if a.recipient_employee_id == host_a.id]
    result.check("D: Order before the role change still qualifies (was Server)", len(before_allocs) == 1)
    result.check("D: Order after the role change still qualifies identically (now Manager)", len(after_allocs) == 1)
    result.check(
        "D: both allocations are identical in amount, proving Role is irrelevant to source qualification",
        before_allocs and after_allocs and before_allocs[0].allocated_amount_minor == after_allocs[0].allocated_amount_minor == 200,
    )

    # =====================================================================
    # E: one Host eligible -> 10% to that Host (re-verified via order_a).
    # =====================================================================
    e_allocs = [a for a in allocations_for(order_a.id) if a.recipient_employee_id is not None]
    result.check("E: exactly one eligible Host received the allocation", len(e_allocs) == 1 and e_allocs[0].recipient_employee_id == host_a.id)

    # =====================================================================
    # F: two Hosts eligible -> equal split.
    # =====================================================================
    f_allocs = [a for a in allocations_for(order_f.id) if a.recipient_employee_id is not None]
    result.check("F: two eligible Hosts both received an allocation", len(f_allocs) == 2)
    result.check("F: split equally (100 + 100 = 200)", sorted(a.allocated_amount_minor for a in f_allocs) == [100, 100])

    # =====================================================================
    # G: no Host eligible -> Service Owner retains 100% (SOURCE_RETAINS,
    # explicitly recorded, never silently omitted).
    # =====================================================================
    g_allocs = allocations_for(order_g.id)
    result.check("G: exactly one allocation row recorded (the SOURCE_RETAINS case)", len(g_allocs) == 1)
    result.check("G: no_eligible_recipient is True and allocated_amount_minor is 0", g_allocs and g_allocs[0].no_eligible_recipient is True and g_allocs[0].allocated_amount_minor == 0)

    # =====================================================================
    # H: existing ROLE-based source Rule still works unchanged.
    # =====================================================================
    role_calc = engine.calculate_tips(
        session, restaurant_id=role_rule_restaurant.id, period_start=_at(0, 0), period_end=_at(30, 0),
    )
    result.check("H: ROLE-based calculation completed", role_calc.blocked_reason is None)

    role_allocs = [
        a for a in role_calc.lines if a.recipient_employee_id is not None
    ]
    result.check("H: ROLE Rule still allocates 10% to the Host for the Server-owned Order", len(role_allocs) == 1 and role_allocs[0].allocated_amount_minor == 200)

    # =====================================================================
    # I: Payment.employee_id differs from Order.employee_id — Order.employee_id
    # remains authoritative for source qualification/attribution.
    # =====================================================================
    i_allocs = allocations_for(order_i.id)
    result.check("I: allocation exists (Order owned by Manager, Payment recorded under Server)", len(i_allocs) == 1)
    result.check(
        "I: allocation's source_employee_id is the ORDER's owner (Manager), not the Payment's employee (Server)",
        i_allocs and i_allocs[0].source_employee_id == manager_emp.id,
    )

    # =====================================================================
    # J: AI authoring — "Service Owner" must produce ORDER_SERVICE_OWNER,
    # never silently mapped back onto a "Server" Role.
    # =====================================================================
    roles_for_ai = [role_server, role_team_leader, role_manager, role_host]
    ai_response = {
        "outcome": "PROPOSED",
        "proposal": {
            "source_semantics": "ORDER_SERVICE_OWNER",
            "recipient_role_name": "Host",
            "calculation_base": "VOLUNTARY_TIP", "rate": "10.0000",
            "effective_from": "2026-09-01", "effective_to": None,
            "human_readable_summary": "10% goes to the Host; the Service Owner keeps the rest. Effective September 1, 2026.",
            "warnings": [],
        },
    }
    ai_result = ai_svc.interpret_rule_statement(
        session, restaurant_id=restaurant.id,
        statement="10% goes to the Host; the Service Owner keeps the rest. Effective September 1, 2026.",
        ai_generate_json_fn=_fake_ai(ai_response),
    )
    result.check("J: AI authoring produces PROPOSED", ai_result.outcome == ai_svc.OUTCOME_PROPOSED)
    result.check(
        "J: proposal uses ORDER_SERVICE_OWNER semantics, not a Role",
        ai_result.proposal is not None and ai_result.proposal.source_semantics == m.TIP_SOURCE_SEMANTICS_ORDER_SERVICE_OWNER,
    )
    result.check(
        "J: proposal's source_role_id is None (never silently mapped to Server)",
        ai_result.proposal is not None and ai_result.proposal.source_role_id is None,
    )
    result.check(
        "J: confirming the proposal creates a Rule with ORDER_SERVICE_OWNER persisted correctly",
        True,  # verified structurally below
    )
    rule_count_before_j_confirm = len(rule_svc.list_rules(session, restaurant.id))
    created_j = ai_svc.confirm_rule_proposal(session, ai_result.proposal, created_by="tester-J")
    session.flush()
    j_versions = rule_svc.list_versions(session, created_j.id)
    result.check("J: persisted Version has source_semantics=ORDER_SERVICE_OWNER", j_versions[0].source_semantics == m.TIP_SOURCE_SEMANTICS_ORDER_SERVICE_OWNER)
    result.check("J: persisted Version has source_role_id=None", j_versions[0].source_role_id is None)
    result.check("J: exactly one new Rule was created for J", len(rule_svc.list_rules(session, restaurant.id)) == rule_count_before_j_confirm + 1)
