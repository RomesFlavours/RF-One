"""Registry person cards (Employee), their explicit sites and their manual POS IDs. No network, no commits.

Employee remains the canonical identity used by Tips, Payroll and Sales.

REGISTRY_MULTISITE_001 (Product Owner specification, 2026-11-22):
- A card is created only manually (`create_person`, with an explicit site) or by Training
  (`training_card`). Nothing here reads Clover's staff list or shifts to create, update or propose a card;
  the former Clover -> Registry import, its proposal queue and its confirmation actions are removed.
- The site of a person is an explicit Registry assignment (`EmployeeAssignment`) to a restaurant or one of
  its locations (`site_employee_ids`). Company membership, Clover links and `Employee.location_id` never
  decide who is listed at a site.
- The POS ID is typed by an authorized operator on an existing card, for a site the person is assigned to
  (`set_pos_id`). Tips pairs site (Clover merchant) + POS ID to attribute Clover work. A correction never
  moves history already attributed; it only lets work still waiting for an identity be attributed.
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


def named_roles(snapshot):
    """Ignore Clover's permission tier and require complete named-role references."""
    snapshot = snapshot or {}
    roles = snapshot.get("roles") or []
    if not roles and isinstance(snapshot.get("role"), dict):
        roles = [snapshot["role"]]
    if not roles or any(not role.get("id") or not role.get("name") for role in roles):
        return {}
    return {role["id"]: role["name"] for role in roles}


def _event(db, action, *, employee_id=None, link=None, account_id=None, details=None):
    db.add(m.EmployeeDirectoryEvent(
        employee_id=employee_id, link_id=link.id if link else None,
        account_id=account_id, action=action, details=details or {},
    ))


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


# ------------------------------------------------------------------ sites (REGISTRY_MULTISITE_001)

ASSIGNMENT_SOURCE_REGISTRY = "REGISTRY"      # explicit site assignment typed in Registry
ASSIGNMENT_SOURCE_TRAINING = "TRAINING"      # explicit site assignment made by a Training entry
POS_LINK_STATE = "MANUAL"                    # a POS ID typed by an operator on the card
POS_CORRECTED_STATE = "CORRECTED"            # a POS ID replaced by a correction (kept for history)


def _now():
    return datetime.now(timezone.utc)


def sites(db):
    """Every RF-One site (Restaurant), lowest id first. Clover is not needed for a site to exist."""
    return list(db.scalars(select(m.Restaurant).order_by(m.Restaurant.id)))


def _current(query, at):
    return query.where(m.EmployeeAssignment.valid_from <= at,
                       m.EmployeeAssignment.valid_to.is_(None) | (m.EmployeeAssignment.valid_to > at))


def _site_condition(restaurant_id):
    site_locations = select(m.RestaurantLocation.location_id).where(
        m.RestaurantLocation.restaurant_id == restaurant_id)
    return (m.EmployeeAssignment.restaurant_id == restaurant_id) | (
        m.EmployeeAssignment.restaurant_id.is_(None) & m.EmployeeAssignment.location_id.in_(site_locations))


def site_employee_ids(db, restaurant_id, *, at=None):
    """Canonical people with a current explicit assignment to this site. Nothing else counts."""
    at = at or _now()
    query = _current(select(m.EmployeeAssignment.employee_id).where(_site_condition(restaurant_id)), at)
    return {resolve_employee_id(db, identity) for identity in db.scalars(query)}


def employee_site_ids(db, employee_id, *, at=None):
    """Sites (Restaurant ids) where the person holds a current explicit assignment."""
    at = at or _now()
    rows = db.execute(_current(select(m.EmployeeAssignment.restaurant_id, m.RestaurantLocation.restaurant_id)
        .outerjoin(m.RestaurantLocation, m.RestaurantLocation.location_id == m.EmployeeAssignment.location_id)
        .where(m.EmployeeAssignment.employee_id == employee_id), at))
    return {own if own is not None else via for own, via in rows if (own if own is not None else via) is not None}


