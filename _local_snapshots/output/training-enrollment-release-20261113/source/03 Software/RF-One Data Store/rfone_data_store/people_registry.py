"""One directory over existing person identities, with explicit source links.

CandidatePerson is the existing physical person model, not a second registry.
Employee and Account stay role/source records and login records respectively.
"""
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, inspect, select, or_, func
from sqlalchemy.orm import Mapped, mapped_column

from . import models as m

COMPANY_STATUSES = ('CANDIDATE', 'EXTERNAL', 'EMPLOYEE')


def lock_identity_evidence(db, *values):
    """Serialize overlapping Registry onboarding evidence on PostgreSQL."""
    if db.bind.dialect.name == 'postgresql':
        import hashlib
        from sqlalchemy import text
        for value in sorted({value.casefold().strip() for value in values if value}):
            key = int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], 'big', signed=True)
            db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': key})


class PersonCompanyStatus(m.Base):
    """Concurrent company relationships, independent of access and job roles."""
    __tablename__ = 'person_company_statuses'
    __table_args__ = (CheckConstraint("code IN ('CANDIDATE', 'EXTERNAL', 'EMPLOYEE')",
                                     name='ck_person_company_status_code'),)
    person_id: Mapped[int] = mapped_column(ForeignKey('candidate_persons.id'), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


def company_statuses(db, person_id):
    codes = set(db.scalars(select(PersonCompanyStatus.code).where(PersonCompanyStatus.person_id == person_id))) if inspect(db.connection()).has_table('person_company_statuses') else set()
    # Existing explicit employee links remain authoritative without a data rewrite.
    if available(db) and db.scalar(select(PersonEmployeeLink.employee_id).where(PersonEmployeeLink.person_id == person_id).limit(1)) is not None:
        codes.add('EMPLOYEE')
    return codes


def set_company_statuses(db, actor, person_id, codes):
    require_admin(actor)
    codes = set(codes)
    if not codes <= set(COMPANY_STATUSES):
        raise ValueError('Invalid company status.')
    if not db.get(m.CandidatePerson, person_id):
        raise ValueError('Person not found.')
    if not inspect(db.connection()).has_table('person_company_statuses'):
        raise ValueError('Company status migration is required.')
    existing = {row.code: row for row in db.scalars(select(PersonCompanyStatus).where(PersonCompanyStatus.person_id == person_id))}
    for code, row in existing.items():
        if code not in codes:
            db.delete(row)
    for code in codes - existing.keys():
        db.add(PersonCompanyStatus(person_id=person_id, code=code))
    db.flush()


def create_identity(db, *, full_name, email=None, phone=None, restaurant_id=None,
                    normalized_name=None, normalized_phone=None):
    """Single persistence path; callers retain their explicit resolution policy."""
    person = m.CandidatePerson(full_name=full_name, primary_email=email, primary_phone=phone,
        restaurant_id=restaurant_id, normalized_name=normalized_name,
        primary_phone_normalized=normalized_phone)
    db.add(person)
    db.flush()
    return person


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


def create_person(db, actor, full_name, email="", phone="", *, company_codes=()):
    require_admin(actor)
    full_name, email, phone = full_name.strip(), email.strip(), phone.strip()
    if not full_name or len(full_name) > 255 or len(email) > 255 or len(phone) > 64:
        raise ValueError("Enter a name within 255 characters and valid contact lengths.")
    if email and (email.count('@') != 1 or email.startswith('@') or email.endswith('@') or any(c.isspace() for c in email)):
        raise ValueError("Enter a valid email address or leave it blank.")
    lock_identity_evidence(db, full_name, email, phone)
    normalized = " ".join(full_name.casefold().split())
    # Names alone cannot distinguish homonyms; contact evidence blocks duplicates.
    match = db.scalar(select(m.CandidatePerson).where(or_(
        m.CandidatePerson.primary_phone == phone if phone else False,
        func.lower(m.CandidatePerson.primary_email) == email.lower() if email else False)))
    if match:
        raise ValueError('Possible existing person. Open the existing record and verify the identity before creating another.')
    person = create_identity(db, full_name=full_name, email=email or None, phone=phone or None,
                             normalized_name=normalized)
    if company_codes:
        set_company_statuses(db, actor, person.id, company_codes)
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
    employee_registry_ready = inspect(db.connection()).has_table('employee_registry_profiles')
    initialized = set(db.scalars(select(m.EmployeeRegistryProfile.employee_id))) if employee_registry_ready else set()
    return dict(people=people, accounts_by_person=by_person, employees_by_person=employee_by_person,
        employee_setup_required=employee_registry_ready and any(key not in initialized for key in employees),
        unlinked_accounts=[a for key, a in accounts.items() if key not in linked_accounts],
        unlinked_employees=[e for key, e in employees.items() if key not in linked_employees])
