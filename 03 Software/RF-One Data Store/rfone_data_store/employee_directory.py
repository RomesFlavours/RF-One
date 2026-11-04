"""Shared employee identity and source observations. No network and no commits.

Employee remains the canonical identity used by Tips, Payroll and Sales. A
provider record stays pending until a human confirms its RF-One identity.
Complete Clover roster and clock observations drive site/person cessation.
Reference management and domain history are preserved; accounts are disabled on dismissal.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from hashlib import sha256
import json
import re
import unicodedata

from sqlalchemy import func, select, update, text
from uuid import uuid4
from sqlalchemy.exc import IntegrityError
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
    for employee in db.scalars(canonical_employees().order_by(m.Employee.display_name, m.Employee.id)):
        names = [_normalized(employee.display_name), *source_names.get(employee.id, [])]
        score = max((max(SequenceMatcher(None, name, other).ratio(),
                         SequenceMatcher(None, " ".join(sorted(name.split())), " ".join(sorted(other.split()))).ratio())
                     for other in names if name and other), default=0)
        if email and (employee.email or "").strip().casefold() == email:
            email_ids.add(employee.id)
        if employee.id in email_ids or score >= 0.80:
            suggestions.append({"employee": employee, "reason": "Email" if employee.id in email_ids else "Name", "score": score})
    return sorted(suggestions, key=lambda row: (row["reason"] != "Email", -row["score"]))


def canonical_employees():
    return select(m.Employee).where(~m.Employee.id.in_(select(m.EmployeeIdentityAlias.employee_id)))


def employees_for_locations(location_ids):
    """Canonical people with origin, source or Workforce site evidence.

    Missing source links remain historical evidence, not termination. No joins
    that multiply people and no implicit current-employment filter: consumers
    must retain former employees when displaying historical work or payments.
    Accepts an ID sequence or a single-column SQL select.
    """
    linked = select(m.EmployeeCloverLink.employee_id).where(
        m.EmployeeCloverLink.location_id.in_(location_ids),
        m.EmployeeCloverLink.employee_id.is_not(None),
    )
    restaurant_ids = select(m.RestaurantLocation.restaurant_id).where(m.RestaurantLocation.location_id.in_(location_ids))
    assigned = select(m.EmployeeAssignment.employee_id).where(
        m.EmployeeAssignment.location_id.in_(location_ids) |
        (m.EmployeeAssignment.location_id.is_(None) & m.EmployeeAssignment.restaurant_id.in_(restaurant_ids)))
    return canonical_employees().where(
        m.Employee.location_id.in_(location_ids) | m.Employee.id.in_(linked) | m.Employee.id.in_(assigned)
    )


def employee_is_active(employee, links):
    """Canonical current employment eligibility, including automatic dismissal."""
    return employee.active is not False and employee.directory_eligible is not False and employee.dismissed_at is None


def employee_location_ids(employee, links, *, include_historical=False):
    """Relevant sites; historical selectors retain all known workplaces."""
    if include_historical:
        return {site for site in (employee.location_id, *(link.location_id for link in links)) if site is not None}
    if links:
        # Current sites first; a person whose only absences are undecided
        # (no clock scan yet, or suspended) keeps them. Ended positions leave.
        return ({link.location_id for link in links if link.state in ("PRESENT", "UNVERIFIED")}
                or {link.location_id for link in links if link.state != "DISMISSED"})
    return {employee.location_id} if employee.location_id is not None else set()


@dataclass(frozen=True)
class EmployeeOption:
    id: int
    display_name: str | None
    location_ids: tuple[int, ...]
    location_names: tuple[str, ...]
    is_active: bool
    is_selected: bool


def employee_options(db, *, location_ids=None, include_inactive=False, selected_employee_ids=()):
    """Read-only canonical choices. Caller supplies its authorized site scope.

    A selected retired ID resolves to its canonical person, but never bypasses
    location scope. Historical/reconciliation callers opt into inactive people.
    Uses a bounded number of queries rather than one query per person/site.
    """
    scope = None if location_ids is None else set(db.scalars(
        select(m.Location.id).where(m.Location.id.in_(location_ids))))
    query = canonical_employees() if scope is None else employees_for_locations(scope)
    employees = list(db.scalars(query))
    by_employee = {employee.id: [] for employee in employees}
    for link in db.scalars(select(m.EmployeeCloverLink).where(
        m.EmployeeCloverLink.employee_id.in_(by_employee))):
        by_employee[link.employee_id].append(link)
    selected_ids = set(selected_employee_ids)
    aliases = dict(db.execute(select(m.EmployeeIdentityAlias.employee_id,
        m.EmployeeIdentityAlias.canonical_employee_id).where(
            m.EmployeeIdentityAlias.employee_id.in_(selected_ids))).all())
    selected_ids = {aliases.get(identity, identity) for identity in selected_ids}
    # Workforce owns assignments. Read their site evidence without copying it.
    assignment_sites = {employee.id: set() for employee in employees}
    now = datetime.now(timezone.utc)
    assignment_query = select(m.EmployeeAssignment.employee_id,
        func.coalesce(m.EmployeeAssignment.location_id, m.RestaurantLocation.location_id)).outerjoin(
            m.RestaurantLocation, m.RestaurantLocation.restaurant_id == m.EmployeeAssignment.restaurant_id
        ).where(m.EmployeeAssignment.employee_id.in_(by_employee))
    if not include_inactive:
        assignment_query = assignment_query.where(
            ((m.EmployeeAssignment.valid_from <= now) &
             (m.EmployeeAssignment.valid_to.is_(None) | (m.EmployeeAssignment.valid_to > now))) |
            m.EmployeeAssignment.employee_id.in_(selected_ids))
    for identity, site in db.execute(assignment_query):
        if site is not None:
            assignment_sites[identity].add(site)
    locations = {loc.id: loc.name for loc in db.scalars(
        select(m.Location) if scope is None else select(m.Location).where(m.Location.id.in_(scope)))}
    options = []
    for employee in employees:
        links = by_employee[employee.id]
        active = bool(employee_is_active(employee, links))
        selected = employee.id in selected_ids
        if not include_inactive and not active and not selected:
            continue
        sites = employee_location_ids(employee, links, include_historical=include_inactive or selected) | assignment_sites[employee.id]
        if not include_inactive and not selected:
            ended_sites = {link.location_id for link in links if link.state == "DISMISSED"}
            live_sites = {link.location_id for link in links if link.state != "DISMISSED"}
            sites -= ended_sites - live_sites
        if scope is not None:
            sites &= scope
            if not sites:
                continue
        site_ids = tuple(sorted((site for site in sites if site in locations),
                                key=lambda site: (locations[site].casefold(), site)))
        options.append(EmployeeOption(employee.id, employee.display_name, site_ids,
                       tuple(locations[site] for site in site_ids), active, selected))
    return sorted(options, key=lambda option: ((option.display_name or "").casefold(), option.id))


def resolve_employee_id(db, employee_id):
    """Public identity resolver for consumers holding a previously issued ID."""
    alias = db.get(m.EmployeeIdentityAlias, employee_id)
    return alias.canonical_employee_id if alias else employee_id


def consolidate(db, *, from_employee_id, into_employee_id, account_id=None):
    """Explicit identity confirmation, never fuzzy matching or source precedence.

    Every declared operational employee FK moves together. Source snapshots and
    work history survive; the retired row remains recoverable through an alias.
    If domain uniqueness rules conflict, the savepoint rolls back the ENTIRE
    consolidation rather than guessing how to combine pay/assignments/history.
    """
    from_employee_id = resolve_employee_id(db, from_employee_id)
    into_employee_id = resolve_employee_id(db, into_employee_id)
    if from_employee_id == into_employee_id:
        raise ValueError("These records already refer to the same RF-One person.")
    locked = list(db.scalars(select(m.Employee).where(m.Employee.id.in_(
        sorted([from_employee_id, into_employee_id]))).order_by(m.Employee.id).with_for_update()))
    if len(locked) != 2:
        raise ValueError("Employee identity not found.")
    old = next(e for e in locked if e.id == from_employee_id)
    old_values = {key: getattr(old, key) for key in ("display_name", "email", "phone", "custom_id", "active", "location_id")}
    moved = {}
    try:
        with db.begin_nested():
            account_links = list(db.scalars(select(m.EmployeeContextLink).where(
                m.EmployeeContextLink.employee_id.in_([from_employee_id, into_employee_id]),
                m.EmployeeContextLink.rfone_account_id.is_not(None))))
            if len(account_links) > 1:
                real = [link for link in account_links
                        if not is_provisional_account(db, db.get(m.RFOneAccount, link.rfone_account_id))]
                if len(real) > 1:
                    raise ValueError("Both identities have operational RF1 accounts. Resolve those accounts before consolidation.")
                keep = real[0] if real else next(link for link in account_links if link.employee_id == into_employee_id)
                for link in account_links:
                    if link is not keep:
                        _event(db, "ACCOUNT_REPLACED", employee_id=into_employee_id, account_id=account_id,
                               details={"previous_account_id": link.rfone_account_id, "account_id": keep.rfone_account_id})
                        db.delete(link)
                db.flush()
            for table in m.Base.metadata.tables.values():
                if table.name in ("employees", "employee_identity_aliases"):
                    continue
                for column in table.columns:
                    if any(fk.target_fullname == "employees.id" for fk in column.foreign_keys):
                        changed = db.execute(update(table).where(column == from_employee_id).values(
                            {column.name: into_employee_id})).rowcount
                        if changed:
                            moved[f"{table.name}.{column.name}"] = changed
            # Keep aliases flattened, so every old ID resolves in one lookup.
            db.execute(update(m.EmployeeIdentityAlias).where(
                m.EmployeeIdentityAlias.canonical_employee_id == from_employee_id
            ).values(canonical_employee_id=into_employee_id))
            db.add(m.EmployeeIdentityAlias(employee_id=from_employee_id,
                canonical_employee_id=into_employee_id, account_id=account_id))
            _event(db, "CONSOLIDATE", employee_id=into_employee_id, account_id=account_id,
                   details={"retired_employee_id": from_employee_id, "retained_management": old_values,
                            "moved_references": moved})
            db.flush()
    except IntegrityError as exc:
        raise ValueError("Identity consolidation conflicts with existing role, payroll or work-history rules. "
                         "Nothing was moved. Resolve the conflicting records before retrying.") from exc
    db.expire_all()
    ensure_employee_account(db, db.get(m.Employee, into_employee_id))
    refresh_lifecycle(db, into_employee_id)
    return db.get(m.Employee, into_employee_id)


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


def import_snapshot(db, *, location_id, merchant_id, records, observed_at=None, run_id=None, complete=True,
                    clock_records=None, clock_decisions=True):
    """Apply one complete, validated employee collection atomically in caller's transaction.

    Incomplete reads are rejected BEFORE any write, including legacy seeding.
    Every unknown external identity stays unlinked until explicit approval.
    `clock_records` is the complete /shifts collection read BEFORE the roster.
    Without it, absences stay MISSING_REVIEW (never a cessation). Offline
    snapshots pass `clock_decisions=False`: evidence only, no lifecycle change.
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
    clock_evidence = clock_observations(clock_records) if clock_records is not None else None
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
        if link.external_employee_id not in seen and link.state not in ("MISSING_REVIEW", "DISMISSED"):
            _event(db, "MISSING_REVIEW", employee_id=link.employee_id, link=link,
                   details={"run_id": run_id})
            link.state = "MISSING_REVIEW"
    db.flush()
    if clock_evidence is not None:
        apply_clock_observations(db, location_id=location_id, merchant_id=merchant_id,
                                 observations=clock_evidence, observed_at=observed_at, decide=clock_decisions)
        pending = [link.id for link in db.scalars(select(m.EmployeeCloverLink).where(
            m.EmployeeCloverLink.merchant_id == merchant_id)) if pending_requires_review(db, link)]
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
    if not has_clock_evidence(link):
        raise ValueError("A Clover identity needs a clock-in or clock-out before employee registration.")
    if create_new:
        location = db.get(m.Location, link.location_id)
        employee = m.Employee(location_id=link.location_id, display_name=(link.snapshot or {}).get("name"),
                              custom_id=(link.snapshot or {}).get("customId"),
                              source_system_id=location.source_system_id,
                              source_employee_id=link.external_employee_id)
        db.add(employee)
        db.flush()
    else:
        employee = db.scalar(select(m.Employee).where(m.Employee.id == resolve_employee_id(db, employee_id)).with_for_update()) if employee_id is not None else None
        if employee is None:
            raise ValueError("Choose an existing RF-One employee or explicitly create a new person.")
    link.employee_id = employee.id
    ensure_employee_account(db, employee)
    refresh_lifecycle(db, employee.id)
    _event(db, "LINK", employee_id=employee.id, link=link, account_id=account_id,
           details={"create_new": create_new})
    db.flush()
    # EMPLOYEE_DIRECTORY_RECORD_HOLD_001 — work acquired while this identity
    # was pending is attributed now, through its Clover ID, in the same
    # transaction as the confirmation.
    from .technical.connectors.clover.identity_holds import reattribute_link
    counts = reattribute_link(db, link)
    _event(db, "REATTRIBUTE", employee_id=employee.id, link=link, account_id=account_id,
           details={"external_employee_id": link.external_employee_id, "counts": counts})
    db.flush()
    return employee


