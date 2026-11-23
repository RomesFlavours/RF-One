"""Registry Role/Department table (REGISTRY_CLOVER_DEPARTMENTS_001, Product Owner 2026-11-20/21).

One central organizational table, owned by Registry and readable by every Domain (Bank, Tips,
Compensation, Training, Organization) through `classification` / `department_of`:

    person -> open Registry assignment (`EmployeeAssignment`) -> RF-One role
           -> department (FOH, BOH, ... inside Restaurant Operations)   `RegistryRoleDepartment`
    historical document code (e.g. Note sheet "2-Serv") -> RF-One role    `RegistryRoleMapping`, per Restaurant

OQ-7 (RF1_OPERATIONAL_DATABASE_001, Product Owner 2026-11-21): a Clover role never determines an RF-One
role, a department or an assignment. Clover correspondences written earlier (`source = CLOVER`) stay in
`RegistryRoleMapping` as history; new ones are refused and they are no longer read. Every change closes the
current row and opens a new one (history kept).
REGISTRY_CLOVER_CREATE_001 (Product Owner, 2026-11-22): the current CLOVER rows are read again in one direction only,
RF-One role -> Clover role of the site, by «Crea in Clover» (`clover_employee_create`); still never Clover -> RF-One.

REGISTRY_MULTISITE_001 (Product Owner, 2026-11-22): the Clover staff-list import is removed, and with it
the former `sync_site` step that refreshed the Clover role catalogue and its report at the end of the import.

TIPS_REGISTRY_ONLY_001 (Product Owner, 2026-11-21): Clover is not a reliable source of roles, departments
or duties; Registry is the only authority. The import therefore NEVER opens, closes or changes a Registry
assignment (`EmployeeAssignment`): a role changed in Clover changes nothing in Registry, and so nothing in
Tips. It only keeps the catalogue of the Clover roles seen at the site (`SourceRole`) and reports the
confirmed people of the site who have no open Registry assignment. OQ-7 (RF1_OPERATIONAL_DATABASE_001,
Product Owner 2026-11-21): a Clover role is not compared with the Registry assignment either — it never
creates, prefills, updates or suggests an assignment. Assignments written by the former automatic sync
(source `CLOVER_ROLE_SYNC`) stay as they are: they are Registry history.
Historical roles from documents (`RegistryPersonSourceRole`) never open assignments and never replace
the current Clover role. Clover data and Tips' `SourceRoleMapping` are never read for writing or changed.
No commits: the caller owns the transaction.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import inspect, select

from . import models as m

ASSIGNMENT_SOURCE = "CLOVER_ROLE_SYNC"      # the same source the former one-off Winter Park sync used
CLOVER = "CLOVER"
REGISTRY = "REGISTRY"                     # classification basis: an open Registry assignment
EXCEL_WP_NOTE = "EXCEL_WP_NOTE"             # "2026 - WP Control Bank.xlsb", sheet Note
SOURCE_LABELS = {CLOVER: "Clover", EXCEL_WP_NOTE: "Excel WP Control Bank · Note"}
ORIGIN_SEED, ORIGIN_PERSON = "SEED", "PERSON"
ROOT_AREA_CODE = "ROOT"                     # "Restaurant Operations"
TABLES = {"registry_departments", "registry_role_departments", "registry_role_mappings", "registry_person_source_roles"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def available(db) -> bool:
    """False on a database without the migration a1c220261121: the import then works exactly as before."""
    return TABLES <= set(inspect(db.connection()).get_table_names())


def _named_roles(snapshot):
    from .employee_directory import named_roles
    return named_roles(snapshot)


def site_restaurant_id(db, location_id) -> int | None:
    return db.scalar(select(m.RestaurantLocation.restaurant_id).where(
        m.RestaurantLocation.location_id == location_id, m.RestaurantLocation.valid_to.is_(None)
    ).order_by(m.RestaurantLocation.id))


def operations_area(db, restaurant_id=None):
    """The Restaurant's own Restaurant Operations area, else the one the departments live in."""
    area = db.scalar(select(m.OperationalArea).where(
        m.OperationalArea.restaurant_id == restaurant_id, m.OperationalArea.code == ROOT_AREA_CODE
    ).order_by(m.OperationalArea.id)) if restaurant_id is not None else None
    return area or db.scalar(select(m.OperationalArea).where(
        m.OperationalArea.code == ROOT_AREA_CODE, m.OperationalArea.restaurant_id.is_not(None)
    ).order_by(m.OperationalArea.id))


