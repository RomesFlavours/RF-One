"""Automated synthetic tests for the Host Tip Audit / Explain report
(HOST_TIP_AUDIT_001).

Mirrors `tips_distribution_engine_validation.py`'s fixture pattern exactly:
one synthetic Restaurant/Location/Roles/Employees/Shifts/Orders/Payments,
the REAL `distribution_engine.calculate_tips` (never a hand-crafted
allocation line) so this suite proves the audit report correctly explains
genuine engine output, recalculated on demand and never persisted, then `tips.host_audit_report`
is exercised and asserted against, and the whole transaction is rolled
back at the end.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .business_date import resolve_and_persist_order_business_date
from .tips import distribution_engine as engine
from .tips import distribution_rule_service as rule_svc
from .tips import host_audit_report as audit
from .tips import review_mode_service as review_svc

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


def _at(day: float, hour: int = 12, minute: int = 0) -> datetime:
    return T0 + timedelta(days=day, hours=hour, minutes=minute)


def _build_fixture_and_assert(session: Session, result: ValidationResult) -> None:
    source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
    session.add(source_system)
    session.flush()

    merchant = m.Merchant(source_system_id=source_system.id, source_merchant_id="HTAMERCH1", name="HTA Test Merchant")
    session.add(merchant)
    session.flush()

    location = m.Location(
        merchant_id=merchant.id, source_system_id=source_system.id, source_location_id="HTAMERCH1",
        name="HTA Test Location", currency="USD", timezone="America/New_York", operating_day_cutoff_time=time(4, 0),
    )
    session.add(location)
    session.flush()

    restaurant = m.Restaurant(name="Synthetic HTA Test Restaurant", default_currency="USD")
    session.add(restaurant)
    session.flush()
    session.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
    session.flush()

    area_foh = m.OperationalArea(restaurant_id=restaurant.id, name="FOH")
    session.add(area_foh)
    session.flush()

    role_server = m.RestaurantRole(restaurant_id=restaurant.id, name="Server")
    role_host = m.RestaurantRole(restaurant_id=restaurant.id, name="Host")
    session.add_all([role_server, role_host])
    session.flush()

    def make_employee(source_id: str, name: str) -> m.Employee:
        emp = m.Employee(
            location_id=location.id, source_system_id=source_system.id, source_employee_id=source_id,
            display_name=name, system_role="EMPLOYEE",
        )
        session.add(emp)
        session.flush()
        return emp

    server1 = make_employee("SRV1", "Alice")
    host_gaby = make_employee("HOSTG", "Gaby")
    host_allie = make_employee("HOSTA", "Allie")

    def make_assignment(employee: m.Employee, role: m.RestaurantRole) -> None:
        session.add(
            m.EmployeeAssignment(
                employee_id=employee.id, restaurant_id=restaurant.id, operational_area_id=area_foh.id,
                restaurant_role_id=role.id, valid_from=_at(-300), valid_to=None, assignment_source="MANUAL",
            )
        )

    make_assignment(server1, role_server)
    make_assignment(host_gaby, role_host)
    make_assignment(host_allie, role_host)
    session.flush()

    def make_shift(employee: m.Employee, clock_in: datetime, clock_out: datetime | None, suffix: str) -> m.Shift:
        shift = m.Shift(
            employee_id=employee.id, source_system_id=source_system.id, location_id=location.id,
            source_shift_id=f"SHIFT-{employee.id}-{suffix}", clock_in=clock_in, clock_out=clock_out,
        )
        session.add(shift)
        session.flush()
        return shift

    # Scenario A/F/I day: Gaby alone, 17:00-22:30.
    shift_gaby_day_a = make_shift(host_gaby, _at(1, 17), _at(1, 22.5), "A")
    # Scenario B day: Gaby AND Allie both active.
    make_shift(host_gaby, _at(2, 17), _at(2, 22), "B1")
    make_shift(host_allie, _at(2, 17), _at(2, 22), "B2")
    # Scenario D day: Gaby's shift window strictly 18:00-20:00, to test
    # payment-before/-during/-after boundaries.
    make_shift(host_gaby, _at(3, 18), _at(3, 20), "D")
    # Scenario E day: Gaby has TWO separate shifts on the SAME day.
    make_shift(host_gaby, _at(4, 10), _at(4, 14), "E1")
    make_shift(host_gaby, _at(4, 18), _at(4, 22), "E2")
    session.flush()

    rule_v1 = rule_svc.create_rule(
        session, restaurant_id=restaurant.id, source_role_id=role_server.id, recipient_role_id=role_host.id,
        calculation_base=m.CALC_BASE_VOLUNTARY_TIP, rate=Decimal("10.0000"), effective_from=_at(-300),
        created_by="tester",
    )
    session.commit()
    session.expire_all()

    order_counter = {"n": 0}

    def next_id(prefix: str) -> str:
        order_counter["n"] += 1
        return f"{prefix}-{order_counter['n']}"

    def make_order_with_tip(*, created_at: datetime, tip_minor: int, total: int = 10000) -> m.Order:
        order = m.Order(
            location_id=location.id, source_system_id=source_system.id, source_order_id=next_id("ORDER"),
            employee_id=server1.id, source_employee_id=server1.source_employee_id,
            created_at=created_at, state="locked", payment_state="PAID", currency="USD", total=total,
        )
        session.add(order)
        session.flush()
        payment = m.Payment(
            order_id=order.id, source_system_id=source_system.id, source_payment_id=next_id("PAY"),
            employee_id=server1.id, source_employee_id=server1.source_employee_id,
            created_at=created_at, amount=total, result="SUCCESS", currency="USD",
        )
        session.add(payment)
        session.flush()
        session.add(m.PaymentTip(payment_id=payment.id, amount=tip_minor, source_present=True))
        session.flush()
        resolve_and_persist_order_business_date(session, order.id)
        return order

    # === Scenario A: one Host active (Gaby alone) ===========================
    order_a = make_order_with_tip(created_at=_at(1, 18), tip_minor=2000)  # 6:00 PM

    # === Scenario B: two Hosts active (Gaby + Allie) ========================
    order_b = make_order_with_tip(created_at=_at(2, 18), tip_minor=2000)

    # === Scenario C: no Host active (day 5, nobody's Shift covers it) ======
    order_c = make_order_with_tip(created_at=_at(5, 18), tip_minor=2000)

    # === Scenario D: shift-boundary payments (Gaby's window 18:00-20:00) ===
    order_d_before = make_order_with_tip(created_at=_at(3, 17), tip_minor=1000)  # before shift start -> excluded
    order_d_during = make_order_with_tip(created_at=_at(3, 19), tip_minor=1000)  # during shift -> included
    order_d_after = make_order_with_tip(created_at=_at(3, 20) + timedelta(minutes=1), tip_minor=1000)  # after shift end -> excluded

    # === Scenario E: two separate same-day shifts (10-14 and 18-22) ========
    order_e_shift1 = make_order_with_tip(created_at=_at(4, 12), tip_minor=1500)
    order_e_shift2 = make_order_with_tip(created_at=_at(4, 20), tip_minor=1500)

    session.commit()
    session.expire_all()

    calc = engine.calculate_tips(
        session, restaurant_id=restaurant.id, period_start=_at(-1, 0), period_end=_at(30, 0),
    )
    summary = calc.summary
    session.commit()
    session.expire_all()
    result.check("Fixture calculation completed (stateless, nothing persisted)", calc.blocked_reason is None)

    # =====================================================================
    # A: one Host active — correct line attribution, correct Host amount.
    # =====================================================================
    report_gaby = audit.build_host_audit_report(
        session, restaurant_id=restaurant.id, host_employee_id=host_gaby.id,
        period_start=_at(1, 0), period_end=_at(1, 23, 59),
    )
    a_lines = [l for g in report_gaby.shift_groups for l in g.lines if l.order_id == order_a.id]
    result.check("A: exactly one line for the single-Host order", len(a_lines) == 1)
    result.check("A: line's Host allocation is the full 10% pool (2000*10%=200)", a_lines and a_lines[0].host_allocated_amount_minor == 200)
    result.check("A: eligible_host_count is 1", a_lines and a_lines[0].eligible_host_count == 1)
    result.check("A: original tip amount is 2000", a_lines and a_lines[0].original_tip_amount_minor == 2000)
    result.check("A: server name resolved correctly", a_lines and a_lines[0].server_employee_name == "Alice")
    result.check("A: Clover Order id is the real source id", a_lines and a_lines[0].clover_order_id == order_a.source_order_id)

    # =====================================================================
    # B: two Hosts active — equal split shown correctly.
    # =====================================================================
    report_gaby_b = audit.build_host_audit_report(
        session, restaurant_id=restaurant.id, host_employee_id=host_gaby.id,
        period_start=_at(2, 0), period_end=_at(2, 23, 59),
    )
    b_lines = [l for g in report_gaby_b.shift_groups for l in g.lines if l.order_id == order_b.id]
    result.check("B: Gaby's line exists for the two-Host order", len(b_lines) == 1)
    result.check("B: eligible_host_count is 2", b_lines and b_lines[0].eligible_host_count == 2)
    result.check("B: Gaby's own share is half the pool (200/2=100)", b_lines and b_lines[0].host_allocated_amount_minor == 100)
    result.check(
        "B: both eligible Hosts are named with their own shares",
        b_lines and {n for n, _ in b_lines[0].eligible_hosts} == {"Gaby", "Allie"}
        and all(amt == 100 for _, amt in b_lines[0].eligible_hosts),
    )

    # =====================================================================
    # C: no Host active — no Host allocation line for anybody.
    # =====================================================================
    c_lines_gaby = [l for g in report_gaby.shift_groups for l in g.lines if l.order_id == order_c.id]
    report_allie_c = audit.build_host_audit_report(
        session, restaurant_id=restaurant.id, host_employee_id=host_allie.id,
        period_start=_at(5, 0), period_end=_at(5, 23, 59),
    )
    c_lines_allie = [l for g in report_allie_c.shift_groups for l in g.lines if l.order_id == order_c.id]
    result.check("C: no-Host order produces no Host allocation line for Gaby", len(c_lines_gaby) == 0)
    result.check("C: no-Host order produces no Host allocation line for Allie", len(c_lines_allie) == 0)

    # =====================================================================
    # D: Host shift boundary — before excluded, during included, after excluded.
    # =====================================================================
    report_gaby_d = audit.build_host_audit_report(
        session, restaurant_id=restaurant.id, host_employee_id=host_gaby.id,
        period_start=_at(3, 0), period_end=_at(3, 23, 59),
    )
    d_order_ids = {l.order_id for g in report_gaby_d.shift_groups for l in g.lines}
    result.check("D: payment before shift start is excluded", order_d_before.id not in d_order_ids)
    result.check("D: payment during shift is included", order_d_during.id in d_order_ids)
    result.check("D: payment after shift end is excluded", order_d_after.id not in d_order_ids)

    # =====================================================================
    # E: multiple Host shifts same day — separate shift grouping, never merged.
    # =====================================================================
    report_gaby_e = audit.build_host_audit_report(
        session, restaurant_id=restaurant.id, host_employee_id=host_gaby.id,
        period_start=_at(4, 0), period_end=_at(4, 23, 59),
    )
    e_groups_with_lines = [g for g in report_gaby_e.shift_groups if g.lines]
    result.check("E: two separate same-day shifts remain two separate groups", len(e_groups_with_lines) == 2)
    result.check(
        "E: each shift group contains only its own order",
        {l.order_id for l in e_groups_with_lines[0].lines} == {order_e_shift1.id}
        and {l.order_id for l in e_groups_with_lines[1].lines} == {order_e_shift2.id}
        or {l.order_id for l in e_groups_with_lines[0].lines} == {order_e_shift2.id}
        and {l.order_id for l in e_groups_with_lines[1].lines} == {order_e_shift1.id},
    )

    # =====================================================================
    # F: reconciliation — line sum equals the independently-computed
    # per-run Host total (`build_employee_review`'s own aggregate).
    # =====================================================================
    report_gaby_full = audit.build_host_audit_report(
        session, restaurant_id=restaurant.id, host_employee_id=host_gaby.id,
        period_start=_at(-1, 0), period_end=_at(30, 0),
    )
    result.check("F: a period reconciliation was produced", len(report_gaby_full.reconciliations) > 0)
    result.check("F: reconciliation reports OK", report_gaby_full.period_reconciliation_ok)
    for rec in report_gaby_full.reconciliations:
        result.check(
            f"F: line sum ({rec.line_sum_minor}) matches engine-reported inbound ({rec.engine_reported_inbound_minor})",
            rec.line_sum_minor == rec.engine_reported_inbound_minor,
        )
    result.check(
        "F: report's own period total equals the sum of its shift-group totals",
        report_gaby_full.period_total_host_tips_minor == sum(g.total_host_tips_minor for g in report_gaby_full.shift_groups),
    )

    # =====================================================================
    # G: historical RuleVersion — the report shows the RuleVersion that
    # ACTUALLY generated the allocation, not a later, current Rule.
    # =====================================================================
    rule_v2 = rule_svc.create_new_version(
        session, rule_v1.id, source_role_id=role_server.id, recipient_role_id=role_host.id,
        calculation_base=m.CALC_BASE_VOLUNTARY_TIP, rate=Decimal("20.0000"), effective_from=_at(20),
        created_by="tester",
    )
    session.commit()
    session.expire_all()
    order_g_new = make_order_with_tip(created_at=_at(21, 18), tip_minor=2000)
    make_shift(host_gaby, _at(21, 17), _at(21, 22), "G")
    session.commit()
    session.expire_all()
    # Recalculates the EXACT same full period as the original run — the
    # engine's own supported "intentional recalculation" path (never a
    # second, overlapping-but-different period, which it refuses) —
    # superseding run 1; the NEW run's own allocations still use whichever
    # RuleVersion was actually effective at each Order's own Settlement
    # Time (v1 for day 1, v2 for day 21+), proving the audit report reads
    # history correctly rather than "today's current Rule."
    calc2 = engine.calculate_tips(
        session, restaurant_id=restaurant.id, period_start=_at(-1, 0), period_end=_at(30, 0),
    )
    session.commit()
    session.expire_all()
    result.check("G: the recalculation completed", calc2.blocked_reason is None)

    report_gaby_old_period = audit.build_host_audit_report(
        session, restaurant_id=restaurant.id, host_employee_id=host_gaby.id,
        period_start=_at(1, 0), period_end=_at(1, 23, 59),
    )
    old_lines = [l for g in report_gaby_old_period.shift_groups for l in g.lines if l.order_id == order_a.id]
    result.check(
        "G: the OLD period's allocation still shows RuleVersion 1 (10%), never the current RuleVersion 2",
        old_lines and old_lines[0].rule_version_id == rule_v1.versions[0].id,
    )
    report_gaby_new_period = audit.build_host_audit_report(
        session, restaurant_id=restaurant.id, host_employee_id=host_gaby.id,
        period_start=_at(21, 0), period_end=_at(21, 23, 59),
    )
    new_lines = [l for g in report_gaby_new_period.shift_groups for l in g.lines if l.order_id == order_g_new.id]
    result.check(
        "G: the NEW period's allocation shows RuleVersion 2 (20%), reflecting the Rule that was actually effective then",
        new_lines and new_lines[0].rule_version_id == rule_v2.id and new_lines[0].host_allocated_amount_minor == 400,
    )

    # =====================================================================
    # H: AUDIT vs AUTOMATIC — calculation result identical in both modes;
    # only the review-workflow setting differs. Rebuilt by recalculating
    # the same window on demand after Scenario G.
    # =====================================================================
    report_gaby_full = audit.build_host_audit_report(
        session, restaurant_id=restaurant.id, host_employee_id=host_gaby.id,
        period_start=_at(-1, 0), period_end=_at(30, 0),
    )
    result.check(
        "H: default review mode (never configured) is AUDIT",
        review_svc.get_review_mode(session, restaurant_id=restaurant.id) == m.TIPS_REVIEW_MODE_AUDIT,
    )
    totals_before = {l.order_id: l.host_allocated_amount_minor for g in report_gaby_full.shift_groups for l in g.lines}
    review_svc.set_review_mode(session, restaurant_id=restaurant.id, review_mode=m.TIPS_REVIEW_MODE_AUTOMATIC)
    session.flush()
    result.check(
        "H: review mode is now AUTOMATIC",
        review_svc.get_review_mode(session, restaurant_id=restaurant.id) == m.TIPS_REVIEW_MODE_AUTOMATIC,
    )
    report_gaby_full_automatic = audit.build_host_audit_report(
        session, restaurant_id=restaurant.id, host_employee_id=host_gaby.id,
        period_start=_at(-1, 0), period_end=_at(30, 0),
    )
    totals_after = {
        l.order_id: l.host_allocated_amount_minor for g in report_gaby_full_automatic.shift_groups for l in g.lines
    }
    result.check("H: switching review mode changes nothing about the calculated allocations", totals_before == totals_after)
    review_svc.set_review_mode(session, restaurant_id=restaurant.id, review_mode=m.TIPS_REVIEW_MODE_AUDIT)
    session.flush()

    # =====================================================================
    # I: CSV export — values match displayed audit data.
    # =====================================================================
    csv_rows = audit.report_to_csv_rows(report_gaby_full)
    result.check("I: CSV has one row per displayed line (plus any unresolved items)", len(csv_rows) == sum(len(g.lines) for g in report_gaby_full.shift_groups) + len(report_gaby_full.unresolved_items))
    csv_row_a = next((r for r in csv_rows if r["clover_order_id"] == order_a.source_order_id), None)
    result.check("I: CSV row exists for order A", csv_row_a is not None)
    result.check(
        "I: CSV host_allocated_amount matches the displayed line",
        csv_row_a is not None and csv_row_a["host_allocated_amount"] == "2.00",
    )
    result.check(
        "I: CSV original_tip_amount matches the displayed line",
        csv_row_a is not None and csv_row_a["original_tip_amount"] == "20.00",
    )
    result.check(
        "I: CSV has all mandated fieldnames",
        set(audit.CSV_FIELDNAMES) <= set(csv_row_a.keys()) if csv_row_a else False,
    )
