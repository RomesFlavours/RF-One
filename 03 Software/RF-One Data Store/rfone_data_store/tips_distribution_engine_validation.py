"""Automated synthetic tests for TIP_DISTRIBUTION_ENGINE_001's core
calculation/allocation engine (task §23).

Mirrors `tips_validation.py`/`tips_distribution_rule_validation.py`'s
pattern: builds one synthetic (never-real) fixture inside a disposable
database, exercises `tips.distribution_engine`, asserts the required
behaviors, and always rolls back at the very end (the fixture itself
commits along the way, exactly like `tips_clover_import_validation.py`,
since the engine's own recalculation-safety behavior must be exercised
against real committed rows, not just a pending transaction).

NEVER touches Clover — every Order/Payment/Shift/EmployeeAssignment row is
inserted directly as an already-ingested RF-One source fact, exactly what
the engine is required to consume (task §2/§22).
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import inspect as sa_inspect, select
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


def _build_fixture_and_assert(session: Session, result: ValidationResult) -> None:
    # --- Base fixture -------------------------------------------------------
    source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
    session.add(source_system)
    session.flush()

    merchant = m.Merchant(source_system_id=source_system.id, source_merchant_id="TDEMERCH1", name="TDE Test Merchant")
    session.add(merchant)
    session.flush()

    location = m.Location(
        merchant_id=merchant.id, source_system_id=source_system.id, source_location_id="TDEMERCH1",
        name="TDE Test Location", currency="USD",
    )
    session.add(location)
    session.flush()

    restaurant = m.Restaurant(name="Synthetic TDE Test Restaurant", default_currency="USD")
    session.add(restaurant)
    session.flush()
    session.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
    session.flush()

    area_foh = m.OperationalArea(restaurant_id=restaurant.id, name="FOH")
    session.add(area_foh)
    session.flush()

    role_server = m.RestaurantRole(restaurant_id=restaurant.id, name="Server")
    role_host = m.RestaurantRole(restaurant_id=restaurant.id, name="Host")
    role_bartender = m.RestaurantRole(restaurant_id=restaurant.id, name="Bartender")
    session.add_all([role_server, role_host, role_bartender])
    session.flush()

    def make_employee(source_id: str, name: str) -> m.Employee:
        emp = m.Employee(
            location_id=location.id, source_system_id=source_system.id, source_employee_id=source_id,
            display_name=name, system_role="EMPLOYEE",
        )
        session.add(emp)
        session.flush()
        return emp

    server1 = make_employee("SRV1", "Server1")
    host_a = make_employee("HOSTA", "HostA")
    host_b = make_employee("HOSTB", "HostB")
    host_c = make_employee("HOSTC", "HostC")
    host_edge10 = make_employee("HOSTE10", "HostEdge10")
    host_edge11 = make_employee("HOSTE11", "HostEdge11")
    host_edge12 = make_employee("HOSTE12", "HostEdge12")
    bartender1 = make_employee("BART1", "Bartender1")

    def make_assignment(employee: m.Employee, role: m.RestaurantRole, valid_from: datetime, valid_to: datetime | None) -> None:
        session.add(
            m.EmployeeAssignment(
                employee_id=employee.id, restaurant_id=restaurant.id, operational_area_id=area_foh.id,
                restaurant_role_id=role.id, valid_from=valid_from, valid_to=valid_to, assignment_source="MANUAL",
            )
        )

    # server1's Server-role assignment spans the whole fixture window.
    make_assignment(server1, role_server, _at(-300), None)
    for host_emp in (host_a, host_b, host_c):
        make_assignment(host_emp, role_host, _at(-300), None)
    # host_edge12's own Shift is deliberately open-ended (clock_out=None, to
    # test "open Shift at Settlement Time -> eligible") and so would
    # otherwise remain Shift-active forever afterward — its Host ROLE
    # assignment is bounded to just its own test window so it never
    # contaminates a LATER scenario's eligible-recipient set (13/14/16).
    for host_emp in (host_edge10, host_edge11, host_edge12):
        make_assignment(host_emp, role_host, _at(9), _at(13))
    make_assignment(bartender1, role_bartender, _at(-300), None)
    session.flush()

    def make_shift(employee: m.Employee, clock_in: datetime, clock_out: datetime | None, suffix: str) -> None:
        session.add(
            m.Shift(
                employee_id=employee.id, source_system_id=source_system.id,
                source_shift_id=f"SHIFT-{employee.id}-{suffix}", clock_in=clock_in, clock_out=clock_out,
            )
        )

    # host_a: active days 1-8 (clock_out strictly AFTER order 8's noon
    # settlement, so the exact-boundary case still counts host_a as
    # eligible), absent days 9-12 (scenario 9's "no Host active", and so
    # scenarios 10/11/12 test ONLY their own dedicated edge-case Host),
    # active again from day 13 onward (scenarios 13/14/16).
    make_shift(host_a, _at(0, 12), _at(8, 13), "1")
    make_shift(host_a, _at(12, 23), _at(200, 0), "2")
    # host_b: active days 7-8 only (scenarios 7/8).
    make_shift(host_b, _at(7, 0), _at(8, 23), "1")
    # host_c: active day 8 only (scenario 8 — three eligible Hosts).
    make_shift(host_c, _at(8, 0), _at(8, 23), "1")
    # Edge-case Hosts (scenarios 10/11/12), each isolated to their own day.
    make_shift(host_edge10, _at(10, 8), _at(10, 11), "1")  # clocks out BEFORE settlement (noon)
    make_shift(host_edge11, _at(11, 13), _at(11, 18), "1")  # clocks in AFTER settlement (noon)
    make_shift(host_edge12, _at(12, 8), None, "1")  # open Shift AT settlement
    # bartender1: active from day 10 onward (scenario 16).
    make_shift(bartender1, _at(10, 0), _at(200, 0), "1")
    session.flush()

    # --- Rule 1: Server -> Host, TIP_PLUS_GRATUITY, 10% (Rome's Flavours'
    # own configuration, but exercised here as ordinary restaurant data). ---
    rule1 = rule_svc.create_rule(
        session, restaurant_id=restaurant.id, source_role_id=role_server.id, recipient_role_id=role_host.id,
        calculation_base=m.CALC_BASE_TIP_PLUS_GRATUITY, rate=Decimal("10.0000"), effective_from=_at(-300),
        created_by="tester",
    )
    session.commit()
    session.expire_all()

    order_counter = {"n": 0}

    def next_id(prefix: str) -> str:
        order_counter["n"] += 1
        return f"{prefix}-{order_counter['n']}"

    def make_order(*, employee: m.Employee | None, created_at: datetime, total: int = 10000) -> m.Order:
        order = m.Order(
            location_id=location.id, source_system_id=source_system.id, source_order_id=next_id("ORDER"),
            employee_id=employee.id if employee else None,
            source_employee_id=employee.source_employee_id if employee else None,
            created_at=created_at, state="locked", payment_state="PAID", currency="USD", total=total,
        )
        session.add(order)
        session.flush()
        return order

    def make_payment(
        *, order: m.Order, employee: m.Employee | None, amount: int, created_at: datetime,
        tip_amount: int | None = None, result: str = "SUCCESS",
    ) -> m.Payment:
        payment = m.Payment(
            order_id=order.id, source_system_id=source_system.id, source_payment_id=next_id("PAY"),
            employee_id=employee.id if employee else None,
            source_employee_id=employee.source_employee_id if employee else None,
            created_at=created_at, amount=amount, result=result, currency="USD",
        )
        session.add(payment)
        session.flush()
        if tip_amount is not None:
            session.add(m.PaymentTip(payment_id=payment.id, amount=tip_amount, source_present=True))
        return payment

    def make_fee(*, order: m.Order, amount: int) -> m.OrderFee:
        fee = m.OrderFee(
            order_id=order.id, source_system_id=source_system.id, fee_type="SERVICE_CHARGE",
            name_raw="Service Charge", amount=amount,
        )
        session.add(fee)
        session.flush()
        return fee

    def allocations_for(calc, order_id: int) -> list:
        return [line for line in calc.lines if line.order_id == order_id]

    # === 1: voluntary tip only ===============================================
    order1 = make_order(employee=server1, created_at=_at(1, 11))
    make_payment(order=order1, employee=server1, amount=10000, created_at=_at(1, 12), tip_amount=1000)

    # === 2: gratuity only =====================================================
    order2 = make_order(employee=server1, created_at=_at(2, 11))
    make_payment(order=order2, employee=server1, amount=10000, created_at=_at(2, 12))
    make_fee(order=order2, amount=800)

    # === 3: tip + gratuity ====================================================
    order3 = make_order(employee=server1, created_at=_at(3, 11))
    make_payment(order=order3, employee=server1, amount=10000, created_at=_at(3, 12), tip_amount=500)
    make_fee(order=order3, amount=300)

    # === 4: split payment, gratuity counted once =============================
    order4 = make_order(employee=server1, created_at=_at(4, 10))
    make_payment(order=order4, employee=server1, amount=5000, created_at=_at(4, 11), tip_amount=200)
    make_payment(order=order4, employee=server1, amount=5000, created_at=_at(4, 12), tip_amount=200)
    make_fee(order=order4, amount=300)

    # === 5: Order.employee owns Gross Tips despite a Payment.employee mismatch
    order5 = make_order(employee=server1, created_at=_at(5, 11))
    make_payment(order=order5, employee=host_a, amount=10000, created_at=_at(5, 12), tip_amount=1000)

    # === 6: one active Host -> full pool ======================================
    order6 = make_order(employee=server1, created_at=_at(6, 11))
    make_payment(order=order6, employee=server1, amount=10000, created_at=_at(6, 12), tip_amount=1000)

    # === 7: two active Hosts -> equal split ===================================
    order7 = make_order(employee=server1, created_at=_at(7, 11))
    make_payment(order=order7, employee=server1, amount=10000, created_at=_at(7, 12), tip_amount=1000)

    # === 8: three active Hosts -> deterministic residual cent =================
    order8 = make_order(employee=server1, created_at=_at(8, 11))
    make_payment(order=order8, employee=server1, amount=100000, created_at=_at(8, 12), tip_amount=10000)

    # === 9: no Host active -> SOURCE_RETAINS ==================================
    order9 = make_order(employee=server1, created_at=_at(9, 11))
    make_payment(order=order9, employee=server1, amount=10000, created_at=_at(9, 12), tip_amount=1000)

    # === 10/11/12: Host clock-in/out edge cases ===============================
    order10 = make_order(employee=server1, created_at=_at(10, 11))
    make_payment(order=order10, employee=server1, amount=10000, created_at=_at(10, 12), tip_amount=1000)
    order11 = make_order(employee=server1, created_at=_at(11, 11))
    make_payment(order=order11, employee=server1, amount=10000, created_at=_at(11, 12), tip_amount=1000)
    order12 = make_order(employee=server1, created_at=_at(12, 11))
    make_payment(order=order12, employee=server1, amount=10000, created_at=_at(12, 12), tip_amount=1000)

    # === 13: effective-dated rule selection (OLD version applies) ============
    order13 = make_order(employee=server1, created_at=_at(13, 11))
    make_payment(order=order13, employee=server1, amount=10000, created_at=_at(13, 12), tip_amount=1000)

    # New rule version — configurable rate, not hardcoded 10% (task §15) —
    # effective AFTER order13's settlement, BEFORE order14's.
    rule1_v2 = rule_svc.create_new_version(
        session, rule1.id, source_role_id=role_server.id, recipient_role_id=role_host.id,
        calculation_base=m.CALC_BASE_TIP_PLUS_GRATUITY, rate=Decimal("25.0000"), effective_from=_at(20),
        created_by="tester",
    )

    # === 14: future rule version does not alter a prior Order's calculation —
    # this Order settles AFTER the new version's effective_from.
    order14 = make_order(employee=server1, created_at=_at(25, 11))
    make_payment(order=order14, employee=server1, amount=10000, created_at=_at(25, 12), tip_amount=1000)

    # === 16: two independent rules do not cascade =============================
    # Deliberately tightly bounded to ONLY cover order16's own settlement time
    # — this rule shares the SAME source_role_id (Server) as rule1, so an
    # unbounded effective window would fire it on every OTHER Order in this
    # fixture too (they all share Order.employee == server1), contaminating
    # every other scenario's expected single-allocation-per-Order shape.
    rule2 = rule_svc.create_rule(
        session, restaurant_id=restaurant.id, source_role_id=role_server.id, recipient_role_id=role_bartender.id,
        calculation_base=m.CALC_BASE_TIP_PLUS_GRATUITY, rate=Decimal("5.0000"), effective_from=_at(15, 12),
        effective_to=_at(17, 0), created_by="tester",
    )
    order16 = make_order(employee=server1, created_at=_at(16, 11))
    make_payment(order=order16, employee=server1, amount=100000, created_at=_at(16, 12), tip_amount=10000)

    session.commit()
    session.expire_all()
    rule1 = session.get(m.TipDistributionRule, rule1.id)
    rule1_v2 = session.get(m.TipDistributionRuleVersion, rule1_v2.id)

    period_start, period_end = _at(-1), _at(400)
    calc1 = engine.calculate_tips(
        session, restaurant_id=restaurant.id, period_start=period_start, period_end=period_end,
    )
    summary1 = calc1.summary

    result.check("first calculation succeeds and persists nothing", calc1.blocked_reason is None)

    # --- 1 ---
    a1 = allocations_for(calc1, order1.id)
    result.check(
        "1: voluntary tip only — base=1000, pool=100 (10%), full pool to the single eligible Host",
        len(a1) == 1 and a1[0].base_amount_minor == 1000 and a1[0].pool_amount_minor == 100
        and a1[0].recipient_employee_id == host_a.id and a1[0].allocated_amount_minor == 100,
    )

    # --- 2 ---
    a2 = allocations_for(calc1, order2.id)
    result.check(
        "2: gratuity only — base=800 (no voluntary tip), pool=80",
        len(a2) == 1 and a2[0].base_amount_minor == 800 and a2[0].pool_amount_minor == 80,
    )

    # --- 3 ---
    a3 = allocations_for(calc1, order3.id)
    result.check(
        "3: tip + gratuity — base=800 (500 tip + 300 gratuity), pool=80",
        len(a3) == 1 and a3[0].base_amount_minor == 800 and a3[0].pool_amount_minor == 80,
    )

    # --- 4 ---
    a4 = allocations_for(calc1, order4.id)
    fees4 = session.scalars(select(m.OrderFee).where(m.OrderFee.order_id == order4.id)).all()
    result.check(
        "4: split-payment Order — gratuity counted once (700 = 400 voluntary + 300 gratuity, "
        "not 400 + 300 + 300), pool=70",
        len(fees4) == 1 and len(a4) == 1 and a4[0].base_amount_minor == 700 and a4[0].pool_amount_minor == 70,
    )

    # --- 5 ---
    a5 = allocations_for(calc1, order5.id)
    result.check(
        "5: Order.employee (server1) owns Gross Tips even though Payment.employee is a different Employee",
        len(a5) == 1 and a5[0].source_employee_id == server1.id and a5[0].source_employee_id != host_a.id,
    )

    # --- 6 ---
    a6 = allocations_for(calc1, order6.id)
    result.check(
        "6: one active Host -> receives the FULL configured pool",
        len(a6) == 1 and a6[0].recipient_employee_id == host_a.id and a6[0].allocated_amount_minor == 100
        and not a6[0].no_eligible_recipient,
    )

    # --- 7 ---
    a7 = allocations_for(calc1, order7.id)
    amounts7 = sorted(a.allocated_amount_minor for a in a7)
    recipients7 = {a.recipient_employee_id for a in a7}
    result.check(
        "7: two active Hosts -> equal 50/50 split of the 100-cent pool",
        len(a7) == 2 and amounts7 == [50, 50] and recipients7 == {host_a.id, host_b.id},
    )

    # --- 8 ---
    a8 = allocations_for(calc1, order8.id)
    amounts8 = sorted(a.allocated_amount_minor for a in a8)
    recipients8 = {a.recipient_employee_id for a in a8}
    result.check(
        "8: three active Hosts -> deterministic residual-cent split of a 1000-cent pool: 333/333/334, "
        "reconciling exactly (spec §17's own literal example)",
        len(a8) == 3 and amounts8 == [333, 333, 334] and sum(amounts8) == 1000
        and recipients8 == {host_a.id, host_b.id, host_c.id},
    )
    result.check(
        "17: atomic allocations reconcile exactly — sum(allocated) == pool_amount_minor for order 8",
        sum(a.allocated_amount_minor for a in a8) == a8[0].pool_amount_minor,
    )

    # --- 9 ---
    a9 = allocations_for(calc1, order9.id)
    result.check(
        "9: no Host active -> SOURCE_RETAINS: one explicit row, recipient NULL, allocated=0, pool preserved",
        len(a9) == 1 and a9[0].recipient_employee_id is None and a9[0].allocated_amount_minor == 0
        and a9[0].no_eligible_recipient is True and a9[0].pool_amount_minor == 100,
    )

    # --- 10/11/12 ---
    a10 = allocations_for(calc1, order10.id)
    result.check(
        "10: Host clocked out before Settlement Time -> not eligible (SOURCE_RETAINS)",
        len(a10) == 1 and a10[0].no_eligible_recipient is True,
    )
    a11 = allocations_for(calc1, order11.id)
    result.check(
        "11: Host clocks in after Settlement Time -> not eligible (SOURCE_RETAINS)",
        len(a11) == 1 and a11[0].no_eligible_recipient is True,
    )
    a12 = allocations_for(calc1, order12.id)
    result.check(
        "12: an open (clock_out NULL) Shift at Settlement Time -> eligible",
        len(a12) == 1 and a12[0].recipient_employee_id == host_edge12.id and a12[0].allocated_amount_minor == 100,
    )

    # --- 13/14/15 ---
    a13 = allocations_for(calc1, order13.id)
    result.check(
        "13/14: an Order settled BEFORE the new rule version's effective_from still resolves to the OLD "
        "version (10% -> pool=100), even though the new version already exists in the database",
        len(a13) == 1 and a13[0].rate == Decimal("10.0000") and a13[0].pool_amount_minor == 100,
    )
    a14 = allocations_for(calc1, order14.id)
    result.check(
        "14/15: an Order settled AFTER the new rule version's effective_from resolves to the NEW, "
        "configurable rate (25%, never hardcoded 10%) -> pool=250",
        len(a14) == 1 and a14[0].rate == Decimal("25.0000") and a14[0].pool_amount_minor == 250,
    )

    # --- 16 ---
    a16 = allocations_for(calc1, order16.id)
    by_rule = {a.rule_version_id: a for a in a16}
    result.check(
        "16: two independent rules both compute from the SAME original base (10000) — Host 10% -> 1000, "
        "Bartender 5% -> 500 — never 5% of the post-Host remainder (9000)",
        len(a16) == 2 and by_rule.get(rule1.versions[0].id) is not None
        and by_rule[rule1.versions[0].id].pool_amount_minor == 1000
        and by_rule[rule1.versions[0].id].base_amount_minor == 10000
        and by_rule[rule2.versions[0].id].pool_amount_minor == 500
        and by_rule[rule2.versions[0].id].base_amount_minor == 10000,
    )

    # --- 18: employee aggregate reconciles to atomic allocations --------------
    review1 = engine.build_employee_review(session, calc1)
    review_by_id = {row.employee_id: row for row in review1}

    all_allocations_run1 = calc1.lines
    manual_outbound = {}
    manual_inbound = {}
    for a in all_allocations_run1:
        if a.source_employee_id is not None:
            manual_outbound[a.source_employee_id] = manual_outbound.get(a.source_employee_id, 0) + a.allocated_amount_minor
        if a.recipient_employee_id is not None:
            manual_inbound[a.recipient_employee_id] = manual_inbound.get(a.recipient_employee_id, 0) + a.allocated_amount_minor

    result.check(
        "18: server1's Review-row Outbound Tip-Out reconciles exactly to the manually-summed atomic "
        "allocations where they are the source employee",
        review_by_id[server1.id].outbound_tip_out_minor == manual_outbound.get(server1.id, 0),
    )
    result.check(
        "18: host_a's Review-row Inbound Tip-Out reconciles exactly to the manually-summed atomic "
        "allocations where they are the recipient",
        review_by_id[host_a.id].inbound_tip_out_minor == manual_inbound.get(host_a.id, 0),
    )
    # TIPS_FINALIZED_PERIOD_CALCULATION_AND_REPORT_001 §6 SUPERSEDES the
    # assertion that used to stand here, which required order 9's
    # no-eligible-recipient outcome to raise a warning on server1's row.
    #
    # The Product Owner's decision is that no eligible recipient at the
    # deciding instant means NO DISTRIBUTION OBLIGATION AROSE: the Service
    # Owner keeps 100% of that Order, and that is a normal, resolved,
    # payable result — not something to flag. Flagging it trained the
    # operator to distrust correct numbers, which is why it was removed.
    # The per-order REASON stays in the Order drill-down, where a question
    # about one order belongs. No AMOUNT is carried onto the employee's
    # row: the AWS deploy task's §6/§10 removed the "would have been
    # distributed" figure entirely, because nothing was withheld and
    # nothing is outstanding — the Service Owner simply earned it.
    result.check(
        "9 (§6): server1's Review row does NOT flag attention for order 9's "
        "no-eligible-recipient allocation, and carries no hypothetical retained amount "
        "— the Service Owner legitimately earned 100% of it",
        not review_by_id[server1.id].needs_attention
        and not hasattr(review_by_id[server1.id], "retained_no_eligible_host_minor"),
    )

    # === 19: ANY period is freely recalculable (TIPS_STATELESS_CALCULATION_001)
    # Replaces the retired overlap-refusal/supersession behaviour: with no
    # stored result there is nothing to conflict with, so the only thing
    # worth asserting is that repeated and overlapping calculations all
    # succeed and stay deterministic.
    run1_allocation_count_before = len(all_allocations_run1)

    calc2 = engine.calculate_tips(
        session, restaurant_id=restaurant.id, period_start=period_start, period_end=period_end,
    )
    result.check(
        "19A: the SAME period can be calculated again, with no refusal and no supersession",
        calc2.blocked_reason is None,
    )
    result.check(
        "19A: recalculating the same period is deterministic — same number of allocation lines",
        len(calc2.lines) == run1_allocation_count_before,
    )
    result.check(
        "19A: recalculating the same period yields identical distributed totals",
        calc2.distributed_total_minor == calc1.distributed_total_minor
        and calc2.voluntary_total_minor == calc1.voluntary_total_minor,
    )

    calc_overlap = engine.calculate_tips(
        session, restaurant_id=restaurant.id, period_start=period_start, period_end=_at(200),
    )
    result.check(
        "19B: a DIFFERENT, partially overlapping period calculates freely (no refusal)",
        calc_overlap.blocked_reason is None,
    )

    calc_subset = engine.calculate_tips(
        session, restaurant_id=restaurant.id, period_start=_at(0), period_end=_at(2),
    )
    result.check("19C: a SUBSET period calculates freely", calc_subset.blocked_reason is None)

    calc_superset = engine.calculate_tips(
        session, restaurant_id=restaurant.id, period_start=_at(-50), period_end=_at(900),
    )
    result.check("19D: a SUPERSET period calculates freely", calc_superset.blocked_reason is None)
    result.check(
        "19D: the superset contains at least as many allocation lines as the original window",
        len(calc_superset.lines) >= run1_allocation_count_before,
    )

    calc_arbitrary = engine.calculate_tips(
        session, restaurant_id=restaurant.id,
        period_start=_at(1, 7) + timedelta(minutes=13),
        period_end=_at(1, 19) + timedelta(minutes=47),
    )
    result.check(
        "19E: arbitrary (non-midnight, minute-level) datetime boundaries calculate normally",
        calc_arbitrary.blocked_reason is None,
    )

    # === G/H: calculating creates NO persisted result records =================
    runs_now = session.scalars(select(m.TipDistributionCalculationRun)).all()
    result.check(
        "G: calculating Tips creates no TipDistributionCalculationRun at all",
        len(runs_now) == 0,
    )
    result.check(
        "H: the persisted allocation table no longer exists in the schema",
        "tip_distribution_allocations" not in sa_inspect(session.get_bind()).get_table_names(),
    )

    # === K: reconciliation invariant =========================================
    result.check(
        "K: Service Owner retained + distributed + unresolved == voluntary tips (difference is exactly 0)",
        calc1.reconciles and calc1.reconciliation_difference_minor == 0,
    )

    # === 20: a Refund never auto-reverses a tip calculation ====================
    payment1 = session.scalars(select(m.Payment).where(m.Payment.order_id == order1.id)).first()
    session.add(
        m.Refund(
            source_system_id=source_system.id, source_refund_id="REFUND-TDE-1", order_id=order1.id,
            payment_id=payment1.id, created_at=_at(1, 13), amount=10000, tip_amount=1000, status="PROCESSED",
        )
    )
    session.commit()
    session.expire_all()

    calc_after_refund = engine.calculate_tips(
        session, restaurant_id=restaurant.id, period_start=period_start, period_end=period_end,
    )
    a1_after_refund = allocations_for(calc_after_refund, order1.id)
    result.check(
        "20: a Refund recorded AFTER the fact never auto-reverses the calculation — recalculating the "
        "same period still yields the full pool=100 to the same Host",
        len(a1_after_refund) == 1 and a1_after_refund[0].allocated_amount_minor == 100
        and a1_after_refund[0].pool_amount_minor == 100,
    )
    review2 = engine.build_employee_review(session, calc_after_refund)
    review2_by_id = {row.employee_id: row for row in review2}
    result.check(
        "20: the Refund appears as a WARNING on server1's Review row, never as an automatic reversal",
        review2_by_id[server1.id].has_warning
        and any("Refund" in note for note in review2_by_id[server1.id].warning_notes),
    )

    # === Order drill-down (task §18) ===========================================
    drilldown8 = engine.get_order_drilldown(session, calc_after_refund, order8.id)
    result.check(
        "drill-down: order 8 shows Settlement Time, Gross Tip, and all 3 recipient allocations",
        drilldown8 is not None and drilldown8["gross_earned_tips_minor"] == 10000
        and len(drilldown8["allocations"]) == 3,
    )

    # === 21: no Clover production calls during calculation =====================
    engine_source = inspect.getsource(engine)
    result.check(
        "21: the calculation engine's source never references a Clover client/network call — every input "
        "is an already-persisted RF-One fact",
        "CloverClient" not in engine_source and "clover_explorer" not in engine_source
        and "requests." not in engine_source and "get_default_client" not in engine_source,
    )