def observe_historical_employee(db, *, location_id, merchant_id, raw, available, observed_at, run_id):
    """Resolve source-backed historical references without changing RF-One management.

    This is a single-object observation, NEVER a complete roster or an absence
    scan. A 404 retains the reference and last known profile, not a termination.
    """
    location = db.get(m.Location, location_id)
    if not location or location.source_location_id != merchant_id or not raw.get("id"):
        raise ValueError("Historical employee reference does not match the configured merchant.")
    ensure_legacy_links(db)
    link = db.scalar(select(m.EmployeeCloverLink).where(m.EmployeeCloverLink.merchant_id == merchant_id,
        m.EmployeeCloverLink.external_employee_id == raw["id"]).with_for_update())
    if link and link.employee_id is not None:
        return db.get(m.Employee, link.employee_id)
    if link is not None:
        return None
    link = m.EmployeeCloverLink(location_id=location_id, merchant_id=merchant_id,
        external_employee_id=raw["id"], snapshot=safe_snapshot(raw), last_seen_at=observed_at,
        last_run_id=run_id, state="UNVERIFIED" if available else "MISSING_REVIEW")
    db.add(link)
    db.flush()
    _event(db, "HISTORICAL_PENDING", link=link,
           details={"snapshot": safe_snapshot(raw), "profile_available": available})
    return None


