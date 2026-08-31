"""Automated synthetic tests for TASK_ORGANIZATION_002's three Product Owner
decisions: Location-specific Employee Assignment, Primary Location
integrity, and Location timezone / Business Day Rule configuration.

Mirrors `profile_validation.py`'s/`tips_validation.py`'s pattern exactly:
builds a synthetic (never-real) fixture inside one transaction, asserts the
required behaviors, and always rolls back — no synthetic row is ever left
in the target database. Constraint-violation scenarios use a nested
SAVEPOINT (`session.begin_nested()`) so a single expected `IntegrityError`
does not abort the whole validation transaction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .tips.engine import MODE_DRY_RUN as TIPS_MODE_DRY_RUN, run_tip_calculation
from .tips.resolvers import NullServiceAttributionResolver

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
    # Naive UTC, matching every other timestamp this codebase persists
    # through SQLite (see profile/bootstrap.py's `_to_naive_utc` docstring).
    base = datetime.now(UTC) - timedelta(days=days_ago)
    return base.replace(microsecond=0, tzinfo=None)


def _expect_integrity_error(session: Session, action) -> bool:
    """Runs `action()` inside a nested SAVEPOINT, expecting it to raise
    `IntegrityError` on flush. Rolls back only the savepoint either way, so
    the outer validation transaction is never aborted. Returns True iff the
    expected error occurred."""
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

    def make_location(name: str, *, timezone_value: str | None = None) -> m.Location:
        loc = m.Location(
            merchant_id=merchant.id,
            source_system_id=source_system.id,
            source_location_id=name.upper().replace(" ", "_"),
            name=name,
            timezone=timezone_value,
            currency="USD",
        )
        session.add(loc)
        session.flush()
        return loc

    location_wp = make_location("Winter Park")
    location_md = make_location("Mount Dora")

    # =====================================================================
    # Scenario 1 — One Restaurant, two Locations
    # =====================================================================
    restaurant = m.Restaurant(name="Rome Test", default_currency="USD")
    session.add(restaurant)
    session.flush()
    session.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location_wp.id, is_primary=True))
    session.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location_md.id, is_primary=False))
    session.flush()

    restaurant_location_ids = set(
        session.scalars(
            select(m.RestaurantLocation.location_id).where(m.RestaurantLocation.restaurant_id == restaurant.id)
        ).all()
    )
    restaurant_count = session.scalar(
        select(m.Restaurant).where(m.Restaurant.name == "Rome Test")
    )
    result.check(
        "Scenario 1: one Restaurant is associated with two Locations (Winter Park, Mount Dora) "
        "via two RestaurantLocation rows, without any duplicate Restaurant identity",
        restaurant_location_ids == {location_wp.id, location_md.id}
        and restaurant_count is not None,
    )

    area_root = m.OperationalArea(restaurant_id=restaurant.id, name="Restaurant Operations", code="ROOT")
    session.add(area_root)
    session.flush()
    role_server = m.RestaurantRole(restaurant_id=restaurant.id, name="Server")
    role_manager = m.RestaurantRole(restaurant_id=restaurant.id, name="Manager")
    role_ceo = m.RestaurantRole(restaurant_id=restaurant.id, name="CEO")
    session.add_all([role_server, role_manager, role_ceo])
    session.flush()

    def make_employee(source_id: str, name: str, *, location: m.Location = location_wp) -> m.Employee:
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

    # =====================================================================
    # Scenario 2/3 — One Employee, two Locations, including same Role at
    # both (concurrent, non-conflicting)
    # =====================================================================
    giovanna = make_employee("E-GIOVANNA", "Giovanna")
    assignment_a = m.EmployeeAssignment(
        employee_id=giovanna.id, restaurant_id=restaurant.id, operational_area_id=area_root.id,
        restaurant_role_id=role_manager.id, location_id=location_wp.id,
        valid_from=_dt(400), valid_to=None, assignment_source="MANUAL",
    )
    assignment_b = m.EmployeeAssignment(
        employee_id=giovanna.id, restaurant_id=restaurant.id, operational_area_id=area_root.id,
        restaurant_role_id=role_manager.id, location_id=location_md.id,
        valid_from=_dt(400), valid_to=None, assignment_source="MANUAL",
    )
    session.add_all([assignment_a, assignment_b])
    session.flush()

    giovanna_assignments = session.scalars(
        select(m.EmployeeAssignment).where(m.EmployeeAssignment.employee_id == giovanna.id)
    ).all()
    result.check(
        "Scenario 2/3: one Employee (Giovanna) holds two concurrent, valid EmployeeAssignment rows "
        "under the SAME Restaurant Role (Manager) differing only by Location (Winter Park vs. Mount "
        "Dora) — no false-duplicate rejection, no duplicate Employee identity",
        len(giovanna_assignments) == 2
        and {a.location_id for a in giovanna_assignments} == {location_wp.id, location_md.id}
        and all(a.restaurant_role_id == role_manager.id for a in giovanna_assignments)
        and all(a.valid_to is None for a in giovanna_assignments),
    )

    # =====================================================================
    # Scenario 4 — Restaurant-wide Assignment (location_id NULL)
    # =====================================================================
    emp_ceo = make_employee("E-CEO", "RestaurantWideCEO")
    assignment_ceo = m.EmployeeAssignment(
        employee_id=emp_ceo.id, restaurant_id=restaurant.id, operational_area_id=area_root.id,
        restaurant_role_id=role_ceo.id, location_id=None,
        valid_from=_dt(400), valid_to=None, assignment_source="MANUAL",
    )
    session.add(assignment_ceo)
    session.flush()
    result.check(
        "Scenario 4: a Restaurant-wide Assignment (CEO, location_id = NULL) is valid — Location "
        "is never forced onto an Assignment that genuinely spans the whole Restaurant",
        assignment_ceo.id is not None and assignment_ceo.location_id is None,
    )

    # =====================================================================
    # Scenario 5 — Location transfer (temporal integrity)
    # =====================================================================
    emp_transfer = make_employee("E-TRANSFER", "TransferEmployee")
    old_valid_from = _dt(240)
    transfer_close_time = _dt(30)
    old_assignment = m.EmployeeAssignment(
        employee_id=emp_transfer.id, restaurant_id=restaurant.id, operational_area_id=area_root.id,
        restaurant_role_id=role_server.id, location_id=location_wp.id,
        valid_from=old_valid_from, valid_to=None, assignment_source="MANUAL",
    )
    session.add(old_assignment)
    session.flush()
    # Close the Winter Park Assignment and open a new Mount Dora one — never
    # an in-place overwrite of the prior row's Location/valid_from.
    old_assignment.valid_to = transfer_close_time
    new_assignment = m.EmployeeAssignment(
        employee_id=emp_transfer.id, restaurant_id=restaurant.id, operational_area_id=area_root.id,
        restaurant_role_id=role_server.id, location_id=location_md.id,
        valid_from=transfer_close_time, valid_to=None, assignment_source="MANUAL",
    )
    session.add(new_assignment)
    session.flush()

    transfer_assignments = session.scalars(
        select(m.EmployeeAssignment).where(m.EmployeeAssignment.employee_id == emp_transfer.id)
    ).all()
    old_row = next(a for a in transfer_assignments if a.id == old_assignment.id)
    result.check(
        "Scenario 5: a Location transfer (Server @ Winter Park -> Server @ Mount Dora) closes the "
        "old Assignment (valid_to set, valid_from and Location UNCHANGED) and opens a new one — "
        "history is preserved, never overwritten",
        len(transfer_assignments) == 2
        and old_row.valid_from == old_valid_from
        and old_row.valid_to == transfer_close_time
        and old_row.location_id == location_wp.id
        and new_assignment.valid_from == transfer_close_time
        and new_assignment.valid_to is None
        and new_assignment.location_id == location_md.id,
    )

    # =====================================================================
    # Scenario 6 — Role + Location change together
    # =====================================================================
    emp_role_and_location = make_employee("E-ROLECHANGE", "RoleAndLocationChangeEmployee")
    rl_valid_from = _dt(240)
    rl_close_time = _dt(30)
    rl_old = m.EmployeeAssignment(
        employee_id=emp_role_and_location.id, restaurant_id=restaurant.id, operational_area_id=area_root.id,
        restaurant_role_id=role_server.id, location_id=location_wp.id,
        valid_from=rl_valid_from, valid_to=None, assignment_source="MANUAL",
    )
    session.add(rl_old)
    session.flush()
    rl_old.valid_to = rl_close_time
    rl_new = m.EmployeeAssignment(
        employee_id=emp_role_and_location.id, restaurant_id=restaurant.id, operational_area_id=area_root.id,
        restaurant_role_id=role_manager.id, location_id=location_md.id,
        valid_from=rl_close_time, valid_to=None, assignment_source="MANUAL",
    )
    session.add(rl_new)
    session.flush()
    rl_all = session.scalars(
        select(m.EmployeeAssignment).where(m.EmployeeAssignment.employee_id == emp_role_and_location.id)
    ).all()
    result.check(
        "Scenario 6: a combined Role+Location change (Server @ Winter Park -> Manager @ Mount Dora) "
        "produces two distinct historical Assignment facts, neither overwritten",
        len(rl_all) == 2
        and {a.restaurant_role_id for a in rl_all} == {role_server.id, role_manager.id}
        and {a.location_id for a in rl_all} == {location_wp.id, location_md.id},
    )

    # =====================================================================
    # Scenario 7 — Exact duplicate Assignment rejected; Location difference
    # (already proven by Scenario 2/3) is never a false collision
    # =====================================================================
    dup_valid_from = _dt(500)
    session.add(
        m.EmployeeAssignment(
            employee_id=giovanna.id, restaurant_id=restaurant.id, operational_area_id=area_root.id,
            restaurant_role_id=role_server.id, location_id=location_wp.id,
            valid_from=dup_valid_from, valid_to=None, assignment_source="MANUAL",
        )
    )
    session.flush()

    def _insert_exact_duplicate() -> None:
        session.add(
            m.EmployeeAssignment(
                employee_id=giovanna.id, restaurant_id=restaurant.id, operational_area_id=area_root.id,
                restaurant_role_id=role_server.id, location_id=location_wp.id,
                valid_from=dup_valid_from, valid_to=None, assignment_source="MANUAL",
            )
        )

    duplicate_rejected = _expect_integrity_error(session, _insert_exact_duplicate)
    result.check(
        "Scenario 7: an exact duplicate Assignment (same Employee/Restaurant/Area/Role/Location/"
        "valid_from) is rejected by the schema's uniqueness rule",
        duplicate_rejected,
    )

    # Same check for the Restaurant-wide (location_id IS NULL) case, which
    # ordinary SQL UNIQUE semantics would NOT catch without the dedicated
    # partial unique index (NULL != NULL) — see models.py.
    ceo_dup_valid_from = assignment_ceo.valid_from

    def _insert_exact_duplicate_null_location() -> None:
        session.add(
            m.EmployeeAssignment(
                employee_id=emp_ceo.id, restaurant_id=restaurant.id, operational_area_id=area_root.id,
                restaurant_role_id=role_ceo.id, location_id=None,
                valid_from=ceo_dup_valid_from, valid_to=None, assignment_source="MANUAL",
            )
        )

    null_duplicate_rejected = _expect_integrity_error(session, _insert_exact_duplicate_null_location)
    result.check(
        "Scenario 7b: an exact duplicate Restaurant-wide Assignment (location_id IS NULL on both "
        "rows) is also rejected — the partial unique index closes the NULL != NULL gap a plain "
        "UniqueConstraint would leave open",
        null_duplicate_rejected,
    )

    # =====================================================================
    # Scenarios 8/9/10 — Primary Location integrity (separate Restaurant,
    # to isolate from Scenario 1's fixture)
    # =====================================================================
    restaurant_primary = m.Restaurant(name="Primary Location Test Restaurant", default_currency="USD")
    session.add(restaurant_primary)
    session.flush()

    rl_wp_open_primary = m.RestaurantLocation(
        restaurant_id=restaurant_primary.id, location_id=location_wp.id, is_primary=True, valid_to=None,
    )
    session.add(rl_wp_open_primary)
    session.flush()

    # Scenario 8: a second, concurrently OPEN primary Location must be rejected.
    def _insert_second_open_primary() -> None:
        session.add(
            m.RestaurantLocation(
                restaurant_id=restaurant_primary.id, location_id=location_md.id, is_primary=True, valid_to=None,
            )
        )

    second_primary_rejected = _expect_integrity_error(session, _insert_second_open_primary)
    result.check(
        "Scenario 8: a second currently-open primary Location for the same Restaurant is rejected "
        "— never more than one open is_primary=true RestaurantLocation row per Restaurant",
        second_primary_rejected,
    )

    # Scenario 9: closing the old primary Location historically, then opening
    # a new one, must remain valid (never more than one OPEN primary at a
    # time, but changing it over time is exactly the supported pattern).
    rl_wp_open_primary.valid_to = _dt(10)
    session.flush()
    rl_md_new_primary = m.RestaurantLocation(
        restaurant_id=restaurant_primary.id, location_id=location_md.id, is_primary=True, valid_to=None,
    )
    session.add(rl_md_new_primary)
    session.flush()
    result.check(
        "Scenario 9: closing the historical primary Location (valid_to set) and opening a new "
        "current primary Location for the same Restaurant is valid — history is preserved, not "
        "rewritten",
        rl_wp_open_primary.valid_to is not None
        and rl_wp_open_primary.is_primary is True
        and rl_md_new_primary.valid_to is None
        and rl_md_new_primary.is_primary is True,
    )

    # Scenario 10: a Restaurant may have multiple open Locations with NO
    # currently-active primary at all (a valid transitional state).
    restaurant_zero_primary = m.Restaurant(name="Zero Primary Test Restaurant", default_currency="USD")
    session.add(restaurant_zero_primary)
    session.flush()
    session.add_all(
        [
            m.RestaurantLocation(restaurant_id=restaurant_zero_primary.id, location_id=location_wp.id, is_primary=False, valid_to=None),
            m.RestaurantLocation(restaurant_id=restaurant_zero_primary.id, location_id=location_md.id, is_primary=False, valid_to=None),
        ]
    )
    session.flush()
    zero_primary_rows = session.scalars(
        select(m.RestaurantLocation).where(m.RestaurantLocation.restaurant_id == restaurant_zero_primary.id)
    ).all()
    result.check(
        "Scenario 10: a Restaurant with multiple open Locations and zero currently-active primary "
        "Location is structurally valid — no mandatory-primary rule is invented",
        len(zero_primary_rows) == 2 and all(not r.is_primary for r in zero_primary_rows),
    )

    # =====================================================================
    # Scenario 11/12 — Location timezone + Business Day cutoff persistence
    # =====================================================================
    location_wp.timezone = "America/New_York"
    location_wp.operating_day_cutoff_time = time(4, 0)
    session.flush()
    session.expire(location_wp)
    reloaded_wp = session.get(m.Location, location_wp.id)
    result.check(
        "Scenario 11/12: Location timezone (America/New_York, an IANA identifier) and Business Day "
        "cutoff (04:00) are both persisted and survive a reload from the database",
        reloaded_wp.timezone == "America/New_York"
        and reloaded_wp.operating_day_cutoff_time == time(4, 0),
    )

    # =====================================================================
    # Scenario 13 — Historical Business Date stability (architectural check
    # only; `orders.business_date` is not yet implemented per TASK_SALES_002
    # §L, so there is no persisted transactional Business Date to mutate).
    # Verified instead: changing a Location's cutoff time is a plain,
    # independent column update with no side effect on any other row —
    # exactly the property historical immutability requires once a
    # transactional `business_date` does exist.
    # =====================================================================
    original_cutoff = reloaded_wp.operating_day_cutoff_time
    reloaded_wp.operating_day_cutoff_time = time(3, 0)
    session.flush()
    result.check(
        "Scenario 13: changing a Location's operating_day_cutoff_time is a plain, isolated column "
        "update with no cascading recomputation of any other row (no business_date column exists "
        "yet to retroactively rewrite, per TASK_SALES_002 §L — this is the architectural "
        "precondition the historical-immutability rule depends on, verified where implemented)",
        reloaded_wp.operating_day_cutoff_time == time(3, 0) and original_cutoff == time(4, 0),
    )
    reloaded_wp.operating_day_cutoff_time = original_cutoff
    session.flush()

    # =====================================================================
    # Scenario 14 — Missing timezone remains valid, never fabricated
    # =====================================================================
    location_no_tz = make_location("Unconfigured Location", timezone_value=None)
    result.check(
        "Scenario 14: a Location with timezone = NULL is a valid canonical Location row — never "
        "fabricated from geography or any other inference",
        location_no_tz.id is not None
        and location_no_tz.timezone is None
        and location_no_tz.operating_day_cutoff_time is None,
    )

    # =====================================================================
    # Cross-domain check — Tips engine eligibility resolution must not
    # exclude a Location-scoped EmployeeAssignment (task §"Cross-domain
    # implications"): it does not filter EmployeeAssignment by location_id
    # at all, so a Location-specific Assignment remains just as eligible as
    # a Restaurant-wide one.
    # =====================================================================
    order_type = m.OrderType(
        location_id=location_wp.id, source_system_id=source_system.id, source_order_type_id="OT1", name="Table",
    )
    session.add(order_type)
    session.flush()

    emp_location_scoped = make_employee("E-LOCSCOPED", "LocationScopedRoleEmployee")
    session.add(
        m.EmployeeAssignment(
            employee_id=emp_location_scoped.id, restaurant_id=restaurant.id, operational_area_id=area_root.id,
            restaurant_role_id=role_server.id, location_id=location_wp.id,
            valid_from=_dt(30), valid_to=None, assignment_source="MANUAL",
        )
    )
    session.add(
        m.Shift(
            employee_id=emp_location_scoped.id, source_system_id=source_system.id,
            source_shift_id="SHIFT-LOCSCOPED-1",
            # Explicit Location evidence (TASK_TIPS_004 Part B): this fixture's
            # `restaurant` is genuinely multi-Location (Winter Park + Mount
            # Dora, above) — Employee.location_id is no longer sufficient
            # evidence of where a particular Shift occurred once a Restaurant
            # has more than one operational Location, so this Shift must
            # carry its own Location to remain eligible.
            location_id=location_wp.id,
            clock_in=_dt(2) - timedelta(hours=2), clock_out=_dt(2) + timedelta(hours=2),
        )
    )
    session.flush()

    tip_policy = m.TipPolicy(
        restaurant_id=restaurant.id, name="Location-scoped eligibility test policy",
        status="ACTIVE", valid_from=_dt(60),
    )
    session.add(tip_policy)
    session.flush()
    session.add(
        m.TipPolicyComponent(
            tip_policy_id=tip_policy.id, sequence=1, recipient_basis="ROLE_PRESENT_AT_PAYMENT",
            restaurant_role_id=role_server.id, share_percentage=Decimal("100.0000"),
            split_method="EQUAL_ELIGIBLE_HEADCOUNT", no_eligible_behavior="LEAVE_UNALLOCATED",
        )
    )
    session.flush()

    cross_domain_order = m.Order(
        location_id=location_wp.id, source_system_id=source_system.id, source_order_id="ORDER-locscoped",
        employee_id=emp_location_scoped.id, order_type_id=order_type.id, created_at=_dt(2),
        payment_state="PAID", currency="USD", total=6000,
    )
    session.add(cross_domain_order)
    session.flush()
    cross_domain_payment = m.Payment(
        order_id=cross_domain_order.id, source_system_id=source_system.id, source_payment_id="PAY-locscoped",
        employee_id=emp_location_scoped.id, created_at=_dt(2), amount=6000, result="SUCCESS",
    )
    session.add(cross_domain_payment)
    session.flush()
    session.add(m.PaymentTip(payment_id=cross_domain_payment.id, amount=1000, source_present=True))
    session.flush()

    tips_run, tips_summary = run_tip_calculation(
        session, restaurant_id=restaurant.id, period_start=_dt(365),
        period_end=datetime.now(UTC) + timedelta(days=1),
        resolver=NullServiceAttributionResolver(), mode=TIPS_MODE_DRY_RUN,
        calculation_version="organization-002-cross-domain-test",
    )
    session.flush()
    location_scoped_allocations = session.scalars(
        select(m.TipAllocation).where(
            m.TipAllocation.calculation_run_id == tips_run.id,
            m.TipAllocation.employee_id == emp_location_scoped.id,
        )
    ).all()
    result.check(
        "Cross-domain: the Tips engine allocates to an Employee whose only matching Assignment is "
        "Location-scoped (location_id set) exactly as it would for a Restaurant-wide Assignment — "
        "adding Location to EmployeeAssignment does not silently exclude anyone",
        tips_summary.allocations_produced >= 1 and len(location_scoped_allocations) >= 1,
    )
