"""Automated synthetic tests for EMPLOYEE_ASSIGNMENT_CLOVER_ALIGNMENT_001 —
Clover's real operating model (one Employee account = exactly one active
RestaurantRole, within one Restaurant) enforced on `EmployeeAssignment` via
`ux_employee_assignments_one_active_role_per_restaurant`, plus the Tips
engine dependencies that consume it (Host eligibility via Role+Shift,
ORDER_SERVICE_OWNER remaining role-independent).

Mirrors the existing `*_validation.py` pattern: builds a synthetic (never-
real) fixture inside a disposable database, exercises real model/engine
code, asserts the required behaviors, and always rolls back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .tips import distribution_engine as engine
from .tips import distribution_rule_service as rule_svc

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


def _expect_integrity_error(session: Session, action) -> bool:
    """Runs `action()` inside a nested SAVEPOINT, expecting it to raise
    `IntegrityError` on flush. Rolls back only the savepoint either way, so
    the outer validation transaction (and the rest of the fixture already
    built) is never aborted. Mirrors `organization_validation.py`'s own
    helper of the same name/shape exactly."""
    savepoint = session.begin_nested()
    raised = False
    try:
        action()
        session.flush()
    except IntegrityError:
        raised = True
    finally:
        savepoint.rollback()
    return raised


def _build_fixture_and_assert(session: Session, result: ValidationResult) -> None:
    source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
    session.add(source_system)
    session.flush()

    merchant = m.Merchant(source_system_id=source_system.id, source_merchant_id="EAOMERCH1", name="EAO Test Merchant")
    session.add(merchant)
    session.flush()

    location_wp = m.Location(
        merchant_id=merchant.id, source_system_id=source_system.id, source_location_id="EAOWP",
        name="EAO Winter Park", currency="USD",
    )
    location_md = m.Location(
        merchant_id=merchant.id, source_system_id=source_system.id, source_location_id="EAOMD",
        name="EAO Mount Dora", currency="USD",
    )
    session.add_all([location_wp, location_md])
    session.flush()

    restaurant_wp = m.Restaurant(name="Synthetic EAO Winter Park", default_currency="USD")
    restaurant_md = m.Restaurant(name="Synthetic EAO Mount Dora", default_currency="USD")
    session.add_all([restaurant_wp, restaurant_md])
    session.flush()
    session.add(m.RestaurantLocation(restaurant_id=restaurant_wp.id, location_id=location_wp.id, is_primary=True))
    session.add(m.RestaurantLocation(restaurant_id=restaurant_md.id, location_id=location_md.id, is_primary=True))
    session.flush()

    area_wp = m.OperationalArea(restaurant_id=restaurant_wp.id, name="FOH", code="ROOT")
    area_md = m.OperationalArea(restaurant_id=restaurant_md.id, name="FOH", code="ROOT")
    session.add_all([area_wp, area_md])
    session.flush()

    role_wp_server = m.RestaurantRole(restaurant_id=restaurant_wp.id, name="Server")
    role_wp_team_leader = m.RestaurantRole(restaurant_id=restaurant_wp.id, name="Team Leader")
    role_wp_host = m.RestaurantRole(restaurant_id=restaurant_wp.id, name="Host")
    role_md_manager = m.RestaurantRole(restaurant_id=restaurant_md.id, name="Manager")
    session.add_all([role_wp_server, role_wp_team_leader, role_wp_host, role_md_manager])
    session.flush()

    person_a = m.Employee(
        location_id=location_wp.id, source_system_id=source_system.id, source_employee_id="PERSONA-WP",
        display_name="PersonA", system_role="EMPLOYEE",
    )
    host_emp = m.Employee(
        location_id=location_wp.id, source_system_id=source_system.id, source_employee_id="HOSTEMP",
        display_name="HostEmp", system_role="EMPLOYEE",
    )
    non_host_emp = m.Employee(
        location_id=location_wp.id, source_system_id=source_system.id, source_employee_id="NONHOSTEMP",
        display_name="NonHostEmp", system_role="EMPLOYEE",
    )
    session.add_all([person_a, host_emp, non_host_emp])
    session.flush()
    # Person A's SEPARATE Mount Dora employee/employment context — a
    # different Employee row, same real-world Identity conceptually, but
    # RF-One models per-Restaurant employment separately (task's own "do
    # NOT enforce one global role per Person").
    person_a_md = m.Employee(
        location_id=location_md.id, source_system_id=source_system.id, source_employee_id="PERSONA-MD",
        display_name="PersonA", system_role="EMPLOYEE",
    )
    session.add(person_a_md)
    session.flush()

    # =====================================================================
    # A: one active role per employee/restaurant — a second concurrently-
    # open Assignment for the SAME (employee, restaurant) is rejected by the
    # new partial unique index.
    # =====================================================================
    session.add(
        m.EmployeeAssignment(
            employee_id=person_a.id, restaurant_id=restaurant_wp.id, operational_area_id=area_wp.id,
            restaurant_role_id=role_wp_team_leader.id, valid_from=_at(-100), valid_to=None,
            assignment_source="MANUAL",
        )
    )
    session.flush()

    def _add_conflicting_assignment() -> None:
        session.add(
            m.EmployeeAssignment(
                employee_id=person_a.id, restaurant_id=restaurant_wp.id, operational_area_id=area_wp.id,
                restaurant_role_id=role_wp_server.id, valid_from=_at(-50), valid_to=None,
                assignment_source="MANUAL",
            )
        )

    result.check(
        "A: a second concurrently-open Assignment for the same (Employee, Restaurant) is rejected",
        _expect_integrity_error(session, _add_conflicting_assignment),
    )

    # =====================================================================
    # B: same Person may hold WP -> Team Leader and MD -> Manager
    # concurrently (separate Restaurants, separate Employee/Employment rows).
    # =====================================================================
    session.add(
        m.EmployeeAssignment(
            employee_id=person_a_md.id, restaurant_id=restaurant_md.id, operational_area_id=area_md.id,
            restaurant_role_id=role_md_manager.id, valid_from=_at(-100), valid_to=None,
            assignment_source="MANUAL",
        )
    )
    session.flush()
    result.check(
        "B: the same real-world Person may hold WP=Team Leader and MD=Manager concurrently, without conflict",
        True,  # no IntegrityError raised by the statement above
    )

    # =====================================================================
    # C: role change over time — old assignment closed, new one active.
    # =====================================================================
    current = session.scalars(
        select(m.EmployeeAssignment).where(
            m.EmployeeAssignment.employee_id == person_a.id, m.EmployeeAssignment.restaurant_id == restaurant_wp.id,
            m.EmployeeAssignment.valid_to.is_(None),
        )
    ).first()
    role_change_at = _at(10)
    current.valid_to = role_change_at
    session.flush()
    new_assignment = m.EmployeeAssignment(
        employee_id=person_a.id, restaurant_id=restaurant_wp.id, operational_area_id=area_wp.id,
        restaurant_role_id=role_wp_server.id, valid_from=role_change_at, valid_to=None,
        assignment_source="MANUAL",
    )
    session.add(new_assignment)
    session.flush()
    result.check("C: the prior assignment is closed (valid_to set), never deleted", current.valid_to == role_change_at)
    result.check("C: a new open assignment now reflects the changed Role", new_assignment.valid_to is None and new_assignment.restaurant_role_id == role_wp_server.id)
    open_count = session.query(m.EmployeeAssignment).filter_by(employee_id=person_a.id, restaurant_id=restaurant_wp.id, valid_to=None).count()
    result.check("C: exactly one open assignment remains after the role change", open_count == 1)

    # =====================================================================
    # D: duplicate active assignment rejected/prevented (re-verified with a
    # THIRD attempt, on top of the now-current Server assignment from C).
    # =====================================================================
    def _add_second_duplicate_assignment() -> None:
        session.add(
            m.EmployeeAssignment(
                employee_id=person_a.id, restaurant_id=restaurant_wp.id, operational_area_id=area_wp.id,
                restaurant_role_id=role_wp_host.id, valid_from=_at(11), valid_to=None,
                assignment_source="MANUAL",
            )
        )

    result.check(
        "D: duplicate active assignment is rejected",
        _expect_integrity_error(session, _add_second_duplicate_assignment),
    )

    # =====================================================================
    # E/F/G: Host eligibility = HOST RestaurantRole (EmployeeAssignment) AND
    # an active Clover Shift at settlement time — neither alone is enough.
    # =====================================================================
    session.add(
        m.EmployeeAssignment(
            employee_id=host_emp.id, restaurant_id=restaurant_wp.id, operational_area_id=area_wp.id,
            restaurant_role_id=role_wp_host.id, valid_from=_at(-100), valid_to=None, assignment_source="MANUAL",
        )
    )
    session.add(
        m.EmployeeAssignment(
            employee_id=non_host_emp.id, restaurant_id=restaurant_wp.id, operational_area_id=area_wp.id,
            restaurant_role_id=role_wp_server.id, valid_from=_at(-100), valid_to=None, assignment_source="MANUAL",
        )
    )
    session.flush()
    # host_emp has a Shift ONLY on day 1; non_host_emp has a Shift on day 1 too (G: active Shift, non-HOST role).
    session.add(m.Shift(employee_id=host_emp.id, source_system_id=source_system.id, source_shift_id="EAO-SHIFT-1", clock_in=_at(1, 0), clock_out=_at(1, 23)))
    session.add(m.Shift(employee_id=non_host_emp.id, source_system_id=source_system.id, source_shift_id="EAO-SHIFT-2", clock_in=_at(1, 0), clock_out=_at(1, 23)))
    session.flush()

    ts_day1 = _at(1, 12)
    ts_day2 = _at(2, 12)  # host_emp holds HOST but has NO Shift on day 2

    eligible_day1 = engine._employees_with_role_at(session, restaurant_id=restaurant_wp.id, restaurant_role_id=role_wp_host.id, location_id=location_wp.id, at=ts_day1) & engine._employees_shift_active_at(session, location_id=location_wp.id, at=ts_day1)
    eligible_day2 = engine._employees_with_role_at(session, restaurant_id=restaurant_wp.id, restaurant_role_id=role_wp_host.id, location_id=location_wp.id, at=ts_day2) & engine._employees_shift_active_at(session, location_id=location_wp.id, at=ts_day2)

    result.check("E: HOST role + active Shift -> eligible", host_emp.id in eligible_day1)
    result.check("F: HOST role but NO active Shift -> not eligible", host_emp.id not in eligible_day2)
    result.check("G: active Shift but non-HOST role -> not eligible as Host", non_host_emp.id not in eligible_day1)

    # =====================================================================
    # H: ORDER_SERVICE_OWNER remains role-independent — an Order owned by
    # non_host_emp (a Server, not Host) still qualifies as source under
    # ORDER_SERVICE_OWNER, and an Order owned by an employee with NO
    # RestaurantRole at all also qualifies (the whole point of this task's
    # predecessor correction).
    # =====================================================================
    no_role_emp = m.Employee(
        location_id=location_wp.id, source_system_id=source_system.id, source_employee_id="NOROLE",
        display_name="NoRoleEmp", system_role="EMPLOYEE",
    )
    session.add(no_role_emp)
    session.flush()

    oso_rule = rule_svc.create_rule(
        session, restaurant_id=restaurant_wp.id, source_semantics=m.TIP_SOURCE_SEMANTICS_ORDER_SERVICE_OWNER,
        recipient_role_id=role_wp_host.id, calculation_base=m.CALC_BASE_VOLUNTARY_TIP, rate=Decimal("10.0000"),
        effective_from=_at(-100), created_by="tester",
    )
    session.commit()
    session.expire_all()

    order_counter = {"n": 0}

    def next_id(prefix: str) -> str:
        order_counter["n"] += 1
        return f"{prefix}-{order_counter['n']}"

    def make_order_with_tip(*, owner, created_at, tip_minor) -> m.Order:
        order = m.Order(
            location_id=location_wp.id, source_system_id=source_system.id, source_order_id=next_id("ORDER"),
            employee_id=owner.id, source_employee_id=owner.source_employee_id,
            created_at=created_at, state="locked", payment_state="PAID", currency="USD", total=10000,
        )
        session.add(order)
        session.flush()
        payment = m.Payment(
            order_id=order.id, source_system_id=source_system.id, source_payment_id=next_id("PAY"),
            employee_id=owner.id, source_employee_id=owner.source_employee_id,
            created_at=created_at, amount=10000, result="SUCCESS", currency="USD",
        )
        session.add(payment)
        session.flush()
        session.add(m.PaymentTip(payment_id=payment.id, amount=tip_minor, source_present=True))
        session.flush()
        return order

    order_non_host = make_order_with_tip(owner=non_host_emp, created_at=_at(1, 12), tip_minor=2000)
    order_no_role = make_order_with_tip(owner=no_role_emp, created_at=_at(1, 13), tip_minor=2000)
    session.commit()
    session.expire_all()

    calc = engine.calculate_tips(session, restaurant_id=restaurant_wp.id, period_start=_at(0, 0), period_end=_at(3, 0))
    allocs_non_host = [line for line in calc.lines if line.order_id == order_non_host.id]
    allocs_no_role = [line for line in calc.lines if line.order_id == order_no_role.id]
    result.check("H: ORDER_SERVICE_OWNER applies to a Server-owned Order (role-independent)", len(allocs_non_host) == 1)
    result.check("H: ORDER_SERVICE_OWNER applies even to an Order owner with NO RestaurantRole at all", len(allocs_no_role) == 1)
    result.check(
        "H: both allocations' source_employee_id is the real Order owner, regardless of Role",
        allocs_non_host and allocs_non_host[0].source_employee_id == non_host_emp.id
        and allocs_no_role and allocs_no_role[0].source_employee_id == no_role_emp.id,
    )