def source_conflicts(links):
    """Current observations only. Reviewed spelling differences stay in history."""
    result = {}
    present = [link for link in links if link.state == "PRESENT"]
    for field in ("name", "email", "customId", "role", "roles"):
        values = {str(link.id): (link.snapshot or {}).get(field) for link in present}
        if len({json.dumps(value, sort_keys=True) for value in values.values()}) > 1:
            result[field] = values
    accounts = {}
    for link in present:
        accounts.setdefault(link.merchant_id, []).append(link.external_employee_id)
    duplicates = {merchant: ids for merchant, ids in accounts.items() if len(ids) > 1}
    if duplicates:
        result["duplicate_accounts"] = duplicates
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


_UNSET = object()


def update_management(db, employee, *, display_name, custom_id, active, account_id, email=_UNSET, phone=_UNSET):
    email = employee.email if email is _UNSET else email
    phone = employee.phone if phone is _UNSET else phone
    if employee.id is not None:
        linked = db.scalar(select(m.EmployeeCloverLink.id).where(m.EmployeeCloverLink.employee_id == employee.id).limit(1))
        if linked and active != employee.active:
            raise ValueError("Clover-linked employment status is maintained by complete synchronization.")
    if not display_name or len(display_name) > 255 or len(custom_id or "") > 64:
        raise ValueError("A name (maximum 255 characters) and a custom ID up to 64 characters are required.")
    if len(email or "") > 255 or len(phone or "") > 64:
        raise ValueError("Email or phone is too long.")
    before = {key: getattr(employee, key) for key in ("display_name", "custom_id", "active", "email", "phone")}
    employee.email, employee.phone = (email or "").strip() or None, (phone or "").strip() or None
    employee.display_name = display_name
    employee.custom_id = custom_id or None
    employee.active = active
    if employee.id is not None and active is False:
        disable_employee_account(db, employee.id)
    if employee.id is not None:
        _event(db, "MANAGEMENT", employee_id=employee.id, account_id=account_id,
               details={"before": before, "after": {key: getattr(employee, key) for key in before}})