def role_departments(db) -> dict[int, int | None]:
    return {r.restaurant_role_id: r.department_id for r in db.scalars(select(m.RegistryRoleDepartment).where(
        m.RegistryRoleDepartment.valid_to.is_(None)))}


def current_mappings(db, restaurant_id) -> dict[tuple[str, str], "m.RegistryRoleMapping"]:
    return {(r.source, r.original_key): r for r in db.scalars(select(m.RegistryRoleMapping).where(
        m.RegistryRoleMapping.restaurant_id == restaurant_id, m.RegistryRoleMapping.valid_to.is_(None)))}


def effective(mapping, role_deps) -> tuple[int | None, int | None]:
    """(RF-One role id, department id) an original role means: the department of the RF-One role, or the
    mapping's own certain department when the RF-One role is not set or has no department."""
    if mapping is None:
        return None, None
    role = mapping.restaurant_role_id
    department = role_deps.get(role) if role else None
    return role, department if department is not None else mapping.department_id


# ---------------------------------------------------------------- data interface for every Domain

def classification(db, *, employee_ids=None, include_history=False) -> list[dict]:
    """Department of each person, one row per person, Restaurant and Registry role.

    basis REGISTRY: the person's open Registry assignment (`EmployeeAssignment`, valid_to NULL) and the
    department of that RF-One role. OQ-7 (Product Owner 2026-11-21): a Clover role never determines a
    role or a department. basis HISTORICAL (only with include_history): a role recorded by a source
    document, for people without an open Registry assignment at that Restaurant. Keys: employee_id,
    restaurant_id, basis, source, original_role, rf_role, department_code, department_name. Read-only."""
    if not available(db):
        return []
    role_deps = role_departments(db)
    departments = {d.id: d for d in db.scalars(select(m.RegistryDepartment))}
    roles = {r.id: r for r in db.scalars(select(m.RestaurantRole))}
    mappings, rows, current = {}, [], set()

    def mapped(restaurant_id, source, key):
        if restaurant_id not in mappings:
            mappings[restaurant_id] = current_mappings(db, restaurant_id)
        return effective(mappings[restaurant_id].get((source, key)), role_deps)

    def row(employee_id, restaurant_id, basis, source, label, role_id, department_id):
        department = departments.get(department_id)
        department = department if department is not None and department.active else None
        return {"employee_id": employee_id, "restaurant_id": restaurant_id, "basis": basis, "source": source,
                "original_role": label, "rf_role": roles[role_id].name if role_id in roles else None,
                "department_code": department.code if department else None,
                "department_name": department.name if department else None}

    query = select(m.EmployeeAssignment).where(m.EmployeeAssignment.valid_to.is_(None))
    if employee_ids is not None:
        query = query.where(m.EmployeeAssignment.employee_id.in_(list(employee_ids)))
    seen = set()
    for assignment in db.scalars(query.order_by(m.EmployeeAssignment.employee_id, m.EmployeeAssignment.id)):
        key = (assignment.employee_id, assignment.restaurant_id, assignment.restaurant_role_id)
        if key in seen:
            continue
        seen.add(key)
        rows.append(row(assignment.employee_id, assignment.restaurant_id, "REGISTRY", REGISTRY, None,
                        assignment.restaurant_role_id, role_deps.get(assignment.restaurant_role_id)))
        current.add((assignment.employee_id, assignment.restaurant_id))
    if include_history:
        query = select(m.RegistryPersonSourceRole)
        if employee_ids is not None:
            query = query.where(m.RegistryPersonSourceRole.employee_id.in_(list(employee_ids)))
        for record in db.scalars(query.order_by(m.RegistryPersonSourceRole.employee_id)):
            if (record.employee_id, record.restaurant_id) in current:
                continue
            role_id, department_id = mapped(record.restaurant_id, record.source, record.original_key)
            rows.append(row(record.employee_id, record.restaurant_id, "HISTORICAL", record.source,
                            record.original_key, role_id, department_id))
    return rows


def department_of(db, employee_id, *, include_history=False) -> set[str]:
    """Department codes a person belongs to today (all sites); with include_history also from documents."""
    return {r["department_code"] for r in classification(db, employee_ids=[employee_id], include_history=include_history)
            if r["department_code"]}


# ---------------------------------------------------------------- Registry management (Anagrafica page)

