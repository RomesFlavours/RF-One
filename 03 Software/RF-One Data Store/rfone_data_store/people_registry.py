"""One directory over existing person identities, with explicit source links.

CandidatePerson is the existing physical person model, not a second registry.
Employee and Account stay role/source records and login records respectively.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, inspect, select
from sqlalchemy.orm import Mapped, mapped_column

from . import models as m


class PersonAccountLink(m.Base):
    __tablename__ = "person_account_links"
    account_id: Mapped[int] = mapped_column(ForeignKey("rfone_accounts.id"), primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("candidate_persons.id"), nullable=False, unique=True)
    linked_by_id: Mapped[int] = mapped_column(ForeignKey("rfone_accounts.id"), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PersonEmployeeLink(m.Base):
    __tablename__ = "person_employee_links"
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("candidate_persons.id"), nullable=False, index=True)
    linked_by_id: Mapped[int] = mapped_column(ForeignKey("rfone_accounts.id"), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def available(db):
    inspector = inspect(db.connection())
    return all(inspector.has_table(name) for name in ("person_account_links", "person_employee_links"))


def require_admin(actor):
    if not actor or actor.status != "ACTIVE" or not actor.is_admin:
        raise PermissionError("Administrator access required.")


def create_person(db, actor, full_name, email="", phone=""):
    require_admin(actor)
    full_name, email, phone = full_name.strip(), email.strip(), phone.strip()
    if not full_name or len(full_name) > 255 or len(email) > 255 or len(phone) > 64:
        raise ValueError("Enter a name within 255 characters and valid contact lengths.")
    if email and ("@" not in email or any(c.isspace() for c in email)):
        raise ValueError("Enter a valid email address or leave it blank.")
    person = m.CandidatePerson(full_name=full_name, primary_email=email or None,
        primary_phone=phone or None, normalized_name=" ".join(full_name.casefold().split()))
    db.add(person); db.flush()
    return person


def link_source(db, actor, person_id, kind, source_id):
    require_admin(actor)
    if not db.get(m.CandidatePerson, person_id):
        raise ValueError("Person not found.")
    if kind == "account":
        source = db.get(m.RFOneAccount, source_id)
        existing = db.get(PersonAccountLink, source_id)
        competing = db.scalar(select(PersonAccountLink).where(PersonAccountLink.person_id == person_id))
        if competing and competing.account_id != source_id:
            raise ValueError("This person already has a linked RF-One account.")
        model, key = PersonAccountLink, "account_id"
    elif kind == "employee":
        source = db.get(m.Employee, source_id)
        existing = db.get(PersonEmployeeLink, source_id)
        model, key = PersonEmployeeLink, "employee_id"
    else:
        raise ValueError("Invalid source record.")
    if source is None:
        raise ValueError("Source record not found.")
    if existing:
        if existing.person_id != person_id:
            raise ValueError("This record is already linked to another person. No identity was changed.")
        return existing
    row = model(**{key: source_id}, person_id=person_id, linked_by_id=actor.id,
        linked_at=datetime.now(timezone.utc))
    db.add(row); db.flush()
    return row


def person_for_account(db, account_id):
    if not available(db):
        return None
    link = db.get(PersonAccountLink, account_id)
    return db.get(m.CandidatePerson, link.person_id) if link else None


def delivery_account(db, person_id):
    link = db.scalar(select(PersonAccountLink).where(PersonAccountLink.person_id == person_id))
    account = db.get(m.RFOneAccount, link.account_id) if link else None
    return account if account and account.status == "ACTIVE" else None


def directory(db):
    people = list(db.scalars(select(m.CandidatePerson).order_by(m.CandidatePerson.full_name, m.CandidatePerson.id)))
    accounts = {a.id: a for a in db.scalars(select(m.RFOneAccount))}
    employees = {e.id: e for e in db.scalars(select(m.Employee))}
    account_links = list(db.scalars(select(PersonAccountLink)))
    employee_links = list(db.scalars(select(PersonEmployeeLink)))
    by_person = {link.person_id: accounts[link.account_id] for link in account_links}
    employee_by_person = {}
    for link in employee_links:
        employee_by_person.setdefault(link.person_id, []).append(employees[link.employee_id])
    linked_accounts = {link.account_id for link in account_links}
    linked_employees = {link.employee_id for link in employee_links}
    initialized = set(db.scalars(select(m.EmployeeRegistryProfile.employee_id)))
    return dict(people=people, accounts_by_person=by_person, employees_by_person=employee_by_person,
        employee_setup_required=any(key not in initialized for key in employees),
        unlinked_accounts=[a for key, a in accounts.items() if key not in linked_accounts],
        unlinked_employees=[e for key, e in employees.items() if key not in linked_employees])