CONTEXT_LABELS = {"RFONE_ACCOUNT": "Account RF1", "ACTING_IDENTITY": "Identità operativa",
                  "TRAINING": "Formazione", "CANDIDATE": "Candidato", "PROJECT_RESPONSIBLE": "Responsabile di progetto"}

CONTEXTS = {
    "RFONE_ACCOUNT": (m.RFOneAccount, "rfone_account_id", "display_name"),
    "ACTING_IDENTITY": (m.ActingIdentity, "acting_identity_id", "display_name"),
    "TRAINING": (m.TrainingAccount, "training_account_id", "username"),
    "CANDIDATE": (m.CandidatePerson, "candidate_person_id", "full_name"),
    "PROJECT_RESPONSIBLE": (m.ProjectResponsible, "project_responsible_id", "name"),
}


def create_person(db, *, display_name, email=None, phone=None, account_id=None):
    person = m.Employee()
    update_management(db, person, display_name=(display_name or "").strip(), custom_id="",
                      active=None, email=email, phone=phone, account_id=account_id)
    db.add(person)
    db.flush()
    ensure_employee_account(db, person)
    _event(db, "RF1_CREATE", employee_id=person.id, account_id=account_id)
    return person


def context_person_id(db, kind, target_id):
    """Resolve explicit person/authentication bridges, never names or privileges."""
    if kind not in CONTEXTS:
        raise ValueError("Unknown person context.")
    if target_id is None:
        return None
    queue, visited, people = [(kind, target_id)], set(), set()
    while queue:
        current_kind, identity = queue.pop()
        if (current_kind, identity) in visited:
            continue
        visited.add((current_kind, identity))
        column = getattr(m.EmployeeContextLink, CONTEXTS[current_kind][1])
        direct = db.scalar(select(m.EmployeeContextLink.employee_id).where(column == identity))
        if direct is not None:
            people.add(resolve_employee_id(db, direct))
        if current_kind == "RFONE_ACCOUNT":
            queue.extend(("TRAINING", value) for value in db.scalars(select(m.RFOneTrainingIdentityLink.training_account_id).where(
                m.RFOneTrainingIdentityLink.rfone_account_id == identity)))
        elif current_kind == "TRAINING":
            actor = db.scalar(select(m.TrainingAccount.acting_identity_id).where(m.TrainingAccount.id == identity))
            if actor is not None:
                queue.append(("ACTING_IDENTITY", actor))
            queue.extend(("RFONE_ACCOUNT", value) for value in db.scalars(select(m.RFOneTrainingIdentityLink.rfone_account_id).where(
                m.RFOneTrainingIdentityLink.training_account_id == identity)))
        elif current_kind == "ACTING_IDENTITY":
            queue.extend(("TRAINING", value) for value in db.scalars(select(m.TrainingAccount.id).where(
                m.TrainingAccount.acting_identity_id == identity)))
    if len(people) > 1:
        raise ValueError("Conflicting confirmed person links in the account/Training identity chain.")
    return next(iter(people), None)


