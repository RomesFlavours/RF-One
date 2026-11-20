"""Automated schema validation (task §40).

Builds a small synthetic fixture — never real Clover data — and asserts
that the required relationships and edge cases actually work end-to-end:
multi-payment Orders, multi-refund Payments, M:N Table Service/Physical
Table/Employee, M:N Item/Category/Modifier, multi-modifier Order Items,
fractional Order Item quantity, declared-vs-derived guest count divergence,
Tip missing-vs-zero distinctness, and both ad hoc discount shapes.

The fixture is inserted inside one transaction and always rolled back at
the end (success or failure), so running validation never leaves synthetic
rows in the target database — including the default local SQLite file that
a future ingestion task will populate with real data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from . import models as m

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


def _now() -> datetime:
    return datetime.now(UTC)


def run_validation(session_factory: sessionmaker[Session]) -> ValidationResult:
    result = ValidationResult(success=True)

    with session_factory() as session:
        try:
            _build_fixture_and_assert(session, result)
        finally:
            # Never persist synthetic fixture rows, regardless of outcome.
            session.rollback()

    return result


def _build_fixture_and_assert(session: Session, result: ValidationResult) -> None:
    source_system = m.SourceSystem(code="CLOVER", name="Clover", active=True)
    session.add(source_system)
    session.flush()

    ingestion_run = m.IngestionRun(
        source_system_id=source_system.id,
        started_at=_now(),
        status="SUCCESS",
    )
    session.add(ingestion_run)
    session.flush()

    merchant = m.Merchant(source_system_id=source_system.id, source_merchant_id="MERCH1", name="Test Merchant")
    session.add(merchant)
    session.flush()

    location = m.Location(
        merchant_id=merchant.id,
        source_system_id=source_system.id,
        source_location_id="LOC1",
        name="Test Location",
        timezone=None,  # not source-confirmed, per task §39 — must remain representable as missing
        currency="USD",
    )
    session.add(location)
    session.flush()

    # --- Physical Table / Table Service M:N (task §9, §40) ---------------
    table_a = m.PhysicalTable(location_id=location.id, table_number="1", seat_capacity=4)
    table_b = m.PhysicalTable(location_id=location.id, table_number="2", seat_capacity=2)
    session.add_all([table_a, table_b])
    session.flush()

    table_service = m.TableService(
        location_id=location.id,
        opened_at=_now(),
        declared_guest_count=4,
        derived_guest_count=3,
        declared_guest_count_source="TECHNICAL_ITEM",
    )
    session.add(table_service)
    session.flush()
    session.add_all(
        [
            m.TableServicePhysicalTable(table_service_id=table_service.id, physical_table_id=table_a.id),
            m.TableServicePhysicalTable(table_service_id=table_service.id, physical_table_id=table_b.id),
        ]
    )

    # --- Employee / Table Service ↔ Employee / Shift (task §10-12, §40) --
    employee_1 = m.Employee(
        location_id=location.id,
        source_system_id=source_system.id,
        source_employee_id="EMP1",
        display_name="Server One",
        system_role="EMPLOYEE",
    )
    employee_2 = m.Employee(
        location_id=location.id,
        source_system_id=source_system.id,
        source_employee_id="EMP2",
        display_name="Manager One",
        system_role="MANAGER",
    )
    session.add_all([employee_1, employee_2])
    session.flush()
    session.add_all(
        [
            m.TableServiceEmployee(table_service_id=table_service.id, employee_id=employee_1.id),
            m.TableServiceEmployee(table_service_id=table_service.id, employee_id=employee_2.id),
        ]
    )

    shift = m.Shift(
        employee_id=employee_1.id,
        source_system_id=source_system.id,
        source_shift_id="SHIFT1",
        clock_in=_now() - timedelta(hours=5),
        clock_out=_now(),
        override_in_employee_id=employee_2.id,
        override_in_time=_now() - timedelta(hours=5, minutes=1),
        server_banking=None,
    )
    session.add(shift)

    # --- Restaurant Profile / Organization (TASK_RESTAURANT_001 §21) ------
    employee_3 = m.Employee(
        location_id=location.id,
        source_system_id=source_system.id,
        source_employee_id="EMP3",
        display_name="Manager Two",
        system_role="MANAGER",
    )
    session.add(employee_3)
    session.flush()

    restaurant = m.Restaurant(name="Test Restaurant", default_currency="USD")
    session.add(restaurant)
    session.flush()

    location_b = m.Location(
        merchant_id=merchant.id,
        source_system_id=source_system.id,
        source_location_id="LOC2",
        name="Test Location B",
        currency="USD",
    )
    session.add(location_b)
    session.flush()

    t0 = _now() - timedelta(days=90)
    t1 = _now() - timedelta(days=60)
    t2 = _now() - timedelta(days=10)

    # #1: one Restaurant can have multiple Locations over time.
    session.add_all(
        [
            m.RestaurantLocation(
                restaurant_id=restaurant.id, location_id=location.id, valid_from=t0, valid_to=t1, is_primary=False
            ),
            m.RestaurantLocation(
                restaurant_id=restaurant.id, location_id=location_b.id, valid_from=t1, valid_to=None, is_primary=True
            ),
        ]
    )

    # #2/#3/#4: multiple Operational Areas, Physical Areas, Restaurant Roles.
    area_foh = m.OperationalArea(restaurant_id=restaurant.id, name="FOH")
    area_bar = m.OperationalArea(restaurant_id=restaurant.id, name="BAR")
    area_mgmt = m.OperationalArea(restaurant_id=restaurant.id, name="MANAGEMENT")
    session.add_all([area_foh, area_bar, area_mgmt])

    physical_dining = m.PhysicalArea(restaurant_id=restaurant.id, name="Dining Room", area_type="INDOOR")
    physical_patio = m.PhysicalArea(restaurant_id=restaurant.id, name="Patio", area_type="OUTDOOR")
    session.add_all([physical_dining, physical_patio])

    role_host = m.RestaurantRole(restaurant_id=restaurant.id, name="Host")
    role_bartender = m.RestaurantRole(restaurant_id=restaurant.id, name="Bartender")
    role_manager = m.RestaurantRole(restaurant_id=restaurant.id, name="Manager")
    session.add_all([role_host, role_bartender, role_manager])
    session.flush()

    # #5/#6: one Role valid in multiple Areas (Manager: FOH + MANAGEMENT);
    # one Area allows multiple Roles (FOH: Host + Manager).
    session.add_all(
        [
            m.OperationalAreaRole(operational_area_id=area_foh.id, restaurant_role_id=role_host.id),
            m.OperationalAreaRole(operational_area_id=area_bar.id, restaurant_role_id=role_bartender.id),
            m.OperationalAreaRole(operational_area_id=area_foh.id, restaurant_role_id=role_manager.id),
            m.OperationalAreaRole(operational_area_id=area_mgmt.id, restaurant_role_id=role_manager.id),
        ]
    )

    # #7/#8/#9/#11: one Employee, multiple assignments over time; Role AND
    # Area both change without rewriting the earlier (closed) assignment;
    # the current assignment is open-ended (valid_to IS NULL).
    assignment_1_historical = m.EmployeeAssignment(
        employee_id=employee_1.id,
        restaurant_id=restaurant.id,
        operational_area_id=area_foh.id,
        restaurant_role_id=role_host.id,
        valid_from=t0,
        valid_to=t1,
        assignment_source="MANUAL",
    )
    assignment_1_current = m.EmployeeAssignment(
        employee_id=employee_1.id,
        restaurant_id=restaurant.id,
        operational_area_id=area_bar.id,
        restaurant_role_id=role_bartender.id,
        valid_from=t1,
        valid_to=None,
        assignment_source="MANUAL",
    )
    session.add_all([assignment_1_historical, assignment_1_current])

    # #6 (continued)/#10: two concurrent assignments for one Employee
    # (same Role, two different Areas), and #10: a second Employee sharing
    # the exact same Role/Area as the first.
    assignment_2_foh_manager = m.EmployeeAssignment(
        employee_id=employee_2.id,
        restaurant_id=restaurant.id,
        operational_area_id=area_foh.id,
        restaurant_role_id=role_manager.id,
        valid_from=t2,
        valid_to=None,
        assignment_source="MANUAL",
    )
    assignment_2_mgmt_manager = m.EmployeeAssignment(
        employee_id=employee_2.id,
        restaurant_id=restaurant.id,
        operational_area_id=area_mgmt.id,
        restaurant_role_id=role_manager.id,
        valid_from=t2,
        valid_to=None,
        assignment_source="MANUAL",
    )
    assignment_3_foh_manager_shared = m.EmployeeAssignment(
        employee_id=employee_3.id,
        restaurant_id=restaurant.id,
        operational_area_id=area_foh.id,
        restaurant_role_id=role_manager.id,
        valid_from=t2,
        valid_to=None,
        assignment_source="MANUAL",
    )
    session.add_all([assignment_2_foh_manager, assignment_2_mgmt_manager, assignment_3_foh_manager_shared])
    session.flush()

    # --- Order Type / Order (task §13-14) ---------------------------------
    order_type = m.OrderType(
        location_id=location.id,
        source_system_id=source_system.id,
        source_order_type_id="OT1",
        name="Table",
    )
    session.add(order_type)
    session.flush()

    order = m.Order(
        location_id=location.id,
        table_service_id=table_service.id,
        source_system_id=source_system.id,
        source_order_id="ORDER1",
        employee_id=employee_1.id,
        order_type_id=order_type.id,
        created_at=_now(),
        payment_state="PAID",
        currency="USD",
        total=10000,
        title_raw="#4 - Inside",
    )
    order_2 = m.Order(
        location_id=location.id,
        table_service_id=table_service.id,
        source_system_id=source_system.id,
        source_order_id="ORDER2",
        created_at=_now(),
        currency="USD",
        total=500,
    )
    session.add_all([order, order_2])
    session.flush()

    # --- Item / Category / Modifier catalog (task §15-18, §40) -----------
    category_a = m.Category(location_id=location.id, source_system_id=source_system.id, source_category_id="CAT1", name="Pizza")
    category_b = m.Category(location_id=location.id, source_system_id=source_system.id, source_category_id="CAT2", name="Specials")
    session.add_all([category_a, category_b])
    session.flush()

    modifier_group = m.ModifierGroup(
        location_id=location.id, source_system_id=source_system.id, source_modifier_group_id="MG1", name="Add/Extra"
    )
    session.add(modifier_group)
    session.flush()

    modifier_1 = m.Modifier(
        location_id=location.id,
        modifier_group_id=modifier_group.id,
        source_system_id=source_system.id,
        source_modifier_id="MOD1",
        name="Extra Cheese",
        price_delta=200,
    )
    modifier_2 = m.Modifier(
        location_id=location.id,
        modifier_group_id=modifier_group.id,
        source_system_id=source_system.id,
        source_modifier_id="MOD2",
        name="First",
        price_delta=0,
    )
    session.add_all([modifier_1, modifier_2])
    session.flush()

    item = m.Item(
        location_id=location.id,
        source_system_id=source_system.id,
        source_item_id="ITEM1",
        name="Margherita Pizza",
        current_price=1200,
    )
    session.add(item)
    session.flush()
    session.add_all(
        [
            m.ItemCategory(item_id=item.id, category_id=category_a.id),
            m.ItemCategory(item_id=item.id, category_id=category_b.id),
            m.ItemModifier(item_id=item.id, modifier_id=modifier_1.id),
            m.ItemModifier(item_id=item.id, modifier_id=modifier_2.id),
        ]
    )

    # --- Order Item — fractional quantity (task §19, §40) -----------------
    order_item = m.OrderItem(
        order_id=order.id,
        item_id=item.id,
        source_system_id=source_system.id,
        source_line_item_id="LI1",
        source_name="Margherita Pizza",
        quantity=Decimal("0.5"),
        quantity_decimal_digits=3,
        historical_unit_price=1200,
        guest_number=1,
        guest_label_raw="Guest 1",
        is_revenue=True,
    )
    session.add(order_item)
    session.flush()
    session.add_all(
        [
            m.OrderItemModifier(
                order_item_id=order_item.id,
                modifier_id=modifier_1.id,
                source_system_id=source_system.id,
                source_modification_id="MOD-APP-1",
                name_raw="Extra Cheese",
                amount=200,
            ),
            m.OrderItemModifier(
                order_item_id=order_item.id,
                modifier_id=modifier_2.id,
                source_system_id=source_system.id,
                source_modification_id="MOD-APP-2",
                name_raw="First",
                amount=0,
            ),
        ]
    )

    # --- Discounts — both ad hoc shapes (task §22-24, §40) -----------------
    discount_definition = m.DiscountDefinition(
        location_id=location.id,
        source_system_id=source_system.id,
        source_discount_id="DISC1",
        name="Friends & Family",
        percentage=Decimal("25.0000"),
    )
    session.add(discount_definition)
    session.flush()

    order_discount_percentage = m.OrderDiscount(
        order_id=order.id,
        discount_definition_id=discount_definition.id,
        source_system_id=source_system.id,
        source_discount_id="APPLIED-DISC-1",
        name_raw="Friends & Family",
        percentage=Decimal("25.0000"),
        amount=None,
    )
    order_discount_amount = m.OrderDiscount(
        order_id=order.id,
        discount_definition_id=None,
        source_system_id=source_system.id,
        source_discount_id="APPLIED-DISC-2",
        name_raw="$50.00 Off",
        percentage=None,
        amount=-5000,
    )
    session.add_all([order_discount_percentage, order_discount_amount])

    order_item_discount = m.OrderItemDiscount(
        order_item_id=order_item.id,
        source_system_id=source_system.id,
        percentage=Decimal("10.0000"),
    )
    session.add(order_item_discount)

    # --- Tax / Fee (task §25-27) -------------------------------------------
    tax_rate = m.TaxRate(
        location_id=location.id,
        source_system_id=source_system.id,
        source_tax_rate_id="TAX1",
        name="Tax",
        rate=Decimal("0.065000"),
    )
    session.add(tax_rate)
    session.flush()
    session.add(
        m.OrderItemTax(
            order_item_id=order_item.id,
            tax_rate_id=tax_rate.id,
            amount=39,
            rate_applied=Decimal("0.065000"),
            source_system_id=source_system.id,
        )
    )
    session.add(
        m.OrderFee(
            order_id=order.id,
            source_system_id=source_system.id,
            source_line_item_id="LI-FEE-1",
            fee_type="SERVICE_CHARGE",
            name_raw="Gratuity",
            amount=1800,
            percentage=Decimal("18.0000"),
        )
    )

    # --- Tender / Payment / Payment Tip / Refund (task §28-31, §40) -------
    tender = m.Tender(
        location_id=location.id,
        source_system_id=source_system.id,
        source_tender_id="TND1",
        label="Credit Card",
    )
    session.add(tender)
    session.flush()

    device = m.Device(
        location_id=location.id,
        source_system_id=source_system.id,
        source_device_id="DEV1",
        model="Clover_C501",
    )
    session.add(device)
    session.flush()

    # Exercise the resolved device_id FK added by TASK_DATABASE_002 on Order
    # (order_2 deliberately keeps device_id NULL, to confirm it stays nullable).
    order.device_id = device.id

    payment_tip_missing = m.Payment(
        order_id=order.id,
        source_system_id=source_system.id,
        source_payment_id="PAY1",
        device_id=device.id,
        employee_id=employee_1.id,
        tender_id=tender.id,
        created_at=_now(),
        amount=4000,
        result="SUCCESS",
    )
    payment_tip_present_zero = m.Payment(
        order_id=order.id,
        source_system_id=source_system.id,
        source_payment_id="PAY2",
        employee_id=employee_1.id,
        tender_id=tender.id,
        created_at=_now(),
        amount=3000,
        result="SUCCESS",
    )
    payment_tip_present_nonzero = m.Payment(
        order_id=order.id,
        source_system_id=source_system.id,
        source_payment_id="PAY3",
        employee_id=employee_1.id,
        tender_id=tender.id,
        created_at=_now(),
        amount=3000,
        result="FAIL",
    )
    session.add_all([payment_tip_missing, payment_tip_present_zero, payment_tip_present_nonzero])
    session.flush()

    # Deliberately: no PaymentTip row at all for payment_tip_missing —
    # this represents "tip field absent from source" at its most literal.
    session.add(m.PaymentTip(payment_id=payment_tip_present_zero.id, amount=0, source_present=True))
    session.add(m.PaymentTip(payment_id=payment_tip_present_nonzero.id, amount=500, source_present=True))

    session.add_all(
        [
            m.Refund(
                source_system_id=source_system.id,
                source_refund_id="REF1",
                order_id=order.id,
                payment_id=payment_tip_present_nonzero.id,
                employee_id=employee_2.id,
                device_id=device.id,
                created_at=_now(),
                amount=1500,
                tax_amount=97,
                tip_amount=0,
                status="SUCCESS",
                voided=False,
            ),
            m.Refund(
                source_system_id=source_system.id,
                source_refund_id="REF2",
                order_id=order.id,
                payment_id=payment_tip_present_nonzero.id,
                employee_id=employee_2.id,
                created_at=_now(),
                amount=1500,
                status="SUCCESS",
                voided=False,
            ),
        ]
    )

    session.add(
        m.SourceRecord(
            ingestion_run_id=ingestion_run.id,
            source_system_id=source_system.id,
            entity_type="order",
            source_id="ORDER1",
            retrieved_at=_now(),
            raw_json={"id": "ORDER1", "note": "synthetic fixture, not real Clover data"},
        )
    )

    session.flush()

    # -----------------------------------------------------------------
    # Assertions
    # -----------------------------------------------------------------

    result.check("all tables can be created and accept inserts", True)

    ts_tables = session.scalars(
        select(m.TableServicePhysicalTable).where(m.TableServicePhysicalTable.table_service_id == table_service.id)
    ).all()
    result.check("one Table Service can have multiple Physical Tables", len(ts_tables) == 2)

    ts_employees = session.scalars(
        select(m.TableServiceEmployee).where(m.TableServiceEmployee.table_service_id == table_service.id)
    ).all()
    result.check("one Table Service can have multiple Employees", len(ts_employees) == 2)

    ts_orders = session.scalars(select(m.Order).where(m.Order.table_service_id == table_service.id)).all()
    result.check("one Table Service can have multiple Orders", len(ts_orders) == 2)

    item_categories = session.scalars(select(m.ItemCategory).where(m.ItemCategory.item_id == item.id)).all()
    result.check("one Item can have multiple Categories", len(item_categories) == 2)

    item_modifiers = session.scalars(select(m.ItemModifier).where(m.ItemModifier.item_id == item.id)).all()
    result.check("one Item can have multiple Modifiers", len(item_modifiers) == 2)

    oi_modifiers = session.scalars(
        select(m.OrderItemModifier).where(m.OrderItemModifier.order_item_id == order_item.id)
    ).all()
    result.check("one Order Item can have multiple Modifiers", len(oi_modifiers) == 2)

    order_payments = session.scalars(select(m.Payment).where(m.Payment.order_id == order.id)).all()
    result.check("one Order can have multiple Payments", len(order_payments) == 3)

    payment_refunds = session.scalars(
        select(m.Refund).where(m.Refund.payment_id == payment_tip_present_nonzero.id)
    ).all()
    result.check("one Payment can have multiple Refunds", len(payment_refunds) == 2)

    fetched_order = session.get(m.Order, order.id)
    fetched_payment = session.get(m.Payment, payment_tip_missing.id)
    fetched_refund = next(r for r in payment_refunds if r.source_refund_id == "REF1")
    result.check(
        "device_id resolves on Order/Payment/Refund alongside device_source_id (TASK_DATABASE_002)",
        fetched_order is not None
        and fetched_order.device_id == device.id
        and fetched_payment is not None
        and fetched_payment.device_id == device.id
        and fetched_refund.device_id == device.id,
    )

    fetched_order_item = session.get(m.OrderItem, order_item.id)
    result.check(
        "Order Item quantity accepts fractional values",
        fetched_order_item is not None and fetched_order_item.quantity == Decimal("0.5"),
    )

    fetched_table_service = session.get(m.TableService, table_service.id)
    result.check(
        "declared_guest_count and derived_guest_count can differ",
        fetched_table_service is not None
        and fetched_table_service.declared_guest_count == 4
        and fetched_table_service.derived_guest_count == 3
        and fetched_table_service.declared_guest_count != fetched_table_service.derived_guest_count,
    )

    tip_missing = session.get(m.PaymentTip, payment_tip_missing.id)
    tip_present_zero = session.get(m.PaymentTip, payment_tip_present_zero.id)
    result.check(
        "Tip missing vs zero can be represented distinctly",
        tip_missing is None  # no row at all: source did not report a tip field
        and tip_present_zero is not None
        and tip_present_zero.source_present is True
        and tip_present_zero.amount == 0,
    )

    fetched_percentage_discount = session.get(m.OrderDiscount, order_discount_percentage.id)
    fetched_amount_discount = session.get(m.OrderDiscount, order_discount_amount.id)
    result.check(
        "ad hoc fixed discount and percentage discount can both be represented",
        fetched_percentage_discount is not None
        and fetched_percentage_discount.percentage == Decimal("25.0000")
        and fetched_percentage_discount.amount is None
        and fetched_amount_discount is not None
        and fetched_amount_discount.amount == -5000
        and fetched_amount_discount.percentage is None,
    )

    # --- Restaurant Profile / Organization (TASK_RESTAURANT_001 §21) ------
    restaurant_locations = session.scalars(
        select(m.RestaurantLocation).where(m.RestaurantLocation.restaurant_id == restaurant.id)
    ).all()
    result.check(
        "#1 one Restaurant can have multiple Locations over time",
        len(restaurant_locations) == 2
        and {rl.location_id for rl in restaurant_locations} == {location.id, location_b.id}
        and any(rl.valid_to is not None for rl in restaurant_locations)
        and any(rl.valid_to is None for rl in restaurant_locations),
    )

    restaurant_areas = session.scalars(
        select(m.OperationalArea).where(m.OperationalArea.restaurant_id == restaurant.id)
    ).all()
    result.check("#2 one Restaurant can have multiple Operational Areas", len(restaurant_areas) == 3)

    restaurant_physical_areas = session.scalars(
        select(m.PhysicalArea).where(m.PhysicalArea.restaurant_id == restaurant.id)
    ).all()
    result.check("#3 one Restaurant can have multiple Physical Areas", len(restaurant_physical_areas) == 2)

    restaurant_roles = session.scalars(
        select(m.RestaurantRole).where(m.RestaurantRole.restaurant_id == restaurant.id)
    ).all()
    result.check("#4 one Restaurant can have multiple Restaurant Roles", len(restaurant_roles) == 3)

    manager_area_links = session.scalars(
        select(m.OperationalAreaRole).where(m.OperationalAreaRole.restaurant_role_id == role_manager.id)
    ).all()
    result.check(
        "#5 one Role can be valid in multiple Operational Areas",
        {link.operational_area_id for link in manager_area_links} == {area_foh.id, area_mgmt.id},
    )

    foh_role_links = session.scalars(
        select(m.OperationalAreaRole).where(m.OperationalAreaRole.operational_area_id == area_foh.id)
    ).all()
    result.check(
        "#6 one Operational Area can allow multiple Roles",
        {link.restaurant_role_id for link in foh_role_links} == {role_host.id, role_manager.id},
    )

    employee_1_assignments = session.scalars(
        select(m.EmployeeAssignment).where(m.EmployeeAssignment.employee_id == employee_1.id)
    ).all()
    result.check("#7 one Employee can have multiple assignments over time", len(employee_1_assignments) == 2)

    result.check(
        "#8 one Employee can change Role without rewriting history",
        assignment_1_historical.restaurant_role_id == role_host.id
        and assignment_1_current.restaurant_role_id == role_bartender.id
        and session.get(m.EmployeeAssignment, assignment_1_historical.id) is not None,
    )
    result.check(
        "#9 one Employee can change Area without rewriting history",
        assignment_1_historical.operational_area_id == area_foh.id
        and assignment_1_current.operational_area_id == area_bar.id
        and session.get(m.EmployeeAssignment, assignment_1_historical.id) is not None,
    )

    shared_role_area_assignments = session.scalars(
        select(m.EmployeeAssignment).where(
            m.EmployeeAssignment.operational_area_id == area_foh.id,
            m.EmployeeAssignment.restaurant_role_id == role_manager.id,
        )
    ).all()
    result.check(
        "#10 two Employees may share the same Role/Area",
        {a.employee_id for a in shared_role_area_assignments} == {employee_2.id, employee_3.id},
    )

    result.check(
        "#11 Assignment validity can be open-ended (valid_to IS NULL)",
        assignment_1_current.valid_to is None and assignment_1_historical.valid_to is not None,
    )

    employee_2_concurrent = session.scalars(
        select(m.EmployeeAssignment).where(
            m.EmployeeAssignment.employee_id == employee_2.id,
            m.EmployeeAssignment.valid_to.is_(None),
        )
    ).all()
    result.check(
        "one Employee can hold multiple concurrent assignments (task §6)",
        len(employee_2_concurrent) == 2
        and {a.operational_area_id for a in employee_2_concurrent} == {area_foh.id, area_mgmt.id},
    )

    fetched_employee_1 = session.get(m.Employee, employee_1.id)
    result.check(
        "#12 Employee activity in a period is not represented by assignment alone "
        "(Employee.active stays unpopulated/independent while EmployeeAssignment is fully usable)",
        fetched_employee_1 is not None
        and fetched_employee_1.active is None
        and len(employee_1_assignments) > 0,
    )

    fetched_physical_table_area = m.PhysicalTable(
        location_id=location.id, physical_area_id=physical_dining.id, table_number="P1"
    )
    session.add(fetched_physical_table_area)
    session.flush()
    result.check(
        "PhysicalTable can optionally resolve to a canonical PhysicalArea (task §14)",
        fetched_physical_table_area.physical_area_id == physical_dining.id,
    )

    # --- Referential integrity: an invalid FK must be rejected -----------
    # Runs inside its own SAVEPOINT so the rest of the fixture/transaction
    # is unaffected by the expected failure.
    fk_rejected = False
    nested = session.begin_nested()
    try:
        session.add(
            m.OrderItem(
                order_id=-1,  # does not exist
                source_system_id=source_system.id,
                source_line_item_id="INVALID-FK-CHECK",
            )
        )
        session.flush()
    except IntegrityError:
        fk_rejected = True
        nested.rollback()
    else:
        nested.rollback()
    result.check("an invalid foreign key reference is rejected by the database", fk_rejected)
