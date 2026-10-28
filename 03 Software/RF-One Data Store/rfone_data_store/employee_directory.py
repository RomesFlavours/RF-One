"""Shared employee identity and source observations. No network and no commits.

Employee remains the canonical identity used by Tips, Payroll and Sales. A
provider record with a possible existing person stays pending until confirmed.
Only source fields on links change during imports; management stays on Employee
and its existing assignment/compensation records.
"""
from __future__ import annotations

from datetime import datetime, timezone
from difflib import SequenceMatcher
from hashlib import sha256
import json
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m


def _normalized(value):
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", value or "").casefold()))


def safe_snapshot(raw):
    """Explicit allowlist: employee PINs and other credentials never enter history."""
    fields = ("id", "name", "email", "customId", "role")
    result = {key: raw.get(key) for key in fields}
    # Roles can be a tier string or expanded provider role objects.
    if isinstance(result["role"], dict):
        result["role"] = {k: result["role"].get(k) for k in ("id", "name", "systemRole")}
    result["roles"] = [
        {k: role.get(k) for k in ("id", "name", "systemRole")}
        for role in (raw.get("roles") or {}).get("elements", [])
        if isinstance(role, dict)
    ]
    return result


def _event(db, action, *, employee_id=None, link=None, account_id=None, details=None):
    db.add(m.EmployeeDirectoryEvent(
        employee_id=employee_id, link_id=link.id if link else None,
        account_id=account_id, action=action, details=details or {},
    ))


def candidates(db, snapshot):
    """Suggestions only, including email matches; never identity decisions."""
    name = _normalized(snapshot.get("name"))
    email = (snapshot.get("email") or "").strip().casefold()
    email_ids = set()
    source_names = {}
    for link in db.scalars(select(m.EmployeeCloverLink).where(m.EmployeeCloverLink.employee_id.is_not(None))):
        source_names.setdefault(link.employee_id, []).append(_normalized((link.snapshot or {}).get("name")))
        if email and ((link.snapshot or {}).get("email") or "").strip().casefold() == email:
            email_ids.add(link.employee_id)
    suggestions = []
    for employee in db.scalars(select(m.Employee).order_by(m.Employee.display_name, m.Employee.id)):
        names = [_normalized(employee.display_name), *source_names.get(employee.id, [])]
        score = max((SequenceMatcher(None, name, other).ratio() for other in names if name and other), default=0)
        if employee.id in email_ids or score >= 0.80:
            suggestions.append({"employee": employee, "reason": "Email" if employee.id in email_ids else "Name", "score": score})
    return sorted(suggestions, key=lambda row: (row["reason"] != "Email", -row["score"]))


def ensure_legacy_links(db):
    """Also supports fixtures/imports made after migration; no matching by name."""
    rows = db.execute(
        select(m.Employee, m.Location.source_location_id)
        .join(m.Location, m.Location.id == m.Employee.location_id)
        .join(m.SourceSystem, m.SourceSystem.id == m.Employee.source_system_id)
        .where(m.SourceSystem.code == "CLOVER", m.Employee.source_employee_id.is_not(None),
               m.Location.source_system_id == m.Employee.source_system_id,
               m.Location.source_location_id.is_not(None))
    )
    for employee, merchant_id in rows:
        link = db.scalar(select(m.EmployeeCloverLink).where(
            m.EmployeeCloverLink.merchant_id == merchant_id,
            m.EmployeeCloverLink.external_employee_id == employee.source_employee_id))
        if link is None:
            db.add(m.EmployeeCloverLink(employee_id=employee.id, location_id=employee.location_id,
                   merchant_id=merchant_id, external_employee_id=employee.source_employee_id, state="UNVERIFIED"))
            db.flush()


