"""Restaurant Profile bootstrap/sync from source (Clover) configuration
(TASK_RESTAURANT_003), as limited by OQ-7.

OQ-7 (RF1_OPERATIONAL_DATABASE_001, Product Owner 2026-11-21): the Registry
(Anagrafica) is the only authority for RF-One roles, departments and
assignments. Clover roles never create, suggest, prefill or change any of
them. What this bootstrap still does:

    T0 (`RestaurantProfileSourceControl.managed_from`)
    root OperationalArea "Restaurant Operations" (minimal granularity, task §7)
    counts of current Clover roles / employees / historical stubs (evidence)
    optional drift check of ingested Clover employee-role facts against a
    fresh read-only snapshot (an ingestion check, never applied to RF-One)

Removed by OQ-7: RestaurantRole + ACTIVE SourceRoleMapping creation from
every current Clover role, the per-Employee EmployeeAssignment open/close
step (`assignment_source = SOURCE_ROLE_MAPPING`) and their issues. Rows they
wrote earlier stay unchanged as history.

This module never talks to Clover directly — it reads already-ingested
canonical facts (`Employee`, `SourceRole`, `EmployeeSourceRole`, all
populated by the separate `ingest_clover.py` pipeline) plus an optional
`FreshCloverSnapshot` (see `source_snapshot.py`) for live congruence
cross-checks. It never commits: like `tips/engine.py`'s
`run_tip_calculation`, it only adds/flushes rows into the caller's session;
the caller decides DRY_RUN (rollback) vs PERSIST (commit).
"""

from __future__ import annotations

from ..employee_directory import employees_for_locations

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


# Provenance of assignments written by the former bootstrap step. Kept only to recognise that
# history; nothing writes it any more (OQ-7).
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

ISSUE_SOURCE_ROLE_RELATIONSHIP_INCONSISTENT = "SOURCE_ROLE_RELATIONSHIP_INCONSISTENT"


@dataclass
class BootstrapSummary:
    managed_from: datetime | None = None
    t0_created: bool = False

    current_source_employees: int = 0
    historical_stubs_skipped: int = 0
    current_source_roles: int = 0

    operational_areas_created: int = 0
    operational_areas_reused: int = 0

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

    # OQ-7 (Product Owner 2026-11-21): a Clover role never creates or determines an RF-One role. The
    # former step that created a RestaurantRole and an ACTIVE SourceRoleMapping for every current Clover
    # role (and the issue that asked for a missing mapping) was removed. Existing RestaurantRoles and
    # SourceRoleMapping rows are kept unchanged as history; RF-One roles are managed only in Registry.

    # --- Current Employees ---------------------------------------------------
    current_employees = session.scalars(
        employees_for_locations(location_ids).where(
            ((m.Employee.location_id.in_(location_ids)) & (m.Employee.source_system_id == source_system_id)) |
            m.Employee.id.in_(select(m.EmployeeCloverLink.employee_id).where(
                m.EmployeeCloverLink.location_id.in_(location_ids), m.EmployeeCloverLink.employee_id.is_not(None))),
            m.Employee.display_name.is_not(None),
        )
    ).all()
    summary.current_source_employees = len(current_employees)

    historical_stub_ids = set(
        session.scalars(
            employees_for_locations(location_ids).with_only_columns(m.Employee.id).where(
                m.Employee.display_name.is_(None),
            )
        ).all()
    )
    summary.historical_stubs_skipped = len(historical_stub_ids)

    # OQ-7 (RF1_OPERATIONAL_DATABASE_001, Product Owner 2026-11-21): the Registry (Anagrafica) is the
    # only authority for role assignments. A Clover role never creates, closes, prefills or suggests an
    # EmployeeAssignment: the former SourceRole -> EmployeeAssignment step was removed from this
    # bootstrap. Assignments it wrote earlier (`assignment_source = SOURCE_ROLE_MAPPING`) stay as
    # Registry history and are never changed here.

    # --- Live congruence cross-check (task §3, §9) --------------------------
    if fresh_snapshot is not None:
        _check_fresh_snapshot_congruence(
            session, run, summary,
            restaurant_id=restaurant_id,
            source_system_id=source_system_id,
            current_source_roles=current_source_roles,
            current_employees=current_employees,
            fresh_snapshot=fresh_snapshot,
        )

    run.status = STATUS_COMPLETE
    run.completed_at = sync_time
    run.notes = (
        f"T0={t0.isoformat()} employees={summary.current_source_employees} "
        f"stubs_skipped={summary.historical_stubs_skipped} "
        f"source_roles={summary.current_source_roles} "
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
        esrs = session.scalars(
            select(m.EmployeeSourceRole).where(m.EmployeeSourceRole.employee_id == employee.id)
        ).all()
        for esr in esrs:
            source_role = source_role_by_id.get(esr.source_role_id)
            if source_role is None:
                continue
            external_ids = set(session.scalars(select(m.EmployeeCloverLink.external_employee_id).where(
                m.EmployeeCloverLink.employee_id == employee.id,
                m.EmployeeCloverLink.location_id == source_role.location_id)))
            if not external_ids and employee.location_id == source_role.location_id and employee.source_employee_id:
                external_ids.add(employee.source_employee_id)
            canonical_pairs.update((external_id, source_role.source_role_id) for external_id in external_ids)

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
