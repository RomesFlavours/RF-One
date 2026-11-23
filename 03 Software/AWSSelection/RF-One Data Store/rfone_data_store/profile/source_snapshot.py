"""Loads the fresh, read-only Clover employees/roles snapshot produced by
`03 Software/Clover Data Explorer/fetch_profile_bootstrap_snapshot.py`
(TASK_RESTAURANT_003 §3).

Pure disk read, same convention as `rfone_data_store/ingestion/clover/
reader.py` — this module never performs a network call itself; only the
Clover Data Explorer touches the live Clover API. Loading a snapshot is
optional: the bootstrap engine works from already-ingested canonical
`Employee`/`SourceRole`/`EmployeeSourceRole` facts alone when no snapshot is
supplied, and additionally cross-checks those facts against a supplied
snapshot for the `SOURCE_ROLE_RELATIONSHIP_INCONSISTENT` /
`PROFILE_MAPPING_WITHOUT_CURRENT_SOURCE_ROLE` reconciliation checks.

Never returns or logs an Employee display name/PIN — only opaque source ids
and counts, matching the report-safety convention this task requires.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# 03 Software/RF-One Data Store/rfone_data_store/profile/source_snapshot.py
#   .parents[3] == "03 Software/"
_SOFTWARE_DIR = Path(__file__).resolve().parents[3]
SNAPSHOT_ROOT = (
    _SOFTWARE_DIR / "Clover Data Explorer" / "data" / "generated_exports" / "_api_cache" / "restaurant_profile_bootstrap"
)


class SnapshotNotFoundError(Exception):
    """Raised when no fresh snapshot directory can be located."""


@dataclass
class FreshCloverSnapshot:
    fetched_at: datetime
    run_dir: Path

    employee_source_ids: set[str] = field(default_factory=set)
    role_source_ids: set[str] = field(default_factory=set)
    # (employee_source_id, role_source_id) pairs observed live, merged from
    # BOTH directions (Employee.roles and Role.employeesRef).
    employee_role_pairs: set[tuple[str, str]] = field(default_factory=set)
    # Pairs present in only one of the two directions in the raw fetch
    # itself (a genuine Clover-side relationship inconsistency, distinct
    # from any RF-One canonical-vs-live drift).
    bidirectional_mismatches: int = 0


def _load_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def latest_snapshot_dir(snapshot_root: Path | None = None) -> Path | None:
    root = snapshot_root or SNAPSHOT_ROOT
    if not root.is_dir():
        return None
    candidates = sorted(p for p in root.iterdir() if p.is_dir())
    return candidates[-1] if candidates else None


def load_latest_snapshot(snapshot_root: Path | None = None) -> FreshCloverSnapshot | None:
    """Returns `None` (never raises) when no snapshot has ever been fetched
    — the bootstrap engine treats that as "no live cross-check available
    this run," not an error, since the snapshot is optional evidence."""
    run_dir = latest_snapshot_dir(snapshot_root)
    if run_dir is None:
        return None
    return load_snapshot(run_dir)


def load_snapshot(run_dir: Path) -> FreshCloverSnapshot:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        raise SnapshotNotFoundError(f"No manifest.json under {run_dir}")
    manifest = _load_json(manifest_path)
    fetched_at = datetime.fromisoformat(manifest["fetched_at"])

    employees_expand_role = _load_json(run_dir / "employees_expand_role.json")
    roles_expand_employees = _load_json(run_dir / "roles_expand_employees.json")

    employee_ids: set[str] = set()
    role_ids: set[str] = set()
    pairs_from_employees: set[tuple[str, str]] = set()
    for emp in employees_expand_role:
        emp_id = emp.get("id")
        if not emp_id:
            continue
        employee_ids.add(emp_id)
        for role in (emp.get("roles") or {}).get("elements") or []:
            role_id = role.get("id")
            if role_id:
                pairs_from_employees.add((emp_id, role_id))

    pairs_from_roles: set[tuple[str, str]] = set()
    for role in roles_expand_employees:
        role_id = role.get("id")
        if not role_id:
            continue
        role_ids.add(role_id)
        for emp in (role.get("employeesRef") or {}).get("elements") or []:
            emp_id = emp.get("id")
            if emp_id:
                pairs_from_roles.add((emp_id, role_id))

    merged_pairs = pairs_from_employees | pairs_from_roles
    mismatches = len(pairs_from_employees.symmetric_difference(pairs_from_roles))

    return FreshCloverSnapshot(
        fetched_at=fetched_at,
        run_dir=run_dir,
        employee_source_ids=employee_ids,
        role_source_ids=role_ids,
        employee_role_pairs=merged_pairs,
        bidirectional_mismatches=mismatches,
    )