def site_role_choices(db, restaurant_id):
    """(role, area) pairs usable at a site: active roles of this restaurant or of every restaurant."""
    rows = db.execute(select(m.RestaurantRole, m.OperationalArea)
        .join(m.OperationalAreaRole, m.OperationalAreaRole.restaurant_role_id == m.RestaurantRole.id)
        .join(m.OperationalArea, m.OperationalArea.id == m.OperationalAreaRole.operational_area_id)
        .where(m.RestaurantRole.active.is_not(False), m.OperationalArea.active.is_not(False),
               m.RestaurantRole.restaurant_id.is_(None) | (m.RestaurantRole.restaurant_id == restaurant_id))
        .order_by(m.RestaurantRole.name, m.OperationalArea.name))
    return [(role, area) for role, area in rows]


def site_role_groups(db, site_rows):
    """For one <select> with an optgroup per site: [(site, [(value 'site:role:area', 'Role · Area')])]."""
    return [(site, [(f"{site.id}:{role.id}:{area.id}", f"{role.name} · {area.name}")
                    for role, area in site_role_choices(db, site.id)]) for site in site_rows]


def parse_site_role(value):
    """'site:role:area' -> (restaurant_id, role_id, area_id); ValueError when missing or malformed."""
    try:
        restaurant_id, role_id, area_id = (int(part) for part in (value or "").split(":"))
    except ValueError:
        raise ValueError("Choose the site and the role of the person.") from None
    return restaurant_id, role_id, area_id


def assign_site(db, *, employee_id, restaurant_id, role_id, area_id, account_id=None,
                source=ASSIGNMENT_SOURCE_REGISTRY, note=None):
    """Explicit assignment of an existing card to a site. A person already assigned there keeps the
    assignment (returns it, nothing changes): changing the role at a site stays an Organization step."""
    employee_id = resolve_employee_id(db, employee_id)
    if db.get(m.Employee, employee_id) is None:
        raise ValueError("Person not found.")
    if db.get(m.Restaurant, restaurant_id) is None:
        raise ValueError("Choose a site.")
    current = db.scalar(_current(select(m.EmployeeAssignment).where(
        m.EmployeeAssignment.employee_id == employee_id, _site_condition(restaurant_id)), _now()).limit(1))
    if current is not None:
        return current
    if (role_id, area_id) not in {(role.id, area.id) for role, area in site_role_choices(db, restaurant_id)}:
        raise ValueError("Choose a role available at this site.")
    assignment = m.EmployeeAssignment(employee_id=employee_id, restaurant_id=restaurant_id, location_id=None,
        restaurant_role_id=role_id, operational_area_id=area_id, valid_from=_now(), valid_to=None,
        assignment_source=source, source_note=note)
    db.add(assignment)
    db.flush()
    _event(db, "SITE_ASSIGN", employee_id=employee_id, account_id=account_id,
           details={"restaurant_id": restaurant_id, "role_id": role_id, "area_id": area_id,
                    "assignment_id": assignment.id, "source": source})
    return assignment


def find_registered(db, *, email=None, phone=None):
    """An existing card with the same email or phone (contact evidence, never the name alone)."""
    email, phone = (email or "").strip().casefold(), (phone or "").strip()
    if not email and not phone:
        return None
    condition = []
    if email:
        condition.append(func.lower(m.Employee.email) == email)
    if phone:
        condition.append(m.Employee.phone == phone)
    from sqlalchemy import or_
    return db.scalar(canonical_employees().where(or_(*condition)).order_by(m.Employee.id).limit(1))


def create_person(db, *, display_name, email=None, phone=None, account_id=None,
                  restaurant_id=None, role_id=None, area_id=None, require_site=True):
    """Manual card: name, contacts and the explicit site (with its role). A person already registered
    (same email or phone) is not created twice: the operator adds the site to the existing card."""
    if require_site and restaurant_id is None:
        raise ValueError("Choose the site of the person.")
    existing = find_registered(db, email=email, phone=phone)
    if existing is not None:
        raise ValueError(f"{existing.display_name or 'This person'} is already registered (RF1 {existing.id}): "
                         "open the card and add the site there.")
    person = m.Employee()
    update_management(db, person, display_name=(display_name or "").strip(), custom_id="",
                      active=None, email=email, phone=phone, account_id=account_id)
    db.add(person)
    db.flush()
    _event(db, "RF1_CREATE", employee_id=person.id, account_id=account_id)
    if restaurant_id is not None:
        assign_site(db, employee_id=person.id, restaurant_id=restaurant_id, role_id=role_id, area_id=area_id,
                    account_id=account_id)
    return person


