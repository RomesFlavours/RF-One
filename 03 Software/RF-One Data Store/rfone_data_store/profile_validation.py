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
    ISSUE_CURRENT_EMPLOYEE_WITH_UNMAPPED_SOURCE_ROLE,
    ISSUE_CURRENT_EMPLOYEE_WITHOUT_SOURCE_ROLE,
    ISSUE_SOURCE_ROLE_WITHOUT_PROFILE_MAPPING,
    MODE_DRY_RUN,
    MODE_PERSIST,
    ROOT_AREA_CODE,
    bootstrap_restaurant_profile,
)
from .tips.engine import ISSUE_NO_VALID_POLICY, MODE_DRY_RUN as TIPS_MODE_DRY_RUN, run_tip_calculation
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
    emp_concurrent = make_employee("E2", "CurrentConcurrentRoles")   # Case: two SourceRoles
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

    # Case 3/4: SourceRole and RestaurantRole remain separate entities;
    # exact-name mapping is explicit (via a SourceRoleMapping row), not implicit.
    mapping_server = session.scalars(
        select(m.SourceRoleMapping).where(
            m.SourceRoleMapping.restaurant_id == restaurant.id, m.SourceRoleMapping.source_role_id == role_server.id
        )
    ).one()
    restaurant_role_server = session.get(m.RestaurantRole, mapping_server.restaurant_role_id)
    result.check(
        "Case 3/4: RestaurantRole is a distinct row in a distinct table from SourceRole (their "
        "integer ids are independent sequences, never compared or unified), connected only by an "
        "explicit SourceRoleMapping row, even though the bootstrap default name is identical",
        restaurant_role_server is not None
        and type(restaurant_role_server) is not type(role_server)
        and m.RestaurantRole.__tablename__ != m.SourceRole.__tablename__
        and restaurant_role_server.name == role_server.name
        and mapping_server.source_role_id == role_server.id
        and mapping_server.restaurant_role_id == restaurant_role_server.id
        and mapping_server.valid_from == t0_sync,
    )

    # Case 5: current Employee receives Assignment from T0, not before.
    assignment_single = session.scalars(
        select(m.EmployeeAssignment).where(
            m.EmployeeAssignment.employee_id == emp_single_role.id, m.EmployeeAssignment.restaurant_id == restaurant.id
        )
    ).one()
    result.check(
        "Case 5: current Employee's EmployeeAssignment.valid_from == T0, not before",
        assignment_single.valid_from == t0_sync
        and assignment_single.valid_to is None
        and assignment_single.restaurant_role_id == restaurant_role_server.id
        and assignment_single.operational_area_id == root_area.id
        and assignment_single.assignment_source == "SOURCE_ROLE_MAPPING",
    )

    # Case 6: historical stub receives no invented current Assignment.
    stub_assignments = session.scalars(
        select(m.EmployeeAssignment).where(m.EmployeeAssignment.employee_id == emp_stub.id)
    ).all()
    result.check(
        "Case 6: historical stub (display_name IS NULL) receives zero EmployeeAssignment rows",
        len(stub_assignments) == 0,
    )

    # Case 7: multiple current SourceRoles create legitimate concurrent Assignments.
    concurrent_assignments = session.scalars(
        select(m.EmployeeAssignment).where(m.EmployeeAssignment.employee_id == emp_concurrent.id)
    ).all()
    concurrent_role_ids = {a.restaurant_role_id for a in concurrent_assignments}
    result.check(
        "Case 7: an Employee with two current SourceRoles (Server + Manager) receives two "
        "concurrent, non-conflicting EmployeeAssignment rows",
        len(concurrent_assignments) == 2
        and all(a.valid_to is None for a in concurrent_assignments)
        and len(concurrent_role_ids) == 2,
    )

    # Case 8: current Employee without SourceRole creates an issue, not a guessed Assignment.
    no_role_assignments = session.scalars(
        select(m.EmployeeAssignment).where(m.EmployeeAssignment.employee_id == emp_no_role.id)
    ).all()
    no_role_issues = session.scalars(
        select(m.RestaurantProfileReconciliationIssue).where(
            m.RestaurantProfileReconciliationIssue.employee_id == emp_no_role.id,
            m.RestaurantProfileReconciliationIssue.issue_type == ISSUE_CURRENT_EMPLOYEE_WITHOUT_SOURCE_ROLE,
        )
    ).all()
    result.check(
        "Case 8: current Employee with zero SourceRoles gets zero guessed Assignments and an "
        "explicit CURRENT_EMPLOYEE_WITHOUT_SOURCE_ROLE issue",
        len(no_role_assignments) == 0 and len(no_role_issues) >= 1,
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
        "mappings/roles/areas/assignments reused, zero new issues) and leaves row counts unchanged",
        summary2.t0_created is False
        and summary2.managed_from == t0_sync
        and summary2.mappings_created == 0
        and summary2.restaurant_roles_created == 0
        and summary2.operational_areas_created == 0
        and summary2.assignments_created == 0
        and summary2.assignments_closed == 0
        and summary2.issues_created == 0
        and counts_before == counts_after,
    )

    # =====================================================================
    # Case 9: SourceRole without mapping -> CURRENT_EMPLOYEE_WITH_UNMAPPED_SOURCE_ROLE
    # (realistic path: an EmployeeSourceRole pointing at a SourceRole that is
    # OUT OF this Restaurant's Location scope, so bootstrap never mapped it)
    # =====================================================================
    other_location = m.Location(
        merchant_id=merchant.id, source_system_id=source_system.id,
        source_location_id="LOC2", name="Other Location", currency="USD",
    )
    session.add(other_location)
    session.flush()
    out_of_scope_role = m.SourceRole(
        location_id=other_location.id, source_system_id=source_system.id,
        source_role_id="R99", name="OutOfScope", source_system_role="EMPLOYEE",
    )
    session.add(out_of_scope_role)
    session.flush()
    link(emp_single_role, out_of_scope_role)
    session.flush()

    run3, summary3 = bootstrap_restaurant_profile(
        session, restaurant_id=restaurant.id, source_system_id=source_system.id,
        mode=MODE_PERSIST, sync_time=_dt(8),
    )
    session.flush()
    unmapped_issues = session.scalars(
        select(m.RestaurantProfileReconciliationIssue).where(
            m.RestaurantProfileReconciliationIssue.employee_id == emp_single_role.id,
            m.RestaurantProfileReconciliationIssue.issue_type == ISSUE_CURRENT_EMPLOYEE_WITH_UNMAPPED_SOURCE_ROLE,
        )
    ).all()
    result.check(
        "Case 9: an EmployeeSourceRole pointing at a SourceRole with no ACTIVE mapping for this "
        "Restaurant produces an explicit CURRENT_EMPLOYEE_WITH_UNMAPPED_SOURCE_ROLE issue, and "
        "does not create an Assignment for that Role",
        len(unmapped_issues) >= 1
        and session.scalars(
            select(m.EmployeeAssignment).where(
                m.EmployeeAssignment.employee_id == emp_single_role.id,
                m.EmployeeAssignment.restaurant_role_id.in_(
                    select(m.SourceRoleMapping.restaurant_role_id).where(
                        m.SourceRoleMapping.source_role_id == out_of_scope_role.id
                    )
                ),
            )
        ).first() is None,
    )
    result.check(
        "SOURCE_ROLE_WITHOUT_PROFILE_MAPPING defensive issue type is defined and importable "
        "(reserved for the case ordinary mapping self-healing cannot reach)",
        ISSUE_SOURCE_ROLE_WITHOUT_PROFILE_MAPPING == "SOURCE_ROLE_WITHOUT_PROFILE_MAPPING",
    )

    # =====================================================================
    # Case 10/11: source Role change closes the old Assignment and opens a
    # new one prospectively; no historical Assignment is overwritten.
    # =====================================================================
    change_assignment_before = session.scalars(
        select(m.EmployeeAssignment).where(m.EmployeeAssignment.employee_id == emp_change.id)
    ).one()
    original_id = change_assignment_before.id
    original_valid_from = change_assignment_before.valid_from

    # Simulate Clover: emp_change is no longer Server, now Manager.
    old_link = session.scalars(
        select(m.EmployeeSourceRole).where(
            m.EmployeeSourceRole.employee_id == emp_change.id, m.EmployeeSourceRole.source_role_id == role_server.id
        )
    ).one()
    session.delete(old_link)
    session.flush()
    link(emp_change, role_manager)
    session.flush()

    t1_sync = _dt(1)
    run4, summary4 = bootstrap_restaurant_profile(
        session, restaurant_id=restaurant.id, source_system_id=source_system.id,
        mode=MODE_PERSIST, sync_time=t1_sync,
    )
    session.flush()

    all_change_assignments = session.scalars(
        select(m.EmployeeAssignment).where(m.EmployeeAssignment.employee_id == emp_change.id)
    ).all()
    closed = [a for a in all_change_assignments if a.id == original_id]
    opened = [a for a in all_change_assignments if a.id != original_id]
    result.check(
        "Case 10/11: a detected source Role change closes the OLD EmployeeAssignment "
        "(valid_to = sync time, valid_from UNCHANGED — not overwritten) and opens a NEW one "
        "(valid_from = sync time, not backdated to T0)",
        len(closed) == 1
        and closed[0].valid_from == original_valid_from  # never overwritten
        and closed[0].valid_to == t1_sync
        and len(opened) == 1
        and opened[0].valid_from == t1_sync
        and opened[0].valid_to is None
        and opened[0].restaurant_role_id != closed[0].restaurant_role_id,
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
    # Case 15: real Tips engine still does not invent service ownership or
    # policy, even though EmployeeAssignments now exist for this Restaurant.
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

    tips_run, tips_summary = run_tip_calculation(
        session,
        restaurant_id=restaurant.id,
        period_start=_dt(365),
        period_end=datetime.now(UTC) + timedelta(days=1),
        resolver=NullServiceAttributionResolver(),
        mode=TIPS_MODE_DRY_RUN,
        calculation_version="profile-bootstrap-test",
    )
    session.flush()
    tips_issues = session.scalars(
        select(m.TipCalculationIssue).where(m.TipCalculationIssue.calculation_run_id == tips_run.id)
    ).all()
    result.check(
        "Case 15: after bootstrapping real EmployeeAssignments, the Tips engine still allocates "
        "nothing and still reports NO_VALID_POLICY (no service owner or policy was invented "
        "merely because Assignments now exist)",
        tips_summary.allocations_produced == 0
        and any(i.issue_type == ISSUE_NO_VALID_POLICY for i in tips_issues),
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
