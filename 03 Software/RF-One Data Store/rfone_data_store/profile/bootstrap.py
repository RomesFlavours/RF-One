"""Restaurant Profile bootstrap/sync from source (Clover) configuration
(TASK_RESTAURANT_003).

Central principle, preserved throughout:

    Source configuration != canonical Restaurant semantics

A source system (Clover) is evidence used to instantiate ONE Restaurant's
Profile through explicit, Restaurant-scoped mappings — never an automatic
ontology equivalence, even when the initial configured names coincide
(`SourceRole.name == RestaurantRole.name` is a bootstrap DEFAULT, not an
identity: the two remain distinct rows connected only by a `SourceRoleMapping`
row).

Canonical path (task §8):

    current Employee (display_name IS NOT NULL)
    -> current EmployeeSourceRole
    -> explicit SourceRole -> RestaurantRole mapping (this Restaurant only)
    -> root OperationalArea (minimal profile granularity, task §7)
    -> EmployeeAssignment valid_from = T0 (first bootstrap) or "now" (a
       later-detected role change, task §13 — never backdated before T0)

Historical Employee stubs (display_name IS NULL) are never touched: no
mapping is looked up for them, no EmployeeAssignment is created (task §8.6).

This module never talks to Clover directly — it reads already-ingested
canonical facts (`Employee`, `SourceRole`, `EmployeeSourceRole`, all
populated by the separate `ingest_clover.py` pipeline) plus an optional
`FreshCloverSnapshot` (see `source_snapshot.py`) for live congruence
cross-checks. It never commits: like `tips/engine.py`'s
`run_tip_calculation`, it only adds/flushes rows into the caller's session;
the caller decides DRY_RUN (rollback) vs PERSIST (commit).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m

if TYPE_CHECKING:
    from .source_snapshot import FreshCloverSnapshot

MODE_DRY_RUN = "DRY_RUN"
MODE_PERSIST = "PERSIST"

STATUS_RUNNING = "RUNNING"
STATUS_COMPLETE = "COMPLETE"
STATUS_FAILED = "FAILED"

CONTROL_STATUS_ACTIVE = "ACTIVE"

MAPPING_STATUS_ACTIVE = "ACTIVE"
MAPPING_SOURCE_BOOTSTRAP = "CLOVER_SOURCE_ROLE_BOOTSTRAP"

ASSIGNMENT_SOURCE_SOURCE_ROLE_MAPPING = "SOURCE_ROLE_MAPPING"

# Minimal-granularity root Operational Area (task §7). NOT an inference of
# FOH/BOH/Bar/Kitchen/Management from Clover role names.
ROOT_AREA_CODE = "ROOT"
ROOT_AREA_NAME = "Restaurant Operations"
ROOT_AREA_DESCRIPTION = (
    "Minimal Restaurant Profile granularity (TASK_RESTAURANT_003): Clover does "
    "not currently expose reliable structured Operational Area evidence for "
    "this Restaurant. This single root Area represents the whole Restaurant "
    "operational context — it is NOT an inference of FOH/BOH/Bar/Kitchen/"
    "Management from Clover role names, and it is not a claim that the "
    "Restaurant has no internal functional areas. It can be refined into "
    "more granular, explicitly Product-Owner-configured Areas later without "
    "invalidating any Assignment created against it."
)

SEVERITY_BLOCKING = "BLOCKING"
SEVERITY_WARNING = "WARNING"

ISSUE_CURRENT_EMPLOYEE_WITHOUT_SOURCE_ROLE = "CURRENT_EMPLOYEE_WITHOUT_SOURCE_ROLE"
ISSUE_SOURCE_ROLE_WITHOUT_PROFILE_MAPPING = "SOURCE_ROLE_WITHOUT_PROFILE_MAPPING"
ISSUE_PROFILE_MAPPING_WITHOUT_CURRENT_SOURCE_ROLE = "PROFILE_MAPPING_WITHOUT_CURRENT_SOURCE_ROLE"
ISSUE_CURRENT_EMPLOYEE_WITH_UNMAPPED_SOURCE_ROLE = "CURRENT_EMPLOYEE_WITH_UNMAPPED_SOURCE_ROLE"
ISSUE_EMPLOYEE_ASSIGNMENT_MISSING_AFTER_BOOTSTRAP = "EMPLOYEE_ASSIGNMENT_MISSING_AFTER_BOOTSTRAP"
ISSUE_SOURCE_ROLE_RELATIONSHIP_INCONSISTENT = "SOURCE_ROLE_RELATIONSHIP_INCONSISTENT"
ISSUE_DUPLICATE_OR_OVERLAPPING_MAPPING = "DUPLICATE_OR_OVERLAPPING_MAPPING"


@dataclass
class BootstrapSummary:
    managed_from: datetime | None = None
    t0_created: bool = False

    current_source_employees: int = 0
    historical_stubs_skipped: int = 0
    current_source_roles: int = 0

    mappings_created: int = 0
    mappings_reused: int = 0

    restaurant_roles_created: int = 0
    restaurant_roles_reused: int = 0

    operational_areas_created: int = 0
    operational_areas_reused: int = 0

    assignments_created: int = 0
    assignments_reused: int = 0
    assignments_closed: int = 0

    issues_created: int = 0
    issues_reused: int = 0
    blocking_issue_count: int = 0
    warning_issue_count: int = 0

    snapshot_used: bool = False
    snapshot_fetched_at: datetime | None = None


def _to_naive_utc(dt: datetime) -> datetime:
    """Every other timestamp already persisted by this codebase round-trips
    through SQLite as a naive (no-offset) string (e.g. Shift/Payment rows
    written by `ingest_clover.py`) — `DateTime(timezone=True)` is honored by
    PostgreSQL but SQLite has no native timezone-aware storage, so a
    tz-aware Python value stringifies WITH a `+00:00` suffix while a naive
    one does not, and SQLite compares these TEXT-encoded columns
    lexicographically. Mixing the two formats in one column would silently
    corrupt range comparisons (e.g. a future Tips calculation's
    `EmployeeAssignment.valid_from <= t` query). Normalizing every
    timestamp this engine writes to naive UTC keeps it consistent with the
    rest of the schema regardless of what tzinfo the caller supplies."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _restaurant_location_ids(session: Session, restaurant_id: int) -> set[int]:
    rows = session.scalars(
        select(m.RestaurantLocation.location_id).where(
            m.RestaurantLocation.restaurant_id == restaurant_id
        )
    ).all()
    return set(rows)