def card_for_person(db, person_id):
    """The Registry card explicitly linked to a physical person (CandidatePerson), if any."""
    from . import people_registry as people
    if not people.available(db):
        return None
    employee_id = db.scalar(select(people.PersonEmployeeLink.employee_id).where(
        people.PersonEmployeeLink.person_id == person_id).order_by(people.PersonEmployeeLink.employee_id).limit(1))
    return db.get(m.Employee, resolve_employee_id(db, employee_id)) if employee_id is not None else None


def training_card(db, *, person_id, restaurant_id, role_id, area_id, actor):
    """Training entry (direct invitation or Send to Training): create or reuse the person's card and assign
    the training site. Reuse order: the card already linked to the person; otherwise the one card with the
    same email that is not linked to another person. Repeating it changes nothing. Returns (card, created)."""
    from . import people_registry as people
    person = db.get(m.CandidatePerson, person_id)
    if person is None:
        raise ValueError("Person not found.")
    if db.get(m.Restaurant, restaurant_id) is None:
        raise ValueError("Choose the training site.")
    card, created = card_for_person(db, person_id), False
    if card is None and person.primary_email:
        matches = list(db.scalars(canonical_employees().where(
            func.lower(m.Employee.email) == person.primary_email.strip().casefold())))
        linked = set(db.scalars(select(people.PersonEmployeeLink.employee_id))) if people.available(db) else set()
        free = [employee for employee in matches if employee.id not in linked]
        if len(free) == 1 and len(matches) == 1:
            card = free[0]
    if card is None:
        card = m.Employee()
        update_management(db, card, display_name=(person.full_name or "").strip() or "Name to complete",
                          custom_id="", active=None, email=person.primary_email, phone=person.primary_phone,
                          account_id=actor.id)
        db.add(card)
        db.flush()
        _event(db, "TRAINING_CREATE", employee_id=card.id, account_id=actor.id, details={"person_id": person_id})
        created = True
    if people.available(db) and db.get(people.PersonEmployeeLink, card.id) is None:
        db.add(people.PersonEmployeeLink(employee_id=card.id, person_id=person_id, linked_by_id=actor.id,
                                         linked_at=_now()))
        db.flush()
        _event(db, "TRAINING_LINK", employee_id=card.id, account_id=actor.id, details={"person_id": person_id})
    assign_site(db, employee_id=card.id, restaurant_id=restaurant_id, role_id=role_id, area_id=area_id,
                account_id=actor.id, source=ASSIGNMENT_SOURCE_TRAINING)
    return card, created


# ------------------------------------------------------------------ POS ID (REGISTRY_MULTISITE_001 §4)

def site_clover_location(db, restaurant_id):
    """The Clover Location (with its merchant) of a site, or None when the site has no POS."""
    return db.scalar(select(m.Location)
        .join(m.RestaurantLocation, m.RestaurantLocation.location_id == m.Location.id)
        .join(m.SourceSystem, m.SourceSystem.id == m.Location.source_system_id)
        .where(m.RestaurantLocation.restaurant_id == restaurant_id, m.RestaurantLocation.valid_to.is_(None),
               m.SourceSystem.code == "CLOVER", m.Location.source_location_id.is_not(None))
        .order_by(m.Location.id).limit(1))


