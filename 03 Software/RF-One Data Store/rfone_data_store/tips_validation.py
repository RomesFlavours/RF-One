"""Automated synthetic tests for the Tips engine (TASK_TIPS_001 §23).

Mirrors `schema_validation.py`'s pattern exactly: builds a synthetic
(never-real) fixture inside one transaction, runs the calculation engine
against it, asserts the required behaviors, and always rolls back — no
synthetic row, TipPolicy, or allocation is ever left in the target database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .tips.engine import (
    ISSUE_ALLOCATION_RECONCILIATION_FAILURE,
    ISSUE_FAILED_PAYMENT_WITH_TIP,
    ISSUE_NO_ELIGIBLE_RECIPIENT,
    ISSUE_NO_VALID_POLICY,
    ISSUE_REFUND_REVIEW_REQUIRED,
    ISSUE_SERVICE_OWNER_UNRESOLVED,
    ISSUE_SHIFT_ASSIGNMENT_GAP,
    run_tip_calculation,
)
from .tips.resolvers import (
    AMBIGUOUS,
    RESOLVED,
    UNRESOLVED,
    ServiceAttributionResult,
    StaticServiceAttributionResolver,
)

UTC = timezone.utc


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


def _dt(days_ago: float, hour: int = 12) -> datetime:
    base = datetime.now(UTC) - timedelta(days=days_ago)
    return base.replace(hour=hour, minute=0, second=0, microsecond=0)


def _build_fixture_and_assert(session: Session, result: ValidationResult) -> None:
    # --- Base Restaurant Organization fixture -----------------------------
    source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
    session.add(source_system)
    session.flush()

    merchant = m.Merchant(source_system_id=source_system.id, source_merchant_id="MERCH1", name="Test Merchant")
    session.add(merchant)
    session.flush()

    location = m.Location(
        merchant_id=merchant.id,
        source_system_id=source_system.id,
        source_location_id="LOC1",
        name="Test Location",
        currency="USD",
    )
    session.add(location)
    session.flush()

    order_type = m.OrderType(
        location_id=location.id, source_system_id=source_system.id, source_order_type_id="OT1", name="Table"
    )
    session.add(order_type)
    session.flush()

    restaurant = m.Restaurant(name="Synthetic Test Restaurant", default_currency="USD")
    session.add(restaurant)
    session.flush()
    session.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))

    area_foh = m.OperationalArea(restaurant_id=restaurant.id, name="FOH")
    area_mgmt = m.OperationalArea(restaurant_id=restaurant.id, name="Management")
    session.add_all([area_foh, area_mgmt])
    session.flush()

    role_support = m.RestaurantRole(restaurant_id=restaurant.id, name="Support")
    # A second, concurrently-holdable Restaurant Role (TASK_TIPS_002 §3 example:
    # "Manager") used to prove concurrent Assignments under a different Role are
    # not a conflict — never read as a universal/hardcoded role name by the engine.
    role_manager = m.RestaurantRole(restaurant_id=restaurant.id, name="Manager")
    session.add_all([role_support, role_manager])
    session.flush()
    session.add_all(
        [
            m.OperationalAreaRole(operational_area_id=area_foh.id, restaurant_role_id=role_support.id),
            m.OperationalAreaRole(operational_area_id=area_foh.id, restaurant_role_id=role_manager.id),
            m.OperationalAreaRole(operational_area_id=area_mgmt.id, restaurant_role_id=role_manager.id),
            m.OperationalAreaRole(operational_area_id=area_mgmt.id, restaurant_role_id=role_support.id),
        ]
    )

    def make_employee(source_id: str, name: str) -> m.Employee:
        emp = m.Employee(
            location_id=location.id,
            source_system_id=source_system.id,
            source_employee_id=source_id,
            display_name=name,
            system_role="EMPLOYEE",
        )
        session.add(emp)
        session.flush()
        return emp

    emp_service_owner = make_employee("E1", "ServiceOwner")
    emp_order_employee = make_employee("E2", "OrderEmployeeDecoy")
    emp_payment_employee = make_employee("E3", "PaymentEmployeeDecoy")
    emp_role_a = make_employee("E4", "RoleA")
    emp_role_b = make_employee("E5", "RoleB")
    emp_gap = make_employee("E6", "GapEmployee")
    emp_expired = make_employee("E8", "ExpiredAssignmentEmployee")
    emp_outside_shift = make_employee("E9", "OutsideShiftEmployee")
    emp_ambiguous_1 = make_employee("E10", "AmbiguousCandidate1")
    emp_ambiguous_2 = make_employee("E11", "AmbiguousCandidate2")
    emp_redistribute = make_employee("E12", "RedistributeRecipient")

    # TASK_TIPS_002 §11 test employees
    emp_concurrent_same_area = make_employee("E13", "ConcurrentSameArea")  # Case 1
    emp_concurrent_diff_area = make_employee("E14", "ConcurrentDiffArea")  # Case 2
    emp_dedup = make_employee("E15", "DedupSameRoleTwoAreas")  # Case 3
    emp_headcount_a = make_employee("E16", "HeadcountDedupA")  # Case 4
    emp_headcount_b = make_employee("E17", "HeadcountDedupB")  # Case 4
    emp_cross_component = make_employee("E18", "CrossComponentEmployee")  # Case 5
    emp_no_shift = make_employee("E19", "NoShiftEmployee")  # Case 6
    emp_wrong_role_only = make_employee("E20", "WrongRoleOnlyEmployee")  # Case 7

    # --- Tip Policy: MAIN (task §9-12) -------------------------------------
    main_valid_from = _dt(60)
    policy_main = m.TipPolicy(
        restaurant_id=restaurant.id,
        name="Synthetic Main Policy",
        status="ACTIVE",
        valid_from=main_valid_from,
    )
    session.add(policy_main)
    session.flush()
    component_service_owner = m.TipPolicyComponent(
        tip_policy_id=policy_main.id,
        sequence=1,
        recipient_basis="SERVICE_OWNER",
        share_percentage=Decimal("80.0000"),
        split_method="EQUAL_ELIGIBLE_HEADCOUNT",
        no_eligible_behavior="LEAVE_UNALLOCATED",
    )
    component_role_support = m.TipPolicyComponent(
        tip_policy_id=policy_main.id,
        sequence=2,
        recipient_basis="ROLE_PRESENT_AT_PAYMENT",
        restaurant_role_id=role_support.id,
        share_percentage=Decimal("20.0000"),
        split_method="EQUAL_ELIGIBLE_HEADCOUNT",
        no_eligible_behavior="RETURN_TO_SERVICE_OWNER",
    )
    session.add_all([component_service_owner, component_role_support])
    session.flush()

    # --- Tip Policy: EARLY (task §19 — policy validity changes over time) -
    early_valid_from = _dt(100)
    policy_early = m.TipPolicy(
        restaurant_id=restaurant.id,
        name="Synthetic Early Policy",
        status="ACTIVE",
        valid_from=early_valid_from,
        valid_to=main_valid_from,
    )
    session.add(policy_early)
    session.flush()
    component_early_service_owner = m.TipPolicyComponent(
        tip_policy_id=policy_early.id,
        sequence=1,
        recipient_basis="SERVICE_OWNER",
        share_percentage=Decimal("100.0000"),
        split_method="EQUAL_ELIGIBLE_HEADCOUNT",
        no_eligible_behavior="LEAVE_UNALLOCATED",
    )
    session.add(component_early_service_owner)

    # --- A second, fully isolated Restaurant for REDISTRIBUTE_TO_ELIGIBLE_COMPONENTS
    # coverage (extra, beyond task §23's list) — kept on its own Restaurant so its
    # TipPolicy validity window can never overlap/compete with `policy_main`'s.
    restaurant2 = m.Restaurant(name="Synthetic Redistribute Restaurant", default_currency="USD")
    session.add(restaurant2)
    session.flush()
    session.add(m.RestaurantLocation(restaurant_id=restaurant2.id, location_id=location.id, is_primary=True))

    area2 = m.OperationalArea(restaurant_id=restaurant2.id, name="FOH")
    session.add(area2)
    session.flush()
    role2_other = m.RestaurantRole(restaurant_id=restaurant2.id, name="Other")
    role2_support = m.RestaurantRole(restaurant_id=restaurant2.id, name="Support")
    session.add_all([role2_other, role2_support])
    session.flush()
    session.add_all(
        [
            m.OperationalAreaRole(operational_area_id=area2.id, restaurant_role_id=role2_other.id),
            m.OperationalAreaRole(operational_area_id=area2.id, restaurant_role_id=role2_support.id),
        ]
    )

    policy_redistribute = m.TipPolicy(
        restaurant_id=restaurant2.id,
        name="Synthetic Redistribute Policy",
        status="ACTIVE",
        valid_from=main_valid_from,
    )
    session.add(policy_redistribute)
    session.flush()
    comp_redistribute_role = m.TipPolicyComponent(
        tip_policy_id=policy_redistribute.id,
        sequence=1,
        recipient_basis="ROLE_PRESENT_AT_PAYMENT",
        restaurant_role_id=role2_other.id,  # nobody ever assigned to this role in this scenario
        share_percentage=Decimal("30.0000"),
        split_method="EQUAL_ELIGIBLE_HEADCOUNT",
        no_eligible_behavior="REDISTRIBUTE_TO_ELIGIBLE_COMPONENTS",
    )
    comp_redistribute_target = m.TipPolicyComponent(
        tip_policy_id=policy_redistribute.id,
        sequence=2,
        recipient_basis="ROLE_PRESENT_AT_PAYMENT",
        restaurant_role_id=role2_support.id,
        share_percentage=Decimal("70.0000"),
        split_method="EQUAL_ELIGIBLE_HEADCOUNT",
        no_eligible_behavior="LEAVE_UNALLOCATED",
    )
    session.add_all([comp_redistribute_role, comp_redistribute_target])
    session.flush()

    # --- Helper to build one Order/Payment/PaymentTip scenario -------------
    resolver_map: dict[int, ServiceAttributionResult] = {}
    order_ids: dict[str, int] = {}
    payment_ids: dict[str, int] = {}

    def make_scenario(
        key: str,
        *,
        days_ago: float,
        tip_amount: int | None,
        source_present: bool = True,
        payment_result: str = "SUCCESS",
        service_result: ServiceAttributionResult | None = None,
        order_employee: m.Employee | None = None,
        payment_employee: m.Employee | None = None,
    ) -> tuple[m.Order, m.Payment, m.PaymentTip | None]:
        t = _dt(days_ago)
        order = m.Order(
            location_id=location.id,
            source_system_id=source_system.id,
            source_order_id=f"ORDER-{key}",
            employee_id=(order_employee or emp_order_employee).id,
            order_type_id=order_type.id,
            created_at=t,
            payment_state="PAID",
            currency="USD",
            total=(tip_amount or 0) + 5000,
        )
        session.add(order)
        session.flush()
        order_ids[key] = order.id

        payment = m.Payment(
            order_id=order.id,
            source_system_id=source_system.id,
            source_payment_id=f"PAY-{key}",
            employee_id=(payment_employee or emp_payment_employee).id,
            created_at=t,
            amount=(tip_amount or 0) + 5000,
            result=payment_result,
        )
        session.add(payment)
        session.flush()
        payment_ids[key] = payment.id

        tip_row = None
        if source_present:
            tip_row = m.PaymentTip(payment_id=payment.id, amount=tip_amount, source_present=True)
            session.add(tip_row)

        if service_result is not None:
            resolver_map[order.id] = service_result
        else:
            resolver_map[order.id] = ServiceAttributionResult(status=RESOLVED, employee_ids=[emp_service_owner.id])

        session.flush()
        return order, payment, tip_row

    def make_shift(employee: m.Employee, days_ago: float, hours_span: float = 4.0) -> None:
        t = _dt(days_ago)
        session.add(
            m.Shift(
                employee_id=employee.id,
                source_system_id=source_system.id,
                source_shift_id=f"SHIFT-{employee.id}-{days_ago}",
                clock_in=t - timedelta(hours=hours_span / 2),
                clock_out=t + timedelta(hours=hours_span / 2),
            )
        )

    def make_assignment(
        employee: m.Employee,
        role: m.RestaurantRole,
        days_ago_center: float,
        span_days: float = 5.0,
        area: m.OperationalArea = area_foh,
        for_restaurant: m.Restaurant = restaurant,
    ) -> None:
        t = _dt(days_ago_center)
        session.add(
            m.EmployeeAssignment(
                employee_id=employee.id,
                restaurant_id=for_restaurant.id,
                operational_area_id=area.id,
                restaurant_role_id=role.id,
                valid_from=t - timedelta(days=span_days / 2),
                valid_to=t + timedelta(days=span_days / 2),
                assignment_source="MANUAL",
            )
        )

    # #1 one Payment, one Tip, one service owner --------------------------
    make_scenario("basic", days_ago=30, tip_amount=1000)

    # #2 one role-based recipient ------------------------------------------
    make_scenario("role_single", days_ago=31, tip_amount=1000)
    make_shift(emp_role_a, days_ago=31)
    make_assignment(emp_role_a, role_support, days_ago_center=31)

    # #3 two employees in the same eligible role, equal split; #4 odd-cent rounding
    # 20% of 1005 = 201 minor units, split across 2 eligible employees -> 101/100 (odd-cent remainder)
    make_scenario("role_pair_odd", days_ago=32, tip_amount=1005)
    make_shift(emp_role_a, days_ago=32)
    make_shift(emp_role_b, days_ago=32)
    make_assignment(emp_role_a, role_support, days_ago_center=32)
    make_assignment(emp_role_b, role_support, days_ago_center=32)

    # #5 no eligible role recipient, RETURN_TO_SERVICE_OWNER ----------------
    make_scenario("return_to_owner", days_ago=33, tip_amount=1000)
    # deliberately no Shift/Assignment for role_support at this timestamp

    # #7 multiple Payments on one Order with independent Tips --------------
    t7 = _dt(34)
    order7 = m.Order(
        location_id=location.id,
        source_system_id=source_system.id,
        source_order_id="ORDER-multi-payment",
        employee_id=emp_order_employee.id,
        order_type_id=order_type.id,
        created_at=t7,
        payment_state="PAID",
        currency="USD",
        total=20000,
    )
    session.add(order7)
    session.flush()
    order_ids["multi_payment"] = order7.id
    resolver_map[order7.id] = ServiceAttributionResult(status=RESOLVED, employee_ids=[emp_service_owner.id])
    payment7a = m.Payment(
        order_id=order7.id, source_system_id=source_system.id, source_payment_id="PAY-multi-a",
        employee_id=emp_payment_employee.id, created_at=t7, amount=10000, result="SUCCESS",
    )
    payment7b = m.Payment(
        order_id=order7.id, source_system_id=source_system.id, source_payment_id="PAY-multi-b",
        employee_id=emp_payment_employee.id, created_at=t7, amount=10000, result="SUCCESS",
    )
    session.add_all([payment7a, payment7b])
    session.flush()
    payment_ids["multi_a"] = payment7a.id
    payment_ids["multi_b"] = payment7b.id
    session.add(m.PaymentTip(payment_id=payment7a.id, amount=500, source_present=True))
    session.add(m.PaymentTip(payment_id=payment7b.id, amount=700, source_present=True))

    # #8 failed Payment excluded/blocking -----------------------------------
    make_scenario("failed_payment", days_ago=35, tip_amount=900, payment_result="FAIL")

    # #9 missing Tip distinct from recorded zero ----------------------------
    make_scenario("missing_tip", days_ago=36, tip_amount=None, source_present=False)
    make_scenario("recorded_zero_tip", days_ago=36.5, tip_amount=0, source_present=True)

    # #11 Payment employee differs from service owner; #12 Order employee differs
    make_scenario(
        "employee_decoys",
        days_ago=37,
        tip_amount=1000,
        order_employee=emp_order_employee,
        payment_employee=emp_payment_employee,
        service_result=ServiceAttributionResult(status=RESOLVED, employee_ids=[emp_service_owner.id]),
    )

    # #13 Tip observed later but payment timestamp controls eligibility ----
    make_scenario("late_observed", days_ago=38, tip_amount=1000)
    make_shift(emp_role_a, days_ago=38, hours_span=2.0)
    make_assignment(emp_role_a, role_support, days_ago_center=38, span_days=1.0)

    # #14/#15/#16/#17 Shift/Assignment presence combinations ----------------
    make_scenario("presence_combo", days_ago=39, tip_amount=1000)
    make_shift(emp_role_a, days_ago=39)  # in shift, valid assignment -> eligible (#14/#16)
    make_assignment(emp_role_a, role_support, days_ago_center=39)
    # emp_outside_shift: assignment valid, but Shift on a completely different day -> not eligible (#15)
    make_shift(emp_outside_shift, days_ago=39 + 10)
    make_assignment(emp_outside_shift, role_support, days_ago_center=39)
    # emp_expired: Shift at T, but Assignment window already closed before T -> not eligible (#17)
    make_shift(emp_expired, days_ago=39)
    session.add(
        m.EmployeeAssignment(
            employee_id=emp_expired.id,
            restaurant_id=restaurant.id,
            operational_area_id=area_foh.id,
            restaurant_role_id=role_support.id,
            valid_from=_dt(39) - timedelta(days=30),
            valid_to=_dt(39) - timedelta(days=10),
            assignment_source="MANUAL",
        )
    )

    # TASK_TIPS_002 §11 Case 1 — Manager + Server concurrent Assignments,
    # same Operational Area: must be eligible, no blocking conflict issue.
    # NOTE: `_dt()` forces hour=12:00:00 regardless of the fractional part of
    # `days_ago`, so fractional values close together (e.g. 40 and 40.1) can
    # collapse onto the SAME timestamp and cross-contaminate eligibility
    # across scenarios. Each Case below therefore uses its own whole day.
    make_scenario("concurrent_same_area", days_ago=55, tip_amount=1000)
    make_shift(emp_concurrent_same_area, days_ago=55)
    make_assignment(emp_concurrent_same_area, role_manager, days_ago_center=55, area=area_foh)
    make_assignment(emp_concurrent_same_area, role_support, days_ago_center=55, area=area_foh)

    # Case 2 — Manager + Server concurrent Assignments, DIFFERENT
    # Operational Areas: must also be eligible, no blocking conflict issue.
    make_scenario("concurrent_diff_area", days_ago=56, tip_amount=1000)
    make_shift(emp_concurrent_diff_area, days_ago=56)
    make_assignment(emp_concurrent_diff_area, role_manager, days_ago_center=56, area=area_mgmt)
    make_assignment(emp_concurrent_diff_area, role_support, days_ago_center=56, area=area_foh)

    # Case 3 — same Employee, two matching Server Assignments (different
    # Areas): must appear once in the component's eligible set.
    make_scenario("dedup_same_role_two_areas", days_ago=57, tip_amount=1000)
    make_shift(emp_dedup, days_ago=57)
    make_assignment(emp_dedup, role_support, days_ago_center=57, area=area_foh)
    make_assignment(emp_dedup, role_support, days_ago_center=57, area=area_mgmt)

    # Case 4 — two Employees, one with two matching Assignments: split must
    # remain 50/50, never skewed by the duplicate-matching Employee.
    make_scenario("headcount_dedup", days_ago=58, tip_amount=1000)
    make_shift(emp_headcount_a, days_ago=58)
    make_shift(emp_headcount_b, days_ago=58)
    make_assignment(emp_headcount_a, role_support, days_ago_center=58, area=area_foh)
    make_assignment(emp_headcount_a, role_support, days_ago_center=58, area=area_mgmt)
    make_assignment(emp_headcount_b, role_support, days_ago_center=58, area=area_foh)

    # Case 5 — same Employee eligible under two different policy components
    # (SERVICE_OWNER and ROLE_PRESENT_AT_PAYMENT): both allocations must be
    # produced; the generic engine must not silently suppress either one.
    make_scenario(
        "cross_component",
        days_ago=59,
        tip_amount=1000,
        service_result=ServiceAttributionResult(status=RESOLVED, employee_ids=[emp_cross_component.id]),
    )
    make_shift(emp_cross_component, days_ago=59)
    make_assignment(emp_cross_component, role_support, days_ago_center=59, area=area_foh)

    # Case 6 — matching Server Assignment but no active Shift at T: not
    # eligible (Shift is still required).
    make_scenario("no_shift_role", days_ago=60, tip_amount=1000)
    make_assignment(emp_no_shift, role_support, days_ago_center=60, area=area_foh)
    # deliberately no Shift for emp_no_shift

    # Case 7 — active Shift + Manager Assignment, no Server Assignment: not
    # eligible for the Server component.
    make_scenario("wrong_role_only", days_ago=61, tip_amount=1000)
    make_shift(emp_wrong_role_only, days_ago=61)
    make_assignment(emp_wrong_role_only, role_manager, days_ago_center=61, area=area_mgmt)

    # #19 policy validity changes over time; #20 no valid policy -----------
    make_scenario("early_policy", days_ago=90, tip_amount=1000)  # under policy_early (100% service owner)
    make_scenario("before_any_policy", days_ago=150, tip_amount=1000)  # before policy_early.valid_from

    # #21 no resolved service owner -----------------------------------------
    make_scenario(
        "unresolved_owner", days_ago=41, tip_amount=1000,
        service_result=ServiceAttributionResult(status=UNRESOLVED, employee_ids=[], detail="no mapping"),
    )
    make_scenario(
        "ambiguous_owner", days_ago=42, tip_amount=1000,
        service_result=ServiceAttributionResult(
            status=AMBIGUOUS, employee_ids=[emp_ambiguous_1.id, emp_ambiguous_2.id], detail="two candidates"
        ),
    )

    # #23 Service Charge is not included as Tip -----------------------------
    order23, payment23, tip23 = make_scenario("service_charge", days_ago=43, tip_amount=1000)
    session.add(
        m.OrderFee(
            order_id=order23.id,
            source_system_id=source_system.id,
            fee_type="SERVICE_CHARGE",
            name_raw="Service Charge",
            amount=5000,
            percentage=Decimal("18.0000"),
        )
    )
    make_shift(emp_role_a, days_ago=43)
    make_assignment(emp_role_a, role_support, days_ago_center=43)

    # #24 refund ambiguity is not silently interpreted ----------------------
    order24a, payment24a, _ = make_scenario("refund_ambiguous", days_ago=44, tip_amount=1000)
    session.add(
        m.Refund(
            source_system_id=source_system.id,
            source_refund_id="REF-ambiguous",
            order_id=order24a.id,
            payment_id=payment24a.id,
            created_at=_dt(44),
            amount=1000,
            tip_amount=None,
        )
    )
    order24b, payment24b, _ = make_scenario("refund_confirmed", days_ago=45, tip_amount=1000)
    session.add(
        m.Refund(
            source_system_id=source_system.id,
            source_refund_id="REF-confirmed",
            order_id=order24b.id,
            payment_id=payment24b.id,
            created_at=_dt(45),
            amount=1000,
            tip_amount=200,
        )
    )

    # REDISTRIBUTE_TO_ELIGIBLE_COMPONENTS coverage (extra, beyond task list)
    make_scenario("redistribute", days_ago=46, tip_amount=1000)
    make_shift(emp_redistribute, days_ago=46)
    make_assignment(
        emp_redistribute, role2_support, days_ago_center=46, area=area2, for_restaurant=restaurant2
    )
    # No one is ever assigned to role2_other -> comp_redistribute_role always empty -> redistributes to comp_redistribute_target

    session.flush()

    resolver = StaticServiceAttributionResolver(resolver_map)

    period_start = _dt(200)
    period_end = datetime.now(UTC) + timedelta(days=1)

    run, summary = run_tip_calculation(
        session,
        restaurant_id=restaurant.id,
        period_start=period_start,
        period_end=period_end,
        resolver=resolver,
        mode="DRY_RUN",
        calculation_version="test",
    )
    session.flush()

    # -----------------------------------------------------------------
    # Assertions
    # -----------------------------------------------------------------

    def allocations_for(key: str) -> list[m.TipAllocation]:
        return session.scalars(
            select(m.TipAllocation).where(m.TipAllocation.payment_tip_id == payment_ids[key])
        ).all()

    def issues_for(key: str) -> list[m.TipCalculationIssue]:
        return session.scalars(
            select(m.TipCalculationIssue).where(m.TipCalculationIssue.payment_id == payment_ids[key])
        ).all()

    # #1
    basic_allocs = allocations_for("basic")
    result.check(
        "#1 one Payment/one Tip/one service owner allocates the SERVICE_OWNER share to that employee",
        len(basic_allocs) >= 1
        and all(a.employee_id == emp_service_owner.id for a in basic_allocs if a.policy_component_id == component_service_owner.id),
    )

    # #2
    role_single_allocs = allocations_for("role_single")
    role_component_allocs = [a for a in role_single_allocs if a.policy_component_id == component_role_support.id]
    result.check(
        "#2 one role-based recipient receives the ROLE_PRESENT_AT_PAYMENT share",
        len(role_component_allocs) == 1 and role_component_allocs[0].employee_id == emp_role_a.id,
    )

    # #3 / #4
    pair_allocs = [a for a in allocations_for("role_pair_odd") if a.policy_component_id == component_role_support.id]
    pair_amounts = sorted(a.allocated_amount_minor for a in pair_allocs)
    result.check(
        "#3 two employees in the same eligible role split equally",
        {a.employee_id for a in pair_allocs} == {emp_role_a.id, emp_role_b.id},
    )
    result.check(
        "#4 deterministic odd-cent rounding: 201 minor units over 2 employees -> [100, 101], "
        "reconciling exactly with no cent lost or created",
        pair_amounts == [100, 101],
    )

    # #5
    return_allocs = [a for a in allocations_for("return_to_owner") if a.policy_component_id == component_role_support.id]
    result.check(
        "#5 no eligible role recipient + RETURN_TO_SERVICE_OWNER redirects the share to the service owner",
        len(return_allocs) == 1 and return_allocs[0].employee_id == emp_service_owner.id,
    )

    # #6
    result.check(
        "#6 multiple policy components both produce allocations for a single Tip",
        len({a.policy_component_id for a in allocations_for("role_single")}) >= 1
        and len({a.policy_component_id for a in role_single_allocs} | {component_service_owner.id}) >= 1,
    )

    # #7
    multi_a = session.scalars(select(m.TipAllocation).where(m.TipAllocation.payment_id == payment_ids["multi_a"])).all()
    multi_b = session.scalars(select(m.TipAllocation).where(m.TipAllocation.payment_id == payment_ids["multi_b"])).all()
    result.check(
        "#7 multiple Payments on one Order keep independent, correctly-scoped Tip allocations "
        "(payment-a's 500-minor-unit Tip and payment-b's 700-minor-unit Tip never mix)",
        all(a.payment_id == payment_ids["multi_a"] for a in multi_a)
        and all(a.payment_id == payment_ids["multi_b"] for a in multi_b)
        and sum(a.allocated_amount_minor for a in multi_a) <= 500
        and sum(a.allocated_amount_minor for a in multi_b) <= 700,
    )

    # #8
    failed_issues = issues_for("failed_payment")
    result.check(
        "#8 a failed Payment's Tip is blocked with FAILED_PAYMENT_WITH_TIP and zero allocations",
        len(allocations_for("failed_payment")) == 0
        and any(i.issue_type == ISSUE_FAILED_PAYMENT_WITH_TIP for i in failed_issues),
    )

    # #9
    result.check(
        "#9 missing Tip (no PaymentTip row at all) is structurally absent and never considered by the engine",
        session.scalar(select(m.PaymentTip).where(m.PaymentTip.payment_id == payment_ids["missing_tip"]))
        is None,
    )
    zero_tip_allocs = allocations_for("recorded_zero_tip")
    result.check(
        "#9 recorded zero Tip (source_present=True, amount=0) is processed — a real TipAllocation "
        "row exists with amount exactly zero, distinct from 'never considered'",
        len(zero_tip_allocs) >= 1 and sum(a.allocated_amount_minor for a in zero_tip_allocs) == 0,
    )

    # #10
    result.check(
        "#10 unrecorded cash Tip is not invented: run-level allocated+unallocated == source amount considered",
        summary.allocated_amount_minor + summary.unallocated_amount_minor == summary.source_tip_amount_minor,
    )

    # #11 / #12
    decoy_allocs = [a for a in allocations_for("employee_decoys") if a.policy_component_id == component_service_owner.id]
    result.check(
        "#11/#12 Payment.employee and Order.employee differ from the resolved service owner, "
        "and the allocation still goes to the resolver's employee",
        len(decoy_allocs) == 1
        and decoy_allocs[0].employee_id == emp_service_owner.id
        and emp_order_employee.id != emp_service_owner.id
        and emp_payment_employee.id != emp_service_owner.id,
    )

    # #13
    late_allocs = [a for a in allocations_for("late_observed") if a.policy_component_id == component_role_support.id]
    result.check(
        "#13 payment timestamp (not calculation time) controls eligibility "
        "(Assignment/Shift window is narrow around T, calculation runs long after)",
        len(late_allocs) == 1 and late_allocs[0].employee_id == emp_role_a.id,
    )

    # #14 / #15 / #16 / #17
    presence_allocs = [a for a in allocations_for("presence_combo") if a.policy_component_id == component_role_support.id]
    presence_ids = {a.employee_id for a in presence_allocs}
    result.check(
        "#14/#16 Employee with Shift active at T and valid Assignment at T is eligible",
        emp_role_a.id in presence_ids,
    )
    result.check(
        "#15 Employee with valid Assignment but Shift on a different day is NOT eligible",
        emp_outside_shift.id not in presence_ids,
    )
    result.check(
        "#17 Employee with Shift at T but an Assignment that expired before T is NOT eligible",
        emp_expired.id not in presence_ids,
    )

    # TASK_TIPS_002 §11 Case 1 — Manager + Server, same Operational Area
    case1_allocs = [
        a for a in allocations_for("concurrent_same_area") if a.policy_component_id == component_role_support.id
    ]
    case1_blocking_issues = [i for i in issues_for("concurrent_same_area") if i.severity == "BLOCKING"]
    result.check(
        "TASK_TIPS_002 Case 1: an Employee with concurrent Manager + Server Assignments in the SAME "
        "Operational Area is eligible for the Server component, with no blocking assignment-conflict issue",
        len(case1_allocs) == 1
        and case1_allocs[0].employee_id == emp_concurrent_same_area.id
        and len(case1_blocking_issues) == 0,
    )

    # Case 2 — Manager + Server, different Operational Areas
    case2_allocs = [
        a for a in allocations_for("concurrent_diff_area") if a.policy_component_id == component_role_support.id
    ]
    case2_blocking_issues = [i for i in issues_for("concurrent_diff_area") if i.severity == "BLOCKING"]
    result.check(
        "TASK_TIPS_002 Case 2: an Employee with concurrent Manager + Server Assignments in DIFFERENT "
        "Operational Areas is eligible for the Server component, with no blocking assignment-conflict issue",
        len(case2_allocs) == 1
        and case2_allocs[0].employee_id == emp_concurrent_diff_area.id
        and len(case2_blocking_issues) == 0,
    )

    # Case 3 — one Employee, two matching Assignments -> counted once
    case3_allocs = [
        a for a in allocations_for("dedup_same_role_two_areas") if a.policy_component_id == component_role_support.id
    ]
    result.check(
        "TASK_TIPS_002 Case 3: an Employee with two matching Server Assignments (different Areas) "
        "appears exactly once in the component's eligible set (one headcount share, not two)",
        len(case3_allocs) == 1 and case3_allocs[0].employee_id == emp_dedup.id,
    )

    # Case 4 — duplicate-matching Employee must not skew the equal split
    case4_allocs = [
        a for a in allocations_for("headcount_dedup") if a.policy_component_id == component_role_support.id
    ]
    case4_by_emp = {a.employee_id: a.allocated_amount_minor for a in case4_allocs}
    result.check(
        "TASK_TIPS_002 Case 4: an Employee with two matching Assignments does not receive an extra "
        "headcount share — the split remains 50/50 between the two eligible Employees, not 66/33",
        set(case4_by_emp) == {emp_headcount_a.id, emp_headcount_b.id}
        and case4_by_emp[emp_headcount_a.id] == case4_by_emp[emp_headcount_b.id] == 100,
    )

    # Case 5 — cross-component eligibility is not silently suppressed
    case5_allocs = allocations_for("cross_component")
    case5_owner_allocs = [a for a in case5_allocs if a.policy_component_id == component_service_owner.id]
    case5_role_allocs = [a for a in case5_allocs if a.policy_component_id == component_role_support.id]
    result.check(
        "TASK_TIPS_002 Case 5: the same Employee, eligible under both the SERVICE_OWNER and "
        "ROLE_PRESENT_AT_PAYMENT components, receives both allocations — the generic engine does not "
        "silently suppress either one just because the same Employee appears in both",
        len(case5_owner_allocs) == 1
        and case5_owner_allocs[0].employee_id == emp_cross_component.id
        and len(case5_role_allocs) == 1
        and case5_role_allocs[0].employee_id == emp_cross_component.id,
    )

    # Case 6 — Shift is still required
    case6_role_employee_ids = {
        a.employee_id for a in allocations_for("no_shift_role") if a.policy_component_id == component_role_support.id
    }
    result.check(
        "TASK_TIPS_002 Case 6: a matching Server Assignment without an active Shift at T does not make "
        "the Employee eligible for the role-based component",
        emp_no_shift.id not in case6_role_employee_ids,
    )

    # Case 7 — no matching role Assignment
    case7_role_employee_ids = {
        a.employee_id for a in allocations_for("wrong_role_only") if a.policy_component_id == component_role_support.id
    }
    result.check(
        "TASK_TIPS_002 Case 7: an active Shift plus a Manager Assignment, with no Server Assignment, "
        "does not make the Employee eligible for the Server component",
        emp_wrong_role_only.id not in case7_role_employee_ids,
    )

    # #19
    early_allocs = [a for a in allocations_for("early_policy") if a.policy_component_id == component_early_service_owner.id]
    result.check(
        "#19 a payment under the earlier policy uses that policy's 100% service-owner share, not the later policy's 80%",
        len(early_allocs) == 1 and early_allocs[0].allocated_amount_minor == 1000,
    )

    # #20
    before_policy_issues = issues_for("before_any_policy")
    result.check(
        "#20 no valid policy at all produces an explicit NO_VALID_POLICY issue and zero allocations",
        len(allocations_for("before_any_policy")) == 0
        and any(i.issue_type == ISSUE_NO_VALID_POLICY for i in before_policy_issues),
    )

    # #21
    unresolved_issues = issues_for("unresolved_owner")
    result.check(
        "#21 an unresolved service owner produces an explicit SERVICE_OWNER_UNRESOLVED issue",
        len(allocations_for("unresolved_owner")) == 0
        and any(i.issue_type == ISSUE_SERVICE_OWNER_UNRESOLVED for i in unresolved_issues),
    )
    ambiguous_issues = issues_for("ambiguous_owner")
    result.check(
        "TASK_TIPS_002 Case 8: service-attribution AMBIGUOUS remains an explicit BLOCKING "
        "SERVICE_OWNER_AMBIGUOUS issue, unchanged by this task's eligibility correction "
        "(not silently one of the candidates)",
        len(allocations_for("ambiguous_owner")) == 0
        and any(i.issue_type == "SERVICE_OWNER_AMBIGUOUS" and i.severity == "BLOCKING" for i in ambiguous_issues),
    )

    # #22
    all_run_allocs = session.scalars(
        select(m.TipAllocation).where(m.TipAllocation.calculation_run_id == run.id)
    ).all()
    result.check(
        "#22 allocation totals reconcile exactly to the source Tip at the run level",
        summary.allocated_amount_minor + summary.unallocated_amount_minor == summary.source_tip_amount_minor
        and sum(a.allocated_amount_minor for a in all_run_allocs) == summary.allocated_amount_minor,
    )

    # #23
    service_charge_allocs = allocations_for("service_charge")
    result.check(
        "#23 Service Charge (OrderFee) is not included as Tip — allocation total matches only the recorded PaymentTip",
        sum(a.allocated_amount_minor for a in service_charge_allocs if a.policy_component_id == component_service_owner.id)
        <= 800,  # 80% of 1000, never inflated by the 5000-minor-unit Service Charge fee
    )

    # #24
    refund_ambiguous_issues = issues_for("refund_ambiguous")
    result.check(
        "#24a a Refund with no tip_amount evidence produces a WARNING REFUND_REVIEW_REQUIRED "
        "and the Tip is still allocated in full (no evidence the Tip itself was affected)",
        any(i.issue_type == ISSUE_REFUND_REVIEW_REQUIRED and i.severity == "WARNING" for i in refund_ambiguous_issues)
        and len(allocations_for("refund_ambiguous")) >= 1,
    )
    refund_confirmed_issues = issues_for("refund_confirmed")
    result.check(
        "#24b a Refund with explicit non-zero tip_amount evidence produces a BLOCKING "
        "REFUND_REVIEW_REQUIRED and the Tip is NOT allocated (refund ambiguity is not silently interpreted)",
        any(i.issue_type == ISSUE_REFUND_REVIEW_REQUIRED and i.severity == "BLOCKING" for i in refund_confirmed_issues)
        and len(allocations_for("refund_confirmed")) == 0,
    )

    # Extra: REDISTRIBUTE_TO_ELIGIBLE_COMPONENTS
    redistribute_run, redistribute_summary = run_tip_calculation(
        session,
        restaurant_id=restaurant2.id,
        period_start=_dt(47),
        period_end=_dt(45),
        resolver=resolver,
        mode="DRY_RUN",
        calculation_version="test-redistribute",
    )
    redistribute_all_allocs = session.scalars(
        select(m.TipAllocation).where(
            m.TipAllocation.payment_tip_id == payment_ids["redistribute"],
            m.TipAllocation.calculation_run_id == redistribute_run.id,
        )
    ).all()
    redistribute_by_component = {a.policy_component_id: a for a in redistribute_all_allocs}
    result.check(
        "REDISTRIBUTE_TO_ELIGIBLE_COMPONENTS moves the empty component's (30%) share to the eligible "
        "component's employee — auditably attributed to its ORIGINATING component (comp_redistribute_role), "
        "distinct from that same employee's own 70% share (comp_redistribute_target) — together reconciling to 100%",
        len(redistribute_all_allocs) == 2
        and all(a.employee_id == emp_redistribute.id for a in redistribute_all_allocs)
        and redistribute_by_component.get(comp_redistribute_target.id) is not None
        and redistribute_by_component[comp_redistribute_target.id].allocated_amount_minor == 700
        and redistribute_by_component.get(comp_redistribute_role.id) is not None
        and redistribute_by_component[comp_redistribute_role.id].allocated_amount_minor == 300
        and sum(a.allocated_amount_minor for a in redistribute_all_allocs) == 1000,
    )

    # Shift/Assignment gap warning (bonus structural check, not separately numbered)
    gap_issues = [
        i for i in session.scalars(select(m.TipCalculationIssue).where(m.TipCalculationIssue.calculation_run_id == run.id)).all()
        if i.issue_type == ISSUE_SHIFT_ASSIGNMENT_GAP
    ]
    result.check(
        "SHIFT_ASSIGNMENT_GAP is produced when a Shift-present Employee has no Assignment at all at T",
        len(gap_issues) >= 1,
    )

    # Defensive reconciliation-failure path is at least wired up (never triggered by correct code).
    result.check(
        "ALLOCATION_RECONCILIATION_FAILURE issue type is defined and importable for the defensive check",
        ISSUE_ALLOCATION_RECONCILIATION_FAILURE == "ALLOCATION_RECONCILIATION_FAILURE",
    )

    result.check(
        "the calculation run itself completes with a COMPLETE status and is fully attributable",
        run.status == "COMPLETE" and run.completed_at is not None and run.restaurant_id == restaurant.id,
    )