def _get_or_create_source_control(
    session: Session, restaurant_id: int, source_system_id: int, sync_time: datetime
) -> tuple["m.RestaurantProfileSourceControl", bool]:
    control = session.scalars(
        select(m.RestaurantProfileSourceControl).where(
            m.RestaurantProfileSourceControl.restaurant_id == restaurant_id,
            m.RestaurantProfileSourceControl.source_system_id == source_system_id,
            m.RestaurantProfileSourceControl.status == CONTROL_STATUS_ACTIVE,
        )
    ).first()
    if control is not None:
        return control, False

    control = m.RestaurantProfileSourceControl(
        restaurant_id=restaurant_id,
        source_system_id=source_system_id,
        managed_from=sync_time,
        status=CONTROL_STATUS_ACTIVE,
        snapshot_note=(
            f"Restaurant Profile source control established (T0) at {sync_time.isoformat()} "
            "by the TASK_RESTAURANT_003 bootstrap engine."
        ),
    )
    session.add(control)
    session.flush()
    return control, True


def _get_or_create_root_area(session: Session, restaurant_id: int) -> tuple["m.OperationalArea", bool]:
    area = session.scalars(
        select(m.OperationalArea).where(
            m.OperationalArea.restaurant_id == restaurant_id,
            m.OperationalArea.code == ROOT_AREA_CODE,
        )
    ).first()
    if area is not None:
        return area, False

    area = m.OperationalArea(
        restaurant_id=restaurant_id,
        name=ROOT_AREA_NAME,
        code=ROOT_AREA_CODE,
        description=ROOT_AREA_DESCRIPTION,
        active=True,
    )
    session.add(area)
    session.flush()
    return area, True


def _get_or_create_restaurant_role(
    session: Session, restaurant_id: int, name: str, source_role: "m.SourceRole", sync_time: datetime
) -> tuple["m.RestaurantRole", bool]:
    role = session.scalars(
        select(m.RestaurantRole).where(
            m.RestaurantRole.restaurant_id == restaurant_id,
            m.RestaurantRole.name == name,
        )
    ).first()
    if role is not None:
        return role, False

    role = m.RestaurantRole(
        restaurant_id=restaurant_id,
        name=name,
        description=(
            f"Bootstrapped {sync_time.date().isoformat()} from Clover named Role "
            f"'{name}' (internal source_role_id={source_role.id}) via TASK_RESTAURANT_003 — "
            "a Restaurant Profile configuration decision using the same initial name, "
            "never an automatic equivalence with the Clover SourceRole."
        ),
        active=True,
    )
    session.add(role)
    session.flush()
    return role, True