def pos_links(db, employee_id):
    """{restaurant_id: link} — the person's current POS ID per site (confirmed links only)."""
    result = {}
    for link in db.scalars(select(m.EmployeeCloverLink).where(
            m.EmployeeCloverLink.employee_id == employee_id).order_by(m.EmployeeCloverLink.id)):
        restaurant_id = db.scalar(select(m.RestaurantLocation.restaurant_id).where(
            m.RestaurantLocation.location_id == link.location_id).order_by(m.RestaurantLocation.id).limit(1))
        if restaurant_id is not None:
            result.setdefault(restaurant_id, link)
    return result


def resolved_identities(db, merchant_id):
    """{Clover employee id: RF-One person} at one merchant — only links confirmed on a card."""
    return {link.external_employee_id: link.employee_id for link in db.scalars(
        select(m.EmployeeCloverLink).where(m.EmployeeCloverLink.merchant_id == merchant_id,
                                         m.EmployeeCloverLink.employee_id.is_not(None)))}


def set_pos_id(db, *, employee_id, restaurant_id, pos_id, account_id=None):
    """Type or correct the POS ID of an existing card for a site the person is assigned to.

    - The same POS ID can never belong to two people at the same site (merchant).
    - A correction detaches the previous ID (state CORRECTED, kept for history): records already attributed
      to the person stay attributed; nothing consolidated is moved.
    - Only work still waiting for an identity with the new ID (attribution NULL) is attributed now.
    Returns (link, counts)."""
    employee_id = resolve_employee_id(db, employee_id)
    person = db.scalar(select(m.Employee).where(m.Employee.id == employee_id).with_for_update())
    if person is None:
        raise ValueError("Person not found.")
    pos_id = (pos_id or "").strip()
    if not pos_id or len(pos_id) > 128 or any(ch.isspace() for ch in pos_id):
        raise ValueError("Enter the POS ID without spaces (maximum 128 characters).")
    if restaurant_id not in employee_site_ids(db, employee_id):
        raise ValueError("The person is not assigned to this site: assign the site first.")
    location = site_clover_location(db, restaurant_id)
    if location is None:
        raise ValueError("This site has no POS connection: a POS ID cannot be recorded.")
    merchant_id = location.source_location_id
    # Serialize POS decisions of one merchant.
    db.scalar(select(m.Location).where(m.Location.id == location.id).with_for_update())
    target = db.scalar(select(m.EmployeeCloverLink).where(m.EmployeeCloverLink.merchant_id == merchant_id,
        m.EmployeeCloverLink.external_employee_id == pos_id).with_for_update())
    if target is not None and target.employee_id not in (None, employee_id):
        other = db.get(m.Employee, target.employee_id)
        raise ValueError(f"POS ID {pos_id} already belongs to {other.display_name if other else 'another person'} "
                         "at this site. Nothing was changed.")
    current = db.scalar(select(m.EmployeeCloverLink).where(m.EmployeeCloverLink.merchant_id == merchant_id,
        m.EmployeeCloverLink.employee_id == employee_id).order_by(m.EmployeeCloverLink.id).with_for_update().limit(1))
    if current is not None and current.external_employee_id == pos_id:
        return current, {}
    previous = None
    if current is not None:
        previous = current.external_employee_id
        current.employee_id = None
        current.state = POS_CORRECTED_STATE
        _event(db, "POS_ID_CORRECTED", employee_id=employee_id, link=current, account_id=account_id,
               details={"restaurant_id": restaurant_id, "before": previous, "after": pos_id})
        db.flush()
    if target is None:
        target = m.EmployeeCloverLink(location_id=location.id, merchant_id=merchant_id,
                                     external_employee_id=pos_id, state=POS_LINK_STATE)
        db.add(target)
    target.employee_id = employee_id
    target.state = POS_LINK_STATE
    db.flush()
    _event(db, "POS_ID_SET", employee_id=employee_id, link=target, account_id=account_id,
           details={"restaurant_id": restaurant_id, "pos_id": pos_id, "previous": previous})
    from .technical.connectors.clover.identity_holds import reattribute_link
    counts = reattribute_link(db, target)
    _event(db, "REATTRIBUTE", employee_id=employee_id, link=target, account_id=account_id,
           details={"external_employee_id": pos_id, "counts": counts})
    db.flush()
    return target, counts


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