def save_department(db, *, name, code, department_id=None, active=True, account_id=None):
    name, code = (name or "").strip(), (code or "").strip().upper()
    if not name or len(name) > 120:
        raise ValueError("Inserisci il nome del reparto (massimo 120 caratteri).")
    if not code or len(code) > 32:
        raise ValueError("Inserisci un codice breve del reparto (massimo 32 caratteri).")
    for other in db.scalars(select(m.RegistryDepartment)):
        if other.id != department_id and (other.code == code or other.name.casefold() == name.casefold()):
            raise ValueError("Esiste già un reparto con questo nome o codice.")
    if department_id:
        row = db.get(m.RegistryDepartment, department_id)
        if row is None:
            raise ValueError("Reparto non trovato.")
    else:
        area = operations_area(db)
        if area is None:
            raise ValueError("L’area Restaurant Operations non esiste.")
        row = m.RegistryDepartment(operational_area_id=area.id)
        db.add(row)
    row.name, row.code, row.active = name, code, bool(active)
    row.updated_by_account_id, row.updated_at = account_id, utc_now()
    db.flush()
    return row


def _department(db, department_id):
    if not department_id:
        return None
    department = db.get(m.RegistryDepartment, department_id)
    if department is None:
        raise ValueError("Reparto non trovato.")
    return department


def set_role_department(db, *, restaurant_role_id, department_id, account_id=None, now=None, origin=ORIGIN_PERSON):
    """The department of an RF-One role (history kept). The classification of everybody with that role follows."""
    now = now or utc_now()
    role = db.get(m.RestaurantRole, restaurant_role_id)
    if role is None:
        raise ValueError("Ruolo RF-One non trovato.")
    _department(db, department_id)
    current = db.scalar(select(m.RegistryRoleDepartment).where(
        m.RegistryRoleDepartment.restaurant_role_id == role.id, m.RegistryRoleDepartment.valid_to.is_(None)))
    if current is not None and current.department_id == (department_id or None):
        return current
    if current is not None:
        current.valid_to = now
        db.flush()
    row = m.RegistryRoleDepartment(restaurant_role_id=role.id, department_id=department_id or None, valid_from=now,
                                   origin=origin, changed_by_account_id=account_id)
    db.add(row)
    db.flush()
    return row


def save_role(db, *, name, department_id, role_id=None, account_id=None):
    """Create or rename an RF-One role through the one Registry role implementation, then set its department.
    A new role belongs to the Restaurant Operations area; an existing role keeps its areas."""
    from . import access_profiles as profiles
    if role_id:
        area_ids = [p.operational_area_id for p in db.scalars(select(m.OperationalAreaRole).where(
            m.OperationalAreaRole.restaurant_role_id == role_id))]
        if not area_ids:
            area_ids = [operations_area(db).id]
    else:
        area = operations_area(db)
        if area is None:
            raise ValueError("L’area Restaurant Operations non esiste.")
        area_ids = [area.id]
    role = profiles.save_role(db, name=name, area_ids=area_ids, role_id=role_id or None, actor=account_id)
    set_role_department(db, restaurant_role_id=role.id, department_id=department_id, account_id=account_id)
    return role


def set_role_mapping(db, *, restaurant_id, source, original_key, original_label=None, restaurant_role_id=None,
                     department_id=None, account_id=None, now=None):
    """What a historical document role means at one Restaurant (history kept). Clover roles are refused
    (OQ-7); it never opens, closes or proposes a Registry assignment."""
    now = now or utc_now()
    if db.get(m.Restaurant, restaurant_id) is None:
        raise ValueError("Ristorante non trovato.")
    source_role = None
    if source == CLOVER:
        # OQ-7: a Clover role never determines an RF-One role or department; existing rows stay as history.
        raise ValueError("I ruoli Clover non determinano ruoli o reparti RF-One: si gestiscono solo in Registry.")
    if source not in SOURCE_LABELS or not (original_key or "").strip():
        raise ValueError("Ruolo originale non valido.")
    role = db.get(m.RestaurantRole, restaurant_role_id) if restaurant_role_id else None
    if restaurant_role_id and (role is None or role.active is False
                               or role.restaurant_id not in (None, restaurant_id)):
        raise ValueError("Scegli un ruolo RF-One attivo valido per questo ristorante.")
    _department(db, department_id)
    current = current_mappings(db, restaurant_id).get((source, original_key))
    if current is not None and current.restaurant_role_id == (restaurant_role_id or None) \
            and current.department_id == (department_id or None):
        return current
    if current is not None:
        current.valid_to = now
        db.flush()
    row = m.RegistryRoleMapping(
        restaurant_id=restaurant_id, source=source, original_key=original_key,
        original_label=original_label or original_key, source_role_id=source_role.id if source_role else None,
        restaurant_role_id=restaurant_role_id or None, department_id=department_id or None, valid_from=now,
        origin=ORIGIN_PERSON, changed_by_account_id=account_id)
    db.add(row)
    db.flush()
    return row