def link_context(db, *, employee_id, kind, target_id, account_id=None):
    if kind not in CONTEXTS:
        raise ValueError("Unknown person context.")
    model, field, _ = CONTEXTS[kind]
    person_id = resolve_employee_id(db, employee_id)
    person = db.scalar(select(m.Employee).where(m.Employee.id == person_id).with_for_update())
    if person is not None and resolve_employee_id(db, person_id) != person_id:
        return link_context(db, employee_id=resolve_employee_id(db, person_id), kind=kind, target_id=target_id, account_id=account_id)
    target = db.scalar(select(model).where(model.id == target_id).with_for_update())
    if person is None or target is None:
        raise ValueError("Person or context record not found.")
    if kind == "ACTING_IDENTITY" and target.kind != "HUMAN_USER":
        raise ValueError("Only human acting identities can be linked to a person.")
    if kind == "TRAINING" and db.get(m.ActingIdentity, target.acting_identity_id).kind != "HUMAN_USER":
        raise ValueError("A person can only link a human Training identity.")
    if kind == "RFONE_ACCOUNT":
        current = db.scalar(select(m.EmployeeContextLink).where(
            m.EmployeeContextLink.employee_id == person.id, m.EmployeeContextLink.rfone_account_id.is_not(None)))
        if current and current.rfone_account_id != target_id:
            if not is_provisional_account(db, db.get(m.RFOneAccount, current.rfone_account_id)):
                raise ValueError("This employee already has an RF1 account. Review the existing account first.")
        if (current is None or current.rfone_account_id != target_id) and is_provisional_account(db, target):
            # Replaced shells stay INACTIVE, unlinked and unusable (PO decision 2026-11-03).
            raise ValueError("A provisional RF1 account cannot be linked; choose the person's real account.")
    if kind in ("TRAINING", "ACTING_IDENTITY"):
        query = select(m.RFOneTrainingIdentityLink.rfone_account_id)
        if kind == "TRAINING":
            query = query.where(m.RFOneTrainingIdentityLink.training_account_id == target_id)
        else:
            query = query.join(m.TrainingAccount, m.TrainingAccount.id == m.RFOneTrainingIdentityLink.training_account_id).where(
                m.TrainingAccount.acting_identity_id == target_id)
        incoming = set(db.scalars(query))
        if incoming and incoming != confirmed_account_ids(db, person.id):
            raise ValueError("Link the person's existing RF1 account first; Training cannot introduce a second account.")
    known_person = context_person_id(db, kind, target_id)
    if known_person is not None and known_person != person.id:
        raise ValueError("Conflicts with an existing confirmed person association. Unlink and review explicitly first.")
    existing = db.scalar(select(m.EmployeeContextLink).where(getattr(m.EmployeeContextLink, field) == target_id))
    if existing:
        if existing.employee_id != person.id:
            raise ValueError("Already linked to another person. Unlink explicitly before reassignment.")
        return existing
    if kind == "RFONE_ACCOUNT" and current and current.rfone_account_id != target_id:
        _event(db, "ACCOUNT_REPLACED", employee_id=person.id, account_id=account_id,
               details={"previous_account_id": current.rfone_account_id, "account_id": target_id})
        db.delete(current)
        db.flush()
    link = m.EmployeeContextLink(employee_id=person.id, created_by_account_id=account_id, **{field: target_id})
    db.add(link)
    db.flush()
    if kind == "RFONE_ACCOUNT" and not employee_is_active(person, []):
        # History may be reconciled for a dismissed person; access stays blocked.
        disable_employee_account(db, person.id)
    _event(db, "CONTEXT_LINK", employee_id=person.id, account_id=account_id,
           details={"kind": kind, "target_id": target_id})
    return link


def unlink_context(db, *, employee_id, link_id, account_id=None):
    person_id = resolve_employee_id(db, employee_id)
    link = db.scalar(select(m.EmployeeContextLink).where(m.EmployeeContextLink.id == link_id,
        m.EmployeeContextLink.employee_id == person_id).with_for_update())
    if link is None:
        raise ValueError("Person context link not found.")
    kind = next(kind for kind, (_, field, _) in CONTEXTS.items() if getattr(link, field) is not None)
    if kind == "RFONE_ACCOUNT":
        raise ValueError("Every employee must retain one RF1 account; replace its provisional account instead.")
    target_id = getattr(link, CONTEXTS[kind][1])
    _event(db, "CONTEXT_UNLINK", employee_id=person_id, account_id=account_id,
           details={"kind": kind, "target_id": target_id})
    db.delete(link)
    db.flush()


def pending_requires_review(db, link):
    if link.employee_id is not None or not has_clock_evidence(link):
        return False
    if link.state != "MISSING_REVIEW":
        return True
    # A disappeared, never-used source account leaves the current queue.
    # A historical work reference still needs attribution and stays visible.
    return db.scalar(select(m.EmployeeDirectoryEvent.id).where(
        m.EmployeeDirectoryEvent.link_id == link.id,
        m.EmployeeDirectoryEvent.action == "HISTORICAL_PENDING").limit(1)) is not None