def import_snapshot(db, *, location_id, merchant_id, records, observed_at=None, run_id=None, complete=True):
    """Apply one complete, validated employee collection atomically in caller's transaction.

    Incomplete reads are rejected BEFORE any write, including legacy seeding.
    New records with a candidate stay unlinked, preventing duplicate people.
    """
    if not complete:
        raise ValueError("Incomplete employee collection; existing site states preserved.")
    location = db.get(m.Location, location_id)
    source = db.get(m.SourceSystem, location.source_system_id) if location else None
    if not location or not source or source.code != "CLOVER" or location.source_location_id != merchant_id:
        raise ValueError("Employee collection merchant does not match the configured Clover Location.")
    if not isinstance(records, list):
        raise ValueError("Invalid employee collection.")
    seen = set()
    for raw in records:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not raw["id"].strip():
            raise ValueError("Employee collection has an invalid identity; site states preserved.")
        if raw["id"] in seen:
            raise ValueError("Duplicate external employee identity in collection; site states preserved.")
        for key in ("name", "email", "customId"):
            if raw.get(key) is not None and not isinstance(raw[key], str):
                raise ValueError("Invalid employee source field; site states preserved.")
        seen.add(raw["id"])
    snapshots = [safe_snapshot(raw) for raw in records]  # validate before mutations
    # Serialize identity decisions across merchants, not just within a site's
    # acquisition lock. Simultaneous WP/MD imports must see each other's people.
    db.scalar(select(m.SourceSystem).where(m.SourceSystem.id == source.id).with_for_update())
    ensure_legacy_links(db)
    observed_at = observed_at or datetime.now(timezone.utc)
    resolved = {}
    pending = []
    for snapshot in snapshots:
        external_id = snapshot["id"]
        link = db.scalar(select(m.EmployeeCloverLink).where(
            m.EmployeeCloverLink.merchant_id == merchant_id,
            m.EmployeeCloverLink.external_employee_id == external_id).with_for_update())
        if link is None:
            link = m.EmployeeCloverLink(location_id=location_id, merchant_id=merchant_id,
                                       external_employee_id=external_id, state="PRESENT")
            db.add(link)
            db.flush()
            if not candidates(db, snapshot):
                employee = m.Employee(location_id=location_id, display_name=snapshot.get("name"),
                                      custom_id=snapshot.get("customId"), source_system_id=source.id,
                                      source_employee_id=external_id,
                                      system_role=snapshot.get("role") if isinstance(snapshot.get("role"), str) else None)
                db.add(employee)
                db.flush()
                link.employee_id = employee.id
                _event(db, "CREATE", employee_id=employee.id, link=link)
        if link.location_id != location_id:
            raise ValueError("External employee identity already belongs to a different configured Location.")
        if link.snapshot != snapshot or link.state != "PRESENT":
            _event(db, "IMPORT", employee_id=link.employee_id, link=link,
                   details={"snapshot": snapshot, "previous_state": link.state})
        link.snapshot = snapshot
        link.last_seen_at = observed_at
        link.last_run_id = run_id
        link.state = "PRESENT"
        if link.employee_id is not None:
            resolved[external_id] = link.employee_id
        else:
            pending.append(link.id)
    for link in db.scalars(select(m.EmployeeCloverLink).where(m.EmployeeCloverLink.merchant_id == merchant_id)):
        if link.external_employee_id not in seen and link.state != "MISSING_REVIEW":
            _event(db, "MISSING_REVIEW", employee_id=link.employee_id, link=link,
                   details={"run_id": run_id})
            link.state = "MISSING_REVIEW"
    db.flush()
    # Historical work can still refer to people absent from today's roster.
    resolved.update({l.external_employee_id: l.employee_id for l in db.scalars(
        select(m.EmployeeCloverLink).where(m.EmployeeCloverLink.merchant_id == merchant_id,
                                         m.EmployeeCloverLink.employee_id.is_not(None)))})
    return resolved, pending


def attach_link(db, *, link_id, employee_id=None, create_new=False, account_id=None):
    link = db.scalar(select(m.EmployeeCloverLink).where(m.EmployeeCloverLink.id == link_id).with_for_update())
    if link is None:
        raise ValueError("Clover link not found.")
    if link.employee_id is not None:
        raise ValueError("This link is already confirmed. Historical identities cannot be reassigned here.")
    if create_new:
        location = db.get(m.Location, link.location_id)
        employee = m.Employee(location_id=link.location_id, display_name=(link.snapshot or {}).get("name"),
                              custom_id=(link.snapshot or {}).get("customId"),
                              source_system_id=location.source_system_id,
                              source_employee_id=link.external_employee_id)
        db.add(employee)
        db.flush()
    else:
        employee = db.get(m.Employee, employee_id) if employee_id is not None else None
        if employee is None:
            raise ValueError("Choose an existing RF-One employee or explicitly create a new person.")
    # Multiple external accounts for one merchant require investigation, not a silent merge.
    other = db.scalar(select(m.EmployeeCloverLink).where(
        m.EmployeeCloverLink.employee_id == employee.id, m.EmployeeCloverLink.merchant_id == link.merchant_id))
    if other:
        raise ValueError("This person already has a Clover account at this merchant. Review the source identity first.")
    link.employee_id = employee.id
    _event(db, "LINK", employee_id=employee.id, link=link, account_id=account_id,
           details={"create_new": create_new})
    db.flush()
    return employee


def source_conflicts(links):
    result = {}
    for field in ("name", "email", "customId", "role", "roles"):
        values = {}
        for link in links:
            if link.state == "PRESENT" and link.snapshot is not None:
                value = link.snapshot.get(field)
                # Missing vs provided is a visible discrepancy too.
                values[link.merchant_id] = value
        if len({json.dumps(v, sort_keys=True) for v in values.values()}) > 1:
            result[field] = values
    return result


def review_fingerprint(links):
    state = [(l.id, l.state, l.snapshot) for l in sorted(links, key=lambda l: l.id)]
    return sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


def is_reviewed(db, employee_id, links):
    last = db.scalar(select(m.EmployeeDirectoryEvent).where(
        m.EmployeeDirectoryEvent.employee_id == employee_id,
        m.EmployeeDirectoryEvent.action == "REVIEW").order_by(m.EmployeeDirectoryEvent.id.desc()))
    return bool(last and last.details.get("fingerprint") == review_fingerprint(links))


def review(db, employee_id, links, account_id):
    _event(db, "REVIEW", employee_id=employee_id, account_id=account_id,
           details={"fingerprint": review_fingerprint(links)})


def update_management(db, employee, *, display_name, custom_id, active, account_id):
    if not display_name or len(display_name) > 255 or len(custom_id or "") > 64:
        raise ValueError("A name (maximum 255 characters) and a custom ID up to 64 characters are required.")
    before = {key: getattr(employee, key) for key in ("display_name", "custom_id", "active")}
    employee.display_name = display_name
    employee.custom_id = custom_id or None
    employee.active = active
    _event(db, "MANAGEMENT", employee_id=employee.id, account_id=account_id,
           details={"before": before, "after": {key: getattr(employee, key) for key in before}})