def _history(db, model, **where):
    query = select(model)
    for key, value in where.items():
        query = query.where(getattr(model, key) == value)
    return list(db.scalars(query.order_by(model.valid_from.desc(), model.id.desc())))


def overview(db) -> dict:
    """Everything the Anagrafica > Reparti e ruoli page shows."""
    if not available(db):
        return {"roles": [], "sites": [], "missing": 0}
    role_deps = role_departments(db)
    departments = {d.id: d for d in db.scalars(select(m.RegistryDepartment))}
    roles = {r.id: r for r in db.scalars(select(m.RestaurantRole))}
    restaurants = {r.id: r for r in db.scalars(select(m.Restaurant))}
    historical = Counter((r.restaurant_id, r.source, r.original_key) for r in db.scalars(select(m.RegistryPersonSourceRole)))
    open_by_role = Counter(a.restaurant_role_id for a in db.scalars(select(m.EmployeeAssignment).where(
        m.EmployeeAssignment.valid_to.is_(None))))
    by_role_today, by_role_history = Counter(), Counter()
    for item in classification(db, include_history=True):
        role_id = next((rid for rid, r in roles.items() if r.name == item["rf_role"]), None)
        (by_role_today if item["basis"] == "REGISTRY" else by_role_history)[role_id] += 1

    def describe(row, model_dep):
        return {"valid_from": row.valid_from, "valid_to": row.valid_to, "origin": row.origin,
                "account_id": row.changed_by_account_id,
                "department": departments[model_dep].name if model_dep in departments else None}

    role_rows = []
    for role in sorted(roles.values(), key=lambda r: r.name.casefold()):
        if role.active is False:
            continue
        department = departments.get(role_deps.get(role.id))
        role_rows.append({
            "id": role.id, "name": role.name, "code": role.code, "department": department,
            "department_id": department.id if department else None, "missing_department": department is None,
            "people_today": by_role_today[role.id], "people_history": by_role_history[role.id],
            "open_assignments": open_by_role[role.id],
            "history": [describe(h, h.department_id) for h in _history(db, m.RegistryRoleDepartment, restaurant_role_id=role.id)]})

    sites = defaultdict(list)
    # OQ-7: only historical document roles are listed; Clover roles never determine RF-One roles or departments
    # (their earlier correspondences stay in the table as history).
    restaurant_ids = {r.restaurant_id for r in db.scalars(select(m.RegistryRoleMapping).where(
        m.RegistryRoleMapping.source != CLOVER))} | {r[0] for r in historical}
    for restaurant_id in restaurant_ids:
        mappings = {k: v for k, v in current_mappings(db, restaurant_id).items() if k[0] != CLOVER}
        keys = {(source, key): (key, None) for (rid, source, key) in historical if rid == restaurant_id}
        for (source, key), mapping in mappings.items():
            keys[(source, key)] = (mapping.original_label, None)
        for (source, key), (label, location) in keys.items():
            mapping = mappings.get((source, key))
            role_id, department_id = effective(mapping, role_deps)
            department = departments.get(department_id)
            people = historical[(restaurant_id, source, key)]
            sites[restaurant_id].append({
                "restaurant_id": restaurant_id, "source": source, "source_label": SOURCE_LABELS.get(source, source),
                "original_key": key, "original_label": label, "location": location.name if location else None,
                "timezone": location.timezone if location else None,
                "people": people, "pending": 0,
                "restaurant_role_id": role_id, "own_department_id": mapping.department_id if mapping else None,
                "department": department, "role_has_department": bool(role_id and role_deps.get(role_id)),
                "missing_department": department is None,
                "history": [dict(describe(h, h.department_id), rf_role=roles[h.restaurant_role_id].name
                                 if h.restaurant_role_id in roles else None)
                            for h in _history(db, m.RegistryRoleMapping, restaurant_id=restaurant_id, source=source,
                                              original_key=key)]})
    site_rows = []
    for restaurant_id, rows in sites.items():
        rows.sort(key=lambda r: (r["source"] != CLOVER, r["original_label"].casefold()))
        name = restaurants[restaurant_id].name if restaurant_id in restaurants else f"#{restaurant_id}"
        site_rows.append({"restaurant_id": restaurant_id, "restaurant": name, "rows": rows})
    site_rows.sort(key=lambda s: s["restaurant"])
    missing = sum(r["missing_department"] for r in role_rows) + sum(r["missing_department"] for s in site_rows for r in s["rows"])
    return {"roles": role_rows, "sites": site_rows, "missing": missing}


