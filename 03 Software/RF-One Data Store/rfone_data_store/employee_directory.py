"""Shared employee identity and source observations. No network and no commits.

Employee remains the canonical identity used by Tips, Payroll and Sales. A
provider record stays pending until a human confirms its RF-One identity.
Only source fields on links change during imports; management stays on Employee
and its existing assignment/compensation records.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from hashlib import sha256
import json
import re
import unicodedata

from sqlalchemy import func, select, update
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
    """Shared display state only; never persists an employment decision."""
    return employee.active is not False


def employee_location_ids(employee, links, *, include_historical=False):
    """Relevant sites; historical selectors retain all known workplaces."""
    if include_historical:
        return {site for site in (employee.location_id, *(link.location_id for link in links)) if site is not None}
    return ({link.location_id for link in links if link.state == "PRESENT"}
            or {link.location_id for link in links if link.state == "UNVERIFIED"}
            or {link.location_id for link in links}
            or ({employee.location_id} if employee.location_id is not None else set()))


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


def import_snapshot(db, *, location_id, merchant_id, records, observed_at=None, run_id=None, complete=True):
    """Apply one complete, validated employee collection atomically in caller's transaction.

    Incomplete reads are rejected BEFORE any write, including legacy seeding.
    Every unknown external identity stays unlinked until explicit approval.
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
        employee = db.scalar(select(m.Employee).where(m.Employee.id == resolve_employee_id(db, employee_id)).with_for_update()) if employee_id is not None else None
        if employee is None:
            raise ValueError("Choose an existing RF-One employee or explicitly create a new person.")
    link.employee_id = employee.id
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
    if not display_name or len(display_name) > 255 or len(custom_id or "") > 64:
        raise ValueError("A name (maximum 255 characters) and a custom ID up to 64 characters are required.")
    if len(email or "") > 255 or len(phone or "") > 64:
        raise ValueError("Email or phone is too long.")
    before = {key: getattr(employee, key) for key in ("display_name", "custom_id", "active", "email", "phone")}
    employee.email, employee.phone = (email or "").strip() or None, (phone or "").strip() or None
    employee.display_name = display_name
    employee.custom_id = custom_id or None
    employee.active = active
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
    _event(db, "RF1_CREATE", employee_id=person.id, account_id=account_id)
    return person


def context_person_id(db, kind, target_id):
    """Resolve explicit person/authentication bridges, never names or privileges."""
    if kind not in CONTEXTS:
        raise ValueError("Unknown person context.")
    if target_id is None:
        return None
    from sqlalchemy import inspect
    from . import people_registry as registry_links, student_registry as training_links
    tables=db.info.get('registry_identity_link_tables')
    if tables is None:
        tables=set(inspect(db.connection()).get_table_names())
        db.info['registry_identity_link_tables']=tables
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
        if current_kind == 'CANDIDATE':
            if 'person_employee_links' in tables:
                people.update(resolve_employee_id(db,value) for value in db.scalars(select(registry_links.PersonEmployeeLink.employee_id).where(registry_links.PersonEmployeeLink.person_id==identity)))
            if 'person_account_links' in tables:
                queue.extend(('RFONE_ACCOUNT',value) for value in db.scalars(select(registry_links.PersonAccountLink.account_id).where(registry_links.PersonAccountLink.person_id==identity)))
            if 'training_person_links' in tables:
                queue.extend(('TRAINING',value) for value in db.scalars(select(training_links.TrainingPersonLink.training_account_id).where(training_links.TrainingPersonLink.person_id==identity)))
        elif current_kind == 'RFONE_ACCOUNT' and 'person_account_links' in tables:
            queue.extend(('CANDIDATE',value) for value in db.scalars(select(registry_links.PersonAccountLink.person_id).where(registry_links.PersonAccountLink.account_id==identity)))
        elif current_kind == 'TRAINING' and 'training_person_links' in tables:
            queue.extend(('CANDIDATE',value) for value in db.scalars(select(training_links.TrainingPersonLink.person_id).where(training_links.TrainingPersonLink.training_account_id==identity)))
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
    known_person = context_person_id(db, kind, target_id)
    if known_person is not None and known_person != person.id:
        raise ValueError("Conflicts with an existing confirmed person association. Unlink and review explicitly first.")
    existing = db.scalar(select(m.EmployeeContextLink).where(getattr(m.EmployeeContextLink, field) == target_id))
    if existing:
        if existing.employee_id != person.id:
            raise ValueError("Already linked to another person. Unlink explicitly before reassignment.")
        return existing
    link = m.EmployeeContextLink(employee_id=person.id, created_by_account_id=account_id, **{field: target_id})
    db.add(link)
    db.flush()
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
    target_id = getattr(link, CONTEXTS[kind][1])
    _event(db, "CONTEXT_UNLINK", employee_id=person_id, account_id=account_id,
           details={"kind": kind, "target_id": target_id})
    db.delete(link)
    db.flush()


def pending_requires_review(db, link):
    if link.employee_id is not None:
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
    return {link.id for link in links if link.state == "MISSING_REVIEW" and link.merchant_id not in present_merchants}
