"""Stateless Tips calculation validation (TIPS_STATELESS_CALCULATION_001).

Proves the canonical principle directly: Tips calculates on demand for ANY
requested interval, persists nothing, and can therefore be recalculated
freely — the same period repeatedly, or periods that overlap, contain or
sit inside one another.

Mirrors `tips_distribution_engine_validation.py`'s fixture pattern: one
synthetic (never-real) Restaurant/Location/Roles/Employees/Shifts/Orders/
Payments inside a disposable database, driven through the REAL
`distribution_engine.calculate_tips` and the REAL
`host_audit_report.build_host_audit_report`, then rolled back.

Covers task items A-L.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from dataclasses import dataclass, field

from sqlalchemy import inspect as sa_inspect, select
from sqlalchemy.orm import Session

from . import models as m
from .tips import distribution_engine as engine
from .tips import distribution_rule_service as rule_svc
from .tips import host_audit_report as audit
from .tips import review_mode_service as review_svc


@dataclass
class ValidationResult:
    success: bool = True
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)

    def check(self, description: str, condition: bool) -> None:
        if condition:
            self.checks_passed.append(description)
        else:
            self.checks_failed.append(description)
            self.success = False

UTC = timezone.utc
T0 = datetime(2026, 5, 1, tzinfo=UTC)


def _at(day: float, hour: int = 12) -> datetime:
    return T0 + timedelta(days=day, hours=hour)


def run_validation(session_factory) -> ValidationResult:
    result = ValidationResult()
    with session_factory() as session:
        try:
            _build_fixture_and_assert(session, result)
        finally:
            session.rollback()
    return result


def _build_fixture_and_assert(session: Session, result: ValidationResult) -> None:
    source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
    session.add(source_system)
    session.flush()

    merchant = m.Merchant(
        source_system_id=source_system.id, source_merchant_id="STATELESS1", name="Stateless Test Merchant")
    session.add(merchant)
    session.flush()

    location = m.Location(
        merchant_id=merchant.id, source_system_id=source_system.id, source_location_id="STATELESS1",
        name="Stateless Test Location", currency="USD", timezone="America/New_York",
        operating_day_cutoff_time=time(2, 0),
    )
    session.add(location)
    session.flush()

    restaurant = m.Restaurant(name="Stateless Test Restaurant", default_currency="USD")
    session.add(restaurant)
    session.flush()
    session.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))

    area = m.OperationalArea(restaurant_id=restaurant.id, name="Ops", code="ROOT", active=True)
    session.add(area)
    role_host = m.RestaurantRole(restaurant_id=restaurant.id, name="Host", code="HOST", active=True)
    session.add(role_host)
    session.flush()

    def make_employee(name: str) -> m.Employee:
        employee = m.Employee(
            location_id=location.id, source_system_id=source_system.id,
            source_employee_id=f"EMP-{name}", display_name=name,
        )
        session.add(employee)
        session.flush()
        return employee

    owner = make_employee("Service Owner")
    host_a = make_employee("Host A")
    host_b = make_employee("Host B")

    for host in (host_a, host_b):
        session.add(
            m.EmployeeAssignment(
                employee_id=host.id, restaurant_id=restaurant.id, operational_area_id=area.id,
                restaurant_role_id=role_host.id, location_id=location.id,
                valid_from=_at(-10, 0), valid_to=None, assignment_source="MANUAL",
            )
        )
        # One long Shift spanning the whole fixture window, so Host
        # eligibility never varies with the chosen period.
        session.add(
            m.Shift(
                employee_id=host.id, source_system_id=source_system.id,
                source_shift_id=f"SHIFT-{host.id}", location_id=location.id,
                clock_in=_at(0, 0), clock_out=_at(10, 0),
            )
        )
    session.flush()

    # ORDER_SERVICE_OWNER rule: 10% of voluntary tips to Hosts on shift.
    rule = rule_svc.create_rule(
        session, restaurant_id=restaurant.id, recipient_role_id=role_host.id,
        calculation_base=m.CALC_BASE_VOLUNTARY_TIP, rate=Decimal("10.0000"),
        effective_from=_at(-5, 0), source_semantics=m.TIP_SOURCE_SEMANTICS_ORDER_SERVICE_OWNER,
        source_role_id=None,
    )
    session.flush()
    rule_v1_id = rule.versions[0].id

    def make_order_with_tip(created_at: datetime, tip_minor: int) -> m.Order:
        order = m.Order(
            location_id=location.id, source_system_id=source_system.id,
            source_order_id=f"ORD-{created_at.isoformat()}", employee_id=owner.id,
            source_employee_id=owner.source_employee_id, created_at=created_at,
            state="locked", payment_state="PAID", currency="USD", total=10000,
        )
        session.add(order)
        session.flush()
        payment = m.Payment(
            order_id=order.id, source_system_id=source_system.id,
            source_payment_id=f"PAY-{order.id}", employee_id=owner.id,
            source_employee_id=owner.source_employee_id, created_at=created_at,
            amount=10000, result="SUCCESS", currency="USD",
        )
        session.add(payment)
        session.flush()
        session.add(m.PaymentTip(payment_id=payment.id, amount=tip_minor, source_present=True))
        session.flush()
        return order

    # Orders spread across days 1, 2 and 3 at varied times of day.
    order_d1 = make_order_with_tip(_at(1, 9), 1000)
    order_d2 = make_order_with_tip(_at(2, 15), 2000)
    order_d3 = make_order_with_tip(_at(3, 21), 3000)
    session.commit()
    session.expire_all()

    full_start, full_end = _at(0, 0), _at(5, 0)

    # === A: the same period calculates repeatedly ============================
    calc_1 = engine.calculate_tips(session, restaurant_id=restaurant.id, period_start=full_start, period_end=full_end)
    calc_2 = engine.calculate_tips(session, restaurant_id=restaurant.id, period_start=full_start, period_end=full_end)
    calc_3 = engine.calculate_tips(session, restaurant_id=restaurant.id, period_start=full_start, period_end=full_end)
    result.check(
        "A: the SAME period can be calculated repeatedly, never refused",
        all(c.blocked_reason is None for c in (calc_1, calc_2, calc_3)),
    )
    result.check(
        "A: repeated calculations of the same period are identical (deterministic from source facts)",
        calc_1.voluntary_total_minor == calc_2.voluntary_total_minor == calc_3.voluntary_total_minor
        and calc_1.distributed_total_minor == calc_2.distributed_total_minor == calc_3.distributed_total_minor
        and len(calc_1.lines) == len(calc_2.lines) == len(calc_3.lines),
    )
    result.check(
        "A: the full window captured all three Orders' voluntary tips ($60.00)",
        calc_1.voluntary_total_minor == 6000,
    )

    # === B: overlapping periods calculate freely =============================
    overlap_left = engine.calculate_tips(
        session, restaurant_id=restaurant.id, period_start=_at(0, 0), period_end=_at(2, 12))
    overlap_right = engine.calculate_tips(
        session, restaurant_id=restaurant.id, period_start=_at(2, 0), period_end=_at(5, 0))
    result.check(
        "B: two PARTIALLY OVERLAPPING periods both calculate, neither refused nor superseded",
        overlap_left.blocked_reason is None and overlap_right.blocked_reason is None,
    )
    result.check(
        "B: each overlapping window sees exactly the Orders that genuinely fall in it "
        "(left covers day-1 only; right covers days 2-3; the windows themselves overlap on day 2)",
        overlap_left.voluntary_total_minor == 1000 and overlap_right.voluntary_total_minor == 5000,
    )
    result.check(
        "B: the two windows really do overlap in time, yet neither affected the other",
        overlap_right.period_start < overlap_left.period_end,
    )

    # === C: subset period ====================================================
    subset = engine.calculate_tips(
        session, restaurant_id=restaurant.id, period_start=_at(2, 0), period_end=_at(2, 23))
    result.check("C: a SUBSET period calculates freely", subset.blocked_reason is None)
    result.check("C: the subset sees only its own Order ($20.00)", subset.voluntary_total_minor == 2000)

    # === D: superset period ==================================================
    superset = engine.calculate_tips(
        session, restaurant_id=restaurant.id, period_start=_at(-20, 0), period_end=_at(40, 0))
    result.check("D: a SUPERSET period calculates freely", superset.blocked_reason is None)
    result.check(
        "D: the superset still totals all three Orders and no more",
        superset.voluntary_total_minor == 6000,
    )

    # === E: arbitrary datetime boundaries ====================================
    arbitrary = engine.calculate_tips(
        session, restaurant_id=restaurant.id,
        period_start=_at(1, 8) + timedelta(minutes=37),
        period_end=_at(2, 16) + timedelta(minutes=14, seconds=30),
    )
    result.check("E: arbitrary minute/second boundaries calculate normally", arbitrary.blocked_reason is None)
    result.check(
        "E: an arbitrary window includes exactly the Orders inside it (day1 09:00 + day2 15:00)",
        arbitrary.voluntary_total_minor == 3000,
    )
    just_misses = engine.calculate_tips(
        session, restaurant_id=restaurant.id,
        period_start=_at(1, 9) + timedelta(seconds=1), period_end=_at(1, 23),
    )
    result.check(
        "E: the period start is INCLUSIVE and the end EXCLUSIVE — a one-second shift excludes the Order",
        just_misses.voluntary_total_minor == 0,
    )

    # === F: RuleVersion effective dating across requested periods ============
    rule_svc.create_new_version(
        session, rule.id, recipient_role_id=role_host.id,
        calculation_base=m.CALC_BASE_VOLUNTARY_TIP, rate=Decimal("20.0000"),
        effective_from=_at(3, 0), source_semantics=m.TIP_SOURCE_SEMANTICS_ORDER_SERVICE_OWNER,
        source_role_id=None,
    )
    session.commit()
    session.expire_all()

    before_change = engine.calculate_tips(
        session, restaurant_id=restaurant.id, period_start=_at(1, 0), period_end=_at(1, 23))
    after_change = engine.calculate_tips(
        session, restaurant_id=restaurant.id, period_start=_at(3, 0), period_end=_at(3, 23))
    result.check(
        "F: an Order before the new Version still uses v1 (10% of $10.00 = $1.00)",
        before_change.distributed_total_minor == 100
        and all(line.rule_version_id == rule_v1_id for line in before_change.recipient_lines),
    )
    result.check(
        "F: an Order after the new Version uses v2 (20% of $30.00 = $6.00)",
        after_change.distributed_total_minor == 600
        and all(line.rule_version_id != rule_v1_id for line in after_change.recipient_lines),
    )
    result.check(
        "F: effective dating is resolved per Order Settlement Time, so a window spanning the change "
        "applies BOTH Versions in the same calculation",
        len(engine.calculate_tips(
            session, restaurant_id=restaurant.id, period_start=full_start, period_end=full_end,
        ).rule_version_ids) == 2,
    )

    # === G/H: no persisted result records ====================================
    runs = session.scalars(select(m.TipDistributionCalculationRun)).all()
    result.check("G: calculating Tips creates NO TipDistributionCalculationRun", len(runs) == 0)
    result.check(
        "H: there is no persisted allocation table left in the schema at all",
        "tip_distribution_allocations" not in sa_inspect(session.get_bind()).get_table_names(),
    )
    result.check(
        "H: the calculation-run table has no supersession column any more",
        "superseded_by_calculation_run_id" not in {
            c["name"] for c in sa_inspect(session.get_bind()).get_columns("tip_distribution_calculation_runs")
        },
    )

    # === I: Host Audit matches the calculation, with no persisted rows =======
    current = engine.calculate_tips(
        session, restaurant_id=restaurant.id, period_start=full_start, period_end=full_end)
    audit_total = 0
    for host in (host_a, host_b):
        report = audit.build_host_audit_report(
            session, restaurant_id=restaurant.id, host_employee_id=host.id,
            period_start=full_start, period_end=full_end,
        )
        audit_total += report.period_total_host_tips_minor
        result.check(
            f"I: Host Audit for {host.display_name} reconciles against the engine's own aggregate",
            report.period_reconciliation_ok,
        )
    result.check(
        "I: the sum of both Hosts' audit totals equals the calculation's distributed total",
        audit_total == current.distributed_total_minor,
    )

    passed_in = audit.build_host_audit_report(
        session, restaurant_id=restaurant.id, host_employee_id=host_a.id,
        period_start=full_start, period_end=full_end, result=current,
    )
    recalculated = audit.build_host_audit_report(
        session, restaurant_id=restaurant.id, host_employee_id=host_a.id,
        period_start=full_start, period_end=full_end,
    )
    result.check(
        "I: passing an already-computed result to the audit gives the same answer as letting it "
        "recalculate — the audit never depends on stored allocations",
        passed_in.period_total_host_tips_minor == recalculated.period_total_host_tips_minor,
    )

    # === J: CSV mirrors the on-demand audit ==================================
    csv_rows = audit.report_to_csv_rows(recalculated)
    displayed_lines = [line for group in recalculated.shift_groups for line in group.lines]
    result.check(
        "J: CSV export has exactly one row per displayed audit line (plus any unresolved items)",
        len(csv_rows) == len(displayed_lines) + len(recalculated.unresolved_items),
    )
    csv_total = sum(
        round(float(row["host_allocated_amount"]) * 100)
        for row in csv_rows if row["host_allocated_amount"]
    )
    result.check(
        "J: the CSV's allocated amounts sum to the same freshly-calculated Host total",
        csv_total == recalculated.period_total_host_tips_minor,
    )
    result.check(
        "J: the CSV no longer carries a calculation-run column (no run exists)",
        "calculation_run_id" not in audit.CSV_FIELDNAMES,
    )

    # === K: reconciliation invariant =========================================
    result.check(
        "K: Service Owner retained + Host allocations + unresolved == voluntary Tip total",
        current.source_retained_total_minor + current.distributed_total_minor
        + current.unresolved_total_minor == current.voluntary_total_minor,
    )
    result.check(
        "K: the reconciliation difference is exactly zero",
        current.reconciles and current.reconciliation_difference_minor == 0,
    )
    result.check("K: this fixture has no unresolved items", current.unresolved_total_minor == 0)

    # === L: AUDIT vs AUTOMATIC are numerically identical =====================
    review_svc.set_review_mode(session, restaurant_id=restaurant.id, review_mode=m.TIPS_REVIEW_MODE_AUDIT)
    session.flush()
    in_audit = engine.calculate_tips(
        session, restaurant_id=restaurant.id, period_start=full_start, period_end=full_end)
    review_svc.set_review_mode(session, restaurant_id=restaurant.id, review_mode=m.TIPS_REVIEW_MODE_AUTOMATIC)
    session.flush()
    in_automatic = engine.calculate_tips(
        session, restaurant_id=restaurant.id, period_start=full_start, period_end=full_end)
    result.check(
        "L: AUDIT and AUTOMATIC produce numerically identical results (workflow emphasis only)",
        in_audit.voluntary_total_minor == in_automatic.voluntary_total_minor
        and in_audit.distributed_total_minor == in_automatic.distributed_total_minor
        and in_audit.source_retained_total_minor == in_automatic.source_retained_total_minor
        and len(in_audit.lines) == len(in_automatic.lines),
    )
    result.check(
        "L: neither review mode persisted anything",
        len(session.scalars(select(m.TipDistributionCalculationRun)).all()) == 0,
    )
