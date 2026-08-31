"""Sales module synthetic regression suite (TASK_REPOSITORY_STABILIZATION_001).

Sales (`01 Domains/Restaurant/Sales/Restaurant Sales Model.md`) previously had
no dedicated validation suite comparable to Tips, Payroll, Organization and
Purchasing, despite being load-bearing evidence for the production Tips
`OrderEmployeeServiceAttributionResolver` (`tips/resolvers.py`). This module
closes that gap for the CURRENTLY IMPLEMENTED Sales invariants only — it does
not redesign Sales, and it does not implement any of the documented-but-not-
yet-persisted gaps (`Order.business_date`, `ORDER_ITEM_VOID`,
`ORDER_CANCELLATION` — see `07 Tasks/Reports/TASK_SALES_002_REPORT.md` §L).
Those gaps are asserted as gaps (see "GAP:"-prefixed checks below), not
fabricated as implemented.

Mirrors `organization_validation.py`'s pattern exactly: builds a synthetic
(never-real) fixture inside one transaction, asserts the required behaviors,
and always rolls back — no synthetic row is ever left in the target
database. Constraint-violation scenarios use a nested SAVEPOINT
(`session.begin_nested()`) so a single expected `IntegrityError` does not
abort the whole validation transaction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .tips.resolvers import AMBIGUOUS, RESOLVED, UNRESOLVED, OrderEmployeeServiceAttributionResolver

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


def _dt(days_ago: float) -> datetime:
    base = datetime.now(UTC) - timedelta(days=days_ago)
    return base.replace(microsecond=0, tzinfo=None)


def _expect_integrity_error(session: Session, action) -> bool:
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

    merchant = m.Merchant(source_system_id=source_system.id, source_merchant_id="MERCH1", name="Test Merchant")
    session.add(merchant)
    session.flush()

    def make_location(name: str) -> m.Location:
        loc = m.Location(
            merchant_id=merchant.id, source_system_id=source_system.id,
            source_location_id=name.upper().replace(" ", "_"), name=name, currency="USD",
        )
        session.add(loc)
        session.flush()
        return loc

    location_wp = make_location("Winter Park")
    location_md = make_location("Mount Dora")

    order_type_wp = m.OrderType(
        location_id=location_wp.id, source_system_id=source_system.id, source_order_type_id="OT-WP", name="Table",
    )
    order_type_md = m.OrderType(
        location_id=location_md.id, source_system_id=source_system.id, source_order_type_id="OT-MD", name="Table",
    )
    session.add_all([order_type_wp, order_type_md])
    session.flush()

    def make_employee(source_id: str, name: str, location: m.Location) -> m.Employee:
        emp = m.Employee(
            location_id=location.id, source_system_id=source_system.id, source_employee_id=source_id,
            display_name=name, system_role="EMPLOYEE",
        )
        session.add(emp)
        session.flush()
        return emp

    emp_wp_a = make_employee("E-WP-A", "Server A (WP)", location_wp)
    emp_wp_b = make_employee("E-WP-B", "Server B (WP)", location_wp)
    emp_md_a = make_employee("E-MD-A", "Server A (MD)", location_md)

    def make_order(
        *, location: m.Location, order_type: m.OrderType, source_order_id: str,
        employee: m.Employee | None, total: int, created_at: datetime,
    ) -> m.Order:
        order = m.Order(
            location_id=location.id, source_system_id=source_system.id, source_order_id=source_order_id,
            employee_id=employee.id if employee else None, order_type_id=order_type.id,
            created_at=created_at, payment_state="PAID", currency="USD", total=total,
        )
        session.add(order)
        session.flush()
        return order

    def make_payment(
        *, order: m.Order, source_payment_id: str, employee: m.Employee | None,
        amount: int, created_at: datetime, result_value: str = "SUCCESS",
    ) -> m.Payment:
        payment = m.Payment(
            order_id=order.id, source_system_id=source_system.id, source_payment_id=source_payment_id,
            employee_id=employee.id if employee else None, created_at=created_at, amount=amount,
            result=result_value, currency="USD",
        )
        session.add(payment)
        session.flush()
        return payment

    # =====================================================================
    # 1/18/19. Restaurant / Location scoping — WP and MD evidence never mix
    # =====================================================================
    order_wp = make_order(
        location=location_wp, order_type=order_type_wp, source_order_id="ORD-WP-1",
        employee=emp_wp_a, total=5000, created_at=_dt(5),
    )
    order_md = make_order(
        location=location_md, order_type=order_type_md, source_order_id="ORD-MD-1",
        employee=emp_md_a, total=4200, created_at=_dt(5),
    )
    wp_orders = session.scalars(select(m.Order).where(m.Order.location_id == location_wp.id)).all()
    md_orders = session.scalars(select(m.Order).where(m.Order.location_id == location_md.id)).all()
    result.check(
        "1/18/19: Orders are correctly scoped to their own Location — a Winter Park Order never "
        "appears under a Mount Dora Location query and vice versa",
        {o.id for o in wp_orders} == {order_wp.id}
        and {o.id for o in md_orders} == {order_md.id},
    )
    result.check(
        "19: Employee attribution does not cross Location — the Winter Park Order's employee_id "
        "belongs to a Winter Park Employee, the Mount Dora Order's to a Mount Dora Employee",
        order_wp.employee_id == emp_wp_a.id and emp_wp_a.location_id == location_wp.id
        and order_md.employee_id == emp_md_a.id and emp_md_a.location_id == location_md.id,
    )

    # =====================================================================
    # 2/21/22. Order identity, persistence, idempotency, stable source IDs
    # =====================================================================
    def _insert_duplicate_order() -> None:
        session.add(
            m.Order(
                location_id=location_wp.id, source_system_id=source_system.id, source_order_id="ORD-WP-1",
                created_at=_dt(5), currency="USD",
            )
        )

    duplicate_order_rejected = _expect_integrity_error(session, _insert_duplicate_order)
    session.expire(order_wp)
    reloaded_order = session.get(m.Order, order_wp.id)
    result.check(
        "2/21: Order identity is idempotent — a second insert with the same (source_system_id, "
        "source_order_id) pair is rejected by the schema's uniqueness rule, so re-ingesting the "
        "same source Order can never silently create a duplicate",
        duplicate_order_rejected,
    )
    result.check(
        "22: Order source_order_id remains stable across a reload from the database (never "
        "renumbered or regenerated on read)",
        reloaded_order.source_order_id == "ORD-WP-1",
    )

    # =====================================================================
    # 3/4/5. Order -> Employee and Payment -> Employee attribution, and
    # their agreement
    # =====================================================================
    payment_agree = make_payment(
        order=order_wp, source_payment_id="PAY-WP-1", employee=emp_wp_a, amount=5000, created_at=_dt(5),
    )
    result.check(
        "3/4/5: Order.employee_id and Payment.employee_id are independently attributable and, in "
        "this scenario, agree — the baseline agreement case the resolver's RESOLVED path depends on",
        order_wp.employee_id == emp_wp_a.id
        and payment_agree.employee_id == emp_wp_a.id
        and order_wp.employee_id == payment_agree.employee_id,
    )

    # =====================================================================
    # 7/9. PaymentTip linked to the correct Payment; with and without Tip
    # =====================================================================
    order_tip_test = make_order(
        location=location_wp, order_type=order_type_wp, source_order_id="ORD-WP-TIP",
        employee=emp_wp_a, total=6000, created_at=_dt(4),
    )
    payment_with_tip = make_payment(
        order=order_tip_test, source_payment_id="PAY-WP-TIP-1", employee=emp_wp_a, amount=5000, created_at=_dt(4),
    )
    payment_without_tip = make_payment(
        order=order_tip_test, source_payment_id="PAY-WP-TIP-2", employee=emp_wp_a, amount=1000, created_at=_dt(4),
    )
    session.add(m.PaymentTip(payment_id=payment_with_tip.id, amount=800, source_present=True))
    session.flush()
    reloaded_with_tip = session.get(m.Payment, payment_with_tip.id)
    reloaded_without_tip = session.get(m.Payment, payment_without_tip.id)
    result.check(
        "7: PaymentTip is linked to exactly the Payment it belongs to — the Payment carrying a Tip "
        "resolves its own Tip row, never another Payment's",
        reloaded_with_tip.tip is not None and reloaded_with_tip.tip.amount == 800,
    )
    result.check(
        "9: a Payment with no PaymentTip row at all (source never reported a tip field) is a "
        "distinct, valid state from a Payment with an explicit source_present=True Tip",
        reloaded_without_tip.tip is None and reloaded_with_tip.tip.source_present is True,
    )

    # =====================================================================
    # 8. Multiple Payments / split payment on one Order
    # =====================================================================
    result.check(
        "8: an Order may have multiple Payments (split payment) whose amounts are independently "
        "attributable and sum to the Order total",
        payment_with_tip.amount + payment_without_tip.amount == order_tip_test.total,
    )

    # =====================================================================
    # 10. Failed payment must not silently become successful evidence.
    # The canonical failure value is "FAIL" (matching real ingestion code —
    # rfone_data_store/ingestion/clover/reconciliation.py,
    # schema_validation.py, tips_validation.py — NOT "FAILED", which this
    # file incorrectly invented in TASK_REPOSITORY_STABILIZATION_001 and
    # which TASK_RESTAURANT_STRUCTURE_001 corrects here).
    # =====================================================================
    order_failed_test = make_order(
        location=location_wp, order_type=order_type_wp, source_order_id="ORD-WP-FAILED",
        employee=emp_wp_a, total=3000, created_at=_dt(3),
    )
    payment_failed = make_payment(
        order=order_failed_test, source_payment_id="PAY-WP-FAILED-1", employee=emp_wp_b,
        amount=3000, created_at=_dt(3), result_value="FAIL",
    )
    payment_success = make_payment(
        order=order_failed_test, source_payment_id="PAY-WP-FAILED-2", employee=emp_wp_a,
        amount=3000, created_at=_dt(3), result_value="SUCCESS",
    )
    result.check(
        "10: a FAIL Payment is preserved as its own first-class, queryable fact (never silently "
        "dropped or merged into the successful Payment) and remains distinguishable via `result` — "
        "Payment model docstring: 'One Order may have many Payments, including FAILED ones'",
        payment_failed.result == "FAIL"
        and payment_success.result == "SUCCESS"
        and payment_failed.id != payment_success.id
        and {p.id for p in order_failed_test.payments} == {payment_failed.id, payment_success.id},
    )

    # =====================================================================
    # 11. Refund remains distinct from Tip
    # =====================================================================
    order_refund_test = make_order(
        location=location_wp, order_type=order_type_wp, source_order_id="ORD-WP-REFUND",
        employee=emp_wp_a, total=4000, created_at=_dt(2),
    )
    payment_refund_test = make_payment(
        order=order_refund_test, source_payment_id="PAY-WP-REFUND-1", employee=emp_wp_a,
        amount=4000, created_at=_dt(2),
    )
    session.add(m.PaymentTip(payment_id=payment_refund_test.id, amount=600, source_present=True))
    refund = m.Refund(
        source_system_id=source_system.id, source_refund_id="REF-1", order_id=order_refund_test.id,
        payment_id=payment_refund_test.id, created_at=_dt(1), amount=1500,
    )
    session.add(refund)
    session.flush()
    reloaded_payment_refund = session.get(m.Payment, payment_refund_test.id)
    result.check(
        "11: Refund and Tip are independent, coexisting facts on the same Payment — the Refund "
        "amount never overwrites, reduces, or is conflated with the PaymentTip amount",
        reloaded_payment_refund.tip.amount == 600
        and len(reloaded_payment_refund.refunds) == 1
        and reloaded_payment_refund.refunds[0].amount == 1500,
    )

    # =====================================================================
    # 12/13/14. Void / Cancellation vs Refund vs Cancellation — DOCUMENTED
    # GAP, not fabricated. Restaurant Sales Model.md §14b defines
    # ORDER_ITEM_VOID and ORDER_CANCELLATION as distinct concepts from
    # Refund, but neither is persisted in models.py yet (TASK_SALES_002
    # §L: "Void ingestion" is an open implementation gap). The only thing
    # this suite can honestly assert today is that the gap is real (no such
    # columns/tables exist) and that Refund itself does not silently double
    # as a void mechanism (Refund.voided describes the Refund's OWN
    # lifecycle, per Restaurant Sales Model.md §14a, not a generic
    # Order/Item void — Refund model has no order-cancellation semantics).
    # =====================================================================
    result.check(
        "12/13/14: GAP confirmed, not fabricated as implemented — no ORDER_ITEM_VOID or "
        "ORDER_CANCELLATION persistence exists in models.py yet (Restaurant Sales Model.md §14b; "
        "TASK_SALES_002_REPORT.md §L, 'Void ingestion'). Refund.voided describes only the Refund's "
        "own later reversal, never a generic Order/Item void — so Refund is not silently standing "
        "in for the missing Void/Cancellation concept",
        not hasattr(m, "OrderItemVoid")
        and not hasattr(m, "OrderCancellation")
        and hasattr(m.Refund, "voided"),
    )

    # =====================================================================
    # 15/16. Order Item quantity semantics, including decimal quantity
    # =====================================================================
    order_qty_test = make_order(
        location=location_wp, order_type=order_type_wp, source_order_id="ORD-WP-QTY",
        employee=emp_wp_a, total=1000, created_at=_dt(6),
    )
    item_decimal_qty = m.OrderItem(
        order_id=order_qty_test.id, source_system_id=source_system.id, source_line_item_id="LI-1",
        source_name="Half portion", quantity=Decimal("0.5"),
    )
    item_missing_qty = m.OrderItem(
        order_id=order_qty_test.id, source_system_id=source_system.id, source_line_item_id="LI-2",
        source_name="Unknown quantity item", quantity=None,
    )
    session.add_all([item_decimal_qty, item_missing_qty])
    session.flush()
    session.expire(item_decimal_qty)
    session.expire(item_missing_qty)
    reloaded_decimal_item = session.get(m.OrderItem, item_decimal_qty.id)
    reloaded_missing_item = session.get(m.OrderItem, item_missing_qty.id)
    result.check(
        "15/16: Order Item quantity is a provider-independent decimal (Numeric(12,4)) and a "
        "fractional quantity (0.5) round-trips exactly through the database, never rounded to an "
        "integer unit count",
        reloaded_decimal_item.quantity == Decimal("0.5"),
    )
    result.check(
        "15: a missing source quantity is preserved as NULL/unknown, never silently defaulted to 1 "
        "(Restaurant Sales Model.md §19-20, 'never silently defaulted to a provider convention')",
        reloaded_missing_item.quantity is None,
    )

    # =====================================================================
    # 17. Business Date semantics — DOCUMENTED GAP, not fabricated
    # =====================================================================
    result.check(
        "17: GAP confirmed, not fabricated as implemented — Order.business_date is conceptually "
        "defined (Restaurant Sales Model.md §6a) but not yet a persisted column (TASK_SALES_002 "
        "§L). If a future task adds this column, this check will start failing and must be updated "
        "to assert the real persisted business_date semantics instead of the gap's absence",
        not hasattr(m.Order, "business_date"),
    )

    # =====================================================================
    # 20. Historical persistence / process restart (expire + reload)
    # =====================================================================
    session.flush()
    session.expire_all()
    reloaded_after_restart = session.get(m.Order, order_wp.id)
    reloaded_payment_after_restart = session.get(m.Payment, payment_agree.id)
    result.check(
        "20: Order and Payment facts survive a full session expire (simulating a process "
        "restart/fresh read) with all values unchanged",
        reloaded_after_restart.source_order_id == "ORD-WP-1"
        and reloaded_after_restart.total == 5000
        and reloaded_payment_after_restart.amount == 5000
        and reloaded_payment_after_restart.employee_id == emp_wp_a.id,
    )

    # =====================================================================
    # 23. Monetary values remain in canonical minor-unit (cents) form
    # =====================================================================
    result.check(
        "23: monetary values (Order.total, Payment.amount) persist as exact integer minor units — "
        "no float representation, no fractional-cent drift",
        isinstance(order_wp.total, int) and order_wp.total == 5000
        and isinstance(payment_agree.amount, int) and payment_agree.amount == 5000,
    )

    # =====================================================================
    # 24. Service Charge / OrderFee remains distinct from Tip
    # =====================================================================
    order_fee_test = make_order(
        location=location_wp, order_type=order_type_wp, source_order_id="ORD-WP-FEE",
        employee=emp_wp_a, total=11000, created_at=_dt(7),
    )
    payment_fee_test = make_payment(
        order=order_fee_test, source_payment_id="PAY-WP-FEE-1", employee=emp_wp_a, amount=11000, created_at=_dt(7),
    )
    session.add(
        m.OrderFee(
            order_id=order_fee_test.id, source_system_id=source_system.id, fee_type="SERVICE_CHARGE",
            name_raw="Service Charge", amount=1000,
        )
    )
    session.add(m.PaymentTip(payment_id=payment_fee_test.id, amount=500, source_present=True))
    session.flush()
    fee_rows = session.scalars(select(m.OrderFee).where(m.OrderFee.order_id == order_fee_test.id)).all()
    result.check(
        "24: an OrderFee (e.g. a synthetic Service Charge line) and a PaymentTip are independent "
        "facts with independent amounts — the fee amount is never summed into, or confused with, "
        "the Tip amount",
        len(fee_rows) == 1 and fee_rows[0].amount == 1000
        and payment_fee_test.tip.amount == 500,
    )

    # =====================================================================
    # 25. Table Service relationships, where currently implemented
    # =====================================================================
    table = m.PhysicalTable(location_id=location_wp.id, table_number="12")
    session.add(table)
    session.flush()
    table_service = m.TableService(location_id=location_wp.id, opened_at=_dt(8), declared_guest_count=2)
    session.add(table_service)
    session.flush()
    session.add(m.TableServicePhysicalTable(table_service_id=table_service.id, physical_table_id=table.id))
    session.flush()
    order_with_service = make_order(
        location=location_wp, order_type=order_type_wp, source_order_id="ORD-WP-TS",
        employee=emp_wp_a, total=2000, created_at=_dt(8),
    )
    order_with_service.table_service_id = table_service.id
    session.flush()
    order_without_service = make_order(
        location=location_wp, order_type=order_type_wp, source_order_id="ORD-WP-NOTS",
        employee=emp_wp_a, total=1500, created_at=_dt(8),
    )
    result.check(
        "25: an Order may optionally link to a Table Service (table_service_id), and an Order with "
        "no Table Service reconstruction available (table_service_id = NULL) remains equally valid "
        "— Table Service reconstruction is not mandatory (Restaurant Sales Model.md §5)",
        order_with_service.table_service_id == table_service.id
        and order_without_service.table_service_id is None,
    )

    # =====================================================================
    # 6/26. Missing/ambiguous attribution produces explicit unresolved
    # status, never a guessed identity — direct check via Refund/Order with
    # no employee_id at all
    # =====================================================================
    order_no_employee = make_order(
        location=location_wp, order_type=order_type_wp, source_order_id="ORD-WP-NOEMP",
        employee=None, total=800, created_at=_dt(9),
    )
    result.check(
        "26: an Order with no employee_id recorded at all is a valid, honestly-represented state — "
        "RF-One never fabricates an Employee to fill the gap",
        order_no_employee.employee_id is None,
    )

    # =====================================================================
    # CRITICAL A-H (TASK_RESTAURANT_STRUCTURE_001): direct regression
    # coverage for the exact evidence OrderEmployeeServiceAttributionResolver
    # consumes, including the approved Product Owner decision that FAILED
    # Payments never participate in SERVICE_OWNER evidence — not duplicating
    # tips_validation.py's own end-to-end engine tests, but testing the
    # Sales-side facts the resolver reads directly. "FAIL" is the canonical
    # failure value (see the scenario-10 note above); "SUCCESS" the
    # canonical economically-valid value tips/engine.py already uses.
    # =====================================================================
    resolver = OrderEmployeeServiceAttributionResolver()

    # A. Order.employee_id = A, SUCCESS Payment.employee_id = A -> RESOLVED A
    order_a = make_order(
        location=location_wp, order_type=order_type_wp, source_order_id="ORD-CRIT-A",
        employee=emp_wp_a, total=5000, created_at=_dt(10),
    )
    make_payment(order=order_a, source_payment_id="PAY-CRIT-A-1", employee=emp_wp_a, amount=5000, created_at=_dt(10))
    resolution_a = resolver.resolve(session, order_a)
    result.check(
        "CRITICAL A: Order.employee_id=A + a SUCCESS Payment.employee_id=A -> RESOLVED A",
        resolution_a.status == RESOLVED and resolution_a.employee_ids == [emp_wp_a.id],
    )

    # B. Order.employee_id = A, FAILED Payment.employee_id = B -> RESOLVED A, NOT AMBIGUOUS
    order_b = make_order(
        location=location_wp, order_type=order_type_wp, source_order_id="ORD-CRIT-B",
        employee=emp_wp_a, total=4500, created_at=_dt(10),
    )
    make_payment(
        order=order_b, source_payment_id="PAY-CRIT-B-1", employee=emp_wp_b, amount=4500,
        created_at=_dt(10), result_value="FAIL",
    )
    resolution_b = resolver.resolve(session, order_b)
    result.check(
        "CRITICAL B: Order.employee_id=A + a FAILED (disagreeing) Payment.employee_id=B -> "
        "RESOLVED A, never AMBIGUOUS — a failed attempt is not authoritative service-attribution "
        "evidence, even when it disagrees",
        resolution_b.status == RESOLVED and resolution_b.employee_ids == [emp_wp_a.id],
    )

    # C. Order.employee_id = A, FAILED Payment.employee_id = A -> RESOLVED A, no extra evidence
    order_c = make_order(
        location=location_wp, order_type=order_type_wp, source_order_id="ORD-CRIT-C",
        employee=emp_wp_a, total=4200, created_at=_dt(10),
    )
    make_payment(
        order=order_c, source_payment_id="PAY-CRIT-C-1", employee=emp_wp_a, amount=4200,
        created_at=_dt(10), result_value="FAIL",
    )
    resolution_c = resolver.resolve(session, order_c)
    result.check(
        "CRITICAL C: Order.employee_id=A + a FAILED (agreeing) Payment.employee_id=A -> RESOLVED A "
        "on Order-level evidence alone — the failed payment corroborates nothing (its own "
        "'agreeing Payment' count in the detail must be 0, not 1)",
        resolution_c.status == RESOLVED
        and resolution_c.employee_ids == [emp_wp_a.id]
        and "0 agreeing" in (resolution_c.detail or ""),
    )

    # D. Order.employee_id = A, SUCCESS Payment.employee_id = B -> AMBIGUOUS
    order_d = make_order(
        location=location_wp, order_type=order_type_wp, source_order_id="ORD-CRIT-D",
        employee=emp_wp_a, total=4800, created_at=_dt(10),
    )
    make_payment(order=order_d, source_payment_id="PAY-CRIT-D-1", employee=emp_wp_b, amount=4800, created_at=_dt(10))
    resolution_d = resolver.resolve(session, order_d)
    result.check(
        "CRITICAL D: Order.employee_id=A + a SUCCESS (disagreeing) Payment.employee_id=B -> "
        "AMBIGUOUS — a genuinely completed, disagreeing observation is never ignored",
        resolution_d.status == AMBIGUOUS and resolution_d.employee_ids == [],
    )

    # E. one FAILED Payment from B + one SUCCESS Payment from A -> RESOLVED A
    order_e = make_order(
        location=location_wp, order_type=order_type_wp, source_order_id="ORD-CRIT-E",
        employee=emp_wp_a, total=9500, created_at=_dt(10),
    )
    make_payment(
        order=order_e, source_payment_id="PAY-CRIT-E-1", employee=emp_wp_b, amount=4500,
        created_at=_dt(10), result_value="FAIL",
    )
    make_payment(order=order_e, source_payment_id="PAY-CRIT-E-2", employee=emp_wp_a, amount=5000, created_at=_dt(10))
    resolution_e = resolver.resolve(session, order_e)
    result.check(
        "CRITICAL E: a disagreeing FAILED Payment (B) alongside an agreeing SUCCESS Payment (A) "
        "-> RESOLVED A — the failed attempt's disagreement is not enough to create ambiguity once "
        "it is excluded from evidence",
        resolution_e.status == RESOLVED and resolution_e.employee_ids == [emp_wp_a.id],
    )

    # F. Multiple SUCCESS Payments all agreeing with A -> RESOLVED A
    order_f = make_order(
        location=location_wp, order_type=order_type_wp, source_order_id="ORD-CRIT-F",
        employee=emp_wp_a, total=9000, created_at=_dt(10),
    )
    make_payment(order=order_f, source_payment_id="PAY-CRIT-F-1", employee=emp_wp_a, amount=4500, created_at=_dt(10))
    make_payment(order=order_f, source_payment_id="PAY-CRIT-F-2", employee=emp_wp_a, amount=4500, created_at=_dt(10))
    resolution_f = resolver.resolve(session, order_f)
    result.check(
        "CRITICAL F: multiple SUCCESS Payments all agreeing with Order.employee_id=A (a genuine "
        "split payment) -> RESOLVED A, not AMBIGUOUS merely because more than one Payment exists",
        resolution_f.status == RESOLVED
        and resolution_f.employee_ids == [emp_wp_a.id]
        and sum(p.amount for p in order_f.payments) == order_f.total,
    )

    # G. Multiple SUCCESS Payments with conflicting Employees -> AMBIGUOUS
    order_g = make_order(
        location=location_wp, order_type=order_type_wp, source_order_id="ORD-CRIT-G",
        employee=emp_wp_a, total=9000, created_at=_dt(10),
    )
    make_payment(order=order_g, source_payment_id="PAY-CRIT-G-1", employee=emp_wp_a, amount=4500, created_at=_dt(10))
    make_payment(order=order_g, source_payment_id="PAY-CRIT-G-2", employee=emp_wp_b, amount=4500, created_at=_dt(10))
    resolution_g = resolver.resolve(session, order_g)
    result.check(
        "CRITICAL G: multiple SUCCESS Payments that conflict with each other (one agrees with A, "
        "one does not) -> AMBIGUOUS",
        resolution_g.status == AMBIGUOUS and resolution_g.employee_ids == [],
    )

    # H. No Order.employee_id, only a FAILED Payment.employee_id present -> UNRESOLVED
    order_h = make_order(
        location=location_wp, order_type=order_type_wp, source_order_id="ORD-CRIT-H",
        employee=None, total=3500, created_at=_dt(10),
    )
    make_payment(
        order=order_h, source_payment_id="PAY-CRIT-H-1", employee=emp_wp_a, amount=3500,
        created_at=_dt(10), result_value="FAIL",
    )
    resolution_h = resolver.resolve(session, order_h)
    result.check(
        "CRITICAL H: no Order.employee_id, and the only Payment evidence is a FAILED "
        "Payment.employee_id -> UNRESOLVED — RF-One never infers a Service Owner from a failed "
        "payment alone, even as a last resort",
        resolution_h.status == UNRESOLVED and resolution_h.employee_ids == [],
    )