# ---------------------------------------------------------------- historical roles from a document

@dataclass
class HistoryLoad:
    rows_read: int = 0
    people: int = 0
    reconciled: int = 0
    already_loaded: int = 0
    loaded: int = 0
    not_found: list = field(default_factory=list)       # identities not in Registry: reported, never created
    incomplete: list = field(default_factory=list)      # rows without identity or role
    duplicates: list = field(default_factory=list)
    name_differences: list = field(default_factory=list)
    department_differences: list = field(default_factory=list)   # document HOUSE vs role table
    current_role_differences: list = field(default_factory=list) # document role vs current Clover role

    def as_dict(self):
        return dict(self.__dict__)


def load_source_roles(db, records, *, restaurant_id, merchant_id, source=EXCEL_WP_NOTE, reference, dry_run=False):
    """Record each person's historical role from a document (records: row, register_id = Clover employee id,
    name, house, role). Reuses the existing person through its Clover identity; never creates people, never
    changes names, status, assignments or the current Clover role. Re-running changes nothing."""
    from .employee_directory import _normalized, resolve_employee_id
    from difflib import SequenceMatcher
    report = HistoryLoad(rows_read=len(records))
    savepoint = db.begin_nested() if dry_run else None
    try:
        mappings, role_deps = current_mappings(db, restaurant_id), role_departments(db)
        departments = {d.id: d.code for d in db.scalars(select(m.RegistryDepartment))}
        seen = {}
        for record in records:
            key, name, role = (record.get("register_id") or "").strip(), (record.get("name") or "").strip(), record.get("role")
            if not key or not name:
                report.incomplete.append({"row": record.get("row"), "reason": "missing Register ID or name"})
                continue
            if key in seen:
                report.duplicates.append({"row": record.get("row"), "same_as_row": seen[key], "register_id": key})
                continue
            seen[key] = record.get("row")
            report.people += 1
            link = db.scalar(select(m.EmployeeCloverLink).where(
                m.EmployeeCloverLink.merchant_id == merchant_id, m.EmployeeCloverLink.external_employee_id == key))
            employee_id = resolve_employee_id(db, link.employee_id) if link is not None and link.employee_id else None
            if employee_id is None:
                report.not_found.append({"row": record.get("row"), "register_id": key, "name": name})
                continue
            report.reconciled += 1
            employee = db.get(m.Employee, employee_id)
            if SequenceMatcher(None, _normalized(employee.display_name), _normalized(name)).ratio() < 0.8:
                report.name_differences.append({"row": record.get("row"), "document": name, "registry": employee.display_name})
            if not role:
                report.incomplete.append({"row": record.get("row"), "employee_id": employee_id, "reason": "no role"})
                continue
            _role_id, department_id = effective(mappings.get((source, role)), role_deps)
            house = (record.get("house") or None)
            if house and departments.get(department_id) and departments[department_id] != house:
                report.department_differences.append({"row": record.get("row"), "employee_id": employee_id,
                                                      "document": house, "table": departments[department_id]})
            if link.state == "PRESENT":
                named = _named_roles(link.snapshot)
                now_role, now_dep = effective(mappings.get((CLOVER, next(iter(named)))) if len(named) == 1 else None, role_deps)
                doc_role, doc_dep = effective(mappings.get((source, role)), role_deps)
                # Discordant only when something certain differs: the department, or two known RF-One roles.
                if (now_dep and doc_dep and now_dep != doc_dep) or (now_role and doc_role and now_role != doc_role):
                    report.current_role_differences.append({"row": record.get("row"), "employee_id": employee_id,
                        "document_role": role, "clover_role_now": ", ".join(named.values())})
            existing = db.scalar(select(m.RegistryPersonSourceRole).where(
                m.RegistryPersonSourceRole.employee_id == employee_id,
                m.RegistryPersonSourceRole.restaurant_id == restaurant_id, m.RegistryPersonSourceRole.source == source))
            if existing is not None:
                report.already_loaded += 1
                continue
            db.add(m.RegistryPersonSourceRole(employee_id=employee_id, restaurant_id=restaurant_id, source=source,
                                              original_key=str(role), declared_department=house,
                                              source_reference=f"{reference} row {record.get('row')}"))
            report.loaded += 1
        db.flush()
    finally:
        if savepoint is not None:
            savepoint.rollback()
    return report