def _ensure_area_role(session: Session, area_id: int, role_id: int) -> None:
    existing = session.get(m.OperationalAreaRole, {"operational_area_id": area_id, "restaurant_role_id": role_id})
    if existing is None:
        session.add(m.OperationalAreaRole(operational_area_id=area_id, restaurant_role_id=role_id))


def _add_issue(
    session: Session,
    run: "m.ProfileBootstrapRun",
    summary: BootstrapSummary,
    *,
    issue_type: str,
    severity: str,
    details: str,
    employee_id: int | None = None,
    source_role_id: int | None = None,
    restaurant_role_id: int | None = None,
    mapping_id: int | None = None,
) -> None:
    """Dedup against any still-unresolved (`status IS NULL`) issue with the
    same natural key, across ANY prior run — never re-created by a later
    idempotent bootstrap/sync (task §14)."""
    existing = session.scalars(
        select(m.RestaurantProfileReconciliationIssue).where(
            m.RestaurantProfileReconciliationIssue.restaurant_id == run.restaurant_id,
            m.RestaurantProfileReconciliationIssue.issue_type == issue_type,
            m.RestaurantProfileReconciliationIssue.employee_id.is_(employee_id),
            m.RestaurantProfileReconciliationIssue.source_role_id.is_(source_role_id),
            m.RestaurantProfileReconciliationIssue.restaurant_role_id.is_(restaurant_role_id),
            m.RestaurantProfileReconciliationIssue.mapping_id.is_(mapping_id),
            m.RestaurantProfileReconciliationIssue.status.is_(None),
        )
    ).first()
    if existing is not None:
        summary.issues_reused += 1
        if severity == SEVERITY_BLOCKING:
            summary.blocking_issue_count += 1
        else:
            summary.warning_issue_count += 1
        return

    session.add(
        m.RestaurantProfileReconciliationIssue(
            bootstrap_run_id=run.id,
            restaurant_id=run.restaurant_id,
            issue_type=issue_type,
            severity=severity,
            employee_id=employee_id,
            source_role_id=source_role_id,
            restaurant_role_id=restaurant_role_id,
            mapping_id=mapping_id,
            details=details,
        )
    )
    summary.issues_created += 1
    if severity == SEVERITY_BLOCKING:
        summary.blocking_issue_count += 1
    else:
        summary.warning_issue_count += 1


