"""Automated synthetic tests for the Restaurant Profile bootstrap engine
(TASK_RESTAURANT_003 §18).

Mirrors `tips_validation.py`'s pattern exactly: builds a synthetic
(never-real) fixture inside one transaction, runs the bootstrap engine
against it, asserts the required behaviors, and always rolls back — no
synthetic row is ever left in the target database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from . import models as m
from .profile.bootstrap import (
    ASSIGNMENT_SOURCE_SOURCE_ROLE_MAPPING,
    MODE_DRY_RUN,
    MODE_PERSIST,
    ROOT_AREA_CODE,
    bootstrap_restaurant_profile,
)
from .tips import distribution_engine

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
    # Naive UTC, matching what every timestamp round-trips to through
    # SQLite in this codebase (see bootstrap.py's `_to_naive_utc` docstring)
    # — avoids aware/naive comparison mismatches in the assertions below.
    base = datetime.now(UTC) - timedelta(days=days_ago)
    return base.replace(microsecond=0, tzinfo=None)


def _build_fixture_and_assert(session: Session, result: ValidationResult) -> None:
    # --- Base source/organization fixture -----------------------------
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

    restaurant = m.Restaurant(name="Synthetic Bootstrap Restaurant", default_currency="USD")
    session.add(restaurant)
    session.flush()
    session.add(m.RestaurantLocation(restaurant_id=restaurant.id, location_id=location.id, is_primary=True))
    session.flush()

    def make_source_role(source_id: str, name: str) -> m.SourceRole:
        role = m.SourceRole(
            location_id=location.id, source_system_id=source_system.id,
            source_role_id=source_id, name=name, source_system_role="EMPLOYEE",
        )
        session.add(role)
        session.flush()
        return role

    role_server = make_source_role("R1", "Server")
    role_manager = make_source_role("R2", "Manager")
    role_boh = make_source_role("R3", "BOH")

    def make_employee(source_id: str, name: str | None) -> m.Employee:
        emp = m.Employee(
            location_id=location.id, source_system_id=source_system.id,
            source_employee_id=source_id, display_name=name,
            system_role="EMPLOYEE",
        )
        session.add(emp)
        session.flush()
        return emp

    emp_single_role = make_employee("E1", "CurrentSingleRole")       # Case: one SourceRole
    emp_concurrent = make_employee("E2", "CurrentConcurrentRoles")   # Case: two SourceRoles at once -> now ambiguous
    emp_no_role = make_employee("E3", "CurrentNoSourceRole")         # Case: zero SourceRoles
    emp_change = make_employee("E4", "CurrentRoleChange")            # Case: role change over time
    emp_stub = make_employee("E5", None)                             # Historical stub

    def link(employee: m.Employee, role: m.SourceRole) -> None:
        session.add(
            m.EmployeeSourceRole(employee_id=employee.id, source_role_id=role.id, source_system_id=source_system.id)
        )

    link(emp_single_role, role_server)
    link(emp_concurrent, role_server)
    link(emp_concurrent, role_manager)
    link(emp_change, role_server)
    session.flush()

    t0_sync = _dt(10)

    # =====================================================================
    # First bootstrap (Case 1: first bootstrap from a current source snapshot)
    # =====================================================================
    run1, summary1 = bootstrap_restaurant_profile(
        session, restaurant_id=restaurant.id, source_system_id=source_system.id,
        mode=MODE_PERSIST, sync_time=t0_sync,
    )
    session.flush()

    result.check(
        "Case 1: first bootstrap establishes T0 and reports the current source counts",
        summary1.t0_created is True
        and summary1.managed_from == t0_sync
        and summary1.current_source_employees == 4  # single, concurrent, no_role, change (stub excluded)
        and summary1.current_source_roles == 3
        and summary1.historical_stubs_skipped == 1,
    )

    root_area = session.scalars(
        select(m.OperationalArea).where(
            m.OperationalArea.restaurant_id == restaurant.id, m.OperationalArea.code == ROOT_AREA_CODE
        )
    ).one()

    # Case 3/4 (OQ-7): Clover roles never create or determine RF-One roles.
    # No RestaurantRole and no SourceRoleMapping is created from the three
    # current Clover roles; RF-One roles are managed only in Registry.
    result.check(
        "Case 3/4 (OQ-7): the bootstrap creates ZERO RestaurantRole and ZERO SourceRoleMapping rows "
        "from the current Clover roles",
        session.scalar(select(func.count()).select_from(m.RestaurantRole)) == 0
        and session.scalar(select(func.count()).select_from(m.SourceRoleMapping)) == 0,
    )
    # Registry roles a person would create by hand in Anagrafica.
    restaurant_role_server = m.RestaurantRole(restaurant_id=restaurant.id, name="Server")
    restaurant_role_manager = m.RestaurantRole(restaurant_id=restaurant.id, name="Manager")
    session.add_all([restaurant_role_server, restaurant_role_manager])
    session.flush()

    # Case 5-8 (OQ-7, RF1_OPERATIONAL_DATABASE_001): the Registry is the only
    # authority for assignments. However many Clover roles a person has (one,
    # two, none) and whether the person is a historical stub, the bootstrap
    # creates no EmployeeAssignment and raises no per-Employee role issue.
    result.check(
        "Case 5-8 (OQ-7): the bootstrap creates ZERO EmployeeAssignment rows from Clover roles "
        "(single role, concurrent roles, no role, historical stub)",
        session.scalar(select(func.count()).select_from(m.EmployeeAssignment)) == 0
        and summary1.issues_created == 0,
    )

    # Case 12/13: exactly one root OperationalArea for this Restaurant —
    # never FOH/BOH/Bar/Kitchen inferred from the 3 distinct SourceRole names.
    all_areas = session.scalars(
        select(m.OperationalArea).where(m.OperationalArea.restaurant_id == restaurant.id)
    ).all()
    result.check(
        "Case 12/13: exactly one (root, ROOT-coded) OperationalArea exists for this Restaurant "
        "despite 3 distinct current SourceRole names (Server/Manager/BOH) — no FOH/BOH/Bar/Kitchen "
        "inference occurred",
        len(all_areas) == 1 and all_areas[0].code == ROOT_AREA_CODE and all_areas[0].name != "BOH",
    )

    # =====================================================================
    # Case 2: second identical bootstrap is idempotent
    # =====================================================================
    counts_before = _table_counts(session, restaurant.id)
    run2, summary2 = bootstrap_restaurant_profile(
        session, restaurant_id=restaurant.id, source_system_id=source_system.id,
        mode=MODE_PERSIST, sync_time=_dt(9),
    )
    session.flush()
    counts_after = _table_counts(session, restaurant.id)
    result.check(
        "Case 2: a second identical bootstrap run creates/closes nothing (T0 reused, all "
        "areas reused, zero new issues) and leaves row counts unchanged",
        summary2.t0_created is False
        and summary2.managed_from == t0_sync
        and summary2.operational_areas_created == 0
        and summary2.issues_created == 0
        and counts_before == counts_after,
    )

    # =====================================================================
    # Case 9-11 (OQ-7): a Clover role change never touches the Registry. A
    # Registry (MANUAL) assignment and an assignment written earlier by the
    # removed SOURCE_ROLE_MAPPING step both stay exactly as they were.
    # =====================================================================
    manual = m.EmployeeAssignment(
        employee_id=emp_change.id, restaurant_id=restaurant.id, operational_area_id=root_area.id,
        restaurant_role_id=restaurant_role_server.id, valid_from=_dt(9), valid_to=None, assignment_source="MANUAL",
    )
    legacy = m.EmployeeAssignment(
        employee_id=emp_single_role.id, restaurant_id=restaurant.id, operational_area_id=root_area.id,
        restaurant_role_id=restaurant_role_server.id, valid_from=t0_sync, valid_to=None,
        assignment_source=ASSIGNMENT_SOURCE_SOURCE_ROLE_MAPPING,
    )
    session.add_all([manual, legacy])
    session.flush()
    before = {a.id: (a.restaurant_role_id, a.valid_from, a.valid_to, a.assignment_source)
              for a in session.scalars(select(m.EmployeeAssignment))}

    # Simulate Clover: emp_change is no longer Server, now Manager; emp_single_role loses every role.
    for row in session.scalars(select(m.EmployeeSourceRole).where(
            m.EmployeeSourceRole.employee_id.in_([emp_change.id, emp_single_role.id]))).all():
        session.delete(row)
    session.flush()
    link(emp_change, role_manager)
    session.flush()

    t1_sync = _dt(1)
    run3, summary3 = bootstrap_restaurant_profile(
        session, restaurant_id=restaurant.id, source_system_id=source_system.id,
        mode=MODE_PERSIST, sync_time=_dt(8),
    )
    run4, summary4 = bootstrap_restaurant_profile(
        session, restaurant_id=restaurant.id, source_system_id=source_system.id,
        mode=MODE_PERSIST, sync_time=t1_sync,
    )
    session.flush()
    after = {a.id: (a.restaurant_role_id, a.valid_from, a.valid_to, a.assignment_source)
             for a in session.scalars(select(m.EmployeeAssignment))}
    result.check(
        "Case 9-11 (OQ-7): after a Clover role change (Server -> Manager) and a Clover role removal, "
        "the bootstrap opens, closes and changes no EmployeeAssignment — the Registry assignment and "
        "the historical SOURCE_ROLE_MAPPING assignment are unchanged",
        before == after
        and len(after) == 2
        and restaurant_role_manager.id not in {v[0] for v in after.values()},
    )
    result.check(
        "Case 9-11 (OQ-7): the Clover role change creates no RestaurantRole or SourceRoleMapping either",
        session.scalar(select(func.count()).select_from(m.RestaurantRole)) == 2
        and session.scalar(select(func.count()).select_from(m.SourceRoleMapping)) == 0,
    )

    # =====================================================================
    # Case 14: dry-run creates no persistent rows.
    # =====================================================================
    savepoint = session.begin_nested()
    run_count_before = session.scalar(select(func.count()).select_from(m.ProfileBootstrapRun))
    assignment_count_before = session.scalar(select(func.count()).select_from(m.EmployeeAssignment))
    run5, summary5 = bootstrap_restaurant_profile(
        session, restaurant_id=restaurant.id, source_system_id=source_system.id,
        mode=MODE_DRY_RUN, sync_time=_dt(0.5),
    )
    session.flush()
    run_count_during = session.scalar(select(func.count()).select_from(m.ProfileBootstrapRun))
    savepoint.rollback()
    run_count_after = session.scalar(select(func.count()).select_from(m.ProfileBootstrapRun))
    assignment_count_after = session.scalar(select(func.count()).select_from(m.EmployeeAssignment))
    result.check(
        "Case 14: a DRY_RUN bootstrap flushes rows visibly within its own transaction but a "
        "rollback (what the CLI performs when --persist is not passed) leaves zero net new rows",
        run_count_during == run_count_before + 1
        and run_count_after == run_count_before
        and assignment_count_after == assignment_count_before,
    )

    # =====================================================================
    # Case 15: the canonical Tip Distribution Engine still does not invent a
    # Rule, even though Registry EmployeeAssignments exist for this Restaurant
    # (TIPS_LEGACY_ENGINE_RETIREMENT_001 replaced the legacy `tips/engine.py`
    # call this check used to make with an equivalent call to the canonical
    # `tips/distribution_engine.py`).
    # =====================================================================
    order_type = m.OrderType(
        location_id=location.id, source_system_id=source_system.id, source_order_type_id="OT1", name="Table"
    )
    session.add(order_type)
    session.flush()
    tip_order = m.Order(
        location_id=location.id, source_system_id=source_system.id, source_order_id="ORDER-profile-test",
        employee_id=emp_single_role.id, order_type_id=order_type.id, created_at=_dt(2),
        payment_state="PAID", currency="USD", total=6000,
    )
    session.add(tip_order)
    session.flush()
    tip_payment = m.Payment(
        order_id=tip_order.id, source_system_id=source_system.id, source_payment_id="PAY-profile-test",
        employee_id=emp_single_role.id, created_at=_dt(2), amount=6000, result="SUCCESS",
    )
    session.add(tip_payment)
    session.flush()
    session.add(m.PaymentTip(payment_id=tip_payment.id, amount=1000, source_present=True))
    session.flush()

    tips_result = distribution_engine.calculate_tips(
        session,
        restaurant_id=restaurant.id,
        # `distribution_engine` always compares its period bounds against a
        # timezone-aware Settlement Time (see its own `_aware_utc` helper) —
        # unlike this file's own naive-UTC `_dt()` convention, so these two
        # bounds are made explicitly aware here (only for this call).
        period_start=_dt(365).replace(tzinfo=UTC),
        period_end=datetime.now(UTC) + timedelta(days=1),
    )
    session.flush()
    tip_order_allocations = [line for line in tips_result.lines if line.order_id == tip_order.id]
    result.check(
        "Case 15: with Registry EmployeeAssignments present, the canonical Tip Distribution Engine "
        "still allocates nothing for this Order — an active Tip Distribution Rule is restaurant-"
        "configured data, never invented merely because EmployeeAssignments now exist",
        tips_result.blocked_reason is None
        and tips_result.summary.rules_applied == 0
        and len(tip_order_allocations) == 0,
    )

    result.check(
        "all bootstrap runs completed with COMPLETE status",
        all(r.status == "COMPLETE" for r in (run1, run2, run3, run4, run5)),
    )


def _table_counts(session: Session, restaurant_id: int) -> dict[str, int]:
    return {
        "operational_areas": session.scalar(
            select(func.count()).select_from(m.OperationalArea).where(m.OperationalArea.restaurant_id == restaurant_id)
        ),
        "restaurant_roles": session.scalar(
            select(func.count()).select_from(m.RestaurantRole).where(m.RestaurantRole.restaurant_id == restaurant_id)
        ),
        "operational_area_roles": session.scalar(
            select(func.count()).select_from(m.OperationalAreaRole)
        ),
        "source_role_mappings": session.scalar(
            select(func.count()).select_from(m.SourceRoleMapping).where(m.SourceRoleMapping.restaurant_id == restaurant_id)
        ),
        "employee_assignments": session.scalar(
            select(func.count()).select_from(m.EmployeeAssignment).where(m.EmployeeAssignment.restaurant_id == restaurant_id)
        ),
        "reconciliation_issues": session.scalar(
            select(func.count()).select_from(m.RestaurantProfileReconciliationIssue).where(
                m.RestaurantProfileReconciliationIssue.restaurant_id == restaurant_id
            )
        ),
    }