def source_absence_link_ids(links):
    """Absence is a site condition, not an alarm for retired duplicate accounts."""
    present_merchants = {link.merchant_id for link in links if link.state == "PRESENT"}
    return {link.id for link in links if link.state in ("MISSING_REVIEW", "DISMISSED") and link.merchant_id not in present_merchants}


def has_clock_evidence(link):
    return link.last_clock_in is not None or link.last_clock_out is not None


def clock_observations(records):
    """Validate an entire source shift collection before any lifecycle change."""
    if not isinstance(records, list):
        raise ValueError("Incomplete or invalid clock collection; roster preserved.")
    observations = {}
    for raw in records:
        if not isinstance(raw, dict):
            raise ValueError("Invalid shift observation; roster preserved.")
        identity = (raw.get("employee") or {}).get("id")
        times = []
        for field in ("inTime", "outTime"):
            value = raw.get(field)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0):
                raise ValueError("Invalid clock timestamp; roster preserved.")
            times.append(datetime.fromtimestamp(value / 1000, timezone.utc) if value is not None else None)
        if not any(times):
            continue
        if not isinstance(identity, str) or not identity.strip():
            raise ValueError("Clock observation has no employee identity; roster preserved.")
        item = observations.setdefault(identity, {"clock_in": None, "clock_out": None,
                                                "name": (raw.get("employee") or {}).get("name")})
        for field, instant in zip(("clock_in", "clock_out"), times):
            if instant is not None and (item[field] is None or instant > item[field]):
                item[field] = instant
    return observations


def is_provisional_account(db, account):
    """The INACTIVE shell made by provisioning: no credential, authority or grant."""
    return bool(account and account.password_hash == "!" and account.status == "INACTIVE"
                and not account.is_admin and not account.is_owner
                and db.scalar(select(m.RFOneAccountDomainAccess.id).where(
                    m.RFOneAccountDomainAccess.account_id == account.id).limit(1)) is None)


def employee_account(db, employee_id):
    return db.scalar(select(m.RFOneAccount).join(m.EmployeeContextLink,
        m.EmployeeContextLink.rfone_account_id == m.RFOneAccount.id).where(
            m.EmployeeContextLink.employee_id == employee_id))


def ensure_employee_account(db, person):
    """One identity shell, no fabricated contact/password and no domain grants."""
    db.flush()
    existing = employee_account(db, person.id)
    if existing is not None:
        return existing
    known = confirmed_account_ids(db, person.id)
    if len(known) > 1:
        raise ValueError("Multiple confirmed RF1 accounts for one employee; explicit account reconciliation required.")
    if known:
        identity = next(iter(known))
        db.add(m.EmployeeContextLink(employee_id=person.id, rfone_account_id=identity))
        _event(db, "ACCOUNT_ASSOCIATED", employee_id=person.id, details={"account_id": identity})
        db.flush()
        return db.get(m.RFOneAccount, identity)
    account = m.RFOneAccount(username="employee-" + uuid4().hex,
        display_name=person.display_name or "Nome da completare", password_hash="!", status="INACTIVE",
        is_admin=False, is_owner=False, session_version=1)
    db.add(account)
    db.flush()
    db.add(m.EmployeeContextLink(employee_id=person.id, rfone_account_id=account.id))
    _event(db, "ACCOUNT_PROVISIONED", employee_id=person.id, details={"account_id": account.id})
    db.flush()
    return account


def account_employee_allows_access(db, account_id):
    """External accounts are unaffected; linked dismissed people fail closed.

    The owner always stays an active administrator (ADMIN_PERMISSIONS_001):
    employment lifecycle never locks the owner out of RF-One.
    """
    account = db.get(m.RFOneAccount, account_id)
    if account is not None and account.is_owner:
        return True
    try:
        identity = context_person_id(db, "RFONE_ACCOUNT", account_id)
    except ValueError:
        return False
    person = db.get(m.Employee, identity) if identity is not None else None
    return person is None or employee_is_active(person, [])