def bootstrap_restaurant_profile(
    session: Session,
    *,
    restaurant_id: int,
    source_system_id: int,
    mode: str = MODE_DRY_RUN,
    sync_time: datetime,
    fresh_snapshot: "FreshCloverSnapshot | None" = None,
) -> tuple["m.ProfileBootstrapRun", BootstrapSummary]:
    """Bootstrap (first run) or sync (later run) the Restaurant Profile for
    `restaurant_id` from `source_system_id`'s already-ingested current
    configuration. Idempotent: reruns with unchanged source configuration
    create/close nothing beyond what already exists (task §14). `sync_time`
    must be supplied by the caller (never file/process time implicitly) —
    it becomes T0 on the very first run, and the "now" used for any
    later-detected role change (task §13).
    """
    sync_time = _to_naive_utc(sync_time)
    run = m.ProfileBootstrapRun(
        restaurant_id=restaurant_id,
        source_system_id=source_system_id,
        started_at=sync_time,
        status=STATUS_RUNNING,
        mode=mode,
    )
    session.add(run)
    session.flush()

    summary = BootstrapSummary()
    if fresh_snapshot is not None:
        summary.snapshot_used = True
        summary.snapshot_fetched_at = fresh_snapshot.fetched_at

    location_ids = _restaurant_location_ids(session, restaurant_id)

    # --- T0 ----------------------------------------------------------------
    control, created = _get_or_create_source_control(session, restaurant_id, source_system_id, sync_time)
    summary.managed_from = control.managed_from
    summary.t0_created = created
    t0 = control.managed_from

    # --- Root Operational Area ----------------------------------------------
    root_area, area_created = _get_or_create_root_area(session, restaurant_id)
    if area_created:
        summary.operational_areas_created += 1
    else:
        summary.operational_areas_reused += 1

    if not location_ids:
        run.status = STATUS_COMPLETE
        run.completed_at = sync_time
        run.notes = "No RestaurantLocation associated with this Restaurant — nothing to bootstrap."
        return run, summary

    # --- SourceRoles currently in scope (this Restaurant's Location(s)) ----
    current_source_roles = session.scalars(
        select(m.SourceRole).where(
            m.SourceRole.source_system_id == source_system_id,
            m.SourceRole.location_id.in_(location_ids),
        )
    ).all()
    summary.current_source_roles = len(current_source_roles)

    mapping_by_source_role_id: dict[int, "m.SourceRoleMapping"] = {}
    for source_role in current_source_roles:
        mapping = session.scalars(
            select(m.SourceRoleMapping).where(
                m.SourceRoleMapping.restaurant_id == restaurant_id,
                m.SourceRoleMapping.source_role_id == source_role.id,
                m.SourceRoleMapping.mapping_status == MAPPING_STATUS_ACTIVE,
            )
        ).all()
        if len(mapping) > 1:
            _add_issue(
                session, run, summary,
                issue_type=ISSUE_DUPLICATE_OR_OVERLAPPING_MAPPING,
                severity=SEVERITY_BLOCKING,
                details=(
                    f"SourceRole id={source_role.id} has {len(mapping)} ACTIVE "
                    f"SourceRoleMapping rows for restaurant_id={restaurant_id} — expected at "
                    "most one. Using the first found; the extras must be reviewed/retired "
                    "explicitly, not silently resolved."
                ),
                source_role_id=source_role.id,
            )
        if mapping:
            mapping_by_source_role_id[source_role.id] = mapping[0]
            summary.mappings_reused += 1
            continue

        restaurant_role, role_created = _get_or_create_restaurant_role(
            session, restaurant_id, source_role.name, source_role, sync_time
        )
        if role_created:
            summary.restaurant_roles_created += 1
        else:
            summary.restaurant_roles_reused += 1

        _ensure_area_role(session, root_area.id, restaurant_role.id)

        new_mapping = m.SourceRoleMapping(
            restaurant_id=restaurant_id,
            source_system_id=source_system_id,
            source_role_id=source_role.id,
            restaurant_role_id=restaurant_role.id,
            valid_from=t0,
            valid_to=None,
            mapping_status=MAPPING_STATUS_ACTIVE,
            mapping_source=MAPPING_SOURCE_BOOTSTRAP,
        )
        session.add(new_mapping)
        session.flush()
        mapping_by_source_role_id[source_role.id] = new_mapping
        summary.mappings_created += 1

    # Defensive: every current-scope SourceRole must now have a mapping.
    for source_role in current_source_roles:
        if source_role.id not in mapping_by_source_role_id:
            _add_issue(
                session, run, summary,
                issue_type=ISSUE_SOURCE_ROLE_WITHOUT_PROFILE_MAPPING,
                severity=SEVERITY_BLOCKING,
                details=(
                    f"SourceRole id={source_role.id} (restaurant_id={restaurant_id}) has no "
                    "ACTIVE SourceRoleMapping after bootstrap — mapping creation did not "
                    "complete for this Role; no RestaurantRole equivalence was guessed."
                ),
                source_role_id=source_role.id,
            )

    # --- Current Employees ---------------------------------------------------
    current_employees = session.scalars(
        select(m.Employee).where(
            m.Employee.location_id.in_(location_ids),
            m.Employee.display_name.is_not(None),
        )
    ).all()
    summary.current_source_employees = len(current_employees)

    historical_stub_ids = set(
        session.scalars(
            select(m.Employee.id).where(
                m.Employee.location_id.in_(location_ids),
                m.Employee.display_name.is_(None),
            )
        ).all()
    )
    summary.historical_stubs_skipped = len(historical_stub_ids)

    desired_role_ids_by_employee: dict[int, set[int]] = {}

    for employee in current_employees:
        source_roles_for_emp = session.scalars(
            select(m.EmployeeSourceRole).where(m.EmployeeSourceRole.employee_id == employee.id)
        ).all()

        desired_role_ids: set[int] = set()
        if not source_roles_for_emp:
            _add_issue(
                session, run, summary,
                issue_type=ISSUE_CURRENT_EMPLOYEE_WITHOUT_SOURCE_ROLE,
                severity=SEVERITY_WARNING,
                details=(
                    f"Employee id={employee.id} is a current Employee (has a display name) but "
                    "has zero EmployeeSourceRole rows — no EmployeeAssignment was guessed for "
                    "this Employee; any Assignment they previously held is being closed "
                    "(the absence of any current SourceRole is treated as explicit negative "
                    "evidence, not silence)."
                ),
                employee_id=employee.id,
            )
        else:
            for esr in source_roles_for_emp:
                mapping = mapping_by_source_role_id.get(esr.source_role_id)
                if mapping is None:
                    _add_issue(
                        session, run, summary,
                        issue_type=ISSUE_CURRENT_EMPLOYEE_WITH_UNMAPPED_SOURCE_ROLE,
                        severity=SEVERITY_BLOCKING,
                        details=(
                            f"Employee id={employee.id} has EmployeeSourceRole -> SourceRole "
                            f"id={esr.source_role_id}, which has no ACTIVE SourceRoleMapping for "
                            f"restaurant_id={restaurant_id} — this Role contributes no "
                            "EmployeeAssignment for this Employee; no equivalence was guessed."
                        ),
                        employee_id=employee.id,
                        source_role_id=esr.source_role_id,
                    )
                    continue
                desired_role_ids.add(mapping.restaurant_role_id)

        desired_role_ids_by_employee[employee.id] = desired_role_ids

        existing_assignments = session.scalars(
            select(m.EmployeeAssignment).where(
                m.EmployeeAssignment.employee_id == employee.id,
                m.EmployeeAssignment.restaurant_id == restaurant_id,
                m.EmployeeAssignment.operational_area_id == root_area.id,
            )
        ).all()
        has_any_prior_assignment = len(existing_assignments) > 0
        open_assignments = [a for a in existing_assignments if a.valid_to is None]
        open_role_ids = {a.restaurant_role_id for a in open_assignments}

        to_open = desired_role_ids - open_role_ids
        to_close = open_role_ids - desired_role_ids
        assignment_valid_from = t0 if not has_any_prior_assignment else sync_time

        for role_id in sorted(to_open):
            session.add(
                m.EmployeeAssignment(
                    employee_id=employee.id,
                    restaurant_id=restaurant_id,
                    operational_area_id=root_area.id,
                    restaurant_role_id=role_id,
                    valid_from=assignment_valid_from,
                    valid_to=None,
                    assignment_source=ASSIGNMENT_SOURCE_SOURCE_ROLE_MAPPING,
                    source_note=(
                        f"Bootstrapped/synced from active SourceRoleMapping at "
                        f"{assignment_valid_from.isoformat()} (TASK_RESTAURANT_003)."
                    ),
                )
            )
            summary.assignments_created += 1

        for a in open_assignments:
            if a.restaurant_role_id in to_close:
                a.valid_to = sync_time
                summary.assignments_closed += 1

        summary.assignments_reused += len(open_role_ids & desired_role_ids)

    session.flush()

    # Defensive post-condition: every desired role must now have an open
    # EmployeeAssignment (task §9's EMPLOYEE_ASSIGNMENT_MISSING_AFTER_BOOTSTRAP).
    for employee_id, desired_role_ids in desired_role_ids_by_employee.items():
        if not desired_role_ids:
            continue
        open_role_ids_now = set(
            session.scalars(
                select(m.EmployeeAssignment.restaurant_role_id).where(
                    m.EmployeeAssignment.employee_id == employee_id,
                    m.EmployeeAssignment.restaurant_id == restaurant_id,
                    m.EmployeeAssignment.operational_area_id == root_area.id,
                    m.EmployeeAssignment.valid_to.is_(None),
                )
            ).all()
        )
        missing = desired_role_ids - open_role_ids_now
        for role_id in sorted(missing):
            _add_issue(
                session, run, summary,
                issue_type=ISSUE_EMPLOYEE_ASSIGNMENT_MISSING_AFTER_BOOTSTRAP,
                severity=SEVERITY_BLOCKING,
                details=(
                    f"Employee id={employee_id} has an ACTIVE SourceRoleMapping to "
                    f"RestaurantRole id={role_id} but no open EmployeeAssignment for it after "
                    "bootstrap — the expected write did not take effect."
                ),
                employee_id=employee_id,
                restaurant_role_id=role_id,
            )

    # --- Live congruence cross-check (task §3, §9) --------------------------
    if fresh_snapshot is not None:
        _check_fresh_snapshot_congruence(
            session, run, summary,
            restaurant_id=restaurant_id,
            source_system_id=source_system_id,
            current_source_roles=current_source_roles,
            mapping_by_source_role_id=mapping_by_source_role_id,
            current_employees=current_employees,
            fresh_snapshot=fresh_snapshot,
        )

    run.status = STATUS_COMPLETE
    run.completed_at = sync_time
    run.notes = (
        f"T0={t0.isoformat()} employees={summary.current_source_employees} "
        f"stubs_skipped={summary.historical_stubs_skipped} "
        f"source_roles={summary.current_source_roles} "
        f"mappings_created={summary.mappings_created} mappings_reused={summary.mappings_reused} "
        f"assignments_created={summary.assignments_created} "
        f"assignments_reused={summary.assignments_reused} "
        f"assignments_closed={summary.assignments_closed} "
        f"issues_created={summary.issues_created} issues_reused={summary.issues_reused}"
    )
    return run, summary