def refresh_lifecycle(db, employee_id):
    """Derive overall employment from per-site positions. Native people are RF1-managed.

    Present anywhere -> active (account access is never restored here).
    Every position ended by a complete scan -> dismissed at the latest clock-in.
    Anything unverified or suspended -> no change, never an inferred cessation.
    """
    person = db.scalar(select(m.Employee).where(m.Employee.id == employee_id).with_for_update())
    links = list(db.scalars(select(m.EmployeeCloverLink).where(m.EmployeeCloverLink.employee_id == employee_id)))
    if person is None or not links:
        return False
    local_clock_in, local_clock_out = db.execute(select(func.max(m.Shift.clock_in), func.max(m.Shift.clock_out)).where(
        m.Shift.employee_id == person.id)).one()
    was_active = employee_is_active(person, links)
    previous = (person.active, person.directory_eligible, _utc(person.dismissed_at) if person.dismissed_at else None)
    evidenced = any(has_clock_evidence(link) for link in links) or local_clock_in is not None or local_clock_out is not None
    if evidenced:
        person.directory_eligible = True
    elif all(link.clocks_checked_at is not None for link in links):
        person.directory_eligible = False
    if any(link.state == "PRESENT" for link in links):
        person.active, person.dismissed_at = True, None
    elif all(link.state == "DISMISSED" for link in links):
        person.active = False
        person.dismissed_at = max((_utc(instant) for instant in [local_clock_in, *(link.last_clock_in for link in links)]
                                   if instant is not None), default=None)
    if person.active is False and previous[0] is not False:
        _event(db, "DISMISSED", employee_id=person.id,
               details={"last_clock_in": person.dismissed_at.isoformat() if person.dismissed_at else None})
    elif person.active is True and previous[0] is False:
        _event(db, "REACTIVATED", employee_id=person.id, details={"previous_dismissed_at":
               previous[2].isoformat() if previous[2] else None})
    if person.directory_eligible != previous[1]:
        _event(db, "DIRECTORY_ELIGIBLE" if person.directory_eligible else "DIRECTORY_INELIGIBLE", employee_id=person.id)
    if not employee_is_active(person, links):
        disable_employee_account(db, person.id, announce=was_active)
    db.flush()
    return evidenced


def merchant_has_pending_identities(links):
    """Unattributed identities with real clocks could be any person's other account."""
    return any(link.employee_id is None and has_clock_evidence(link) for link in links)


def apply_clock_observations(db, *, location_id, merchant_id, observations, observed_at, decide=True):
    """Retain latest clocks per link and, after a complete scan, settle positions.

    `decide=False` (offline/file snapshots) records clock evidence only: an old
    snapshot never ends a position or changes a person's employment.
    """
    links = {link.external_employee_id: link for link in db.scalars(select(m.EmployeeCloverLink).where(
        m.EmployeeCloverLink.merchant_id == merchant_id).with_for_update())}
    # Removed source profiles with real historical clocks still need explicit
    # attribution. No person is manufactured from those references.
    for identity, clocks in observations.items():
        if identity not in links:
            snapshot = {"id": identity, "name": clocks.get("name")}
            link = m.EmployeeCloverLink(location_id=location_id, merchant_id=merchant_id,
                external_employee_id=identity, snapshot=snapshot, state="MISSING_REVIEW")
            db.add(link)
            db.flush()
            _event(db, "HISTORICAL_PENDING", link=link, details={"snapshot": snapshot, "profile_available": False})
            links[identity] = link
    # Only clocks recorded for THIS site; unscoped local shifts are never attributed to a site.
    known_clocks = {identity: (clock_in, clock_out) for identity, clock_in, clock_out in db.execute(
        select(m.Shift.employee_id, func.max(m.Shift.clock_in), func.max(m.Shift.clock_out))
        .where(m.Shift.location_id == location_id).group_by(m.Shift.employee_id))}
    for identity, link in links.items():
        clocks = dict(observations.get(identity, {}))
        local = known_clocks.get(link.employee_id, (None, None)) if link.employee_id is not None else (None, None)
        for field, instant in zip(("clock_in", "clock_out"), local):
            if instant is not None and (clocks.get(field) is None or _utc(instant) > _utc(clocks[field])):
                clocks[field] = instant
        # Keep previously observed clocks if POS retention removes older shifts.
        for field, key in (("last_clock_in", "clock_in"), ("last_clock_out", "clock_out")):
            instant = clocks.get(key)
            previous = getattr(link, field)
            if instant is not None and (previous is None or _utc(instant) > _utc(previous)):
                setattr(link, field, instant)
        if decide:
            link.clocks_checked_at = observed_at
    db.flush()
    if not decide:
        return
    suspended = merchant_has_pending_identities(links.values())
    for link in links.values():
        if link.state not in ("MISSING_REVIEW", "DISMISSED"):
            link.dismissed_at = None
            continue
        if link.employee_id is not None and suspended and link.state == "MISSING_REVIEW":
            continue  # Pending attribution might be this same person: no cessation yet.
        if link.state != "DISMISSED" and link.employee_id is not None:
            _event(db, "POSITION_ENDED", employee_id=link.employee_id, link=link,
                   details={"last_clock_in": link.last_clock_in.isoformat() if link.last_clock_in else None})
        link.state = "DISMISSED"
        link.dismissed_at = link.last_clock_in
    db.flush()
    people = sorted({link.employee_id for link in links.values() if link.employee_id is not None})
    with_account = set(db.scalars(select(m.EmployeeContextLink.employee_id).where(
        m.EmployeeContextLink.employee_id.in_(people), m.EmployeeContextLink.rfone_account_id.is_not(None))))
    for employee_id in people:
        evidenced = refresh_lifecycle(db, employee_id)
        # Only a person with real clocks is a registered employee owed an account.
        if evidenced and employee_id not in with_account:
            try:
                with db.begin_nested():
                    ensure_employee_account(db, db.get(m.Employee, employee_id))
            except ValueError:
                pass  # Account conflict stays visible in the directory/audit; never blocks the roster.