def _check_fresh_snapshot_congruence(
    session: Session,
    run: "m.ProfileBootstrapRun",
    summary: BootstrapSummary,
    *,
    restaurant_id: int,
    source_system_id: int,
    current_source_roles: list["m.SourceRole"],
    mapping_by_source_role_id: dict[int, "m.SourceRoleMapping"],
    current_employees: list["m.Employee"],
    fresh_snapshot: "FreshCloverSnapshot",
) -> None:
    """Cross-checks canonical `EmployeeSourceRole` membership against a
    freshly fetched, live Clover snapshot (task §3) — detects drift between
    the already-ingested canonical facts and what Clover reports right now,
    without re-ingesting anything itself."""
    source_role_by_id = {sr.id: sr for sr in current_source_roles}
    employee_by_id = {e.id: e for e in current_employees}

    canonical_pairs: set[tuple[str, str]] = set()
    for employee in current_employees:
        if not employee.source_employee_id:
            continue
        esrs = session.scalars(
            select(m.EmployeeSourceRole).where(m.EmployeeSourceRole.employee_id == employee.id)
        ).all()
        for esr in esrs:
            source_role = source_role_by_id.get(esr.source_role_id)
            if source_role is None:
                continue
            canonical_pairs.add((employee.source_employee_id, source_role.source_role_id))

    missing_from_canonical = fresh_snapshot.employee_role_pairs - canonical_pairs
    stale_in_canonical = canonical_pairs - fresh_snapshot.employee_role_pairs

    if missing_from_canonical or stale_in_canonical:
        _add_issue(
            session, run, summary,
            issue_type=ISSUE_SOURCE_ROLE_RELATIONSHIP_INCONSISTENT,
            severity=SEVERITY_WARNING,
            details=(
                f"Live Clover snapshot (fetched {fresh_snapshot.fetched_at.isoformat()}) vs "
                f"canonical employee_source_roles: {len(missing_from_canonical)} pair(s) live "
                f"but not yet ingested canonically, {len(stale_in_canonical)} pair(s) canonical "
                "but no longer confirmed live. Canonical data was NOT modified by this check — "
                "re-running `ingest_clover.py` is the correct remediation if this persists."
            ),
        )

    # SourceRole ids mapped in RF-One that are no longer present in the live
    # roles list at all.
    live_role_ids = fresh_snapshot.role_source_ids
    for source_role in current_source_roles:
        mapping = mapping_by_source_role_id.get(source_role.id)
        if mapping is None:
            continue
        if source_role.source_role_id not in live_role_ids:
            _add_issue(
                session, run, summary,
                issue_type=ISSUE_PROFILE_MAPPING_WITHOUT_CURRENT_SOURCE_ROLE,
                severity=SEVERITY_WARNING,
                details=(
                    f"SourceRoleMapping id={mapping.id} (source_role_id={source_role.id}) is "
                    "ACTIVE, but that Clover Role id no longer appears in the live "
                    f"roles snapshot fetched {fresh_snapshot.fetched_at.isoformat()} — the "
                    "mapping was left in place (not auto-retired); review whether the Role was "
                    "renamed/removed in Clover."
                ),
                mapping_id=mapping.id,
                source_role_id=source_role.id,
            )