def clock_scan_due(db, *, merchant_id, roster_ids, now, max_age_seconds=3600):
    """Bound Clover load: the full /shifts history is paged only when needed.

    Clover's /shifts endpoint has no server-side time filter, so the minute
    poller asks for it when the roster changed, a link was never verified,
    a suspended cessation may now be settled, or the evidence is over an hour old.
    """
    links = list(db.scalars(select(m.EmployeeCloverLink).where(m.EmployeeCloverLink.merchant_id == merchant_id)))
    if {link.external_employee_id for link in links if link.state == "PRESENT"} != set(roster_ids):
        return True
    checks = [link.clocks_checked_at for link in links]
    if not links or any(check is None for check in checks):
        return True
    if (any(link.employee_id is not None and link.state == "MISSING_REVIEW" for link in links)
            and not merchant_has_pending_identities(links)):
        return True
    return (_utc(now) - min(_utc(check) for check in checks)).total_seconds() > max_age_seconds


def lifecycle_audit(db):
    """Read-only compatibility inventory for migration/operator review."""
    rows = []
    for person in db.scalars(canonical_employees()):
        accounts = list(db.scalars(select(m.EmployeeContextLink.rfone_account_id).where(
            m.EmployeeContextLink.employee_id == person.id, m.EmployeeContextLink.rfone_account_id.is_not(None))))
        clocks = db.scalar(select(func.count()).select_from(m.Shift).where(
            m.Shift.employee_id == person.id, (m.Shift.clock_in.is_not(None) | m.Shift.clock_out.is_not(None))))
        rows.append({"employee_id": person.id, "account_ids": accounts, "known_shifts": clocks,
                     "needs_account": not accounts, "account_conflict": len(accounts) > 1,
                     "source_clocks_need_verification": bool(person.source_employee_id and not clocks)})
    return rows


def _utc(instant):
    return instant.replace(tzinfo=timezone.utc) if instant.tzinfo is None else instant.astimezone(timezone.utc)


def interview_employee_options(db, *, location_ids):
    """Recipients for NEW employee interviews: strictly current, no retained selection.

    `location_ids` is required so every caller states its scope: an empty
    list returns nobody (never "all sites"); None means unrestricted and is
    passed only by a caller whose scope is deliberately unrestricted, never
    as a fallback for a missing authorization scope.
    """
    return employee_options(db, location_ids=location_ids)


def require_active_employee(db, employee_id, *, location_ids=None):
    """Revalidate at submission time; a previously rendered recipient may be dismissed.

    `location_ids` filters by site evidence (Clover/Workforce), not by
    organizational applicability (employee_applicability)."""
    canonical = resolve_employee_id(db, employee_id)
    if not any(option.id == canonical for option in employee_options(db, location_ids=location_ids)):
        raise ValueError("Employee is dismissed or outside the authorized active locations.")
    return db.get(m.Employee, canonical)


def context_employee_allows_access(db, kind, target_id):
    identity = context_person_id(db, kind, target_id)
    return identity is None or employee_is_active(db.get(m.Employee, identity), [])


def employee_account_session_version(db, kind, target_id):
    identity = context_person_id(db, kind, target_id)
    if identity is None:
        return None
    return db.scalar(select(m.RFOneAccount.session_version).join(m.EmployeeContextLink,
        m.EmployeeContextLink.rfone_account_id == m.RFOneAccount.id).where(
            m.EmployeeContextLink.employee_id == identity))


def disable_employee_account(db, employee_id, *, announce=True):
    """Block new logins and invalidate open sessions; account and history stay.

    The owner account is never deactivated (it must stay an active
    administrator); the conflict is recorded for the Product Owner instead.
    """
    for account in db.scalars(select(m.RFOneAccount).join(m.EmployeeContextLink,
        m.EmployeeContextLink.rfone_account_id == m.RFOneAccount.id).where(
            m.EmployeeContextLink.employee_id == employee_id)):
        if account.is_owner:
            if announce:
                _event(db, "OWNER_ACCESS_PROTECTED", employee_id=employee_id, details={"account_id": account.id})
            continue
        changed = account.status != "INACTIVE"
        account.status = "INACTIVE"
        if changed or announce:
            account.session_version = (account.session_version or 0) + 1


CONFIRMED_ACCOUNT_PAIRS_SQL = """
SELECT employee_id, rfone_account_id AS account_id FROM employee_context_links WHERE rfone_account_id IS NOT NULL
UNION
SELECT c.employee_id, b.rfone_account_id FROM employee_context_links c
JOIN rfone_training_identity_links b ON b.training_account_id = c.training_account_id
UNION
SELECT c.employee_id, b.rfone_account_id FROM employee_context_links c
JOIN training_accounts t ON t.acting_identity_id = c.acting_identity_id
JOIN rfone_training_identity_links b ON b.training_account_id = t.id
"""


def confirmed_account_ids(db, employee_id):
    return set(db.scalars(text("SELECT account_id FROM (" + CONFIRMED_ACCOUNT_PAIRS_SQL +
                              ") confirmed WHERE employee_id = :employee").bindparams(employee=employee_id)))
